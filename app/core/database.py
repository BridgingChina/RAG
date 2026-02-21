import re

from sqlalchemy import Connection, Engine, bindparam, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Latest schema version supported by this codebase.
LATEST_SCHEMA_VERSION = 6


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _schema_version_table_exists(conn: Connection) -> bool:
    result = conn.execute(text("SELECT to_regclass('public.schema_version')"))
    return result.scalar_one() is not None


def get_current_schema_version(engine: Engine, *, conn: Connection | None = None) -> int | None:
    """Get current schema version from database.

    Returns None if schema_version table doesn't exist yet.
    """
    if conn is None:
        with engine.connect() as new_conn:
            return get_current_schema_version(engine, conn=new_conn)

    if not _schema_version_table_exists(conn):
        return None

    result = conn.execute(
        text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    )
    return result.scalar_one_or_none()


def set_schema_version(
    engine: Engine,
    version: int,
    description: str,
    *,
    conn: Connection | None = None,
) -> None:
    """Record a schema version in the database.

    Uses ON CONFLICT DO NOTHING to handle concurrent initialization safely.
    """
    if conn is None:
        with engine.connect() as new_conn:
            new_conn.execute(
                text(
                    "INSERT INTO schema_version (version, description) "
                    "VALUES (:version, :description) "
                    "ON CONFLICT (version) DO NOTHING"
                ),
                {"version": version, "description": description},
            )
            new_conn.commit()
        return

    conn.execute(
        text(
            "INSERT INTO schema_version (version, description) "
            "VALUES (:version, :description) "
            "ON CONFLICT (version) DO NOTHING"
        ),
        {"version": version, "description": description},
    )


def verify_schema_compatibility(engine: Engine, *, conn: Connection | None = None) -> None:
    """Verify that the actual database schema matches expected configuration.

    Raises RuntimeError if schema exists but doesn't match (e.g., wrong embedding dimension).
    """
    if conn is None:
        with engine.connect() as new_conn:
            verify_schema_compatibility(engine, conn=new_conn)
        return

    required_schema: dict[str, set[str]] = {
        "schema_version": {"version", "description", "created_at"},
        "sources": {
            "id",
            "type",
            "title",
            "url",
            "file_path",
            "accessed_at",
            "created_at",
        },
        "bridges": {
            "id",
            "name",
            "aliases",
            "location",
            "era",
            "bridge_type",
            "material",
            "function",
            "summary",
            "created_at",
        },
        "taxonomy_nodes": {"id", "lvl1", "lvl2", "lvl3", "description"},
        "chunks": {
            "id",
            "source_id",
            "content",
            "section_title",
            "lvl1",
            "lvl2",
            "lvl3",
            "bridge_id",
            "bridge_binding_status",
            "page_range",
            "embedding",
            "contextual_text",
            "search_text",
            "tsv",
            "needs_reindex",
            "updated_at",
            "created_at",
        },
        "chunk_bridge_links": {
            "id",
            "chunk_id",
            "bridge_id",
            "role",
            "confidence",
            "method",
            "created_at",
        },
        "ingest_tasks": {
            "id",
            "status",
            "file_name",
            "file_type",
            "file_size",
            "r2_raw_key",
            "r2_parsed_prefix",
            "zhipu_task_id",
            "source_id",
            "parsed_content",
            "chunk_count",
            "image_count",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        },
    }

    required_tables = sorted(required_schema.keys())

    tables_stmt = (
        text(
            "SELECT table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN :names"
        )
        .bindparams(bindparam("names", expanding=True))
    )
    existing_tables = set(
        conn.execute(tables_stmt, {"names": required_tables}).scalars().all()
    )

    # Fresh database: no tables yet, so there's nothing to validate.
    if not existing_tables:
        return

    missing_tables = set(required_tables) - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Schema mismatch: missing required tables: "
            + ", ".join(sorted(missing_tables))
            + ". Migration required."
        )

    columns_stmt = (
        text(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name IN :names"
        )
        .bindparams(bindparam("names", expanding=True))
    )
    rows = conn.execute(columns_stmt, {"names": required_tables}).all()
    columns_by_table: dict[str, set[str]] = {t: set() for t in required_tables}
    for table_name, column_name in rows:
        columns_by_table[table_name].add(column_name)

    missing_columns: dict[str, set[str]] = {}
    for table_name, required_columns in required_schema.items():
        actual_columns = columns_by_table.get(table_name, set())
        missing = required_columns - actual_columns
        if missing:
            missing_columns[table_name] = missing

    if missing_columns:
        parts: list[str] = []
        for table_name in sorted(missing_columns.keys()):
            parts.append(f"{table_name}({', '.join(sorted(missing_columns[table_name]))})")
        raise RuntimeError(
            "Schema mismatch: missing required columns: "
            + "; ".join(parts)
            + ". Migration required."
        )

    # Check if chunks.embedding has correct vector dimension
    result = conn.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) "
            "FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
    )
    row = result.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(
            "Schema mismatch: chunks.embedding column type could not be inspected. "
            "Migration required."
        )

    type_expr = str(row[0])
    match = re.search(r"vector\((\d+)\)", type_expr)
    if match is None:
        raise RuntimeError(
            f"Schema mismatch: chunks.embedding type is '{type_expr}', expected vector({EMBEDDING_DIM}). "
            "Migration required."
        )

    actual_dim = int(match.group(1))
    if actual_dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"Schema mismatch: chunks.embedding has {actual_dim} dimensions, "
            f"but EMBEDDING_DIM={EMBEDDING_DIM}. Migration required."
        )


