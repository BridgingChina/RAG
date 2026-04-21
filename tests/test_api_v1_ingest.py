"""Tests for V1 Ingest API endpoint.

Phase C: chat calls route through ``chat_for_task``, so the e2e fixture
patches the symbol on every service module the ingest pipeline touches
(context_enricher / bridge_linker / tagger) instead of stubbing the
ZhipuProvider class. Embedding still flows through ``get_provider()`` (Zhipu
is locked for embedding per design §2), so the fixture also patches
``ZhipuProvider.embed`` to return a deterministic vector.
"""
import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.constants import EMBEDDING_DIM
from app.core.database import get_db
from app.main import app
from app.models import Base, Chunk, ChunkBridgeLink
from app.providers import ChatResponse
from app.providers.base import ChatMessage


def _fake_embed(texts, *, model=None):
    async def _run():
        embeddings: list[list[float]] = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            seed = list(digest)
            vec = [(seed[i % len(seed)] / 255.0) for i in range(EMBEDDING_DIM)]
            embeddings.append(vec)
        return embeddings
    return _run()


async def _fake_chat_for_task(task_key: str, messages: list[ChatMessage]) -> ChatResponse:
    """Route stub responses by task_key — one task_key per service after
    Phase C (ingest_context_enricher / ingest_bridge_linker / ingest_tagger)."""
    if task_key == "ingest_context_enricher":
        payload = {
            "contextual_text": "该片段来自测试文档，介绍赵州桥的结构特点与历史背景。",
            "entities": ["赵州桥", "石拱桥"],
            "resolved_references": {},
        }
    elif task_key == "ingest_bridge_linker":
        payload = {
            "primary_bridge": "赵州桥",
            "primary_confidence": 0.9,
            "secondary_bridges": [],
            "candidate_bridges": [],
        }
    elif task_key == "ingest_tagger":
        payload = {
            "lvl1": "形制与技术",
            "lvl2": "结构体系",
            "lvl3": "拱桥结构",
            "bridge_name": None,
        }
    else:
        payload = {}
    return ChatResponse(
        content=json.dumps(payload, ensure_ascii=False),
        usage={},
        model="stub-model",
    )


@pytest.fixture
def client():
    return TestClient(app)


def test_ingest_v1_endpoint_exists():
    """Test that /api/v1/ingest endpoint is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ingest" in route_paths


def test_ingest_v1_endpoint_schema(client):
    """Test request validation for /api/v1/ingest (returns 401 without auth)."""
    response = client.post("/api/v1/ingest", json={})
    assert response.status_code in (401, 422)  # 401 without auth, 422 with auth


def test_ingest_request_requires_content(client):
    """Test that content field is required (returns 401 without auth)."""
    response = client.post(
        "/api/v1/ingest",
        json={"source_type": "note"},
    )
    assert response.status_code in (401, 422)  # 401 without auth, 422 with auth


def test_ingest_response_schema():
    """Test IngestResponse schema structure."""
    from app.api.v1.schemas import IngestResponse, IngestedChunkSummary

    _uuid1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
    response = IngestResponse(
        source_id=_uuid1,
        title="测试文档",
        primary_bridge_names=["赵州桥"],
        ambiguous_chunk_count=0,
        auto_created_bridges=[],
        chunk_count=2,
        chunks=[
            IngestedChunkSummary(
                content_preview="测试内容...",
                lvl1="形制与技术",
                lvl2="结构体系",
                binding_status="primary",
                primary_bridge_name="赵州桥",
                secondary_bridge_names=[],
            )
        ],
    )
    assert response.source_id == _uuid1
    assert response.chunk_count == 2
    assert response.primary_bridge_names == ["赵州桥"]
    assert len(response.chunks) == 1


@pytest.fixture
def client_e2e(db_engine, monkeypatch):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    Base.metadata.create_all(bind=connection)

    session.execute(text("DELETE FROM chunk_bridge_links"))
    session.execute(text("DELETE FROM chunks"))
    session.execute(text("DELETE FROM sources"))
    session.execute(text("DELETE FROM bridges"))
    session.execute(text("DELETE FROM taxonomy_nodes"))
    session.flush()

    # Allow the app code to call session.commit() while keeping a rollbackable outer transaction.
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    # Patch chat_for_task on each service module — this is the Phase C
    # equivalent of the old "patch ZhipuProvider" approach. embed() still
    # lives on ZhipuProvider (locked by design §2), so stub that too.
    from app.providers import zhipu as zhipu_module
    from app.services import bridge_linker as bridge_linker_module
    from app.services import context_enricher as context_enricher_module
    from app.services import tagger as tagger_module
    from app.services import chunker as chunker_module

    monkeypatch.setattr(context_enricher_module, "chat_for_task", _fake_chat_for_task)
    monkeypatch.setattr(bridge_linker_module, "chat_for_task", _fake_chat_for_task)
    monkeypatch.setattr(tagger_module, "chat_for_task", _fake_chat_for_task)
    monkeypatch.setattr(zhipu_module.ZhipuProvider, "embed", _fake_embed)

    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


def test_ingest_v1_e2e_writes_chunks_and_tsv(client_e2e):
    client, session = client_e2e

    long_text = "。".join([f"这是第{i}句，描述赵州桥的结构与工艺细节" for i in range(1, 20)]) + "。"
    markdown = f"""---
bridge: 赵州桥
title: 测试导入文档
---

# 第一节
{long_text}
"""

    resp = client.post("/api/v1/ingest", json={"content": markdown, "source_type": "note"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunk_count"] >= 1
    assert body["primary_bridge_names"] == ["赵州桥"]
    assert "bridge_name" not in body

    chunks = session.query(Chunk).order_by(Chunk.id.asc()).all()
    assert len(chunks) == body["chunk_count"]
    assert all(c.bridge_binding_status == "primary" for c in chunks)

    links = session.query(ChunkBridgeLink).all()
    assert len(links) >= body["chunk_count"]
    assert all(link.role in {"primary", "secondary", "candidate"} for link in links)

    missing_tsv = session.execute(text("SELECT COUNT(*) FROM chunks WHERE tsv IS NULL")).scalar_one()
    assert missing_tsv == 0
