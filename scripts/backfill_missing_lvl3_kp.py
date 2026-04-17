"""Backfill missing KnowledgePoint rows for lvl3 taxonomy nodes.

The codebase enforces a 1:1 convention: every lvl3 ``taxonomy_nodes`` row must
have a matching ``knowledge_points`` row with the same ``name`` and with
``knowledge_points.taxonomy_node_id`` pointing at it. Production has one orphan
(``形制与技术 / 结构体系 / 浮桥结构``) that was missed by the seed run. This
one-shot script detects orphans and inserts same-name placeholder KPs so that
downstream Phase-1 tasks can rely on the invariant.

Usage:
    python3 scripts/backfill_missing_lvl3_kp.py              # dry-run (preview)
    python3 scripts/backfill_missing_lvl3_kp.py --execute    # commit inserts
"""
import sys

import click
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import KnowledgePoint, TaxonomyNode


def find_orphans(db: Session) -> list[TaxonomyNode]:
    """Return lvl3 taxonomy nodes that have no matching KnowledgePoint."""
    return (
        db.query(TaxonomyNode)
        .outerjoin(KnowledgePoint, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id)
        .filter(TaxonomyNode.lvl3.isnot(None))
        .filter(KnowledgePoint.id.is_(None))
        .order_by(TaxonomyNode.lvl1, TaxonomyNode.lvl2, TaxonomyNode.lvl3)
        .all()
    )


@click.command()
@click.option("--execute", is_flag=True, help="Actually write to DB (default is dry-run)")
def main(execute: bool) -> None:
    """Backfill placeholder KnowledgePoints for lvl3 taxonomy nodes missing one."""
    mode = "EXECUTE" if execute else "DRY-RUN"
    click.echo(f"\n{'='*60}")
    click.echo(f"  Backfill Missing lvl3 KnowledgePoints [{mode}]")
    click.echo(f"  Database: {settings.database_url[:50]}...")
    click.echo(f"{'='*60}\n")

    if not execute:
        click.echo("DRY-RUN mode — no data will be written. Use --execute to commit.\n")

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        orphans = find_orphans(db)

        if not orphans:
            click.echo("0 orphans — nothing to do.\n")
            return

        click.echo(f"Found {len(orphans)} orphan lvl3 node(s):\n")
        for node in orphans:
            click.echo(f"  - {node.lvl1} / {node.lvl2} / {node.lvl3}  (id={node.id})")
        click.echo("")

        if not execute:
            click.echo("Re-run with --execute to insert placeholder KnowledgePoints.\n")
            return

        inserted = 0
        for node in orphans:
            kp = KnowledgePoint(
                taxonomy_node_id=node.id,
                name=node.lvl3,
                summary=f"（占位）{node.lvl3}相关的桥梁知识点。",
            )
            db.add(kp)
            inserted += 1
            click.echo(f"  + inserted KP for: {node.lvl1} / {node.lvl2} / {node.lvl3}")

        db.commit()
        click.echo(f"\nInserted {inserted} placeholder KnowledgePoint(s). Committed.\n")

    except Exception as e:
        db.rollback()
        click.echo(f"FATAL: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
