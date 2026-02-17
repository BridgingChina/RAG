"""DB migration / backfill helper for Bridge RAG System.

This repo does not use Alembic. `Base.metadata.create_all()` won't add new
columns or indexes to an existing database, so older DBs need a one-off DDL +
backfill run.

What this script does (idempotent):
1) Ensure required extensions (pgvector).
2) Create missing tables (best-effort) via SQLAlchemy metadata.
3) Add new columns if missing:
   - chunks.contextual_text (TEXT)
   - chunks.search_text (TEXT)
   - chunks.tsv (TSVECTOR)
   - chunks.bridge_binding_status (VARCHAR(20))
   - bridges.function (VARCHAR)  # used by facet-based candidate selection
4) Create new indexes if missing:
   - chunks.tsv GIN index
   - chunks.embedding IVFFLAT index (pgvector)
   - chunk_bridge_links indexes
5) Backfill chunks.tsv for existing rows (Tokenizer -> to_tsvector('simple', ...))
6) Stamp schema_version to latest supported version when migration succeeds

Usage:
    python scripts/migrate_db.py
    python scripts/migrate_db.py --database-url postgresql+psycopg://...
    python scripts/migrate_db.py --force --batch-size 500
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import LATEST_SCHEMA_VERSION
from app.models import Base
from app.services.tokenizer import Tokenizer, default_user_dict_path


def _q(conn, sql: str, params: dict[str, object] | None = None):
    return conn.execute(text(sql), params or {})


def _column_info(conn, *, table: str, column: str) -> dict[str, str] | None:
    row = _q(
        conn,
        """
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table
          AND column_name = :column
        """,
        {"table": table, "column": column},
    ).mappings().first()
    return dict(row) if row else None


def _add_column_if_missing(conn, *, table: str, column: str, ddl_type: str) -> bool:
    if _column_info(conn, table=table, column=column) is not None:
        return False
    _q(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}")
    return True


def _index_exists(conn, *, index_name: str) -> bool:
    # to_regclass() resolves names in the current search_path; add public. prefix.
    name = index_name if "." in index_name else f"public.{index_name}"
    return _q(conn, "SELECT to_regclass(:name)", {"name": name}).scalar_one() is not None


def _table_exists(conn, *, table_name: str) -> bool:
    name = table_name if "." in table_name else f"public.{table_name}"
    return _q(conn, "SELECT to_regclass(:name)", {"name": name}).scalar_one() is not None


def _latest_schema_version(conn) -> int | None:
    if not _table_exists(conn, table_name="schema_version"):
        return None
    return _q(
        conn,
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1",
    ).scalar_one_or_none()


def _stamp_schema_version(conn, *, version: int, description: str) -> bool:
    if not _table_exists(conn, table_name="schema_version"):
        return False

    current = _latest_schema_version(conn)
    if current is not None and current >= version:
        return False

    _q(
        conn,
        """
        INSERT INTO schema_version (version, description)
        VALUES (:version, :description)
        ON CONFLICT (version) DO NOTHING
        """,
        {"version": version, "description": description},
    )
    conn.commit()
    return True


def _create_index_best_effort(conn, *, name: str, ddl_sql: str) -> bool:
    if _index_exists(conn, index_name=name):
        return False
    _q(conn, ddl_sql)
    return True


def _format_seconds(s: float) -> str:
    if s < 1:
        return f"{s * 1000:.0f}ms"
    return f"{s:.2f}s"


@click.command()
@click.option(
    "--database-url",
    envvar="DATABASE_URL",
    default=None,
    help="Override database URL (defaults to settings.database_url).",
)
@click.option(
    "--user-dict-path",
    default=default_user_dict_path(),
    show_default=True,
    help="jieba user dict used for Tokenizer backfill.",
)
@click.option("--batch-size", default=1000, show_default=True, type=int)
@click.option(
    "--force",
    is_flag=True,
    help="Recompute tsv for all chunks (default: only rows where tsv IS NULL).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without applying DDL/backfill.",
)
def main(
    database_url: str | None,
    user_dict_path: str,
    batch_size: int,
    force: bool,
    dry_run: bool,
) -> None:
    db_url = database_url or settings.database_url
    target_schema_version = LATEST_SCHEMA_VERSION
    target_schema_description = "Schema v3 with users and audit_logs"
    click.echo(f"DB migrate/backfill starting...")
    click.echo(f"- database_url: {db_url}")
    click.echo(f"- dry_run: {dry_run}")
    click.echo(f"- force: {force}")
    click.echo(f"- batch_size: {batch_size}")
    click.echo(f"- target_schema_version: {target_schema_version}")

    # Tokenizer: best-effort user dict.
    tokenizer: Tokenizer
    dict_path = Path(user_dict_path)
    if dict_path.exists():
        tokenizer = Tokenizer(user_dict_path=str(dict_path))
        click.echo(f"- tokenizer.user_dict: {dict_path}")
    else:
        tokenizer = Tokenizer()
        click.echo(f"- tokenizer.user_dict: (missing) {dict_path} (continuing without it)")

    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # Extensions / base schema.
            click.echo("\n[1/4] Ensuring extensions & base tables...")
            if dry_run:
                click.echo("  (dry-run) would run: CREATE EXTENSION IF NOT EXISTS vector")
            else:
                _q(conn, "CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()

            # Always call create_all to ensure newly added tables are created as well.
            if dry_run:
                click.echo("  (dry-run) would run: Base.metadata.create_all(...)")
            else:
                Base.metadata.create_all(engine)
                click.echo("  OK: Base metadata ensured")

            # Columns.
            click.echo("\n[2/4] Adding missing columns (idempotent)...")
            added_cols: list[str] = []
            col_specs = [
                ("chunks", "contextual_text", "TEXT"),
                ("chunks", "search_text", "TEXT"),
                ("chunks", "tsv", "TSVECTOR"),
                ("chunks", "bridge_binding_status", "VARCHAR(20) DEFAULT 'none'"),
                ("bridges", "function", "VARCHAR(100)"),
            ]
            for table, column, ddl_type in col_specs:
                exists = _column_info(conn, table=table, column=column) is not None
                if exists:
                    click.echo(f"  OK: {table}.{column} exists")
                    continue
                if dry_run:
                    click.echo(f"  (dry-run) would add: {table}.{column} {ddl_type}")
                    continue
                try:
                    if _add_column_if_missing(conn, table=table, column=column, ddl_type=ddl_type):
                        conn.commit()
                        added_cols.append(f"{table}.{column}")
                        click.echo(f"  ADDED: {table}.{column} ({ddl_type})")
                    else:
                        click.echo(f"  OK: {table}.{column} exists")
                except SQLAlchemyError as e:
                    click.echo(f"  ERROR: failed to add {table}.{column}: {e}", err=True)
                    raise

            # Sanity check: tsv column type (if present).
            tsv_info = _column_info(conn, table="chunks", column="tsv")
            if tsv_info and tsv_info.get("udt_name") not in {"tsvector"}:
                raise RuntimeError(
                    "chunks.tsv exists but is not TSVECTOR "
                    f"(information_schema.udt_name={tsv_info.get('udt_name')})."
                )

            # Backfill bridge_binding_status based on existing bridge_id.
            if not dry_run and _column_info(conn, table="chunks", column="bridge_binding_status"):
                _q(
                    conn,
                    """
                    UPDATE chunks
                    SET bridge_binding_status = CASE
                        WHEN bridge_id IS NULL THEN 'none'
                        ELSE 'primary'
                    END
                    WHERE bridge_binding_status IS NULL
                       OR bridge_binding_status NOT IN ('none', 'primary', 'ambiguous')
                    """,
                )
                conn.commit()

            # Indexes.
            click.echo("\n[3/4] Creating missing indexes (best-effort)...")
            index_ddls: list[tuple[str, str]] = [
                (
                    "ix_chunks_tsv",
                    "CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON chunks USING gin (tsv)",
                ),
                (
                    "ix_chunks_embedding_ivfflat",
                    "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_ivfflat "
                    "ON chunks USING ivfflat (embedding vector_cosine_ops)",
                ),
                (
                    "ix_chunks_binding_status",
                    "CREATE INDEX IF NOT EXISTS ix_chunks_binding_status "
                    "ON chunks (bridge_binding_status)",
                ),
                (
                    "ix_chunk_bridge_links_chunk_id",
                    "CREATE INDEX IF NOT EXISTS ix_chunk_bridge_links_chunk_id "
                    "ON chunk_bridge_links (chunk_id)",
                ),
                (
                    "ix_chunk_bridge_links_bridge_id",
                    "CREATE INDEX IF NOT EXISTS ix_chunk_bridge_links_bridge_id "
                    "ON chunk_bridge_links (bridge_id)",
                ),
                (
                    "ix_chunk_bridge_links_role_confidence",
                    "CREATE INDEX IF NOT EXISTS ix_chunk_bridge_links_role_confidence "
                    "ON chunk_bridge_links (role, confidence)",
                ),
            ]
            for idx_name, ddl_sql in index_ddls:
                if _index_exists(conn, index_name=idx_name):
                    click.echo(f"  OK: {idx_name} exists")
                    continue
                if dry_run:
                    click.echo(f"  (dry-run) would create: {idx_name}")
                    continue
                try:
                    created = _create_index_best_effort(conn, name=idx_name, ddl_sql=ddl_sql)
                    conn.commit()
                    if created:
                        click.echo(f"  CREATED: {idx_name}")
                    else:
                        click.echo(f"  OK: {idx_name} exists")
                except SQLAlchemyError as e:
                    # HNSW depends on pgvector version; treat as non-fatal.
                    click.echo(
                        f"  WARN: failed to create index {idx_name} (continuing): {e}"
                    )
                    conn.rollback()

            # Backfill.
            click.echo("\n[4/4] Backfilling chunks.tsv ...")
            if tsv_info is None:
                click.echo("  SKIP: chunks.tsv does not exist (unexpected)")
                if dry_run:
                    click.echo(
                        "  (dry-run) would stamp schema_version "
                        f"to {target_schema_version}"
                    )
                else:
                    stamped = _stamp_schema_version(
                        conn,
                        version=target_schema_version,
                        description=target_schema_description,
                    )
                    if stamped:
                        click.echo(f"  STAMPED: schema_version={target_schema_version}")
                    else:
                        click.echo("  OK: schema_version already up-to-date")
                return

            if dry_run:
                click.echo("  (dry-run) would backfill tsv using Tokenizer + to_tsvector('simple', ...)")
                click.echo(
                    "  (dry-run) would stamp schema_version "
                    f"to {target_schema_version}"
                )
                return

            total = _q(conn, "SELECT COUNT(*) FROM chunks").scalar_one()
            if force:
                remaining = total
            else:
                remaining = _q(conn, "SELECT COUNT(*) FROM chunks WHERE tsv IS NULL").scalar_one()

            click.echo(f"  chunks total: {total}")
            click.echo(f"  rows to update: {remaining}")
            if remaining == 0:
                click.echo("  OK: nothing to backfill")
                stamped = _stamp_schema_version(
                    conn,
                    version=target_schema_version,
                    description=target_schema_description,
                )
                if stamped:
                    click.echo(f"  STAMPED: schema_version={target_schema_version}")
                else:
                    click.echo("  OK: schema_version already up-to-date")
                return

            update_stmt = text(
                "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
            )

            updated = 0
            last_id = 0
            started = time.time()
            while True:
                rows = _q(
                    conn,
                    """
                    SELECT id, COALESCE(search_text, content) AS src_text
                    FROM chunks
                    WHERE id > :last_id
                      AND (:force OR tsv IS NULL)
                    ORDER BY id
                    LIMIT :limit
                    """,
                    {"last_id": last_id, "limit": batch_size, "force": force},
                ).all()
                if not rows:
                    break

                last_id = rows[-1][0]
                mappings = []
                for chunk_id, src_text in rows:
                    src_text = src_text or ""
                    tsv_text = tokenizer.to_tsvector_text(src_text)
                    mappings.append({"id": chunk_id, "tsv_text": tsv_text})

                conn.execute(update_stmt, mappings)
                conn.commit()

                updated += len(rows)
                elapsed = time.time() - started
                rate = updated / elapsed if elapsed > 0 else 0.0
                click.echo(
                    f"  progress: {updated}/{remaining} "
                    f"({_format_seconds(elapsed)}, {rate:.0f} rows/s)"
                )

            click.echo(f"  DONE: updated {updated} rows in {_format_seconds(time.time() - started)}")
            stamped = _stamp_schema_version(
                conn,
                version=target_schema_version,
                description=target_schema_description,
            )
            if stamped:
                click.echo(f"  STAMPED: schema_version={target_schema_version}")
            else:
                click.echo("  OK: schema_version already up-to-date")

    except Exception as e:
        click.echo(f"\nFAILED: {e}", err=True)
        sys.exit(1)

    click.echo("\nSUCCESS: migration/backfill complete.")


if __name__ == "__main__":
    main()
