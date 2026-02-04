"""V2 API schema tests."""


def test_ask_request_has_target_bridge_id():
    from app.api.schemas import AskRequest
    req = AskRequest(question="测试", target_bridge_id=42)
    assert req.target_bridge_id == 42


def test_confidence_schema():
    from app.api.schemas import ConfidenceResponse
    conf = ConfidenceResponse(level="high", reason="证据充分")
    assert conf.level == "high"


def test_ask_response_v2_has_new_fields():
    from app.api.schemas import AskResponseV2, ConfidenceResponse
    resp = AskResponseV2(
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
    from app.api.schemas import ChunkSummary
    chunk = ChunkSummary(
        chunk_id=1,
        bridge_id=42,
        bridge_name="Test Bridge",
        preview="This is a preview of the chunk content",
    )
    assert chunk.preview == "This is a preview of the chunk content"


def test_evidence_groups_response_has_three_channels():
    from app.api.schemas import EvidenceGroupsResponse, ChunkSummary
    groups = EvidenceGroupsResponse(
        anchor=[ChunkSummary(chunk_id=1, bridge_id=1, bridge_name="Bridge A", preview="Anchor text")],
        concept=[ChunkSummary(chunk_id=2, bridge_id=None, bridge_name=None, preview="Concept text")],
        analogy=[ChunkSummary(chunk_id=3, bridge_id=2, bridge_name="Bridge B", preview="Analogy text")],
    )
    assert len(groups.anchor) == 1
    assert len(groups.concept) == 1
    assert len(groups.analogy) == 1
    assert groups.anchor[0].preview == "Anchor text"
    assert groups.concept[0].preview == "Concept text"
    assert groups.analogy[0].preview == "Analogy text"
