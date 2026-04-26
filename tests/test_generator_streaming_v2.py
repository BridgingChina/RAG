"""Tests for Generator.generate_streaming_v2 (true-streaming JSON version)."""
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
            '{"summaries":[',
            '"A [1]",',
            '"B [2]"',
            '],',
            '"details":[',
            '{"explanation":"正文A","citations":[1]},',
            '{"explanation":"正文B","citations":[2]}',
            ']}',
        ]:
            yield tok

    gen = Generator()
    with patch("app.services.generator.chat_stream_for_task", side_effect=fake_stream):
        events = [evt async for evt in gen.generate_streaming_v2("q?", _empty_evidence())]

    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]
    outline = events[0][1]
    assert outline["key_points"][0]["summary"] == "A"
    assert outline["key_points"][0]["citations"] == [1]


@pytest.mark.asyncio
async def test_generate_streaming_v2_propagates_parse_degraded():
    """If LLM returns no JSON, generator must raise ParseDegradedError up to caller."""
    from app.services.json_stream_parser import ParseDegradedError

    async def fake_stream(task_key, messages):
        yield "no json structure here"

    gen = Generator()
    with patch("app.services.generator.chat_stream_for_task", side_effect=fake_stream):
        with pytest.raises(ParseDegradedError) as exc:
            async for _ in gen.generate_streaming_v2("q?", _empty_evidence()):
                pass
    assert "no json structure" in exc.value.fallback_payload["explanation"]


@pytest.mark.asyncio
async def test_generate_streaming_v2_handles_legacy_key_points_schema():
    """If GLM emits legacy key_points instead of summaries+details, fall back."""
    async def fake_stream(task_key, messages):
        yield (
            '{"key_points":['
            '{"summary":"S1","explanation":"E1","citations":[1]},'
            '{"summary":"S2","explanation":"E2","citations":[2]}'
            ']}'
        )

    gen = Generator()
    with patch("app.services.generator.chat_stream_for_task", side_effect=fake_stream):
        events = [evt async for evt in gen.generate_streaming_v2("q?", _empty_evidence())]

    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]
    assert events[0][1]["key_points"][0]["summary"] == "S1"
