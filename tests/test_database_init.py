"""Tests for database initialization functions."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from sqlalchemy import Engine

from app.core.database import (
    get_current_schema_version,
    set_schema_version,
    init_database,
    verify_schema_compatibility,
    LATEST_SCHEMA_VERSION,
)


class TestGetCurrentSchemaVersion:
    """Tests for get_current_schema_version()."""

    def test_get_current_schema_version_none(self):
        """Should return None when schema_version table doesn't exist."""
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()
        mock_exists_result = MagicMock()
        mock_exists_result.scalar_one.return_value = None

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_connection.execute.return_value = mock_exists_result

        result = get_current_schema_version(mock_engine)
        assert result is None

    def test_get_current_schema_version_returns_version(self):
        """Should return version number when table exists with data."""
        # Mock engine with existing schema_version
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()
        mock_exists_result = MagicMock()
        mock_exists_result.scalar_one.return_value = "schema_version"
        mock_version_result = MagicMock()
        mock_version_result.scalar_one_or_none.return_value = 1

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_connection.execute.side_effect = [mock_exists_result, mock_version_result]

        result = get_current_schema_version(mock_engine)
        assert result == 1


class TestSetSchemaVersion:
    """Tests for set_schema_version()."""

    def test_set_schema_version_creates_record(self):
        """Should create schema_version record."""
        # Mock engine
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        # Call function
        set_schema_version(mock_engine, 1, "Initial schema")

        # Verify execute was called (insert statement)
        assert mock_connection.execute.called
        assert mock_connection.commit.called


class TestVerifySchemaCompatibility:
    """Tests for verify_schema_compatibility()."""

    def test_verify_schema_compatibility_no_table(self):
        """Should pass when no tables exist yet (fresh DB)."""
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        mock_tables_result = MagicMock()
        mock_tables_result.scalars.return_value.all.return_value = []
        mock_connection.execute.return_value = mock_tables_result

        # Should not raise
        verify_schema_compatibility(mock_engine)

    def test_verify_schema_compatibility_correct_dimension(self):
        """Should pass when required tables/columns exist and embedding dimension matches."""
        from app.core.constants import EMBEDDING_DIM

        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()
        mock_tables_result = MagicMock()
        mock_columns_result = MagicMock()
        mock_dim_result = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        required_tables = [
            "schema_version",
            "sources",
            "bridges",
            "taxonomy_nodes",
            "chunks",
            "chunk_bridge_links",
        ]
        mock_tables_result.scalars.return_value.all.return_value = required_tables

        required_columns = {
            "schema_version": {"version", "description", "created_at"},
            "sources": {"id", "type", "title", "url", "file_path", "accessed_at", "created_at"},
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
        }

        mock_columns_result.all.return_value = [
            (table, column)
            for table, columns in required_columns.items()
            for column in columns
        ]

        mock_dim_result.fetchone.return_value = (f"vector({EMBEDDING_DIM})",)

        mock_connection.execute.side_effect = [
            mock_tables_result,
            mock_columns_result,
            mock_dim_result,
        ]

        # Should not raise
        verify_schema_compatibility(mock_engine)

    def test_verify_schema_compatibility_wrong_dimension(self):
        """Should raise RuntimeError when dimension doesn't match."""
        from app.core.constants import EMBEDDING_DIM

        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()
        mock_tables_result = MagicMock()
        mock_columns_result = MagicMock()
        mock_dim_result = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        required_tables = [
            "schema_version",
            "sources",
            "bridges",
            "taxonomy_nodes",
            "chunks",
            "chunk_bridge_links",
        ]
        mock_tables_result.scalars.return_value.all.return_value = required_tables

        required_columns = {
            "schema_version": {"version", "description", "created_at"},
            "sources": {"id", "type", "title", "url", "file_path", "accessed_at", "created_at"},
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
        }
        mock_columns_result.all.return_value = [
            (table, column)
            for table, columns in required_columns.items()
            for column in columns
        ]

        wrong_dim = EMBEDDING_DIM + 1
        mock_dim_result.fetchone.return_value = (f"vector({wrong_dim})",)

        mock_connection.execute.side_effect = [
            mock_tables_result,
            mock_columns_result,
            mock_dim_result,
        ]

        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            verify_schema_compatibility(mock_engine)

        assert "Schema mismatch" in str(exc_info.value)
        assert str(wrong_dim) in str(exc_info.value)
        assert str(EMBEDDING_DIM) in str(exc_info.value)

    def test_verify_schema_compatibility_missing_tables(self):
        """Should raise when some required tables exist but not all."""
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        mock_tables_result = MagicMock()
        mock_tables_result.scalars.return_value.all.return_value = ["schema_version"]
        mock_connection.execute.return_value = mock_tables_result

        with pytest.raises(RuntimeError) as exc_info:
            verify_schema_compatibility(mock_engine)

        assert "missing required tables" in str(exc_info.value).lower()


