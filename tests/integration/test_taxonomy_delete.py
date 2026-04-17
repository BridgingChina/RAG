"""Regression tests for DELETE /api/v1/taxonomy/nodes/{id}.

Background: the endpoint only checked `chunks` before issuing the DELETE, but
`knowledge_points.taxonomy_node_id` has a FK to `taxonomy_nodes.id` with
default RESTRICT semantics. Deleting a node that had KPs attached surfaced
as `Internal Server Error` (psycopg.errors.ForeignKeyViolation). This test
pins the business-level 409 behavior.
"""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.taxonomy import delete_taxonomy_node
from app.models import TaxonomyNode, User
from app.models.knowledge_point import KnowledgePoint


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def _make_admin(db_session) -> User:
    user = User(
        username=f"tax_admin_{uuid.uuid4().hex[:8]}",
        hashed_password="$2b$12$placeholder.hash.not.used",
        display_name="Taxonomy Test Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_delete_taxonomy_node_blocked_by_knowledge_point(db_session):
    """Node with an attached KnowledgePoint must refuse delete with 409."""
    node = TaxonomyNode(lvl1="形制与技术", lvl2="斜拉结构")
    db_session.add(node)
    db_session.flush()

    kp = KnowledgePoint(name="斜拉桥主梁", taxonomy_node_id=node.id)
    db_session.add(kp)
    db_session.flush()

    admin = _make_admin(db_session)

    with pytest.raises(HTTPException) as excinfo:
        delete_taxonomy_node(
            node_id=node.id,
            request=_fake_request(),
            db=db_session,
            current_user=admin,
        )

    assert excinfo.value.status_code == 409
    assert "knowledge point" in excinfo.value.detail.lower()

    # Node must remain — the guard fires before any mutation.
    assert (
        db_session.query(TaxonomyNode).filter(TaxonomyNode.id == node.id).first()
        is not None
    )


def test_delete_taxonomy_node_returns_404_for_missing_id(db_session):
    """Sanity check: unknown node_id still behaves correctly after the change."""
    admin = _make_admin(db_session)
    with pytest.raises(HTTPException) as excinfo:
        delete_taxonomy_node(
            node_id=uuid.uuid4(),
            request=_fake_request(),
            db=db_session,
            current_user=admin,
        )
    assert excinfo.value.status_code == 404
