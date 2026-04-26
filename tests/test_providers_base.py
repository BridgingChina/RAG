"""ABC contract tests for LLMProvider.chat_stream."""
import inspect
import pytest
from app.providers.base import LLMProvider


def test_chat_stream_is_abstract():
    """LLMProvider must expose chat_stream as an abstract method."""
    assert "chat_stream" in LLMProvider.__abstractmethods__


def test_chat_stream_signature_is_async_generator():
    """Concrete subclasses must yield from chat_stream (signature returns AsyncGenerator)."""
    sig = inspect.signature(LLMProvider.chat_stream)
    params = list(sig.parameters)
    assert params == ["self", "messages", "model"], f"unexpected params: {params}"
    assert sig.parameters["model"].kind == inspect.Parameter.KEYWORD_ONLY
