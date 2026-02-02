import pytest

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
