from app.api.public.v1.schemas.recognition import (
    RecognitionCandidate,
    RecognitionData,
    RecognitionFallback,
    RecognitionMeta,
)


def test_candidate_serializes_required_fields():
    c = RecognitionCandidate(
        bridge_id="abc-123",
        name="赵州桥",
        bridge_type="石拱桥",
        era="隋唐",
        region="河北",
        thumbnail=None,
        confidence_hints=["LLM exact match"],
    )
    dumped = c.model_dump()
    assert dumped["bridge_id"] == "abc-123"
    assert dumped["thumbnail"] is None


def test_data_allows_empty_candidates_with_fallback():
    d = RecognitionData(
        candidates=[],
        fallback_suggestions=RecognitionFallback(search_hint="某桥", region_hint=None),
    )
    assert d.candidates == []
    assert d.fallback_suggestions.search_hint == "某桥"


def test_meta_branch_enum():
    m = RecognitionMeta(model="qwen/qwen3-vl-235b-a22b-instruct", latency_ms=1234, branch="exact")
    assert m.branch == "exact"
