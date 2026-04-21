import inspect
import pytest
from app.providers.base import LLMProvider, ChatMessage, ModelInfo


def test_modelinfo_required_fields():
    m = ModelInfo(id="x", display_name="X", kind="chat")
    assert m.id == "x"
    assert m.context_window is None
    assert m.extra == {}


def test_list_models_is_abstract():
    assert "list_models" in LLMProvider.__abstractmethods__


def test_chat_has_model_keyword_only():
    sig = inspect.signature(LLMProvider.chat)
    assert "model" in sig.parameters


def test_embed_has_model_keyword_only():
    sig = inspect.signature(LLMProvider.embed)
    assert "model" in sig.parameters
