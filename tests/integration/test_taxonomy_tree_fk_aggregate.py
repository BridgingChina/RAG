"""Integration test: GET /api/v1/taxonomy/tree lvl3 chunk counts aggregate via FK.

Phase 2 Task 3 — the tree endpoint's chunk_count for lvl3 nodes is now
computed by joining chunks → knowledge_points → taxonomy_nodes through the
knowledge_point_id FK rather than grouping on the lvl3 string column. The
result must equal what the string aggregation would have produced for the
current (consistent) data set.
"""
from app.api.v1.taxonomy import get_taxonomy_tree
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode


def test_tree_lvl3_chunk_count_via_fk(db_session, test_source):
    lvl1 = "t3_l1"
    lvl2 = "t3_l2"
    lvl3a = "t3_l3a"
    lvl3b = "t3_l3b"

    nodes = [
        TaxonomyNode(lvl1=lvl1),
        TaxonomyNode(lvl1=lvl1, lvl2=lvl2),
        TaxonomyNode(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3a),
        TaxonomyNode(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3b),
    ]
    db_session.add_all(nodes)
    db_session.flush()

    tn_l3a = next(n for n in nodes if n.lvl3 == lvl3a)
    tn_l3b = next(n for n in nodes if n.lvl3 == lvl3b)

    kp_a = KnowledgePoint(name=lvl3a, lvl1=tn_l3a.lvl1, lvl2=tn_l3a.lvl2, taxonomy_node_id=tn_l3a.id)
    kp_b = KnowledgePoint(name=lvl3b, lvl1=tn_l3b.lvl1, lvl2=tn_l3b.lvl2, taxonomy_node_id=tn_l3b.id)
    db_session.add_all([kp_a, kp_b])
    db_session.flush()

    # 3 chunks under lvl3a, 1 chunk under lvl3b, 1 chunk with NULL FK
    for content, kp_id in [
        ("t3-a1", kp_a.id), ("t3-a2", kp_a.id), ("t3-a3", kp_a.id),
        ("t3-b1", kp_b.id),
    ]:
        db_session.add(Chunk(
            source_id=test_source.id, content=content,
            lvl1=lvl1, lvl2=lvl2,
            lvl3=lvl3a if kp_id == kp_a.id else lvl3b,
            knowledge_point_id=kp_id,
            embedding=[0.0] * EMBEDDING_DIM,
        ))
    # Decoy: has lvl3 label but NULL FK — must NOT be counted under the new aggregation
    db_session.add(Chunk(
        source_id=test_source.id, content="t3-decoy",
        lvl1=lvl1, lvl2=lvl2, lvl3=lvl3a,
        knowledge_point_id=None,
        embedding=[0.0] * EMBEDDING_DIM,
    ))
    db_session.flush()

    tree = get_taxonomy_tree(db=db_session)

    l1_item = next(item for item in tree.items if item.label == lvl1)
    l2_item = next(c for c in l1_item.children if c.label == lvl2)
    counts = {c.label: c.chunk_count for c in l2_item.children}

    assert counts[lvl3a] == 3, (
        f"lvl3a should count only chunks with FK → kp_a (not the decoy); got {counts[lvl3a]}"
    )
    assert counts[lvl3b] == 1
