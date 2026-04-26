"""Route registration tests for /v1/recognition. Full e2e tests in Task 8."""
import io

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import Bridge


def test_recognition_route_registered():
    paths = [r.path for r in app.routes]
    assert "/v1/recognition" in paths


def test_recognition_route_is_post_only():
    """GET /v1/recognition should not be exposed."""
    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path:
            methods_by_path.setdefault(path, set()).update(methods)
    methods = methods_by_path.get("/v1/recognition", set())
    assert "POST" in methods
    assert "GET" not in methods


def test_recognition_415_returns_structured_error():
    """Wrong MIME → 415 with code='unsupported_media_type'."""
    client = TestClient(app)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("evil.gif", io.BytesIO(b"GIF89a"), "image/gif")},
    )
    assert resp.status_code == 415
    body = resp.json()
    assert body["error"]["code"] == "unsupported_media_type"
    assert "image/jpeg" in body["error"]["message"]


def test_recognition_413_returns_structured_error(monkeypatch):
    """Oversize → 413 with code='file_too_large'."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "recognition_max_image_bytes", 100)

    client = TestClient(app)
    big = io.BytesIO(b"x" * 200)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("big.jpg", big, "image/jpeg")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"


def test_recognition_503_when_api_key_missing(monkeypatch):
    """Missing API key → 503 with code='vision_disabled' (NOT 'SERVICE_UNAVAILABLE')."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    client = TestClient(app)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fake"), "image/jpeg")},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "vision_disabled"


@pytest.fixture
def client(db_session):
    """TestClient that shares the test's transactional db_session.

    Pattern from tests/integration/test_ask_v1_e2e.py — without this, the route's
    Depends(get_db) opens its own connection and can't see fixture-seeded data.
    """
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _stub_openrouter_response(content: str) -> Response:
    """Helper: build a synthetic OpenRouter chat completion response."""
    return Response(200, json={"choices": [{"message": {"content": content}}]})


@respx.mock
def test_recognition_exact_happy_path(client, db_session, monkeypatch):
    """Happy path: LLM returns matched_name, route returns one exact-branch candidate with meta."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=_stub_openrouter_response('{"matched_name":"赵州桥","free_form":null}')
    )

    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fake"), "image/jpeg")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["candidates"][0]["name"] == "赵州桥"
    assert body["data"]["candidates"][0]["bridge_type"] == "石拱桥"
    assert body["data"]["fallback_suggestions"] is None
    # meta envelope must surface model + branch
    assert body["meta"]["model"] == settings.openrouter_vision_model
    assert body["meta"]["branch"] == "exact"
    assert isinstance(body["meta"]["latency_ms"], int)


@respx.mock
def test_recognition_fuzzy_branch(client, db_session, monkeypatch):
    """LLM gives free_form only — fuzzy matches via ILIKE."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    db_session.add(Bridge(name="安济桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=_stub_openrouter_response(
            '{"matched_name":null,"free_form":{"bridge_name":"安济","region":"河北","bridge_type":"石拱桥","hints":["跨度大","唐代"]}}'
        )
    )

    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["candidates"][0]["name"] == "安济桥"
    assert body["data"]["candidates"][0]["confidence_hints"] == ["跨度大", "唐代"]
    assert body["meta"]["branch"] == "fuzzy"


@respx.mock
def test_recognition_fallback_branch_unknown_bridge(client, db_session, monkeypatch):
    """LLM identifies a bridge not in our DB → empty candidates + fallback hints."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=_stub_openrouter_response(
            '{"matched_name":null,"free_form":{"bridge_name":"某不存在的桥","region":"火星","bridge_type":"","hints":[]}}'
        )
    )

    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["candidates"] == []
    assert body["data"]["fallback_suggestions"]["search_hint"] == "某不存在的桥"
    assert body["data"]["fallback_suggestions"]["region_hint"] == "火星"
    assert body["meta"]["branch"] == "fallback"


@respx.mock
def test_recognition_fallback_branch_not_a_bridge(client, db_session, monkeypatch):
    """LLM says it's not a bridge → empty candidates + null fallback."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=_stub_openrouter_response('{"matched_name":null,"free_form":null}')
    )

    resp = client.post(
        "/v1/recognition",
        files={"image": ("cat.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["candidates"] == []
    assert body["data"]["fallback_suggestions"] is None
    assert body["meta"]["branch"] == "fallback"


@respx.mock
def test_recognition_503_when_both_models_fail(client, db_session, monkeypatch):
    """Both primary and fallback OpenRouter models 503 → endpoint surfaces vision_unavailable."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()

    respx.post(f"{settings.openrouter_base_url}/chat/completions").respond(503, json={"error": "down"})

    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "vision_unavailable"


@respx.mock
def test_recognition_malformed_llm_json_degrades_to_fallback(client, db_session, monkeypatch):
    """LLM returns garbage 200 — parse_vision_json degrades to fallback branch, not 5xx."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=_stub_openrouter_response("not json at all")
    )

    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )

    # The LLM body itself was 200 with garbage. parse_vision_json yields an empty
    # VisionResult, route_candidates returns ([], None, "fallback"). User sees an
    # empty result rather than an upstream 5xx.
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["candidates"] == []
    assert body["data"]["fallback_suggestions"] is None
    assert body["meta"]["branch"] == "fallback"
