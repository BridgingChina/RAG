"""API v1 schema tests."""

import uuid

# Deterministic UUID constants for test IDs
UUID_1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
UUID_2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
UUID_3 = uuid.UUID("00000000-0000-4000-8000-000000000003")
UUID_10 = uuid.UUID("00000000-0000-4000-8000-000000000010")
UUID_20 = uuid.UUID("00000000-0000-4000-8000-000000000020")
UUID_30 = uuid.UUID("00000000-0000-4000-8000-000000000030")
UUID_42 = uuid.UUID("00000000-0000-4000-8000-000000000042")


def test_ask_request_has_target_bridge_id():
    from app.api.v1.schemas import AskRequest
    req = AskRequest(question="测试", target_bridge_id=UUID_42)
    assert req.target_bridge_id == UUID_42


def test_confidence_schema():
    from app.api.v1.schemas import ConfidenceResponse
    conf = ConfidenceResponse(level="high", reason="证据充分")
    assert conf.level == "high"


def test_ask_response_has_expected_fields():
    from app.api.v1.schemas import AskResponse, ConfidenceResponse
    resp = AskResponse(
        summary="要点",
        details="详细",
        analogy="类比",
        citations=[],
        sources=[],
        confidence=ConfidenceResponse(level="high", reason="测试"),
        evidence_groups=None,
        degraded=None,
    )
    assert resp.analogy == "类比"
    assert resp.confidence.level == "high"


def test_chunk_summary_uses_preview():
    from app.api.v1.schemas import ChunkSummary
    chunk = ChunkSummary(
        chunk_id=UUID_1,
        bridge_id=UUID_42,
        bridge_name="Test Bridge",
        preview="This is a preview of the chunk content",
    )
    assert chunk.preview == "This is a preview of the chunk content"


def test_evidence_groups_response_has_three_channels():
    from app.api.v1.schemas import EvidenceGroupsResponse, ChunkSummary
    groups = EvidenceGroupsResponse(
        anchor=[ChunkSummary(chunk_id=UUID_1, bridge_id=UUID_1, bridge_name="Bridge A", preview="Anchor text")],
        concept=[ChunkSummary(chunk_id=UUID_2, bridge_id=None, bridge_name=None, preview="Concept text")],
        analogy=[ChunkSummary(chunk_id=UUID_3, bridge_id=UUID_2, bridge_name="Bridge B", preview="Analogy text")],
    )
    assert len(groups.anchor) == 1
    assert len(groups.concept) == 1
    assert len(groups.analogy) == 1
    assert groups.anchor[0].preview == "Anchor text"
    assert groups.concept[0].preview == "Concept text"
    assert groups.analogy[0].preview == "Analogy text"


def test_debug_response_schema():
    """DebugResponse serializes correctly."""
    from app.api.v1.schemas.ask import ChannelDebugResponse, DebugResponse

    channel = ChannelDebugResponse(
        channel="anchor",
        filter_desc="bridge_id=1",
        vec_ids=[UUID_10, UUID_20],
        fts_ids=[UUID_20, UUID_30],
        rrf_scores=[[UUID_20, 0.033], [UUID_10, 0.016], [UUID_30, 0.016]],
        final_ids=[UUID_20, UUID_10],
    )
    debug = DebugResponse(
        facet={"bridge_type": "拱桥"},
        channels=[channel],
        timings={"embed": 0.12, "anchor": 0.08},
    )
    data = debug.model_dump()
    assert data["channels"][0]["channel"] == "anchor"
    assert data["timings"]["embed"] == 0.12


def test_ask_request_accepts_debug_flag():
    """AskRequest accepts optional debug field."""
    from app.api.v1.schemas.ask import AskRequest

    req = AskRequest(question="test", debug=True)
    assert req.debug is True

    req_default = AskRequest(question="test")
    assert req_default.debug is False
