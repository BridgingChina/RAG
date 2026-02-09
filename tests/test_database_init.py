"""Tests for database initialization functions."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from sqlalchemy import Engine
from sqlalchemy.exc import ProgrammingError

from app.core.database import (
    get_current_schema_version,
    set_schema_version,
    init_database,
)


class TestGetCurrentSchemaVersion:
    """Tests for get_current_schema_version()."""

    def test_get_current_schema_version_none(self):
        """Should return None when schema_version table doesn't exist."""
        # Mock engine that raises ProgrammingError on query
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        # Simulate table doesn't exist
        mock_connection.execute.side_effect = ProgrammingError(
            "relation does not exist", None, None
        )

        result = get_current_schema_version(mock_engine)
        assert result is None

    def test_get_current_schema_version_returns_version(self):
        """Should return version number when table exists with data."""
        # Mock engine with existing schema_version
        mock_engine = Mock(spec=Engine)
        mock_connection = MagicMock()

        # Setup context manager
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_connection)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        # Mock result with version 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1
        mock_connection.execute.return_value = mock_result

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


class TestInitDatabase:
    """Tests for init_database()."""

    @patch("app.models.Base")
    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.set_schema_version")
    @patch("app.core.database.engine")
    def test_init_database_success(
        self, mock_engine, mock_set_version, mock_get_version, mock_base
    ):
        """Should initialize all tables and set version to 1."""
        # Database not initialized yet
        mock_get_version.return_value = None

        # Call function
        init_database()

        # Verify tables created
        mock_base.metadata.create_all.assert_called_once_with(mock_engine)

        # Verify version set to 1
        mock_set_version.assert_called_once_with(
            mock_engine, 1, "Initial schema"
        )

    @patch("app.core.database.get_current_schema_version")
    @patch("app.core.database.set_schema_version")
    @patch("app.core.database.logger")
    def test_init_database_already_initialized(
        self, mock_logger, mock_set_version, mock_get_version
    ):
        """Should skip initialization when version=1 exists."""
        # Database already initialized
        mock_get_version.return_value = 1

        # Call function
        init_database()

        # Verify no version set
        mock_set_version.assert_not_called()

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

        # Simulate error during table creation
        mock_base.metadata.create_all.side_effect = Exception("Database error")

        # Call function should raise the exception
        with pytest.raises(Exception, match="Database error"):
            init_database()

        # Verify error was logged
        mock_logger.error.assert_called()
