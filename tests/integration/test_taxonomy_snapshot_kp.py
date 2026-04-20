"""Regression tests for ``load_taxonomy_snapshot`` KP-join behaviour.

Phase 3 of the lvl3-KP merge (schema v10, 2026-04-17) purged lvl3 rows
from ``taxonomy_nodes`` — the authoritative source for lvl3 moved to
``knowledge_points``. The ingest tagger builds its prompt whitelist from
this snapshot, so the loader must now join KP rows back in or every new
chunk lands with ``lvl3=NULL`` and a NULL ``knowledge_point_id`` FK.

These tests pin that behaviour so any future schema shuffle that breaks
the KP-join surface here before it reaches production tagging.
"""
from app.core.taxonomy_loader import load_taxonomy_snapshot
from app.models import KnowledgePoint, TaxonomyNode


def test_snapshot_includes_kp_name_as_lvl3(db_session):
    tn = TaxonomyNode(lvl1="snap_l1", lvl2="snap_l2", lvl3=None)
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="snap_kp", lvl1="snap_l1", lvl2="snap_l2")
    db_session.add(kp)
    db_session.flush()

    tree = load_taxonomy_snapshot(db_session)

    assert "snap_kp" in tree["snap_l1"]["snap_l2"]


def test_snapshot_skips_orphan_kp_without_matching_lvl1(db_session):
    kp = KnowledgePoint(name="orphan_kp", lvl1="ghost_l1", lvl2="ghost_l2")
    db_session.add(kp)
    db_session.flush()

    tree = load_taxonomy_snapshot(db_session)

    assert "ghost_l1" not in tree


def test_snapshot_skips_kp_when_lvl2_missing_from_taxonomy(db_session):
    tn = TaxonomyNode(lvl1="half_l1", lvl2="real_l2", lvl3=None)
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="wandering_kp", lvl1="half_l1", lvl2="ghost_l2")
    db_session.add(kp)
    db_session.flush()

    tree = load_taxonomy_snapshot(db_session)

    assert "ghost_l2" not in tree["half_l1"]
    assert tree["half_l1"]["real_l2"] == []


def test_snapshot_deduplicates_when_legacy_lvl3_and_kp_coexist(db_session):
    tn_lvl2 = TaxonomyNode(lvl1="dup_l1", lvl2="dup_l2", lvl3=None)
    tn_legacy_lvl3 = TaxonomyNode(lvl1="dup_l1", lvl2="dup_l2", lvl3="dup_kp")
    db_session.add_all([tn_lvl2, tn_legacy_lvl3])
    db_session.flush()
    kp = KnowledgePoint(name="dup_kp", lvl1="dup_l1", lvl2="dup_l2")
    db_session.add(kp)
    db_session.flush()

    tree = load_taxonomy_snapshot(db_session)

    assert tree["dup_l1"]["dup_l2"].count("dup_kp") == 1
