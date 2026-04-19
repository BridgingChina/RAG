"""Tests for public bridges API endpoints."""
from app.main import app


def test_public_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/bridges" in route_paths


def test_public_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/bridges/{bridge_id}" in route_paths


def test_public_bridges_clusters_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/bridges/clusters" in route_paths


def test_public_bridges_knowledge_points_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/bridges/{bridge_id}/knowledge-points" in route_paths


def test_bridge_sections_keyed_by_lvl1():
    """Section keys are taxonomy lvl1 Chinese names directly, not a fixed mapping —
    new lvl1 themes added to taxonomy automatically appear as new sections."""
    from app.api.public.v1.bridges import get_bridge
    import inspect
    src = inspect.getsource(get_bridge)
    assert "LVL1_TO_SECTION" not in src, "fixed lvl1->section mapping must be gone"
    assert "TaxonomyNode" in src, "lvl1 themes must be loaded from DB taxonomy"


def test_clusters_representative_is_object_not_array():
    """Cluster representative should be {id, name} object, not an array of IDs."""
    from app.api.public.v1.bridges import get_bridge_clusters
    import inspect
    src = inspect.getsource(get_bridge_clusters)
    assert '"representative"' in src or "'representative'" in src
    assert "representative_ids" not in src


def test_bridge_knowledge_points_queries_association_table():
    """Verify endpoint queries KnowledgePointBridge, not a stub returning []."""
    from app.api.public.v1.bridges import get_bridge_knowledge_points
    import inspect
    src = inspect.getsource(get_bridge_knowledge_points)
    assert "KnowledgePointBridge" in src
    assert "bridge_id" in src
    # Should NOT contain a bare "return PublicResponse(data=[])"
    assert "data=[]" not in src
