"""Tests for OpenAICompatProvider.chat_stream — mock httpx, verify SSE parsing.

Mirrors tests/test_zhipu_stream.py shape (FakeStreamCM, patch httpx.AsyncClient).
Provider fixture follows tests/test_openai_compat_provider.py — real ProviderConfig
+ monkeypatch the env key.
"""
import pytest
import httpx
from unittest.mock import MagicMock, patch

from app.providers.base import ChatMessage
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError
from app.providers.openai_compat import OpenAICompatProvider


class _FakeStreamCM:
    """Minimal async context manager mimicking httpx's stream() return value."""

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


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("OPENROUTER_KEY_FOR_STREAM_TEST", "fake-key-1234567890ab")
    config = ProviderConfig(
        provider_id="pid-openrouter-stream",
        kind="openai_compat",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_KEY_FOR_STREAM_TEST",
    )
    return OpenAICompatProvider(config)


@pytest.mark.asyncio
async def test_chat_stream_yields_content_deltas(provider):
    lines = [
        'data: {"choices": [{"delta": {"content": "Hello"}}]}',
        'data: {"choices": [{"delta": {"content": " world"}}]}',
        'data: [DONE]',
    ]
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        # httpx.AsyncClient.stream is sync (returns an async CM); override the
        # auto-AsyncMock so client.stream() doesn't return a coroutine.
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [
            t
            async for t in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="anthropic/claude-3-haiku",
            )
        ]
    assert deltas == ["Hello", " world"]


@pytest.mark.asyncio
async def test_chat_stream_skips_blank_and_non_data_lines(provider):
    lines = [
        "",
        ": keepalive comment",
        "event: ping",
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        "data: [DONE]",
    ]
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [
            t
            async for t in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="anthropic/claude-3-haiku",
            )
        ]
    assert deltas == ["ok"]


@pytest.mark.asyncio
async def test_chat_stream_drops_unparseable_lines_and_continues(provider):
    lines = [
        "data: not-json",
        'data: {"choices": [{"delta": {"content": "saved"}}]}',
        "data: [DONE]",
    ]
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [
            t
            async for t in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="anthropic/claude-3-haiku",
            )
        ]
    assert deltas == ["saved"]


@pytest.mark.asyncio
async def test_chat_stream_raises_on_http_5xx(provider):
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM([], status=503))
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="anthropic/claude-3-haiku",
            ):
                pass


@pytest.mark.asyncio
async def test_chat_stream_requires_model(provider):
    """OpenAI-compat has no fallback model default — empty/None must raise."""
    with pytest.raises(ProviderConfigurationError):
        async for _ in provider.chat_stream(
            [ChatMessage(role="user", content="hi")],
            model=None,
        ):
            pass
    with pytest.raises(ProviderConfigurationError):
        async for _ in provider.chat_stream(
            [ChatMessage(role="user", content="hi")],
            model="",
        ):
            pass
