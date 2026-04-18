"""Tests for public API route skeleton."""
from app.main import app


def _route_paths() -> list[str]:
    return [route.path for route in app.routes]


def test_public_router_registered():
    """Test that public routes are registered under /v1."""
    assert "/v1/config" in _route_paths()


def test_old_mobile_prefix_removed():
    """DoD #4 (issue #158): confirm /api/mobile/v1/* is no longer registered.

    Guards against a half-rollback where a compat shim or stale router
    leaves the old prefix live alongside /v1, which would silently keep
    the deprecated surface reachable.
    """
    assert not any(p.startswith("/api/mobile/") for p in _route_paths())


def test_public_routes_not_mounted_under_admin_prefix():
    """Public-only paths must not collide with admin /api/v1/* surface.

    If public_router is accidentally also mounted at /api/v1, paths like
    /api/v1/bridges/clusters would shadow the admin bridges/{bridge_id}
    parametric route (clusters becomes UUID-parsed → 422). This test
    pins separation between the two API surfaces.
    """
    paths = _route_paths()
    assert "/api/v1/bridges/clusters" not in paths
    assert "/api/v1/qa/ask" not in paths
    assert "/api/v1/knowledge/tree" not in paths
