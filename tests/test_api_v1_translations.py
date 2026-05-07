"""Admin translations API smoke tests (i18n Phase 3 + v15 inline审校).

Focuses on route registration + input validation — end-to-end审校 behaviour is
covered by the service-layer tests in ``test_translation_service.py``.

The functional ``/by-row`` test exercises the legacy-upsert path with a real
DB session, since that logic only manifests when actual business rows + a
unique-constraint-protected review table are present.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_current_user
from app.core.database import get_db
from app.main import app
from app.models import Bridge, KnowledgePointKeyPoint, TranslationReview
from app.models.current_user import CurrentUser


def test_admin_translation_routes_registered():
    """All six endpoints must be registered under /api/v1/translations."""
    paths = {r.path for r in app.routes}
    expected = {
        "/api/v1/translations",
        "/api/v1/translations/by-row",
        "/api/v1/translations/generate",
        "/api/v1/translations/batch-generate",
        "/api/v1/translations/{review_id}/review",
        "/api/v1/translations/coverage",
    }
    assert expected.issubset(paths), f"Missing routes: {expected - paths}"


def test_admin_translation_endpoints_require_auth():
    """Unauthenticated requests must be rejected with 401 (not 200)."""
    client = TestClient(app)
    assert client.get("/api/v1/translations").status_code in {401, 403}
    assert client.get("/api/v1/translations/coverage").status_code in {401, 403}
    assert client.get(
        "/api/v1/translations/by-row?table=bridges&row_id=00000000-0000-0000-0000-000000000000"
    ).status_code in {401, 403}
    assert client.post(
        "/api/v1/translations/generate",
        json={
            "table_name": "bridges",
            "row_id": "00000000-0000-0000-0000-000000000000",
            "field_name": "name_en",
        },
    ).status_code in {401, 403}


# --- /by-row functional test ---------------------------------------------


@pytest.fixture
def admin_client(db_session):
    """TestClient with auth bypassed and DB pinned to the rollbackable session."""
    def _override_db():
        yield db_session

    def _override_user():
        return CurrentUser(id="admin-test", email="admin@test", role="admin")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_by_row_returns_existing_and_upserts_legacy(admin_client, db_session):
    """A bridge with description_en already populated but no review row
    should yield a synthetic ``human_reviewed`` from /by-row, while an
    explicit pending_ai review for name_en should pass through unchanged.
    Re-fetching is idempotent (no duplicate rows)."""
    # Bridge model uses ``summary`` for the zh body, but TRANSLATABLE_FIELDS
    # registers (description, description_en); the upsert tolerates a missing
    # source field by storing an empty source_text. Test the en path.
    bridge = Bridge(
        name="测试桥",
        summary="位于河北省的测试桥梁。",
        description_en="A test bridge in Hebei.",  # legacy populated
    )
    db_session.add(bridge)
    db_session.flush()

    # An explicit review row already exists for name_en
    db_session.add(TranslationReview(
        table_name="bridges",
        row_id=bridge.id,
        field_name="name_en",
        source_text="测试桥",
        ai_translation="Test Bridge",
        status="ai_generated",
    ))
    db_session.flush()

    resp = admin_client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={bridge.id}",
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    by_field = {it["field_name"]: it for it in items}
    assert "name_en" in by_field
    assert by_field["name_en"]["status"] == "ai_generated"
    assert "description_en" in by_field
    legacy = by_field["description_en"]
    assert legacy["status"] == "human_reviewed"
    assert legacy["reviewed_translation"] == "A test bridge in Hebei."
    assert legacy["reviewed_by"] == "legacy"

    # Idempotency: a second call must not produce a duplicate description_en
    resp2 = admin_client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={bridge.id}",
    )
    items2 = resp2.json()
    description_count = sum(1 for it in items2 if it["field_name"] == "description_en")
    assert description_count == 1, "Legacy upsert must be idempotent under unique constraint"


def test_by_row_rejects_unknown_table(admin_client):
    resp = admin_client.get(
        "/api/v1/translations/by-row?table=nonsense&row_id=00000000-0000-0000-0000-000000000000",
    )
    assert resp.status_code == 400
    assert "Unknown" in resp.json()["detail"]


def test_by_row_rejects_invalid_row_id(admin_client):
    resp = admin_client.get(
        "/api/v1/translations/by-row?table=bridges&row_id=not-a-uuid",
    )
    assert resp.status_code == 400


def test_by_row_supports_multi_row_id(admin_client, db_session):
    b1 = Bridge(name="桥A", summary="x")
    b2 = Bridge(name="桥B", summary="y")
    db_session.add_all([b1, b2])
    db_session.flush()

    for b in (b1, b2):
        db_session.add(TranslationReview(
            table_name="bridges",
            row_id=b.id,
            field_name="name_en",
            source_text=b.name,
            status="pending_ai",
        ))
    db_session.flush()

    resp = admin_client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={b1.id},{b2.id}",
    )
    assert resp.status_code == 200
    items = resp.json()
    name_en_rows = [it for it in items if it["field_name"] == "name_en"]
    assert {it["row_id"] for it in name_en_rows} == {str(b1.id), str(b2.id)}


def test_by_row_works_for_knowledge_point_key_points(admin_client, db_session):
    """v15: knowledge_point_key_points is a translatable target."""
    from app.models import KnowledgePoint, TaxonomyNode
    # Build a minimal taxonomy + KP + key_point chain
    tx = TaxonomyNode(lvl1="形制与技术", lvl2="结构体系", lvl3="拱圈")
    db_session.add(tx)
    db_session.flush()
    kp = KnowledgePoint(name="拱圈", taxonomy_node_id=tx.id)
    db_session.add(kp)
    db_session.flush()
    key_point = KnowledgePointKeyPoint(
        knowledge_point_id=kp.id,
        summary="圆弧拱受力均匀",
        explanation="由于圆弧的几何…",
        order_index=0,
        summary_en="Circular arches distribute load evenly.",  # legacy populated
    )
    db_session.add(key_point)
    db_session.flush()

    resp = admin_client.get(
        f"/api/v1/translations/by-row?table=knowledge_point_key_points&row_id={key_point.id}",
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    by_field = {it["field_name"]: it for it in items}
    # summary_en upserted as human_reviewed (legacy)
    assert by_field["summary_en"]["status"] == "human_reviewed"
    assert by_field["summary_en"]["reviewed_translation"] == "Circular arches distribute load evenly."
    # explanation_en is empty → no synthetic record (truly pending)
    assert "explanation_en" not in by_field
