"""Unit tests for resolve_knowledge_point_id.

Covers the Phase 1 invariant that a (lvl1, lvl2, lvl3) string path resolves
to the id of the same-name KnowledgePoint sitting under that taxonomy node.
"""
from app.models import KnowledgePoint, TaxonomyNode
from app.services.kp_resolver import resolve_knowledge_point_id


def test_returns_kp_id_when_path_matches(db_session):
    tn = TaxonomyNode(lvl1="r_l1", lvl2="r_l2", lvl3="r_l3")
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="r_l3", taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    resolved = resolve_knowledge_point_id(db_session, "r_l1", "r_l2", "r_l3")
    assert resolved == kp.id


def test_returns_none_when_lvl3_missing(db_session):
    assert resolve_knowledge_point_id(db_session, "any", "any", None) is None


def test_returns_none_when_no_taxonomy_match(db_session):
    assert resolve_knowledge_point_id(db_session, "ghost_l1", "ghost_l2", "ghost_l3") is None


def test_returns_none_when_taxonomy_exists_but_no_kp(db_session):
    tn = TaxonomyNode(lvl1="orphan_l1", lvl2="orphan_l2", lvl3="orphan_l3")
    db_session.add(tn)
    db_session.flush()

    assert resolve_knowledge_point_id(db_session, "orphan_l1", "orphan_l2", "orphan_l3") is None


def test_disambiguates_by_full_path(db_session):
    tn_a = TaxonomyNode(lvl1="l1a", lvl2="shared_l2", lvl3="shared_l3")
    tn_b = TaxonomyNode(lvl1="l1b", lvl2="shared_l2", lvl3="shared_l3")
    db_session.add_all([tn_a, tn_b])
    db_session.flush()
    kp_a = KnowledgePoint(name="shared_l3", taxonomy_node_id=tn_a.id)
    kp_b = KnowledgePoint(name="shared_l3", taxonomy_node_id=tn_b.id)
    db_session.add_all([kp_a, kp_b])
    db_session.flush()

    assert resolve_knowledge_point_id(db_session, "l1a", "shared_l2", "shared_l3") == kp_a.id
    assert resolve_knowledge_point_id(db_session, "l1b", "shared_l2", "shared_l3") == kp_b.id
