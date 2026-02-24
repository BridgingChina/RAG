"""Smoke tests for ingest-tasks API endpoints."""
from app.main import app


def test_ingest_tasks_endpoints_exist():
    """Verify ingest-task routes are registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ingest-tasks/presign" in route_paths
    assert "/api/v1/ingest-tasks" in route_paths
    assert "/api/v1/ingest-tasks/batch-delete" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/confirm" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/retry" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/download-url" in route_paths
