"""Tests for mobile API error response format."""
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# -- helper: add temporary test routes that raise known HTTPExceptions --------
_PREFIX = "/api/mobile/v1/test-error-handler"

@app.get(f"{_PREFIX}/404")
async def _test_mobile_404():
    raise HTTPException(status_code=404, detail="Bridge not found")

@app.get(f"{_PREFIX}/400")
async def _test_mobile_400():
    raise HTTPException(status_code=400, detail="Invalid coordinates")

@app.get("/api/v1/test-error-handler/401")
async def _test_admin_401():
    raise HTTPException(status_code=401, detail="Not authenticated")


# -- tests --------------------------------------------------------------------

def test_mobile_404_returns_spec_error_format():
    resp = client.get(f"{_PREFIX}/404")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Bridge not found"
    assert "detail" not in body


def test_mobile_400_returns_spec_error_format():
    resp = client.get(f"{_PREFIX}/400")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "BAD_REQUEST"
    assert body["error"]["message"] == "Invalid coordinates"


def test_admin_api_preserves_default_error_format():
    resp = client.get("/api/v1/test-error-handler/401")
    assert resp.status_code == 401
    body = resp.json()
    assert "detail" in body
    assert body["detail"] == "Not authenticated"
    assert "error" not in body


def test_mobile_unmapped_status_uses_http_code():
    """Status codes not in the mapping get a fallback code like HTTP_418."""
    @app.get(f"{_PREFIX}/418")
    async def _test_mobile_418():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    resp = client.get(f"{_PREFIX}/418")
    assert resp.status_code == 418
    body = resp.json()
    assert body["error"]["code"] == "HTTP_418"


def test_mobile_all_mapped_codes():
    """Verify all mapped status codes produce correct error codes."""
    expected = {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    for status, code in expected.items():
        route = f"{_PREFIX}/mapped-{status}"
        app.add_api_route(
            route,
            lambda s=status: (_ for _ in ()).throw(HTTPException(status_code=s, detail="test")),
            methods=["GET"],
        )
        resp = client.get(route)
        assert resp.status_code == status, f"Expected {status}"
        assert resp.json()["error"]["code"] == code, f"Expected code {code} for {status}"
