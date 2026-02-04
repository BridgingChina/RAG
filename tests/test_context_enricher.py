import pytest


class MockProvider:
    async def chat(self, messages):
        from app.providers import ChatResponse
        return ChatResponse(
            content='{"contextual_text": "来自《中国古桥》的片段，介绍赵州桥的敞肩式结构特点。", "entities": ["赵州桥", "敞肩式"], "resolved_references": {"该桥": "赵州桥"}}',
            usage={"total_tokens": 100},
        )


@pytest.mark.asyncio
async def test_enrich_basic():
    from app.services.context_enricher import ContextEnricher
    enricher = ContextEnricher(provider=MockProvider())
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
async def test_enrich_with_surrounding_context():
    from app.services.context_enricher import ContextEnricher
    enricher = ContextEnricher(provider=MockProvider())
    result = await enricher.enrich(
        content="它的主拱跨度达37米。",
        source_title="中国古桥",
        section_title="第三章",
        page_range="46",
        surrounding_chunks=["赵州桥是我国著名的古代石拱桥。"],
    )
    assert result.contextual_text is not None
