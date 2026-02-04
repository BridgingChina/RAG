import pytest


def test_ask_v2_endpoint_exists():
    from app.main import app

    # Check that the route is registered
    route_paths = [route.path for route in app.routes]
    assert "/ask/v2" in route_paths

    # Check it's a POST route
    for route in app.routes:
        if route.path == "/ask/v2":
            assert "POST" in route.methods or hasattr(route, "methods") and "POST" in route.methods
            break
