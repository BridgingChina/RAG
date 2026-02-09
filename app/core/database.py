from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
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
    """Record a schema version in the database."""
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO schema_version (version, description) VALUES (:version, :description)"),
            {"version": version, "description": description},
        )
        conn.commit()


def init_database() -> None:
    """Initialize database schema if needed.

    Checks current schema version and creates all tables if version is None.
    Sets version to 1 after successful initialization.
    """
    try:
        current_version = get_current_schema_version(engine)

        if current_version is not None:
            logger.info(f"Database already initialized at version {current_version}")
            return

        logger.info("Initializing database schema...")

        # Import Base here to avoid circular imports
        from app.models import Base

        # Create all tables
        Base.metadata.create_all(engine)

        # Set initial version
        set_schema_version(engine, 1, "Initial schema")

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
