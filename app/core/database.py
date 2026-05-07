import re

from sqlalchemy import Connection, Engine, bindparam, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Latest schema version supported by this codebase.
# v13 (2026-04-21): Multi-provider + task-level model routing — adds
# llm_providers / llm_provider_models / llm_task_routes plus a Zhipu seed so
# existing LLM call sites keep working after Phase C migrates them to
# ``chat_for_task(task_key)``.
# v12 (2026-04-21): i18n Phase 3 — *_en translation columns on bridges /
# knowledge_points / flashcards / taxonomy_nodes, chunks.cached_en_summary for
# Phase 4 translate-around evidence cache, and translation_reviews审校 table.
LATEST_SCHEMA_VERSION = 14


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
            "id", "type", "title", "url", "file_path", "accessed_at", "created_at",
        },
        "bridges": {
            "id", "name", "aliases", "region", "era", "bridge_type",
            "material", "function", "summary",
            "latitude", "longitude",
            "created_at", "updated_at",
            # v12 i18n columns
            "name_en", "description_en",
        },
        "taxonomy_nodes": {"id", "lvl1", "lvl2", "lvl3", "description", "name_en"},
        "chunks": {
            "id", "source_id", "content", "section_title",
            "lvl1", "lvl2", "lvl3",
            "bridge_id", "bridge_binding_status", "page_range",
            "embedding", "contextual_text", "search_text", "tsv",
            "needs_reindex", "updated_at", "created_at",
            "knowledge_point_id",
            # v12 i18n: translate-around evidence summary cache
            "cached_en_summary", "cached_en_summary_at",
        },
        "chunk_bridge_links": {
            "id", "chunk_id", "bridge_id", "role", "confidence", "method", "created_at",
        },
        "audit_logs": {
            "id", "user_id", "action", "resource_type", "resource_id",
            "detail", "ip_address", "created_at",
        },
        "ingest_tasks": {
            "id", "status", "file_name", "file_type", "file_size",
            "r2_raw_key", "r2_parsed_prefix", "zhipu_task_id",
            "source_id", "parsed_content", "chunk_count", "image_count",
            "error_message", "created_by", "created_at", "updated_at",
        },
        "knowledge_points": {
            "id", "taxonomy_node_id", "name", "aliases", "difficulty",
            "summary", "l2_content", "created_at", "updated_at",
            "lvl1", "lvl2",
            # v12 i18n columns
            "name_en", "summary_en",
        },
        "knowledge_point_key_points": {
            "id", "knowledge_point_id", "summary", "explanation",
            "order_index", "chunk_ids", "illustration_urls",
            "related_term_ids", "created_at",
        },
        "flashcards": {
            "id", "knowledge_point_id", "card_type", "front_title", "front_hint",
            "back_answer", "back_key_features", "back_example_bridge_id",
            "created_at", "updated_at",
            # v12 i18n columns
            "front_title_en", "back_answer_en",
        },
        "translation_reviews": {
            "id", "table_name", "row_id", "field_name", "source_text",
            "ai_translation", "reviewed_translation", "status",
            "reviewed_by", "reviewed_at", "created_at",
        },
        "favorites": {
            "id", "user_id", "target_id", "target_type", "created_at",
        },
        "review_progress": {
            "user_id", "flashcard_id", "mastery",
            "last_reviewed_at", "next_review_at", "interval_days", "ease_factor",
        },
        "view_history": {
            "id", "user_id", "target_id", "target_type", "viewed_at",
        },
        # v13 LLM routing tables
        "llm_providers": {
            "id", "name", "kind", "base_url", "api_key_env", "extra_headers",
            "enabled", "timeout_read", "last_tested_at", "last_test_ok",
            "last_test_error", "created_at", "updated_at",
        },
        "llm_provider_models": {
            "id", "provider_id", "model_id", "display_name", "kind",
            "context_window", "extra", "fetched_at",
        },
        "llm_task_routes": {
            "task_key", "provider_id", "model_id", "updated_at", "updated_by",
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


def _seed_llm_routes(conn: Connection) -> None:
    """Seed the Zhipu provider + 7 default task routes (schema v13).

    Idempotent — safe to run on an already-seeded database. Mirrors the seed
    block in ``scripts/migrate_db.py::migrate_v12_to_v13`` so v0 fresh installs
    and v12→v13 migrations converge on the same initial routing config.
    """
    zhipu_row = conn.execute(text("""
        INSERT INTO llm_providers (name, kind, base_url, api_key_env)
        VALUES ('智谱 AI（默认）', 'zhipu',
                'https://open.bigmodel.cn/api/paas/v4', 'ZHIPU_API_KEY')
        ON CONFLICT (name) DO NOTHING
        RETURNING id
    """)).fetchone()
    if zhipu_row is None:
        zhipu_id = conn.execute(text(
            "SELECT id FROM llm_providers WHERE name = '智谱 AI（默认）'"
        )).scalar()
    else:
        zhipu_id = zhipu_row[0]

    seed_routes = [
        ("qa_generation",           "glm-4.7"),
        ("qa_facet_extraction",     "glm-4-flash"),
        ("ingest_tagger",           "glm-4.7"),
        ("ingest_context_enricher", "glm-4.7"),
        ("ingest_bridge_linker",    "glm-4.7"),
        ("content_generation",      "glm-4.7"),
        ("translation",             "glm-4.7"),
    ]
    for task_key, model_id in seed_routes:
        conn.execute(
            text(
                "INSERT INTO llm_task_routes (task_key, provider_id, model_id) "
                "VALUES (:task_key, :pid, :model_id) "
                "ON CONFLICT (task_key) DO NOTHING"
            ),
            {"task_key": task_key, "pid": zhipu_id, "model_id": model_id},
        )


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
                if current_version != LATEST_SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Schema version mismatch: DB has v{current_version}, "
                        f"code expects v{LATEST_SCHEMA_VERSION}. "
                        f"Run `python scripts/reset_db.py --force` to recreate."
                    )
                verify_schema_compatibility(engine, conn=conn)
                logger.info(f"Database already initialized at version {current_version}")
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

            # Seed LLM routing config (Zhipu provider + 7 task routes).
            _seed_llm_routes(conn)

            # Verify schema compatibility before stamping version
            verify_schema_compatibility(engine, conn=conn)

            # Set initial version
            set_schema_version(
                engine, LATEST_SCHEMA_VERSION,
                f"Initial schema at v{LATEST_SCHEMA_VERSION}",
                conn=conn,
            )

            logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
