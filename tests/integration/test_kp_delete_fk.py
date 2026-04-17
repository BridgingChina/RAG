"""Integration test: DELETE /api/v1/knowledge-points/{id} FK guard.

Mirrors the taxonomy-delete guard introduced earlier. Phase 2 switches readers
to chunks.knowledge_point_id, so silently SET NULL-ing chunks when a KP is
deleted would corrupt retrieval results. The endpoint must reject the delete
with 409 whenever any chunk still points at it.
"""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.knowledge_points import delete_knowledge_point
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode, User


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def _make_admin(db_session) -> User:
    user = User(
        username=f"kpdel_admin_{uuid.uuid4().hex[:8]}",
        hashed_password="$2b$12$placeholder",
        display_name="KP Delete Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_delete_kp_blocked_by_chunk_reference(db_session, test_source):
    tn = TaxonomyNode(lvl1="kpdel_l1", lvl2="kpdel_l2", lvl3="kpdel_l3")
    db_session.add(tn)
    db_session.flush()

    kp = KnowledgePoint(name="kpdel_l3", taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    chunk = Chunk(
        source_id=test_source.id, content="kpdel-guard",
        lvl1="kpdel_l1", lvl2="kpdel_l2", lvl3="kpdel_l3",
        knowledge_point_id=kp.id,
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()

    with pytest.raises(HTTPException) as excinfo:
        delete_knowledge_point(
            kp_id=kp.id,
            request=_fake_request(),
            db=db_session,
            current_user=_make_admin(db_session),
        )

    assert excinfo.value.status_code == 409
    assert "chunk" in excinfo.value.detail.lower()
    assert db_session.query(KnowledgePoint).filter(KnowledgePoint.id == kp.id).first() is not None


def test_delete_kp_allowed_when_no_chunks(db_session):
    tn = TaxonomyNode(lvl1="kpfree_l1", lvl2="kpfree_l2", lvl3="kpfree_l3")
    db_session.add(tn)
    db_session.flush()

    kp = KnowledgePoint(name="kpfree_l3", taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()
    kp_id = kp.id

    result = delete_knowledge_point(
        kp_id=kp_id,
        request=_fake_request(),
        db=db_session,
        current_user=_make_admin(db_session),
    )
    assert result is None
    assert db_session.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first() is None


def test_delete_kp_returns_404_for_missing_id(db_session):
    with pytest.raises(HTTPException) as excinfo:
        delete_knowledge_point(
            kp_id=uuid.uuid4(),
            request=_fake_request(),
            db=db_session,
            current_user=_make_admin(db_session),
        )
    assert excinfo.value.status_code == 404
