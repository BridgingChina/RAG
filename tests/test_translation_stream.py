"""Tests for translate_answer_stream + extract_evidence_summaries_async."""
import pytest
from unittest.mock import patch
from app.services.translation_service import (
    translate_answer_stream,
    extract_evidence_summaries_async,
)


@pytest.mark.asyncio
async def test_translate_answer_stream_yields_tokens():
    async def fake_stream(task_key, messages):
        for tok in ["Hello", " world"]:
            yield tok
    with patch(
        "app.services.translation_service.chat_stream_for_task",
        side_effect=fake_stream,
    ):
        tokens = [t async for t in translate_answer_stream("question?", [])]
    assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_extract_evidence_summaries_async_swallows_errors(caplog):
    """Background helper must never raise."""
    async def boom(task_key, messages):
        raise RuntimeError("upstream down")

    with patch(
        "app.services.translation_service.chat_for_task",
        side_effect=boom,
    ):
        # Should not raise
        await extract_evidence_summaries_async(
            answer_text="hi",
            merged=[{"chunk_id": "abc", "content": "stuff"}],
        )
