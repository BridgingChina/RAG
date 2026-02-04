"""Integration tests for V1 retrieval enhancement features.

Tests the full pipeline of tokenizer, facet extraction, hybrid retrieval,
and generation with confidence assessment.
"""

import pytest

from app.providers import ChatMessage, ChatResponse
from app.services.tokenizer import Tokenizer
from app.services.facet_extractor import FacetExtractor, Facet
from app.services.ranker import rrf_merge
from app.services.hybrid_retriever import (
    HybridRetrievalResult,
    RetrievedChunk,
)
from app.services.generator import Generator, GenerationResultV2, Confidence


class MockProvider:
    """Mock LLM provider for testing.

    Returns deterministic responses based on prompt content.
    """

    async def embed(self, texts):
        return [[0.1] * 2048 for _ in texts]

    async def chat(self, messages):
        content = messages[0].content
        if "枚举值约束" in content:
            # Facet extraction response
            return ChatResponse(
                content='{"bridge_type": "石拱桥", "material": null, "era": null, "region": null, "function": null}',
                usage={"total_tokens": 50},
            )
        else:
            # Generation response
            return ChatResponse(
                content='{"summary": "测试要点", "details": "测试详细", "analogy": null, "confidence": {"level": "medium", "reason": "测试"}}',
                usage={"total_tokens": 100},
            )


def test_tokenizer_integration():
    """Verify Tokenizer works end-to-end.

    Tests:
    - Basic tokenization returns expected terms
    - tsquery format is correct
    - tsvector text is correct
    - Single character tokens are filtered
    """
    tokenizer = Tokenizer()

    # Test basic tokenization
    text = "赵州桥是石拱桥"
    tokens = tokenizer.tokenize(text)
    assert "赵州桥" in tokens
    assert "石拱桥" in tokens

    # Test tsquery format
    tsquery = tokenizer.to_tsquery("赵州桥的结构特点")
    assert " & " in tsquery
    assert "赵州桥" in tsquery
    # Single chars should be filtered
    assert "的" not in tsquery or len("的") <= 1

    # Test tsvector text format
    tsvector = tokenizer.to_tsvector_text("赵州桥是石拱桥")
    assert " " in tsvector
    assert "赵州桥" in tsvector
    assert "是" not in tsvector  # single chars filtered


@pytest.mark.asyncio
async def test_facet_extractor_integration():
    """Verify FacetExtractor with mock provider.

    Tests:
    - Extract facets from query
    - Parse JSON response correctly
    - Validate facet values against allowed enum values
    - Return empty Facet on parse error
    """
    provider = MockProvider()
    extractor = FacetExtractor(provider=provider)

    facet = await extractor.extract("石拱桥有什么特点")

    # Should extract bridge_type
    assert facet.bridge_type == "石拱桥"
    # Other fields should be null
    assert facet.material is None
    assert facet.era is None
    assert facet.region is None
    assert facet.function is None

    # Test to_lists normalization
    lists = facet.to_lists()
    assert lists["bridge_type"] == ["石拱桥"]
    assert lists["material"] == []
    assert lists["era"] == []
    assert lists["region"] == []
    assert lists["function"] == []


def test_rrf_merge_integration():
    """Verify RRF merge works correctly.

    Tests:
    - Merge two ranked lists
    - Items in both lists get higher scores
    - Results are sorted by score descending
    - Handles empty lists
    """
    # Test basic merge with overlap
    vec_results = [1, 2, 3, 4, 5]
    fts_results = [3, 1, 6, 7]

    merged = rrf_merge(vec_results, fts_results, k=60)

    # Item 3 appears in both lists (rank 3 and rank 1) -> highest score
    # Item 1 appears in both lists (rank 1 and rank 2) -> second highest
    assert len(merged) == 7  # All unique items

    # Convert to dict for easier assertions
    score_map = dict(merged)

    # Items in both lists should have higher scores
    assert score_map[3] > score_map[2]
    assert score_map[1] > score_map[4]

    # Results should be sorted by score descending
    scores = [s for _, s in merged]
    assert scores == sorted(scores, reverse=True)

    # Test with empty lists
    assert rrf_merge([], [], k=60) == []
    assert rrf_merge([1, 2], [], k=60) == [(1, 1/61), (2, 1/62)]


