"""Route registration tests for /v1/recognition. Full e2e tests in Task 8."""
from app.main import app


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
