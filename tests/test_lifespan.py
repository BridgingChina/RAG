"""Tests for FastAPI lifespan event handler."""

import pytest
from unittest.mock import patch, MagicMock


class TestLifespan:
    """Tests for FastAPI lifespan function."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"ENV": "development"})
    @patch("app.main.init_database")
    @patch("app.main.logger")
    async def test_lifespan_calls_init_database(self, mock_logger, mock_init_db):
        """Should call init_database() on startup."""
        from app.main import lifespan

        # Create a mock app
        mock_app = MagicMock()

        # Execute the lifespan context manager
        async with lifespan(mock_app):
            # Inside the context - application is running
            pass

        # Verify init_database was called
        mock_init_db.assert_called_once()

        # Verify startup logging
        assert any(
            "Starting application" in str(call)
            for call in mock_logger.info.call_args_list
        )
        assert any(
            "Database initialization complete" in str(call)
            for call in mock_logger.info.call_args_list
        )

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"ENV": "development"})
    @patch("app.main.init_database")
    @patch("app.main.logger")
    async def test_lifespan_handles_init_errors(self, mock_logger, mock_init_db):
        """Should handle and re-raise initialization errors."""
        from app.main import lifespan

        # Create a mock app
        mock_app = MagicMock()

        # Simulate init_database raising an exception
        mock_init_db.side_effect = Exception("Database connection failed")

        # Execute the lifespan context manager - should raise the exception
        with pytest.raises(Exception, match="Database connection failed"):
            async with lifespan(mock_app):
                pass

        # Verify error was logged
        mock_logger.error.assert_called()
        assert any(
            "Database initialization failed" in str(call)
            for call in mock_logger.error.call_args_list
        )

    @pytest.mark.asyncio
    @patch.dict("os.environ", {}, clear=False)
    @patch("app.main.init_database")
    @patch("app.main.logger")
    async def test_lifespan_rejects_default_secret_key_in_production(
        self, mock_logger, mock_init_db
    ):
        """Should raise RuntimeError if SECRET_KEY is default and ENV is not development."""
        import os

        os.environ.pop("ENV", None)

        from app.main import lifespan

        mock_app = MagicMock()

        with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
            async with lifespan(mock_app):
                pass