def _migrate_schema(engine: Engine, current_version: int, *, conn: Connection) -> None:
    """Run incremental schema migrations."""
    if current_version < 3:
        logger.info("Migrating schema v2 → v3: adding users and audit_logs tables...")
        from app.models.user import User
        from app.models.audit_log import AuditLog

        User.__table__.create(conn, checkfirst=True)
        AuditLog.__table__.create(conn, checkfirst=True)
        set_schema_version(engine, 3, "Add users and audit_logs tables", conn=conn)
        logger.info("Migration to v3 complete.")

    if current_version < 4:
        logger.info("Migrating schema v3 → v4: adding chunks.needs_reindex column...")
        conn.execute(
            text(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
                "needs_reindex BOOLEAN NOT NULL DEFAULT false"
            )
        )
        set_schema_version(engine, 4, "Add chunk needs_reindex flag", conn=conn)
        logger.info("Migration to v4 complete.")

    if current_version < 5:
        logger.info("Migrating schema v4 → v5: adding chunks.updated_at column...")
        conn.execute(
            text(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            )
        )
        # Backfill: set updated_at = created_at for existing rows
        conn.execute(text("UPDATE chunks SET updated_at = created_at"))
        set_schema_version(engine, 5, "Add chunk updated_at for optimistic locking", conn=conn)
        logger.info("Migration to v5 complete.")

    if current_version < 6:
        logger.info("Migrating schema v5 → v6: adding ingest_tasks table...")
        from app.models.ingest_task import IngestTask

        IngestTask.__table__.create(conn, checkfirst=True)
        set_schema_version(engine, 6, "Add ingest_tasks table", conn=conn)
        logger.info("Migration to v6 complete.")


def _seed_taxonomy_if_empty(conn: Connection) -> None:
    """Seed taxonomy_nodes from config/taxonomy.yaml if table is empty."""
    result = conn.execute(text("SELECT COUNT(*) FROM taxonomy_nodes"))
    if result.scalar_one() > 0:
        return

    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()

    for lvl1, lvl2_dict in taxonomy.items():
        conn.execute(
            text("INSERT INTO taxonomy_nodes (lvl1) VALUES (:lvl1)"),
            {"lvl1": lvl1},
        )
        for lvl2, lvl3_list in lvl2_dict.items():
            conn.execute(
                text(
                    "INSERT INTO taxonomy_nodes (lvl1, lvl2) VALUES (:lvl1, :lvl2)"
                ),
                {"lvl1": lvl1, "lvl2": lvl2},
            )
            for lvl3 in lvl3_list:
                conn.execute(
                    text(
                        "INSERT INTO taxonomy_nodes (lvl1, lvl2, lvl3) VALUES (:lvl1, :lvl2, :lvl3)"
                    ),
                    {"lvl1": lvl1, "lvl2": lvl2, "lvl3": lvl3},
                )


def init_database() -> None:
    """Initialize database schema if needed.

    Checks current schema version and creates all tables if version is None.
    Sets version to LATEST_SCHEMA_VERSION after successful initialization.

    Uses PostgreSQL advisory lock to serialize concurrent first-run initializations.
    The lock is held on a single connection throughout the entire init sequence.
    """
    # Use advisory lock to prevent concurrent initialization
    # Lock ID: SHA256("bridge_rag_init")[:4] -> 606059278
    # Derived from project-specific string to avoid conflicts with other locks
    INIT_LOCK_ID = 606059278

    try:
        # Single-transaction initialization with a transaction-scoped advisory lock.
        # Any failure will automatically roll back and release the lock.
        with engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": INIT_LOCK_ID},
            )

            # Re-check version after acquiring lock (another process may have just initialized)
            current_version = get_current_schema_version(engine, conn=conn)
            if current_version is not None:
                if current_version < LATEST_SCHEMA_VERSION:
                    _migrate_schema(engine, current_version, conn=conn)
                elif current_version > LATEST_SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Unsupported database schema version {current_version}. "
                        f"Expected {LATEST_SCHEMA_VERSION}. Migration required."
                    )
                verify_schema_compatibility(engine, conn=conn)
                logger.info(f"Database already initialized at version {get_current_schema_version(engine, conn=conn)}")
                return

            logger.info("Initializing database schema...")

            # Create pgvector extension if it doesn't exist
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Import Base here to avoid circular imports
            from app.models import Base

            # Create all tables using the same connection/transaction
            Base.metadata.create_all(conn)

            # Seed taxonomy_nodes from YAML if empty
            _seed_taxonomy_if_empty(conn)

            # Verify schema compatibility before stamping version
            verify_schema_compatibility(engine, conn=conn)

            # Set initial version
            set_schema_version(
                engine, LATEST_SCHEMA_VERSION, "Schema v6 with ingest_tasks table", conn=conn
            )

            logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
