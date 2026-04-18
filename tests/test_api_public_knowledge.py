"""Tests for public knowledge API endpoints."""
from app.main import app


def test_public_knowledge_tree_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/knowledge/tree" in route_paths


def test_public_knowledge_point_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/knowledge/points/{point_id}" in route_paths


def test_public_knowledge_point_bridges_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/knowledge/points/{point_id}/bridges" in route_paths


def test_knowledge_point_flashcards_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/knowledge/points/{point_id}/flashcards" in route_paths


def test_flashcards_resolve_example_bridge_name():
    from app.api.public.v1.knowledge import get_knowledge_point_flashcards
    import inspect
    src = inspect.getsource(get_knowledge_point_flashcards)
    assert "Bridge.name" in src or "bridge_names" in src


def test_knowledge_point_bridges_queries_association_table():
    """Verify endpoint queries KnowledgePointBridge, not a stub returning []."""
    from app.api.public.v1.knowledge import get_knowledge_point_bridges
    import inspect
    src = inspect.getsource(get_knowledge_point_bridges)
    assert "KnowledgePointBridge" in src
    assert "knowledge_point_id" in src
    # Should NOT contain a bare "data=[]"
    assert "data=[]" not in src
