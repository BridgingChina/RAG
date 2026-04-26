import pytest
from pydantic import ValidationError

from app.api.public.v1.schemas.recognition import (
    RecognitionCandidate,
    RecognitionData,
    RecognitionFallback,
    RecognitionMeta,
)


def test_candidate_serializes_required_fields():
    c = RecognitionCandidate(
        bridge_id="00000000-0000-0000-0000-0000000000ab",
        name="赵州桥",
        bridge_type="石拱桥",
        era="隋唐",
        region="河北",
        thumbnail=None,
        confidence_hints=["LLM exact match"],
    )
    dumped = c.model_dump()
    assert str(dumped["bridge_id"]) == "00000000-0000-0000-0000-0000000000ab"
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


def test_meta_branch_rejects_unknown():
    with pytest.raises(ValidationError):
        RecognitionMeta(model="x", latency_ms=1, branch="bogus")  # type: ignore[arg-type]


def test_candidate_requires_confidence_hints():
    with pytest.raises(ValidationError):
        RecognitionCandidate(
            bridge_id="00000000-0000-0000-0000-000000000001",
            name="x", bridge_type="x", era="x", region="x", thumbnail=None,
        )  # missing confidence_hints


def test_candidate_dump_keys_locked():
    c = RecognitionCandidate(
        bridge_id="00000000-0000-0000-0000-000000000001",
        name="b", bridge_type="c", era="d", region="e",
        thumbnail=None, confidence_hints=[],
    )
    assert set(c.model_dump().keys()) == {
        "bridge_id", "name", "bridge_type", "era", "region",
        "thumbnail", "confidence_hints",
    }
