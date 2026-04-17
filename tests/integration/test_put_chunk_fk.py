"""Integration test: PUT /api/v1/chunks/{id} double-writes knowledge_point_id.

Closes the gap surfaced by the Phase 1 final review — the ChunkEditor's
single-save path goes through this endpoint, and Phase 1 requires that
any write of lvl1/lvl2/lvl3 also refreshes the new FK column.
"""
import uuid
from unittest.mock import MagicMock

from app.api.v1.chunks import update_chunk
from app.api.v1.schemas.chunk import ChunkUpdate
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode, User


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def _make_admin(db_session) -> User:
    user = User(
        username=f"put_admin_{uuid.uuid4().hex[:8]}",
        hashed_password="$2b$12$placeholder",
        display_name="Put Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _seed_taxonomy_kp(db_session, lvl1: str, lvl2: str, lvl3: str) -> tuple[TaxonomyNode, KnowledgePoint]:
    tn = TaxonomyNode(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3)
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name=lvl3, lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()
    return tn, kp


def test_put_chunk_sets_knowledge_point_id_when_lvl3_changes(db_session, test_source):
    _, kp_a = _seed_taxonomy_kp(db_session, "put_l1", "put_l2", "put_l3a")
    _, kp_b = _seed_taxonomy_kp(db_session, "put_l1", "put_l2", "put_l3b")

    chunk = Chunk(
        source_id=test_source.id, content="put-chunk",
        lvl1="put_l1", lvl2="put_l2", lvl3="put_l3a",
        knowledge_point_id=kp_a.id,
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()
    chunk_id = chunk.id

    update_chunk(
        chunk_id=chunk_id,
        body=ChunkUpdate(lvl3="put_l3b"),
        request=_fake_request(),
        db=db_session,
        current_user=_make_admin(db_session),
    )

    db_session.expire_all()
    reloaded = db_session.query(Chunk).filter(Chunk.id == chunk_id).one()
    assert reloaded.lvl3 == "put_l3b"
    assert reloaded.knowledge_point_id == kp_b.id, \
        "FK should follow the new lvl3 label"


def test_put_chunk_preserves_knowledge_point_id_when_only_non_lvl_fields_change(
    db_session, test_source,
):
    _, kp = _seed_taxonomy_kp(db_session, "putp_l1", "putp_l2", "putp_l3")
    chunk = Chunk(
        source_id=test_source.id, content="putp-chunk",
        lvl1="putp_l1", lvl2="putp_l2", lvl3="putp_l3",
        knowledge_point_id=kp.id,
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()
    chunk_id = chunk.id

    update_chunk(
        chunk_id=chunk_id,
        body=ChunkUpdate(section_title="Renamed Section"),
        request=_fake_request(),
        db=db_session,
        current_user=_make_admin(db_session),
    )

    db_session.expire_all()
    reloaded = db_session.query(Chunk).filter(Chunk.id == chunk_id).one()
    assert reloaded.section_title == "Renamed Section"
    assert reloaded.knowledge_point_id == kp.id, \
        "FK must not be touched when no lvl field is in update_data"
