"""Integration tests for database initialization with real database."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.core.database import init_database
from app.models import Base, Chunk, Source


@pytest.fixture(scope="module")
def test_engine():
    """Create a test engine for integration tests.

    This fixture creates tables from scratch for testing database initialization.
    """
    engine = create_engine(settings.database_url)

    # Check if database is available
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(
            "PostgreSQL+pgvector test DB not available. "
            "Start it with `docker compose up -d db` and retry."
        )

    # Drop all tables to start fresh
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS chunks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS sources CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS bridges CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS taxonomy_nodes CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS schema_version CASCADE"))
        conn.commit()

    yield engine

    # Cleanup: Drop all tables after tests
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS chunks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS sources CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS bridges CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS taxonomy_nodes CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS schema_version CASCADE"))
        conn.commit()

    engine.dispose()


@pytest.mark.integration
def test_init_database_creates_schema_version_table(test_engine):
    """Test that init_database creates the schema_version table."""
    inspector = inspect(test_engine)

    # Verify table doesn't exist before initialization
    assert not inspector.has_table("schema_version")

    # Initialize database
    # We need to use the global engine from database.py, so temporarily replace it
    from app.core import database
    original_engine = database.engine
    database.engine = test_engine

    try:
        init_database()

        # Verify schema_version table was created
        inspector = inspect(test_engine)
        assert inspector.has_table("schema_version")

        # Verify table has expected columns
        columns = inspector.get_columns("schema_version")
        column_names = {col["name"] for col in columns}
        assert "version" in column_names
        assert "description" in column_names
        assert "created_at" in column_names
    finally:
        database.engine = original_engine


@pytest.mark.integration
def test_init_database_creates_all_tables(test_engine):
    """Test that init_database creates all required tables."""
    from app.core import database
    original_engine = database.engine
    database.engine = test_engine

    try:
        init_database()

        inspector = inspect(test_engine)

        # Verify all tables exist
        assert inspector.has_table("schema_version")
        assert inspector.has_table("chunks")
        assert inspector.has_table("bridges")
        assert inspector.has_table("sources")
        assert inspector.has_table("taxonomy_nodes")
    finally:
        database.engine = original_engine


@pytest.mark.integration
def test_init_database_sets_version_to_1(test_engine):
    """Test that init_database sets version to 1 with correct description."""
    from app.core import database
    original_engine = database.engine
    database.engine = test_engine

    try:
        init_database()

        # Query schema_version table
        with test_engine.connect() as conn:
            result = conn.execute(
                text("SELECT version, description FROM schema_version ORDER BY version DESC LIMIT 1")
            )
            row = result.fetchone()

            assert row is not None
            assert row[0] == 1  # version
            assert row[1] == "Initial schema"  # description
    finally:
        database.engine = original_engine


@pytest.mark.integration
def test_init_database_idempotent(test_engine):
    """Test that calling init_database twice doesn't cause errors."""
    from app.core import database
    original_engine = database.engine
    database.engine = test_engine

    try:
        # First initialization
        init_database()

        # Verify version is 1
        with test_engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            )
            version1 = result.scalar_one()
            assert version1 == 1

        # Second initialization (should be idempotent)
        init_database()

        # Verify version is still 1 (not incremented)
        with test_engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            )
            version2 = result.scalar_one()
            assert version2 == 1

            # Verify only one version record exists
            result = conn.execute(text("SELECT COUNT(*) FROM schema_version"))
            count = result.scalar_one()
            assert count == 1
    finally:
        database.engine = original_engine


@pytest.mark.integration
def test_chunk_embedding_dimension_matches_constant(test_engine):
    """Test that chunks can store EMBEDDING_DIM-dimensional embeddings."""
    from sqlalchemy.orm import Session
    from app.core import database

    original_engine = database.engine
    database.engine = test_engine

    try:
        # Initialize database
        init_database()

        # Enable pgvector extension
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

        # Create test data using ORM
        session = Session(bind=test_engine)
        try:
            # Create a test source
            source = Source(type="test", title="Test Source")
            session.add(source)
            session.flush()

            # Create an EMBEDDING_DIM-dimensional embedding
            embedding = [0.1] * EMBEDDING_DIM
            assert len(embedding) == EMBEDDING_DIM

            # Insert chunk with EMBEDDING_DIM-dim embedding
            chunk = Chunk(
                source_id=source.id,
                content="Test chunk content",
                embedding=embedding
            )
            session.add(chunk)
            session.commit()

            # Verify embedding was stored correctly
            stored_chunk = session.query(Chunk).first()
            assert stored_chunk is not None
            assert len(stored_chunk.embedding) == EMBEDDING_DIM

        finally:
            session.close()
    finally:
        database.engine = original_engine


@pytest.mark.integration
def test_ivfflat_index_exists(test_engine):
    """Test that the IVFFLAT index on chunks.embedding was created."""
    from app.core import database
    original_engine = database.engine
    database.engine = test_engine

    try:
        # Initialize database
        init_database()

        # Enable pgvector extension (required for IVFFLAT)
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

        # Recreate tables with indexes (since extension was just created)
        Base.metadata.drop_all(test_engine)
        Base.metadata.create_all(test_engine)

        # Query pg_indexes to check for IVFFLAT index
        with test_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'chunks' AND indexname = 'ix_chunks_embedding_ivfflat'"
                )
            )
            index_row = result.fetchone()

            assert index_row is not None, "IVFFLAT index not found"
            assert "ivfflat" in index_row[1].lower(), "Index is not using IVFFLAT method"
            assert "vector_cosine_ops" in index_row[1].lower(), "Index is not using cosine distance"
    finally:
        database.engine = original_engine
