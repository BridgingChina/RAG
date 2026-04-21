"""Integration test for Phase C task routing — real DB, stubbed upstream.

Proves that ``chat_for_task("qa_generation", ...)`` resolves the seeded Zhipu
route (migration v13) to ``glm-4.7`` and delegates to the Zhipu provider's
``chat()`` method. We monkey-patch :meth:`ZhipuProvider.chat` so the test
does NOT make a real HTTP request — only the routing wiring is exercised.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.llm import chat_for_task
from app.llm import router
from app.llm.registry import _registry
from app.providers.base import ChatMessage, ChatResponse
from app.providers.zhipu import ZhipuProvider


@pytest.fixture(autouse=True)
def _fresh_router_state():
    router.invalidate_all()
    _registry.invalidate_all()
    yield
    router.invalidate_all()
    _registry.invalidate_all()


def _db_available() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(sql_text("SELECT 1"))
            return True
        finally:
            db.close()
    except OperationalError:
        return False


@pytest.mark.asyncio
async def test_chat_for_task_qa_generation_routes_to_seeded_zhipu(monkeypatch):
    """The seeded ``qa_generation`` route (migration v13) should resolve to
    ZhipuProvider + model ``glm-4.7``."""
    if not _db_available():
        pytest.skip("PostgreSQL test DB not available")

    # Ensure the llm_task_routes seed exists (migration v13). Skip otherwise
    # — this test requires Phase B to be applied.
    db = SessionLocal()
    try:
        row = db.execute(
            sql_text(
                "SELECT model_id, provider_id FROM llm_task_routes "
                "WHERE task_key = 'qa_generation'"
            )
        ).first()
        if row is None:
            pytest.skip("qa_generation task route not seeded (run migrate_db.py)")
        seeded_model = row[0]
    finally:
        db.close()

    captured_calls: list[dict] = []

    async def _fake_chat(self, messages, *, model=None):
        captured_calls.append({"model": model, "messages": messages})
        return ChatResponse(
            content='{"summary": "stub"}',
            usage={"total_tokens": 1},
            model=model or "",
        )

    monkeypatch.setattr(ZhipuProvider, "chat", _fake_chat)

    resp = await chat_for_task(
        "qa_generation",
        [ChatMessage(role="user", content="ping")],
    )

    assert resp.model == seeded_model
    assert seeded_model == "glm-4.7"
    assert len(captured_calls) == 1
    assert captured_calls[0]["model"] == "glm-4.7"


@pytest.mark.asyncio
async def test_chat_for_task_unknown_key_raises():
    """A task_key with no row in llm_task_routes must raise
    ``TaskRouteNotFoundError`` so the miss surfaces as HTTP 500 at the edge."""
    if not _db_available():
        pytest.skip("PostgreSQL test DB not available")

    from app.providers.errors import TaskRouteNotFoundError

    with pytest.raises(TaskRouteNotFoundError):
        await chat_for_task(
            "__definitely_not_a_real_task_key__",
            [ChatMessage(role="user", content="ping")],
        )
