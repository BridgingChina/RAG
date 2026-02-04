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
