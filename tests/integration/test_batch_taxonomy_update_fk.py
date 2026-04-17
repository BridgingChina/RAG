"""Integration test for POST /api/v1/taxonomy/batch-update (Phase 1 double-write).

Validates that the batch update endpoint not only rewrites lvl1/lvl2/lvl3 on
the target chunks but also resolves and writes the matching
KnowledgePoint id to the new chunks.knowledge_point_id FK.
"""
import uuid
from unittest.mock import MagicMock

from app.api.v1.schemas.taxonomy import TaxonomyBatchUpdate
from app.api.v1.taxonomy import batch_update_chunks
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode, User


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def _make_admin(db_session) -> User:
    user = User(
        username=f"batch_admin_{uuid.uuid4().hex[:8]}",
        hashed_password="$2b$12$placeholder",
        display_name="Batch Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_batch_update_populates_knowledge_point_id(db_session, test_source):
    tn = TaxonomyNode(lvl1="bu_l1", lvl2="bu_l2", lvl3="bu_l3")
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="bu_l3", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    chunks = [
        Chunk(
            source_id=test_source.id, content=f"bu-{i}",
            embedding=[0.0] * EMBEDDING_DIM,
        )
        for i in range(2)
    ]
    db_session.add_all(chunks)
    db_session.flush()
    chunk_ids = [c.id for c in chunks]

    body = TaxonomyBatchUpdate(
        chunk_ids=chunk_ids, lvl1="bu_l1", lvl2="bu_l2", lvl3="bu_l3",
    )
    result = batch_update_chunks(
        body=body,
        request=_fake_request(),
        db=db_session,
        current_user=_make_admin(db_session),
    )
    assert result.updated_count == 2

    db_session.expire_all()
    reloaded = db_session.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
    for c in reloaded:
        assert c.lvl3 == "bu_l3"
        assert c.knowledge_point_id == kp.id


def test_batch_update_sets_knowledge_point_id_to_null_when_path_has_no_kp(
    db_session, test_source,
):
    """lvl3 node exists in taxonomy but no matching KP → FK stays NULL."""
    tn = TaxonomyNode(lvl1="bunul_l1", lvl2="bunul_l2", lvl3="bunul_l3")
    db_session.add(tn)
    db_session.flush()

    chunk = Chunk(
        source_id=test_source.id, content="bunul-0",
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()

    body = TaxonomyBatchUpdate(
        chunk_ids=[chunk.id], lvl1="bunul_l1", lvl2="bunul_l2", lvl3="bunul_l3",
    )
    batch_update_chunks(
        body=body,
        request=_fake_request(),
        db=db_session,
        current_user=_make_admin(db_session),
    )

    db_session.expire_all()
    reloaded = db_session.query(Chunk).filter(Chunk.id == chunk.id).one()
    assert reloaded.lvl3 == "bunul_l3"
    assert reloaded.knowledge_point_id is None
