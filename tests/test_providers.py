import httpx
import pytest
from tenacity import wait_none
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.constants import EMBEDDING_DIM
from app.providers import ChatMessage, ZhipuProvider
from app.providers.zhipu_coding import ZhipuCodingProvider


@pytest.fixture
def provider():
    return ZhipuProvider()


@pytest.fixture
def fast_retry_provider(provider):
    """Disable tenacity backoff on provider.chat / provider.embed.

    ``monkeypatch(tenacity.nap.sleep)`` is a no-op for async retries
    (the async path dispatches via ``tenacity.asyncio._portable_async_sleep``).
    Replacing ``.retry.wait`` with ``wait_none()`` works regardless of sync
    vs async because it's consulted by both Retrying and AsyncRetrying.
    """
    original_chat_wait = provider.chat.retry.wait
    original_embed_wait = provider.embed.retry.wait
    provider.chat.retry.wait = wait_none()
    provider.embed.retry.wait = wait_none()
    try:
        yield provider
    finally:
        provider.chat.retry.wait = original_chat_wait
        provider.embed.retry.wait = original_embed_wait


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


def _failing_http_response(status_code: int) -> MagicMock:
    err = _make_http_error(status_code)
    failing = MagicMock()
    failing.raise_for_status = MagicMock(side_effect=err)
    return failing


# --- Sanity: the decorator is actually there (prevent silent removal) ---

# Keep in sync with the tenacity @retry decorator on ZhipuProvider.chat/embed.
# Bumped from 6 to 8: Zhipu slow-response periods can eat through retries
# on ReadTimeouts alone (2026-04-16 晋祠十字桥 RCA). 8 attempts + 90s
# read timeout + per-chunk fallbacks = resilient to sustained upstream load.
EXPECTED_MAX_ATTEMPTS = 8


def test_chat_has_retry_decorator():
    """Lock the invariant: chat() must remain @retry-decorated."""
    assert hasattr(ZhipuProvider.chat, "retry"), "chat() must be @retry-decorated"
    assert ZhipuProvider.chat.retry.stop.max_attempt_number == EXPECTED_MAX_ATTEMPTS


def test_embed_has_retry_decorator():
    assert hasattr(ZhipuProvider.embed, "retry"), "embed() must be @retry-decorated"
    assert ZhipuProvider.embed.retry.stop.max_attempt_number == EXPECTED_MAX_ATTEMPTS


def test_coding_provider_inherits_chat_retry():
    """ZhipuCodingProvider inherits chat unchanged, so it inherits the @retry decorator too."""
    # The decorated function object is shared via inheritance
    assert ZhipuCodingProvider.chat is ZhipuProvider.chat
    assert hasattr(ZhipuCodingProvider.chat, "retry")


# --- Retry on HTTPStatusError ---


@pytest.mark.asyncio
async def test_chat_retries_on_429_then_succeeds(fast_retry_provider):
    """chat() should retry on 429 and succeed on a later attempt."""
    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return _failing_http_response(429)
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_chat_retries_on_500_then_succeeds(fast_retry_provider):
    """chat() should retry on 5xx errors."""
    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return _failing_http_response(503)
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_chat_gives_up_after_max_attempts(fast_retry_provider):
    """chat() should stop retrying after stop_after_attempt(3) and reraise."""
    call_count = {"n": 0}
    max_attempts = fast_retry_provider.chat.retry.stop.max_attempt_number

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        return _failing_http_response(429)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert excinfo.value.response.status_code == 429
    assert call_count["n"] == max_attempts


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_chat_does_not_retry_on_non_retryable_4xx(fast_retry_provider, status_code):
    """chat() must not retry on non-429 4xx responses -- they will never self-heal."""
    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        return _failing_http_response(status_code)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        with pytest.raises(httpx.HTTPStatusError):
            await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert call_count["n"] == 1


# --- Retry on transport errors (issue #148 Bug #1 — the dominant real failure mode) ---


@pytest.mark.asyncio
async def test_chat_retries_on_read_timeout(fast_retry_provider):
    """ReadTimeout is the dominant failure mode for long GLM prompts. Must retry."""
    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise httpx.ReadTimeout("gateway timed out")
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_chat_retries_on_connect_error(fast_retry_provider):
    """ConnectError (DNS / TCP handshake) must retry."""
    call_count = {"n": 0}

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise httpx.ConnectError("name resolution failed")
        return _make_chat_success_response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        result = await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_chat_retries_on_pool_timeout(fast_retry_provider):
    """PoolTimeout (httpx pool exhausted) must retry."""
    call_count = {"n": 0}
    max_attempts = fast_retry_provider.chat.retry.stop.max_attempt_number

    def side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        raise httpx.PoolTimeout("pool exhausted")

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=side_effect)

        with pytest.raises(httpx.PoolTimeout):
            await fast_retry_provider.chat([ChatMessage(role="user", content="hi")])

    # Exhaust all attempts -- proves transport errors use the same budget
    assert call_count["n"] == max_attempts


# --- A5: list_models + model= kwarg + ChatResponse.model fill ---


@pytest.mark.asyncio
async def test_list_models_parses_response(provider):
    """list_models() should GET /models and map rows into ModelInfo."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "glm-4.7", "object": "model"},
            {"id": "glm-4-flash", "object": "model"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get

        models = await provider.list_models()

        # Confirm URL shape
        call_args = mock_get.call_args
        assert call_args.args[0] == "https://open.bigmodel.cn/api/paas/v4/models"

    assert {m.id for m in models} == {"glm-4.7", "glm-4-flash"}
    # Zhipu doesn't tag kind → default "chat" is fine for now
    assert all(m.kind == "chat" for m in models)


@pytest.mark.asyncio
async def test_chat_uses_passed_model(provider):
    """chat(model='glm-4-custom') should pass that model in the request body
    and surface it on ChatResponse.model."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        resp = await provider.chat(
            [ChatMessage(role="user", content="hello")], model="glm-4-custom"
        )

        call_args = mock_post.call_args
        json_payload = call_args.kwargs["json"]
        assert json_payload["model"] == "glm-4-custom"

    assert resp.model == "glm-4-custom"


@pytest.mark.asyncio
async def test_chat_falls_back_to_self_chat_model_when_model_none(provider):
    """Without model=, chat() should fall back to self.chat_model
    (settings.chat_model, default 'glm-4.7')."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await provider.chat([ChatMessage(role="user", content="hello")])

        call_args = mock_post.call_args
        json_payload = call_args.kwargs["json"]
        # should fall back to settings.chat_model (default "glm-4.7")
        assert json_payload["model"] == provider.chat_model
