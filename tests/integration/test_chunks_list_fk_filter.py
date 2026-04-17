"""Integration test: GET /api/v1/chunks uses knowledge_point_id FK for lvl3 filter.

Phase 2 Task 2 — the list endpoint's `?lvl3=<label>` query param now filters
by chunks.knowledge_point_id (via a KP id subquery that respects lvl1/lvl2
scoping) instead of the `chunks.lvl3` string. The returned set must match
what the old string filter would have returned.
"""
import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.chunks import list_chunks
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode


def test_list_filters_by_kp_fk_when_lvl3_given(db_session, test_source):
    tn_a = TaxonomyNode(lvl1="cf_l1a", lvl2="shared_l2", lvl3="shared_l3")
    tn_b = TaxonomyNode(lvl1="cf_l1b", lvl2="shared_l2", lvl3="shared_l3")
    db_session.add_all([tn_a, tn_b])
    db_session.flush()
    kp_a = KnowledgePoint(name="shared_l3", lvl1=tn_a.lvl1, lvl2=tn_a.lvl2, taxonomy_node_id=tn_a.id)
    kp_b = KnowledgePoint(name="shared_l3", lvl1=tn_b.lvl1, lvl2=tn_b.lvl2, taxonomy_node_id=tn_b.id)
    db_session.add_all([kp_a, kp_b])
    db_session.flush()

    # 2 chunks under cf_l1a, 1 chunk under cf_l1b, 1 chunk unrelated (lvl3=NULL)
    chunks = [
        Chunk(source_id=test_source.id, content="cf-a1",
              lvl1="cf_l1a", lvl2="shared_l2", lvl3="shared_l3",
              knowledge_point_id=kp_a.id,
              embedding=[0.0] * EMBEDDING_DIM),
        Chunk(source_id=test_source.id, content="cf-a2",
              lvl1="cf_l1a", lvl2="shared_l2", lvl3="shared_l3",
              knowledge_point_id=kp_a.id,
              embedding=[0.0] * EMBEDDING_DIM),
        Chunk(source_id=test_source.id, content="cf-b1",
              lvl1="cf_l1b", lvl2="shared_l2", lvl3="shared_l3",
              knowledge_point_id=kp_b.id,
              embedding=[0.0] * EMBEDDING_DIM),
        Chunk(source_id=test_source.id, content="cf-unrelated",
              lvl1="cf_l1a", lvl2="shared_l2", lvl3=None,
              embedding=[0.0] * EMBEDDING_DIM),
    ]
    db_session.add_all(chunks)
    db_session.flush()

    result = list_chunks(
        page=1, page_size=100, bridge_id=None,
        lvl1="cf_l1a", lvl2="shared_l2", lvl3="shared_l3",
        binding_status=None, source_id=None, q=None,
        db=db_session,
    )

    returned_previews = {item.content_preview for item in result.items}
    assert returned_previews == {"cf-a1", "cf-a2"}, (
        "should return only the 2 chunks under cf_l1a (kp_a), "
        "NOT the one under cf_l1b"
    )


def test_list_empty_when_lvl3_has_no_kp(db_session, test_source):
    tn = TaxonomyNode(lvl1="cfnok_l1", lvl2="cfnok_l2", lvl3="cfnok_l3")
    db_session.add(tn)
    db_session.flush()
    # taxonomy exists but no KP attached. Phase 1 chunks pointing here would
    # have knowledge_point_id=NULL — filter by FK returns empty.
    chunk = Chunk(
        source_id=test_source.id, content="cfnok-1",
        lvl1="cfnok_l1", lvl2="cfnok_l2", lvl3="cfnok_l3",
        knowledge_point_id=None,
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()

    result = list_chunks(
        page=1, page_size=100, bridge_id=None,
        lvl1="cfnok_l1", lvl2="cfnok_l2", lvl3="cfnok_l3",
        binding_status=None, source_id=None, q=None,
        db=db_session,
    )
    assert result.total == 0


def test_list_without_lvl3_filter_unchanged(db_session, test_source):
    """Without lvl3, the endpoint still returns chunks matching lvl1 / lvl2."""
    tn = TaxonomyNode(lvl1="cfny_l1", lvl2="cfny_l2", lvl3="cfny_l3")
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="cfny_l3", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    chunk = Chunk(
        source_id=test_source.id, content="cfny-1",
        lvl1="cfny_l1", lvl2="cfny_l2", lvl3="cfny_l3",
        knowledge_point_id=kp.id,
        embedding=[0.0] * EMBEDDING_DIM,
    )
    db_session.add(chunk)
    db_session.flush()

    result = list_chunks(
        page=1, page_size=100, bridge_id=None,
        lvl1="cfny_l1", lvl2="cfny_l2", lvl3=None,
        binding_status=None, source_id=None, q=None,
        db=db_session,
    )
    assert any(item.content_preview == "cfny-1" for item in result.items)
