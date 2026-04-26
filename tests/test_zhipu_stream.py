"""Tests for ZhipuProvider.chat_stream — mock httpx, verify SSE line parsing."""
import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.providers.base import ChatMessage
from app.providers.zhipu import ZhipuProvider


class _FakeStreamCM:
    """Minimal async context manager that mimics httpx's stream() return value."""
    def __init__(self, lines, status=200):
        self._lines = lines
        self._status = status

    async def __aenter__(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if self._status >= 400:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "boom", request=None, response=MagicMock(status_code=self._status)
            )

        async def aiter_lines():
            for line in self._lines:
                yield line

        resp.aiter_lines = aiter_lines
        return resp

    async def __aexit__(self, *exc):
        return False


def _build_provider():
    # ZhipuProvider.__init__ reads api_key/chat_model from settings (no kwargs).
    # Override the attributes after construction so tests don't depend on env.
    provider = ZhipuProvider()
    provider.api_key = "fake-key"
    provider.chat_model = "glm-4.7"
    return provider


@pytest.mark.asyncio
async def test_chat_stream_yields_content_deltas():
    lines = [
        'data: {"choices": [{"delta": {"content": "你好"}}]}',
        'data: {"choices": [{"delta": {"content": "世界"}}]}',
        'data: [DONE]',
    ]
    provider = _build_provider()
    with patch("app.providers.zhipu.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        # __aenter__.return_value auto-becomes AsyncMock, which would make
        # client.stream() return a coroutine. httpx.AsyncClient.stream is sync
        # (returns an async CM), so override with a plain MagicMock.
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = []
        async for token in provider.chat_stream([ChatMessage(role="user", content="hi")]):
            deltas.append(token)
    assert deltas == ["你好", "世界"]


@pytest.mark.asyncio
async def test_chat_stream_skips_blank_and_non_data_lines():
    lines = [
        '',
        ': keepalive comment',
        'event: ping',
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        'data: [DONE]',
    ]
    provider = _build_provider()
    with patch("app.providers.zhipu.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        # __aenter__.return_value auto-becomes AsyncMock, which would make
        # client.stream() return a coroutine. httpx.AsyncClient.stream is sync
        # (returns an async CM), so override with a plain MagicMock.
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [t async for t in provider.chat_stream([ChatMessage(role="user", content="hi")])]
    assert deltas == ["ok"]


@pytest.mark.asyncio
async def test_chat_stream_drops_unparseable_lines_and_continues():
    lines = [
        'data: not-json',
        'data: {"choices": [{"delta": {"content": "saved"}}]}',
        'data: [DONE]',
    ]
    provider = _build_provider()
    with patch("app.providers.zhipu.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        # __aenter__.return_value auto-becomes AsyncMock, which would make
        # client.stream() return a coroutine. httpx.AsyncClient.stream is sync
        # (returns an async CM), so override with a plain MagicMock.
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [t async for t in provider.chat_stream([ChatMessage(role="user", content="hi")])]
    assert deltas == ["saved"]


@pytest.mark.asyncio
async def test_chat_stream_raises_on_http_5xx():
    provider = _build_provider()
    with patch("app.providers.zhipu.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM([], status=503))
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in provider.chat_stream([ChatMessage(role="user", content="hi")]):
                pass
