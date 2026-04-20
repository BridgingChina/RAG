"""Re-queue completed ingest tasks whose chunks lost lvl3 / knowledge_point_id.

Context: Phase 3 of the lvl3-KP merge (schema v10, deployed 2026-04-17)
purged lvl3 rows from ``taxonomy_nodes`` but ``load_taxonomy_snapshot``
(the tagger's whitelist source) was not updated to read the new
authoritative location (``knowledge_points``). Every ingest that ran
between 2026-04-17 and the taxonomy-loader fix produced chunks with
``lvl3=NULL`` and ``knowledge_point_id=NULL`` even when a matching
KnowledgePoint existed. See ``app/core/taxonomy_loader.py`` docstring
for the full RCA.

This script selects affected tasks by their bug fingerprint (tagger
reached lvl2 but stopped there, FK also NULL) and re-queues them
through the full ingest pipeline — re-using the exact ``_cleanup_task
_data`` + ``status='queued'`` path that the ``/retry`` HTTP endpoint
already uses. The scheduler (issue #152) picks them up on its next
tick and respects the global concurrency budget, so Zhipu's rate limit
is not burst-hit.

Why not just re-run ``start_indexing`` in place: that function is not
idempotent. ``ChunkBridgeLink`` has a UNIQUE(chunk_id, bridge_id), so
re-linking on existing chunks raises IntegrityError; ``parsed_content``
is cleared on completion so ``parse_markdown`` returns an empty
frontmatter and bridge hints are lost. The full-pipeline retry side-
steps both.

Usage:
    python3 scripts/requeue_tasks_missing_lvl3.py                # dry-run
    python3 scripts/requeue_tasks_missing_lvl3.py --execute      # commit
    python3 scripts/requeue_tasks_missing_lvl3.py --since 2026-04-17 --execute
    python3 scripts/requeue_tasks_missing_lvl3.py --task <uuid> --execute
"""
import sys
from datetime import datetime, timezone

import click
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.ingest_tasks import CleanupError, _cleanup_task_data
from app.core.config import settings
from app.models import Chunk
from app.models.ingest_task import IngestTask
from app.services.audit_service import AuditService


# Phase 3 deploy date (schema v10 applied in prod). Tasks completed before
# this point were not affected by the taxonomy-snapshot bug.
DEFAULT_SINCE = datetime(2026, 4, 17, tzinfo=timezone.utc)


def find_affected_tasks(
    db: Session,
    since: datetime,
    task_id_filter: str | None,
) -> list[tuple[IngestTask, int]]:
    """Return (task, affected_chunk_count) tuples for completed tasks whose
    source has at least one chunk matching the bug fingerprint.

    Bug fingerprint:
        lvl1 IS NOT NULL AND lvl2 IS NOT NULL
        AND lvl3 IS NULL AND knowledge_point_id IS NULL

    Rationale: legitimate lvl3-NULL chunks (tagger couldn't classify at all)
    usually have NULL lvl1/lvl2 too. The four-way predicate catches only
    the "tagger reached lvl2 but whitelist was empty" path.
    """
    bug_fingerprint = (
        Chunk.lvl1.isnot(None)
        & Chunk.lvl2.isnot(None)
        & Chunk.lvl3.is_(None)
        & Chunk.knowledge_point_id.is_(None)
    )

    affected_chunks_subq = (
        db.query(
            Chunk.source_id,
            func.count(Chunk.id).label("affected_count"),
        )
        .filter(bug_fingerprint)
        .group_by(Chunk.source_id)
        .subquery()
    )

    q = (
        db.query(IngestTask, affected_chunks_subq.c.affected_count)
        .join(
            affected_chunks_subq,
            IngestTask.source_id == affected_chunks_subq.c.source_id,
        )
        .filter(IngestTask.status == "completed")
        .filter(IngestTask.updated_at >= since)
    )
    if task_id_filter:
        q = q.filter(IngestTask.id == task_id_filter)

    return [(task, count) for task, count in q.order_by(IngestTask.updated_at.asc()).all()]


def requeue_task(db: Session, task: IngestTask) -> None:
    """Apply the same cleanup + status reset that ``POST /retry`` performs.

    Leaves the caller to commit so the audit row and status flip land in
    one transaction.
    """
    _cleanup_task_data(db, task)
    task.status = "queued"
    task.error_message = None
    task.chunk_count = None
    task.parsed_content = None
    task.image_count = 0
    db.flush()

    AuditService.log(
        db,
        action=AuditService.RETRY,
        resource_type="ingest_task",
        user_id=None,
        resource_id=str(task.id),
        detail={
            "file_name": task.file_name,
            "reason": "requeue_tasks_missing_lvl3 script (Phase 3 tagger snapshot bug)",
        },
        ip_address=None,
    )


@click.command()
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Actually commit changes. Without this flag the script only prints what it would do.",
)
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    default=None,
    help="Only consider tasks with updated_at >= this date (UTC). Defaults to 2026-04-17 (Phase 3 deploy).",
)
@click.option(
    "--task",
    "task_id_filter",
    default=None,
    help="Re-queue a single task by id (still subject to the bug fingerprint).",
)
def main(execute: bool, since: datetime | None, task_id_filter: str | None) -> None:
    cutoff = since.replace(tzinfo=timezone.utc) if since else DEFAULT_SINCE

    engine = create_engine(settings.database_url)
    SessionFactory = sessionmaker(bind=engine)
    db = SessionFactory()

    try:
        affected = find_affected_tasks(db, cutoff, task_id_filter)

        if not affected:
            click.echo(f"No affected tasks found (since={cutoff.isoformat()}).")
            return

        click.echo(f"Found {len(affected)} task(s) with bug-fingerprint chunks:")
        click.echo(
            f"  {'file_name':<40}  {'task_id':<36}  affected_chunks  updated_at"
        )
        for task, count in affected:
            click.echo(
                f"  {task.file_name[:40]:<40}  {str(task.id):<36}  {count:>15}  {task.updated_at.isoformat()}"
            )

        if not execute:
            click.echo("")
            click.echo("Dry-run: no changes made. Re-run with --execute to commit.")
            return

        click.echo("")
        click.echo("--execute given; applying cleanup + re-queue per task...")

        requeued = 0
        failed: list[tuple[IngestTask, str]] = []
        for task, _count in affected:
            try:
                requeue_task(db, task)
                db.commit()
                requeued += 1
                click.echo(f"  [OK] {task.file_name} ({task.id}) -> queued")
            except CleanupError as exc:
                db.rollback()
                failed.append((task, str(exc)))
                click.echo(f"  [FAIL] {task.file_name} ({task.id}): {exc}", err=True)
            except Exception as exc:  # noqa: BLE001 — surface unexpected failures
                db.rollback()
                failed.append((task, repr(exc)))
                click.echo(f"  [FAIL] {task.file_name} ({task.id}): {exc!r}", err=True)

        click.echo("")
        click.echo(f"Re-queued: {requeued}/{len(affected)}")
        if failed:
            click.echo(f"Failed: {len(failed)}", err=True)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
