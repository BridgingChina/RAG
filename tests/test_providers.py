import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_embed_returns_1024_dimensions(provider):
    """Test that embed() returns 1024-dimensional vectors."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1024}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        embeddings = await provider.embed(["test text"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1024


@pytest.mark.asyncio
async def test_embed_passes_dimensions_parameter(provider):
    """Test that the dimensions parameter is passed to the Zhipu API."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1024}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await provider.embed(["test text"])

        # Verify the API call includes dimensions=1024
        call_args = mock_post.call_args
        json_payload = call_args.kwargs["json"]
        assert "dimensions" in json_payload
        assert json_payload["dimensions"] == 1024
