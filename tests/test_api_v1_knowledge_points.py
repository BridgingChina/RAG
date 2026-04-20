"""Tests for admin knowledge points API."""
from app.main import app


def test_knowledge_points_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/v1/knowledge-points" in paths
    assert "/api/v1/knowledge-points/{kp_id}" in paths
    assert "/api/v1/knowledge-points/{kp_id}/generate-key-points" in paths


def test_key_point_crud_routes_registered():
    """Manual CRUD for individual key points is exposed next to the AI
    generate endpoint — admins must be able to edit what AI produces."""
    paths = {(route.path, frozenset(route.methods)) for route in app.routes if hasattr(route, "methods") and route.methods}
    assert ("/api/v1/knowledge-points/{kp_id}/key-points", frozenset({"POST"})) in paths
    assert ("/api/v1/knowledge-points/{kp_id}/key-points/reorder", frozenset({"PUT"})) in paths
    assert ("/api/v1/knowledge-points/{kp_id}/key-points/{kpkp_id}", frozenset({"PUT"})) in paths
    assert ("/api/v1/knowledge-points/{kp_id}/key-points/{kpkp_id}", frozenset({"DELETE"})) in paths


def test_key_point_reorder_registered_before_parametric_id():
    """FastAPI matches routes in registration order. If `/reorder` were
    registered after `/{kpkp_id}`, PUT /reorder would 422 on 'reorder' as UUID."""
    order = [
        route.path
        for route in app.routes
        if hasattr(route, "path")
        and route.path.startswith("/api/v1/knowledge-points/{kp_id}/key-points")
    ]
    reorder_idx = next(
        (i for i, p in enumerate(order) if p.endswith("/reorder")),
        -1,
    )
    parametric_idx = next(
        (i for i, p in enumerate(order) if p.endswith("/{kpkp_id}")),
        -1,
    )
    assert reorder_idx >= 0, "reorder route not registered"
    assert parametric_idx >= 0, "parametric id route not registered"
    assert reorder_idx < parametric_idx, (
        "'/reorder' must be registered before '/{kpkp_id}' — "
        "otherwise FastAPI eats 'reorder' as a UUID path param"
    )
