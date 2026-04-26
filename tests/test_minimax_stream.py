"""Tests for MiniMaxProvider.chat_stream — verifies base_resp envelope handling.

The override exists because OpenAI-compat parent's chat_stream doesn't know
about MiniMax's `base_resp` envelope. A frame with status_code != 0 is a
business-level error (insufficient quota, model offline, etc.) that the
non-streaming chat() path translates to ProviderUnavailableError. The
streaming path must do the same — silently dropping the envelope would let
the caller observe partial content + no error signal.

Mirrors tests/test_openai_compat_stream.py shape (FakeStreamCM, patch
httpx.AsyncClient on app.providers.openai_compat — MiniMax's override
inherits the same import path).
"""
import pytest
import httpx
from unittest.mock import MagicMock, patch

from app.providers.base import ChatMessage
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderUnavailableError
from app.providers.minimax import MiniMaxProvider


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
    monkeypatch.setenv("MINIMAX_KEY_FOR_STREAM_TEST", "fake-key-1234567890ab")
    config = ProviderConfig(
        provider_id="pid-minimax-stream",
        kind="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key_env="MINIMAX_KEY_FOR_STREAM_TEST",
    )
    return MiniMaxProvider(config)


@pytest.mark.asyncio
async def test_chat_stream_yields_content_when_base_resp_ok(provider):
    """Successful stream: each frame either has no base_resp or status_code=0."""
    lines = [
        'data: {"choices": [{"delta": {"content": "你好"}}]}',
        'data: {"choices": [{"delta": {"content": "世界"}}], "base_resp": {"status_code": 0, "status_msg": "ok"}}',
        'data: [DONE]',
    ]
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        deltas = [
            t
            async for t in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="abab6.5s-chat",
            )
        ]
    assert deltas == ["你好", "世界"]


@pytest.mark.asyncio
async def test_chat_stream_aborts_on_base_resp_error(provider):
    """A frame with status_code != 0 must raise ProviderUnavailableError.

    Critical: the error message must contain the status_code so ops/parsers
    can act on it (e.g. distinguish quota=1004 from model-offline=2013).
    """
    lines = [
        'data: {"choices": [{"delta": {"content": "你好"}}]}',
        'data: {"choices": [{"delta": {"content": ""}}], "base_resp": {"status_code": 1004, "status_msg": "insufficient quota"}}',
        'data: [DONE]',
    ]
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM(lines))
        with pytest.raises(ProviderUnavailableError, match="status_code=1004"):
            async for _ in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="abab6.5s-chat",
            ):
                pass


@pytest.mark.asyncio
async def test_chat_stream_skips_keepalive_and_non_data_lines(provider):
    """Keepalives, comments, and event lines must be skipped without error."""
    lines = [
        "",
        ": comment",
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
                model="abab6.5s-chat",
            )
        ]
    assert deltas == ["ok"]


@pytest.mark.asyncio
async def test_chat_stream_raises_on_http_5xx(provider):
    """Transport-level errors propagate — caller's _streaming_with_retry handles them."""
    with patch("app.providers.openai_compat.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.stream = MagicMock(return_value=_FakeStreamCM([], status=503))
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in provider.chat_stream(
                [ChatMessage(role="user", content="hi")],
                model="abab6.5s-chat",
            ):
                pass