def test_hybrid_retrieval_result_structure():
    """Verify HybridRetrievalResult.all_chunks() works.

    Tests:
    - all_chunks() returns chunks from all channels
    - Chunks are in correct order (anchor -> concept -> analogy)
    - Empty result returns empty list
    - All chunk metadata is preserved
    """
    # Create test chunks
    anchor = [
        RetrievedChunk(chunk_id=1, content="A1", bridge_id=10, bridge_name="桥A", score=0.9),
        RetrievedChunk(chunk_id=2, content="A2", bridge_id=10, bridge_name="桥A", score=0.8),
    ]
    concept = [
        RetrievedChunk(chunk_id=3, content="C1", bridge_id=None, bridge_name="", score=0.7),
    ]
    analogy = [
        RetrievedChunk(chunk_id=4, content="X1", bridge_id=20, bridge_name="桥B", score=0.6),
        RetrievedChunk(chunk_id=5, content="X2", bridge_id=30, bridge_name="桥C", score=0.5),
    ]

    result = HybridRetrievalResult(
        anchor_chunks=anchor,
        concept_chunks=concept,
        analogy_chunks=analogy,
    )

    all_chunks = result.all_chunks()

    # Check count
    assert len(all_chunks) == 5

    # Check order: anchor -> concept -> analogy
    assert all_chunks[0].chunk_id == 1
    assert all_chunks[1].chunk_id == 2
    assert all_chunks[2].chunk_id == 3
    assert all_chunks[3].chunk_id == 4
    assert all_chunks[4].chunk_id == 5

    # Check metadata preservation
    assert all_chunks[0].bridge_name == "桥A"
    assert all_chunks[2].bridge_id is None
    assert all_chunks[3].bridge_name == "桥B"

    # Test empty result
    empty = HybridRetrievalResult([], [], [])
    assert empty.all_chunks() == []


@pytest.mark.asyncio
async def test_generator_v2_integration():
    """Verify Generator.generate_v2() with confidence.

    Tests:
    - Generate V2 result with confidence assessment
    - Parse JSON response correctly
    - Build citations from all chunks
    - Extract unique sources
    - Handle malformed JSON gracefully
    """
    provider = MockProvider()
    generator = Generator(provider=provider)

    # Create mock evidence with all three channels
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="赵州桥信息", bridge_id=1, bridge_name="赵州桥", score=0.9),
        ],
        concept_chunks=[
            RetrievedChunk(chunk_id=2, content="通用知识", bridge_id=None, bridge_name="", score=0.7),
        ],
        analogy_chunks=[
            RetrievedChunk(chunk_id=3, content="类比桥信息", bridge_id=2, bridge_name="卢沟桥", score=0.6),
        ],
    )

    result = await generator.generate_v2("测试问题", evidence)

    # Check result structure
    assert isinstance(result, GenerationResultV2)
    assert result.summary == "测试要点"
    assert result.details == "测试详细"
    assert result.analogy is None

    # Check confidence
    assert isinstance(result.confidence, Confidence)
    assert result.confidence.level == "medium"
    assert result.confidence.reason == "测试"

    # Check citations - should have one per chunk
    assert len(result.citations) == 3
    citation_ids = [c.chunk_id for c in result.citations]
    assert citation_ids == [1, 2, 3]

    # Check sources - should have unique source titles
    # Note: empty bridge_name becomes "来源2" fallback
    assert len(result.sources) == 3  # "赵州桥", "来源2", "卢沟桥"
    assert "赵州桥" in result.sources
    assert "卢沟桥" in result.sources
    assert "来源2" in result.sources


@pytest.mark.asyncio
async def test_generator_v2_malformed_json():
    """Verify Generator handles malformed JSON gracefully."""
    class BadProvider:
        async def embed(self, texts):
            return [[0.1] * 2048 for _ in texts]

        async def chat(self, messages):
            return ChatResponse(
                content="This is not valid JSON at all",
                usage={"total_tokens": 50},
            )

    provider = BadProvider()
    generator = Generator(provider=provider)

    evidence = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[],
    )

    result = await generator.generate_v2("测试问题", evidence)

    # Should return result with low confidence
    assert result.confidence.level == "low"
    assert "解析" in result.confidence.reason or "格式" in result.confidence.reason
    assert result.citations == []
    assert result.sources == []


@pytest.mark.asyncio
async def test_full_pipeline_integration():
    """Test full V2 pipeline end-to-end.

    This test verifies:
    1. Tokenizer processes query
    2. FacetExtractor extracts facets
    3. RRF merges results
    4. Generator produces V2 result with confidence
    """
    provider = MockProvider()
    tokenizer = Tokenizer()
    extractor = FacetExtractor(provider=provider)
    generator = Generator(provider=provider)

    # Step 1: Tokenize query
    query = "赵州桥是石拱桥吗"
    tokens = tokenizer.tokenize(query)
    assert "赵州桥" in tokens

    # Step 2: Extract facets
    facet = await extractor.extract(query)
    assert facet.bridge_type == "石拱桥"

    # Step 3: RRF merge (simulated retrieval results)
    vec = [1, 2, 3]
    fts = [2, 3, 4]
    merged = rrf_merge(vec, fts, k=60)
    merged_ids = [cid for cid, _ in merged]
    assert len(merged_ids) == 4
    assert 2 in merged_ids  # Item in both lists
    assert 3 in merged_ids  # Item in both lists

    # Step 4: Generate V2 result
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="赵州桥信息", bridge_id=1, bridge_name="赵州桥", score=0.9),
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )
    result = await generator.generate_v2(query, evidence)

    # Verify final result
    assert result.summary == "测试要点"
    assert result.confidence.level == "medium"
    assert len(result.citations) == 1
