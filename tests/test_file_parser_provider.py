"""Unit tests for FileParserProvider (mocked httpx)."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_create_task_returns_task_id():
    """create_task sends file to Zhipu and returns task_id."""
    with patch("app.providers.file_parser.settings") as mock_settings:
        mock_settings.zhipu_api_key = "test-key"
        mock_settings.zhipu_parser_tool_type = "expert"

        from app.providers.file_parser import FileParserProvider

        provider = FileParserProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "task_id": "zhipu-task-123",
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.providers.file_parser.httpx.AsyncClient", return_value=mock_client):
            task_id = await provider.create_task(
                file_bytes=b"fake-pdf-content",
                file_name="test.pdf",
                file_type="pdf",
            )

        assert task_id == "zhipu-task-123"


@pytest.mark.asyncio
async def test_get_result_returns_parse_result():
    """get_result returns parsed content when status is succeeded."""
    with patch("app.providers.file_parser.settings") as mock_settings:
        mock_settings.zhipu_api_key = "test-key"
        mock_settings.zhipu_parser_tool_type = "expert"

        from app.providers.file_parser import FileParserProvider, ParseResult

        provider = FileParserProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "status": "succeeded",
                "content": "# Parsed markdown",
                "parsing_result_url": "https://download.url/result.zip",
            }
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.providers.file_parser.httpx.AsyncClient", return_value=mock_client):
            result = await provider.get_result("zhipu-task-123", format_type="text")

        assert result.status == "succeeded"
        assert result.content == "# Parsed markdown"
