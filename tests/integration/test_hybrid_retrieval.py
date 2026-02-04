import pytest

from app.services.facet_extractor import Facet
from app.services.hybrid_retriever import FETCH_MULTIPLIER, RRF_K, HybridRetriever
from app.services.ranker import rrf_merge
from app.services.tokenizer import Tokenizer


def _emb(v0: float, v1: float = 0.0) -> list[float]:
    vec = [0.0] * 2048
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


def test_select_candidate_bridges_matches_facet_and_excludes_target(
    db_session, test_bridges
):
    retriever = HybridRetriever(provider=MockProvider(_emb(1.0)))

    facet = Facet(
        bridge_type="石拱桥",
        material="石",
        era="隋唐",
        region="华北",
    )
    target_id = test_bridges["target"].id

    candidates = retriever._select_candidate_bridges(db_session, target_id, facet)

    assert set(candidates) == {
        test_bridges["candidate1"].id,
        test_bridges["candidate2"].id,
    }
    assert target_id not in candidates


@pytest.mark.asyncio
async def test_retrieve_channel_rrf_fuses_vec_and_fts(db_session, test_bridges, chunk_factory):
    target_id = test_bridges["target"].id

    # Build a small, deterministic dataset where vec and FTS rankings differ.
    chunk_factory(
        content="桥梁 结构 受力 原理",
        bridge_id=target_id,
        embedding=_emb(1.0, 0.0),  # vec rank 1, no FTS match for query "石拱桥"
    )
    fts_top = chunk_factory(
        content="石拱桥 石拱桥 石拱桥 关键特征",
        bridge_id=target_id,
        embedding=_emb(0.9, 0.1),  # vec rank 2, FTS rank 1
    )
    chunk_factory(
        content="桥梁 施工 工艺",
        bridge_id=target_id,
        embedding=_emb(0.0, 1.0),  # vec rank 3, no FTS match
    )
    chunk_factory(
        content="石拱桥 基本概念",
        bridge_id=target_id,
        embedding=_emb(-1.0, 0.0),  # vec rank 4, FTS rank 2
    )

    query = "石拱桥"
    query_embedding = _emb(1.0, 0.0)
    provider = MockProvider(query_embedding)
    retriever = HybridRetriever(provider=provider, tokenizer=Tokenizer())

    limit = 3
    results = await retriever._retrieve_channel(
        db_session,
        query,
        query_embedding,
        bridge_filter=target_id,
        limit=limit,
    )

    fetch_limit = limit * FETCH_MULTIPLIER
    vec_results = retriever._vector_search(
        db_session, query_embedding, target_id, False, fetch_limit
    )
    fts_results = retriever._fts_search(db_session, query, target_id, False, fetch_limit)
    merged = rrf_merge(vec_results, fts_results, k=RRF_K)

    expected_ids = [cid for cid, _ in merged][:limit]
    assert [c.chunk_id for c in results] == expected_ids

    # Sanity: the item that ranks highly in both lists should stay near the top.
    assert fts_top.id in expected_ids


@pytest.mark.asyncio
async def test_apply_diversity_limits_one_per_bridge_for_analogy_channel(
    db_session, test_bridges, test_chunks
):
    candidate_ids = [test_bridges["candidate1"].id, test_bridges["candidate2"].id]
    query_embedding = _emb(1.0, 0.0)
    retriever = HybridRetriever(provider=MockProvider(query_embedding), tokenizer=Tokenizer())

    results = await retriever._retrieve_channel(
        db_session,
        query="石拱桥",
        query_embedding=query_embedding,
        bridge_filter=candidate_ids,
        limit=2,
    )

    assert len(results) == 2
    assert {c.bridge_id for c in results} == set(candidate_ids)


@pytest.mark.asyncio
async def test_retrieve_respects_default_quota_6_2_2(db_session, test_bridges, test_chunks):
    query_embedding = _emb(1.0, 0.0)
    retriever = HybridRetriever(provider=MockProvider(query_embedding), tokenizer=Tokenizer())

    facet = Facet(
        bridge_type="石拱桥",
        material="石",
        era="隋唐",
        region="华北",
    )

    result = await retriever.retrieve(
        db_session,
        query="赵州桥 石拱桥",
        target_bridge_id=test_bridges["target"].id,
        facet=facet,
    )

    assert len(result.anchor_chunks) == 6
    assert len(result.concept_chunks) == 2
    assert len(result.analogy_chunks) == 2

    assert {c.bridge_id for c in result.anchor_chunks} == {test_bridges["target"].id}
    assert {c.bridge_id for c in result.concept_chunks} == {None}
    assert {c.bridge_id for c in result.analogy_chunks} == {
        test_bridges["candidate1"].id,
        test_bridges["candidate2"].id,
    }

