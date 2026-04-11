import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.constants import EMBEDDING_DIM
from app.providers import ChatMessage, ZhipuProvider


@pytest.fixture
def provider():
    return ZhipuProvider()


def test_provider_has_required_methods(provider):
    assert hasattr(provider, "embed")
    assert hasattr(provider, "chat")
    assert callable(provider.embed)
    assert callable(provider.chat)


def test_chat_message_structure():
    msg = ChatMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


@pytest.mark.asyncio
async def test_embed_returns_expected_dimensions(provider):
    """Test that embed() returns EMBEDDING_DIM-dimensional vectors."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * EMBEDDING_DIM}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        embeddings = await provider.embed(["test text"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_embed_passes_dimensions_parameter(provider):
    """Test that the dimensions parameter is passed to the Zhipu API."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * EMBEDDING_DIM}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await provider.embed(["test text"])

        # Verify the API call includes dimensions=EMBEDDING_DIM
        call_args = mock_post.call_args
        json_payload = call_args.kwargs["json"]
        assert "dimensions" in json_payload
        assert json_payload["dimensions"] == EMBEDDING_DIM


# --- Retry behavior tests (issue #148 Bug #1) ---


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with the given status code."""
    request = httpx.Request("POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Client error '{status_code}'", request=request, response=response
    )


def _make_chat_success_response() -> MagicMock:
    """Build a successful mock chat response."""
    resp = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"total_tokens": 1},
    }
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_chat_retries_on_429_then_succeeds(provider, monkeypatch):
    """chat() should retry on 429 and succeed on a later attempt."""
    # Speed up retries: override tenacity sleep to a no-op
    import tenacity
    monkeypatch.setattr(tenacity.nap, "sleep", lambda _s: None)

    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            err = _make_http_error(429)
            failing = MagicMock()
            failing.raise_for_status = MagicMock(side_effect=err)
            return failing
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_chat_retries_on_500_then_succeeds(provider, monkeypatch):
    """chat() should retry on 5xx errors."""
    import tenacity
    monkeypatch.setattr(tenacity.nap, "sleep", lambda _s: None)

    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            err = _make_http_error(503)
            failing = MagicMock()
            failing.raise_for_status = MagicMock(side_effect=err)
            return failing
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_chat_gives_up_after_max_attempts(provider, monkeypatch):
    """chat() should stop retrying after stop_after_attempt(3) and reraise."""
    import tenacity
    monkeypatch.setattr(tenacity.nap, "sleep", lambda _s: None)

    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        err = _make_http_error(429)
        failing = MagicMock()
        failing.raise_for_status = MagicMock(side_effect=err)
        return failing

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await provider.chat([ChatMessage(role="user", content="hi")])

    assert excinfo.value.response.status_code == 429
    assert call_count["n"] == 3  # stop_after_attempt(3)


@pytest.mark.asyncio
async def test_chat_does_not_retry_on_4xx_non_429(provider, monkeypatch):
    """chat() should NOT retry on 400/401/404 (non-retryable client errors)."""
    import tenacity
    monkeypatch.setattr(tenacity.nap, "sleep", lambda _s: None)

    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        err = _make_http_error(401)
        failing = MagicMock()
        failing.raise_for_status = MagicMock(side_effect=err)
        return failing

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat([ChatMessage(role="user", content="hi")])

    assert call_count["n"] == 1  # no retry on 401
