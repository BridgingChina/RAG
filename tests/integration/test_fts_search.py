import pytest

from app.core.constants import EMBEDDING_DIM
from app.services.hybrid_retriever import HybridRetriever
from app.services.tokenizer import Tokenizer


def _emb(v0: float, v1: float = 0.0) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[0] = v0
    vec[1] = v1
    return vec


class MockProvider:
    def __init__(self, embedding: list[float]):
        self._embedding = embedding

    async def embed(self, texts):
        return [self._embedding for _ in texts]

    async def chat(self, messages):
        raise AssertionError("MockProvider.chat should not be called in these tests")


def test_fts_search_matches_tsv_and_orders_by_rank(db_session, test_bridges, chunk_factory):
    target_id = test_bridges["target"].id

    low = chunk_factory(
        content="石拱桥 基本概念",
        bridge_id=target_id,
        embedding=_emb(1.0, 0.0),
    )
    high = chunk_factory(
        content="石拱桥 石拱桥 石拱桥 关键特征",
        bridge_id=target_id,
        embedding=_emb(0.9, 0.1),
    )

    retriever = HybridRetriever(provider=MockProvider(_emb(1.0, 0.0)), tokenizer=Tokenizer())
    ids = retriever._fts_search(
        db_session,
        query="石拱桥",
        bridge_filter=target_id,
        require_no_bridge_id=False,
        limit=10,
    )

    assert ids[0] == high.id
    assert low.id in ids


def test_fts_search_falls_back_on_invalid_tsquery(monkeypatch, db_session, chunk_factory):
    chunk_factory(
        content="石拱桥 基本概念",
        bridge_id=None,
        embedding=_emb(1.0, 0.0),
    )

    def bad_tsquery(self, text: str) -> str:
        return "石拱桥 &"

    monkeypatch.setattr(Tokenizer, "to_tsquery", bad_tsquery)

    retriever = HybridRetriever(provider=MockProvider(_emb(1.0, 0.0)), tokenizer=Tokenizer())
    ids = retriever._fts_search(
        db_session,
        query="石拱桥",
        bridge_filter=None,
        require_no_bridge_id=False,
        limit=10,
    )

    assert ids == []
    assert "fts" in getattr(retriever, "last_degraded", [])
