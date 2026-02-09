from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_schema_version(engine: Engine) -> int | None:
    """Get current schema version from database.

    Returns None if schema_version table doesn't exist yet.
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            )
            return result.scalar_one_or_none()
    except ProgrammingError:
        # Table doesn't exist yet
        return None


def set_schema_version(engine: Engine, version: int, description: str) -> None:
    """Record a schema version in the database.

    Uses ON CONFLICT DO NOTHING to handle concurrent initialization safely.
    """
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_version (version, description) "
                "VALUES (:version, :description) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": version, "description": description},
        )
        conn.commit()


def verify_schema_compatibility(engine: Engine) -> None:
    """Verify that the actual database schema matches expected configuration.

    Raises RuntimeError if schema exists but doesn't match (e.g., wrong embedding dimension).
    """
    try:
        with engine.connect() as conn:
            # Check if chunks table exists and has correct embedding dimension
            result = conn.execute(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
                )
            )
            row = result.fetchone()
            if row is not None:
                # atttypmod for vector(N) is N+4
                actual_dim = row[0] - 4
                if actual_dim != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"Schema mismatch: chunks.embedding has {actual_dim} dimensions, "
                        f"but EMBEDDING_DIM={EMBEDDING_DIM}. "
                        f"Migration required before setting schema version."
                    )
    except ProgrammingError:
        # Table doesn't exist yet, which is fine for fresh initialization
        pass


def init_database() -> None:
    """Initialize database schema if needed.

    Checks current schema version and creates all tables if version is None.
    Sets version to 1 after successful initialization.

    Uses PostgreSQL advisory lock to serialize concurrent first-run initializations.
    """
    # Use advisory lock to prevent concurrent initialization
    # Lock ID: SHA256("bridge_rag_init")[:4] -> 606059278
    # Derived from project-specific string to avoid conflicts with other locks
    INIT_LOCK_ID = 606059278

    try:
        # Acquire advisory lock (blocks until available)
        with engine.connect() as conn:
            conn.execute(text(f"SELECT pg_advisory_lock({INIT_LOCK_ID})"))
            conn.commit()

        try:
            # Re-check version after acquiring lock (another process may have just initialized)
            current_version = get_current_schema_version(engine)

            if current_version is not None:
                logger.info(f"Database already initialized at version {current_version}")
                return

            logger.info("Initializing database schema...")

            # Create pgvector extension if it doesn't exist
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()

            # Import Base here to avoid circular imports
            from app.models import Base

            # Create all tables
            Base.metadata.create_all(engine)

            # Verify schema compatibility before stamping version
            verify_schema_compatibility(engine)

            # Set initial version
            set_schema_version(engine, 1, "Initial schema")

            logger.info("Database initialization completed successfully")

        finally:
            # Always release the advisory lock
            with engine.connect() as conn:
                conn.execute(text(f"SELECT pg_advisory_unlock({INIT_LOCK_ID})"))
                conn.commit()

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
