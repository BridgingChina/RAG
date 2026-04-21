"""Tests for OpenAICompatProvider — DeepSeek / Moonshot / OpenRouter / etc.

Mirrors the MagicMock + patch("httpx.AsyncClient") style from
tests/test_providers.py. Structural JSON assertion via
mock_post.call_args.kwargs["json"].
"""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import ChatMessage
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError
from app.providers.openai_compat import OpenAICompatProvider


@pytest.fixture
def config():
    return ProviderConfig(
        provider_id="pid-deepseek",
        kind="openai_compat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_KEY_FOR_TEST",
    )


@pytest.fixture
def openrouter_config():
    return ProviderConfig(
        provider_id="pid-openrouter",
        kind="openai_compat",
        base_url="https://openrouter.ai/api",
        api_key_env="OPENROUTER_KEY_FOR_TEST",
        extra_headers={
            "HTTP-Referer": "https://example.com",
            "X-Title": "BridgingChina",
        },
    )


def _make_chat_success_response() -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_embed_success_response(n: int, dim: int = 4) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "data": [{"index": i, "embedding": [0.1] * dim} for i in range(n)],
    }
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_chat_sends_correct_endpoint_and_model(monkeypatch, config):
    """chat() hits {base_url}/v1/chat/completions with the passed model
    and carries the Bearer token from the resolved env var."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=_make_chat_success_response())
        mock_client.return_value.__aenter__.return_value.post = mock_post

        resp = await provider.chat(
            [ChatMessage(role="user", content="hi")],
            model="deepseek-chat",
        )

        call_args = mock_post.call_args
        # Endpoint shape
        assert call_args.args[0] == "https://api.deepseek.com/v1/chat/completions"
        # Body carries the model
        json_payload = call_args.kwargs["json"]
        assert json_payload["model"] == "deepseek-chat"
        # Authorization header carries Bearer key
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer fake-key-1234567890ab"
        assert headers["Content-Type"] == "application/json"

    assert resp.model == "deepseek-chat"
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_chat_falls_back_requires_no_default_since_provider_has_no_chat_model_attr(
    monkeypatch, config
):
    """OpenAICompatProvider has no default chat_model — None and empty string
    both must raise ProviderConfigurationError (no silent fallback)."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)
    with pytest.raises(ProviderConfigurationError):
        await provider.chat([ChatMessage(role="user", content="hi")])  # no model=
    with pytest.raises(ProviderConfigurationError):
        await provider.chat([ChatMessage(role="user", content="hi")], model="")


@pytest.mark.asyncio
async def test_embed_sends_correct_endpoint_and_model(monkeypatch, config):
    """embed() hits {base_url}/v1/embeddings with the passed model."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=_make_embed_success_response(1))
        mock_client.return_value.__aenter__.return_value.post = mock_post

        vectors = await provider.embed(["text"], model="text-embedding-3-small")

        call_args = mock_post.call_args
        assert call_args.args[0] == "https://api.deepseek.com/v1/embeddings"
        json_payload = call_args.kwargs["json"]
        assert json_payload["model"] == "text-embedding-3-small"
        assert json_payload["input"] == ["text"]

    assert len(vectors) == 1
    assert len(vectors[0]) == 4


@pytest.mark.asyncio
async def test_embed_requires_model(monkeypatch, config):
    """embed() without model= must raise — no default."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)
    with pytest.raises(ProviderConfigurationError):
        await provider.embed(["text"])  # no model=


@pytest.mark.asyncio
async def test_raises_configuration_error_when_env_missing(monkeypatch, config):
    """Missing env var → ProviderConfigurationError from resolve_api_key."""
    monkeypatch.delenv("DEEPSEEK_KEY_FOR_TEST", raising=False)

    provider = OpenAICompatProvider(config)
    with pytest.raises(ProviderConfigurationError):
        await provider.chat(
            [ChatMessage(role="user", content="hi")],
            model="deepseek-chat",
        )


@pytest.mark.asyncio
async def test_extra_headers_are_passed_through(monkeypatch, openrouter_config):
    """OpenRouter's HTTP-Referer + X-Title must appear in the headers."""
    monkeypatch.setenv("OPENROUTER_KEY_FOR_TEST", "sk-or-1234567890abcdef")

    provider = OpenAICompatProvider(openrouter_config)

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=_make_chat_success_response())
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await provider.chat(
            [ChatMessage(role="user", content="hi")],
            model="openai/gpt-4o",
        )

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "BridgingChina"
        assert headers["Authorization"] == "Bearer sk-or-1234567890abcdef"


@pytest.mark.asyncio
async def test_list_models_parses_response(monkeypatch, config):
    """GET /v1/models → ModelInfo list, kind='chat' default, extras preserved."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get

        models = await provider.list_models()

        assert mock_get.call_args.args[0] == "https://api.deepseek.com/v1/models"

    assert len(models) == 1
    assert models[0].id == "deepseek-chat"
    assert models[0].kind == "chat"
    assert models[0].extra.get("owned_by") == "deepseek"


@pytest.mark.asyncio
async def test_list_models_raises_unavailable_on_5xx(monkeypatch, config):
    """HTTP 503 must map to ProviderUnavailableError (not leak httpx)."""
    monkeypatch.setenv("DEEPSEEK_KEY_FOR_TEST", "fake-key-1234567890ab")

    provider = OpenAICompatProvider(config)

    request = httpx.Request("GET", "https://api.deepseek.com/v1/models")
    response = httpx.Response(503, request=request)
    err = httpx.HTTPStatusError("Server error 503", request=request, response=response)

    failing = MagicMock()
    failing.raise_for_status = MagicMock(side_effect=err)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=failing)

        with pytest.raises(ProviderUnavailableError):
            await provider.list_models()
