"""Integration test: knowledge tree node IDs must be unique (issue #146).

The bug: PostgreSQL sorts NULLs last by default, so lvl3 nodes were
processed before their parent lvl2 nodes. The lvl2 dict entry was
created with the lvl3 node's ID, causing parent and child to share IDs.
"""
from app.api.mobile.v1.knowledge import get_knowledge_tree
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint


def _collect_ids(node: dict, result: list[str] | None = None) -> list[str]:
    """Recursively collect all 'id' values from a tree node."""
    if result is None:
        result = []
    result.append(node["id"])
    for child in node.get("children", []):
        _collect_ids(child, result)
    return result


def test_tree_nodes_have_unique_ids(db_session):
    """Phase 3: tree is lvl1 → lvl2 → KP (3 layers). Each layer must have a
    distinct ID; the KP's id sits where lvl3 used to. Retains the spirit of
    the original issue #146 regression — the lvl2 category and its first
    child must not collide."""
    lvl1_node = TaxonomyNode(lvl1="功能与社会")
    lvl2_node = TaxonomyNode(lvl1="功能与社会", lvl2="交通功能")
    db_session.add_all([lvl1_node, lvl2_node])
    db_session.flush()

    kp = KnowledgePoint(
        name="人行通道",
        lvl1=lvl2_node.lvl1,
        lvl2=lvl2_node.lvl2,
    )
    db_session.add(kp)
    db_session.flush()

    assert len({lvl1_node.id, lvl2_node.id, kp.id}) == 3

    result = get_knowledge_tree(depth=None, db=db_session)
    lines = result.data["lines"]
    assert len(lines) == 1

    all_ids = []
    for line in lines:
        _collect_ids(line, all_ids)

    assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs: {all_ids}"

    line_node = lines[0]
    assert line_node["id"] == str(lvl1_node.id)
    assert line_node["name"] == "功能与社会"

    category_node = line_node["children"][0]
    assert category_node["id"] == str(lvl2_node.id)
    assert category_node["name"] == "交通功能"

    kp_node = category_node["children"][0]
    assert kp_node["id"] == str(kp.id)
    assert kp_node["name"] == "人行通道"
    assert kp_node["type"] == "knowledge_point"


def test_tree_includes_knowledge_points_with_own_ids(db_session):
    """Knowledge points under lvl3 nodes must have their own IDs."""
    lvl1_node = TaxonomyNode(lvl1="形制与技术")
    lvl2_node = TaxonomyNode(lvl1="形制与技术", lvl2="结构体系")
    lvl3_node = TaxonomyNode(lvl1="形制与技术", lvl2="结构体系", lvl3="拱桥结构")
    db_session.add_all([lvl1_node, lvl2_node, lvl3_node])
    db_session.flush()

    kp = KnowledgePoint(
        name="石拱桥力学原理",
        lvl1=lvl3_node.lvl1,
        lvl2=lvl3_node.lvl2,
        taxonomy_node_id=lvl3_node.id,
    )
    db_session.add(kp)
    db_session.flush()

    result = get_knowledge_tree(depth=None, db=db_session)
    lines = result.data["lines"]

    all_ids = []
    for line in lines:
        _collect_ids(line, all_ids)

    # Must include the KP id and it must be unique
    assert str(kp.id) in all_ids
    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicate IDs found in tree: {all_ids}"
    )
