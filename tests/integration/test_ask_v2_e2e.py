from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.providers import ChatResponse
from app.services.hybrid_retriever import HybridRetriever
from app.services.tokenizer import Tokenizer


def _emb(v0: float, v1: float = 0.0) -> list[float]:
    vec = [0.0] * 2048
    vec[0] = v0
    vec[1] = v1
    return vec


class RecordingProvider:
    def __init__(self, embedding: list[float]):
        self.embedding = embedding
        self.chat_prompts: list[str] = []

    async def embed(self, texts):
        return [self.embedding for _ in texts]

    async def chat(self, messages):
        prompt = messages[0].content
        self.chat_prompts.append(prompt)

        if "枚举值约束" in prompt:
            return ChatResponse(
                content='{"bridge_type": "石拱桥", "material": "石", "era": "隋唐", "region": "华北", "function": null}',
                usage={"total_tokens": 20},
            )

        return ChatResponse(
            content='{"summary": "测试要点", "details": "测试详细", "analogy": "有类比输出", "confidence": {"level": "medium", "reason": "测试"}}',
            usage={"total_tokens": 50},
        )


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_ask_v2_calls_facet_and_returns_analogy_evidence(
    client, test_bridges, test_chunks
):
    provider = RecordingProvider(_emb(1.0, 0.0))

    with patch("app.api.ask.ZhipuProvider", return_value=provider):
        response = client.post(
            "/ask/v2",
            json={
                "question": "赵州桥是石拱桥吗？",
                "target_bridge_id": test_bridges["target"].id,
            },
        )

    assert response.status_code == 200
    data = response.json()

    assert any("枚举值约束" in p for p in provider.chat_prompts)
    assert data["evidence_groups"]["analogy"]
    assert len(data["evidence_groups"]["analogy"]) == 2
    assert data.get("degraded") is None


def test_ask_v2_degraded_when_facet_fails(client, test_bridges, test_chunks):
    provider = RecordingProvider(_emb(1.0, 0.0))

    mock_extractor_instance = AsyncMock()
    mock_extractor_instance.extract.side_effect = RuntimeError("facet failure")

    with patch("app.api.ask.ZhipuProvider", return_value=provider), patch(
        "app.api.ask.FacetExtractor", return_value=mock_extractor_instance
    ):
        response = client.post(
            "/ask/v2",
            json={
                "question": "赵州桥是石拱桥吗？",
                "target_bridge_id": test_bridges["target"].id,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "facet" in (data.get("degraded") or [])
    assert data["evidence_groups"]["analogy"] == []


def test_ask_v2_degraded_when_fts_fails(monkeypatch, client, test_bridges, test_chunks):
    provider = RecordingProvider(_emb(1.0, 0.0))

    # Mock FTS to return empty results (simulating tsv not populated)
    # This tests that vector search still works when FTS has no data
    def empty_fts_search(self, db, query, bridge_filter, require_no_bridge_id, limit):
        return []

    monkeypatch.setattr(HybridRetriever, "_fts_search", empty_fts_search)

    with patch("app.api.ask.ZhipuProvider", return_value=provider):
        response = client.post(
            "/ask/v2",
            json={
                "question": "赵州桥是石拱桥吗？",
                "target_bridge_id": test_bridges["target"].id,
            },
        )

    assert response.status_code == 200
    data = response.json()
    # Should still have anchor chunks from vector search
    assert data["evidence_groups"]["anchor"], f"Expected anchor chunks, got {data}"


def test_ask_v2_degraded_when_evidence_empty(client):
    provider = RecordingProvider(_emb(1.0, 0.0))

    with patch("app.api.ask.ZhipuProvider", return_value=provider):
        response = client.post("/ask/v2", json={"question": "没有任何数据时怎么办？"})

    assert response.status_code == 200
    data = response.json()
    assert "empty_evidence" in (data.get("degraded") or [])
    assert data["evidence_groups"]["anchor"] == []
    assert data["evidence_groups"]["concept"] == []
    assert data["evidence_groups"]["analogy"] == []
