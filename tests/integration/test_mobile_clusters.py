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

    # Both bridges exist in bounds and land in different grid cells at
    # zoom=4 (grid_size=11.25); they surface as two points, not a cluster.
    total = len(data["clusters"]) + len(data["points"])
    assert total == 2, f"expected both bridges, got {data}"
    # Every point/cluster must have a non-null representative id
    all_reps = [p["id"] for p in data["points"]] + [
        c["representative"]["id"] for c in data["clusters"] if c.get("representative")
    ]
    assert None not in all_reps
    assert set(all_reps) == {str(b1.id), str(b2.id)}


def test_clusters_endpoint_aggregates_multiple_bridges_in_same_cell(client, db_session):
    """cnt>1 branch: multiple bridges in one grid cell yield ONE cluster.

    This is the branch the original test never exercised — ``array_agg[1]``
    is only meaningful when the group has >1 rows. At zoom=4, grid_size
    is 180/16 = 11.25°; both bridges below fall into bucket (2, 9).
    """
    _reset_bridges(db_session)
    b1 = Bridge(
        name="桥A", bridge_type="石拱桥",
        latitude=30.1, longitude=110.1, era="宋", region="华中",
    )
    b2 = Bridge(
        name="桥B", bridge_type="石拱桥",
        latitude=30.5, longitude=110.8, era="宋", region="华中",
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    response = client.get(
        "/api/mobile/v1/bridges/clusters",
        params={
            "bounds_sw_lat": 20,
            "bounds_sw_lng": 100,
            "bounds_ne_lat": 40,
            "bounds_ne_lng": 120,
            "zoom": 4,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # Both bridges in the same cell -> exactly one cluster, count=2
    assert len(data["clusters"]) == 1
    assert data["clusters"][0]["count"] == 2
    # representative.id must be one of the two bridge UUIDs
    rep = data["clusters"][0]["representative"]
    assert rep is not None
    assert rep["id"] in {str(b1.id), str(b2.id)}
    assert rep["name"] in {"桥A", "桥B"}


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
