"""Integration test for mobile clusters UUID aggregation fix (issue #148 Bug #3).

Before the fix, ``func.min(Bridge.id)`` raised
``psycopg.errors.UndefinedFunction: function min(uuid) does not exist``
because Postgres has no min() aggregate for the UUID type.
This test exercises the real SQL via TestClient + real DB.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from app.core.database import get_db
from app.main import app
from app.models import Bridge


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _reset_bridges(db_session):
    db_session.execute(sql_text("DELETE FROM chunk_bridge_links"))
    db_session.execute(sql_text("DELETE FROM chunks"))
    db_session.execute(sql_text("DELETE FROM bridges"))
    db_session.flush()


def test_clusters_endpoint_returns_200_with_uuid_bridges(client, db_session):
    """Cluster endpoint should execute SQL without min(uuid) error."""
    _reset_bridges(db_session)

    # Two bridges in the same grid cell at low zoom -> should cluster together
    b1 = Bridge(
        name="赵州桥", bridge_type="石拱桥",
        latitude=37.74, longitude=114.77, era="隋唐", region="河北",
    )
    b2 = Bridge(
        name="洛阳桥", bridge_type="石梁桥",
        latitude=24.94, longitude=118.66, era="宋", region="福建",
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    response = client.get(
        "/api/mobile/v1/bridges/clusters",
        params={
            "bounds_sw_lat": 20,
            "bounds_sw_lng": 100,
            "bounds_ne_lat": 50,
            "bounds_ne_lng": 130,
            "zoom": 4,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    data = body["data"]
    assert "clusters" in data
    assert "points" in data

    # Both bridges exist in bounds -- whether they cluster or show as points
    # depends on grid_size at zoom=4, but either way the SQL must execute.
    total = len(data["clusters"]) + len(data["points"])
    assert total >= 1


def test_clusters_endpoint_returns_representative_id(client, db_session):
    """Each cluster/point should have a representative id from array_agg[1]."""
    _reset_bridges(db_session)

    bridge = Bridge(
        name="卢沟桥", bridge_type="石拱桥",
        latitude=39.85, longitude=116.21, era="金", region="北京",
    )
    db_session.add(bridge)
    db_session.flush()

    response = client.get(
        "/api/mobile/v1/bridges/clusters",
        params={
            "bounds_sw_lat": 39,
            "bounds_sw_lng": 116,
            "bounds_ne_lat": 40,
            "bounds_ne_lng": 117,
            "zoom": 10,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]

    # Single bridge at high zoom should become a point (cnt == 1)
    assert len(data["points"]) == 1
    assert data["points"][0]["id"] == str(bridge.id)
    assert data["points"][0]["name"] == "卢沟桥"
