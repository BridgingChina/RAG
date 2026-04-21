"""Tests for MiniMaxProvider — OpenAI-compatible shape + base_resp envelope.

MiniMax wraps responses in {..., "base_resp": {"status_code": int, "status_msg": str}}.
status_code == 0 → normal path; non-zero → ProviderUnavailableError.
Embedding is out-of-scope in Phase A and MUST raise NotImplementedError.

Uses the same MagicMock + patch("httpx.AsyncClient") pattern as
tests/test_openai_compat_provider.py (respx isn't installed).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import ChatMessage
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError
from app.providers.minimax import MiniMaxProvider


@pytest.fixture
def config():
    return ProviderConfig(
        provider_id="pid-minimax",
        kind="minimax",
        base_url="https://api.minimaxi.com",
        api_key_env="MINIMAX_KEY_FOR_TEST",
    )


def _make_chat_success_response(
    content: str = "hello from minimax",
    status_code: int = 0,
    status_msg: str = "success",
) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "id": "chatcmpl-fake",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        "base_resp": {"status_code": status_code, "status_msg": status_msg},
    }
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_chat_unwraps_base_resp_success(monkeypatch, config):
    """base_resp.status_code == 0 → normal path, content returned."""
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=_make_chat_success_response())
        mock_client.return_value.__aenter__.return_value.post = mock_post

        resp = await provider.chat(
            [ChatMessage(role="user", content="hi")],
            model="abab6.5s-chat",
        )

        call_args = mock_post.call_args
        assert call_args.args[0] == "https://api.minimaxi.com/v1/chat/completions"
        json_payload = call_args.kwargs["json"]
        assert json_payload["model"] == "abab6.5s-chat"
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer fake-key-1234567890ab"

    assert resp.content == "hello from minimax"
    assert resp.model == "abab6.5s-chat"
    assert resp.usage.get("total_tokens") == 8


@pytest.mark.asyncio
async def test_chat_translates_base_resp_error_to_unavailable(monkeypatch, config):
    """base_resp.status_code != 0 → ProviderUnavailableError.

    Message must include status_code + status_msg so ops can debug.
    """
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)

    # Mock a failure: HTTP 200 BUT base_resp contains a rate-limit error code.
    err_resp = MagicMock()
    err_resp.json.return_value = {
        "choices": [],
        "base_resp": {"status_code": 1004, "status_msg": "rate limit reached"},
    }
    err_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=err_resp)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.chat(
                [ChatMessage(role="user", content="hi")],
                model="abab6.5s-chat",
            )

    msg = str(exc_info.value)
    assert "1004" in msg
    assert "rate limit" in msg.lower()


@pytest.mark.asyncio
async def test_chat_raises_when_model_not_passed(monkeypatch, config):
    """Inherits OpenAICompat's fail-fast behavior — no fallback default."""
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)
    with pytest.raises(ProviderConfigurationError):
        await provider.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_embed_raises_not_implemented(monkeypatch, config):
    """MiniMax embed is out-of-scope for Phase A — MUST raise NotImplementedError,
    not silently fall back. If future A/B adds MiniMax embeddings, override then."""
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)
    with pytest.raises(NotImplementedError) as exc_info:
        await provider.embed(["some text"], model="embo-01")
    assert "MiniMax" in str(exc_info.value)
    assert "embed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_list_models_passes_through_unwrapped_data(monkeypatch, config):
    """If MiniMax's /v1/models is NOT wrapped, behavior matches OpenAICompat."""
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "abab6.5s-chat", "object": "model"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get

        models = await provider.list_models()

        assert mock_get.call_args.args[0] == "https://api.minimaxi.com/v1/models"

    assert len(models) == 1
    assert models[0].id == "abab6.5s-chat"
    assert models[0].kind == "chat"


@pytest.mark.asyncio
async def test_list_models_unwraps_base_resp_wrapped_data(monkeypatch, config):
    """If MiniMax's /v1/models IS wrapped with base_resp, unwrap gracefully."""
    monkeypatch.setenv("MINIMAX_KEY_FOR_TEST", "fake-key-1234567890ab")
    provider = MiniMaxProvider(config)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "abab6.5s-chat", "object": "model"},
            {"id": "abab5.5-chat", "object": "model"},
        ],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get

        models = await provider.list_models()

    assert len(models) == 2
    assert {m.id for m in models} == {"abab6.5s-chat", "abab5.5-chat"}
    assert all(m.kind == "chat" for m in models)
