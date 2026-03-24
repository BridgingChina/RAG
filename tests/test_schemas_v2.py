"""API v1 schema tests."""
import uuid


def test_ask_request_has_target_bridge_id():
    from app.api.v1.schemas import AskRequest
    bridge_uuid = uuid.uuid4()
    req = AskRequest(question="测试", target_bridge_id=bridge_uuid)
    assert req.target_bridge_id == bridge_uuid


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
    chunk_uuid = uuid.uuid4()
    bridge_uuid = uuid.uuid4()
    chunk = ChunkSummary(
        chunk_id=chunk_uuid,
        bridge_id=bridge_uuid,
        bridge_name="Test Bridge",
        preview="This is a preview of the chunk content",
    )
    assert chunk.preview == "This is a preview of the chunk content"


def test_evidence_groups_response_has_three_channels():
    from app.api.v1.schemas import EvidenceGroupsResponse, ChunkSummary
    id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    bid1, bid2 = uuid.uuid4(), uuid.uuid4()
    groups = EvidenceGroupsResponse(
        anchor=[ChunkSummary(chunk_id=id1, bridge_id=bid1, bridge_name="Bridge A", preview="Anchor text")],
        concept=[ChunkSummary(chunk_id=id2, bridge_id=None, bridge_name=None, preview="Concept text")],
        analogy=[ChunkSummary(chunk_id=id3, bridge_id=bid2, bridge_name="Bridge B", preview="Analogy text")],
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

    id1, id2, id3, id4 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    channel = ChannelDebugResponse(
        channel="anchor",
        filter_desc="bridge_id=<uuid>",
        vec_ids=[id1, id2],
        fts_ids=[id2, id3],
        rrf_scores=[[str(id2), 0.033], [str(id1), 0.016], [str(id3), 0.016]],
        final_ids=[id2, id1],
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