class TestInitDatabase:
    """Tests for init_database()."""

    @patch("app.models.Base")
    @patch("app.core.database._seed_taxonomy_if_empty")
    @patch("app.core.database.verify_schema_compatibility")
    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.set_schema_version")
    @patch("app.core.database.engine")
    def test_init_database_success(
        self, mock_engine, mock_set_version, mock_get_version, mock_verify, mock_seed, mock_base
    ):
        """Should initialize all tables and set version to LATEST_SCHEMA_VERSION."""
        # Database not initialized yet
        mock_get_version.return_value = None

        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=None)

        # Call function
        init_database()

        # Verify tables created
        mock_base.metadata.create_all.assert_called_once_with(mock_conn)

        # Verify taxonomy seeded
        mock_seed.assert_called_once_with(mock_conn)

        # Verify schema compatibility checked
        mock_verify.assert_called_once_with(mock_engine, conn=mock_conn)

        # Verify version set to LATEST_SCHEMA_VERSION
        mock_set_version.assert_called_once_with(
            mock_engine, LATEST_SCHEMA_VERSION, "Schema v4 with chunk needs_reindex flag", conn=mock_conn
        )

    @patch("app.core.database.verify_schema_compatibility")
    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.set_schema_version")
    @patch("app.core.database.engine")
    @patch("app.core.database.logger")
    def test_init_database_already_initialized(
        self, mock_logger, mock_engine, mock_set_version, mock_get_version, mock_verify
    ):
        """Should skip initialization when version=LATEST_SCHEMA_VERSION exists."""
        # Database already initialized at latest version
        mock_get_version.return_value = LATEST_SCHEMA_VERSION

        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=None)

        # Call function
        init_database()

        # Verify no version set
        mock_set_version.assert_not_called()

        # Verify schema compatibility checked even when version exists
        mock_verify.assert_called_once_with(mock_engine, conn=mock_conn)

        # Verify logged
        mock_logger.info.assert_called()

    @patch("app.models.Base")
    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.engine")
    @patch("app.core.database.logger")
    def test_init_database_handles_errors(
        self, mock_logger, mock_engine, mock_get_version, mock_base
    ):
        """Should handle database errors gracefully."""
        # Database not initialized
        mock_get_version.return_value = None

        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=None)

        # Simulate error during table creation
        mock_base.metadata.create_all.side_effect = Exception("Database error")

        # Call function should raise the exception
        with pytest.raises(Exception, match="Database error"):
            init_database()

        # Verify error was logged
        mock_logger.error.assert_called()

    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.engine")
    def test_init_database_fails_on_version_mismatch(
        self, mock_engine, mock_get_version
    ):
        """Should fail fast when schema_version is higher than LATEST_SCHEMA_VERSION."""
        mock_get_version.return_value = 999

        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=None)

        with pytest.raises(RuntimeError) as exc_info:
            init_database()

        assert "Unsupported database schema version" in str(exc_info.value)
