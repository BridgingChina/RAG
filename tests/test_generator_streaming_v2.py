"""Tests for Generator.generate_streaming_v2 (true-streaming version)."""
import pytest
from unittest.mock import patch
from app.services.generator import Generator
from app.services.hybrid_retriever import HybridRetrievalResult


def _empty_evidence():
    return HybridRetrievalResult(anchor_chunks=[], concept_chunks=[], analogy_chunks=[])


@pytest.mark.asyncio
async def test_generate_streaming_v2_yields_outline_then_details():
    async def fake_stream(task_key, messages):
        for tok in [
            "# 要点\n",
            "- A [1]\n",
            "- B [2]\n",
            "## 要点 1\n",
            "正文A [证据 1]\n",
            "## 要点 2\n",
            "正文B [证据 2]\n",
        ]:
            yield tok

    gen = Generator()
    with patch("app.services.generator.chat_stream_for_task", side_effect=fake_stream):
        events = [evt async for evt in gen.generate_streaming_v2("q?", _empty_evidence())]

    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]


@pytest.mark.asyncio
async def test_generate_streaming_v2_propagates_parse_degraded():
    """If LLM returns no headings, generator must raise ParseDegradedError up to caller."""
    from app.services.markdown_stream_parser import ParseDegradedError

    async def fake_stream(task_key, messages):
        yield "no markdown structure here"

    gen = Generator()
    with patch("app.services.generator.chat_stream_for_task", side_effect=fake_stream):
        with pytest.raises(ParseDegradedError) as exc:
            async for _ in gen.generate_streaming_v2("q?", _empty_evidence()):
                pass
    assert "no markdown structure" in exc.value.fallback_payload["explanation"]
