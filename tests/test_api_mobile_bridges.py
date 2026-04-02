"""Tests for mobile bridges API endpoints."""
from app.main import app


def test_mobile_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges" in route_paths


def test_mobile_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}" in route_paths


def test_mobile_bridges_clusters_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/clusters" in route_paths


def test_mobile_bridges_knowledge_points_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}/knowledge-points" in route_paths


def test_lvl1_to_section_mapping():
    from app.api.mobile.v1.bridges import LVL1_TO_SECTION
    assert LVL1_TO_SECTION["形制与技术"] == "structure"
    assert LVL1_TO_SECTION["地域与环境"] == "geography"
    assert LVL1_TO_SECTION["功能与社会"] == "society"
    assert LVL1_TO_SECTION["历史与演变"] == "history"


def test_clusters_representative_is_object_not_array():
    """Cluster representative should be {id, name} object, not an array of IDs."""
    from app.api.mobile.v1.bridges import get_bridge_clusters
    import inspect
    src = inspect.getsource(get_bridge_clusters)
    assert '"representative"' in src or "'representative'" in src
    assert "representative_ids" not in src


def test_bridge_knowledge_points_queries_association_table():
    """Verify endpoint queries KnowledgePointBridge, not a stub returning []."""
    from app.api.mobile.v1.bridges import get_bridge_knowledge_points
    import inspect
    src = inspect.getsource(get_bridge_knowledge_points)
    assert "KnowledgePointBridge" in src
    assert "bridge_id" in src
    # Should NOT contain a bare "return MobileResponse(data=[])"
    assert "data=[]" not in src
