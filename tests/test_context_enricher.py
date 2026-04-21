"""Tests for ContextEnricher.

Phase C: the service no longer takes an injected provider. Tests monkey-patch
``app.services.context_enricher.chat_for_task`` to stub LLM responses.
"""
import pytest

from app.providers import ChatResponse
from app.services import context_enricher as enricher_module
from app.services.context_enricher import ContextEnricher


def _patch_chat(monkeypatch, content: str):
    async def _fake(task_key, messages):
        return ChatResponse(content=content, usage={"total_tokens": 100}, model="stub-model")

    monkeypatch.setattr(enricher_module, "chat_for_task", _fake)


@pytest.mark.asyncio
async def test_enrich_basic(monkeypatch):
    _patch_chat(
        monkeypatch,
        '{"contextual_text": "来自《中国古桥》的片段，介绍赵州桥的敞肩式结构特点。",'
        ' "entities": ["赵州桥", "敞肩式"], "resolved_references": {"该桥": "赵州桥"}}',
    )
    enricher = ContextEnricher()
    result = await enricher.enrich(
        content="该桥采用敞肩式结构，主拱跨度37米。",
        source_title="中国古桥",
        section_title="第三章 石拱桥",
        page_range="45-46",
    )
    assert result.contextual_text is not None
    assert len(result.contextual_text) > 0
    assert "赵州桥" in result.entities or "敞肩式" in result.entities


@pytest.mark.asyncio
async def test_enrich_with_surrounding_context(monkeypatch):
    _patch_chat(
        monkeypatch,
        '{"contextual_text": "来自《中国古桥》的片段，介绍赵州桥的敞肩式结构特点。",'
        ' "entities": ["赵州桥"], "resolved_references": {"它": "赵州桥"}}',
    )
    enricher = ContextEnricher()
    result = await enricher.enrich(
        content="它的主拱跨度达37米。",
        source_title="中国古桥",
        section_title="第三章",
        page_range="46",
        surrounding_chunks=["赵州桥是我国著名的古代石拱桥。"],
    )
    assert result.contextual_text is not None
