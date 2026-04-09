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
    """Each node in the knowledge tree must have a distinct ID.

    Regression test for issue #146: lvl2 category and its first lvl3
    child shared the same ID because NULLs sorted last in ORDER BY.
    """
    # Create taxonomy: lvl1 → lvl2 → lvl3
    lvl1_node = TaxonomyNode(lvl1="功能与社会")
    lvl2_node = TaxonomyNode(lvl1="功能与社会", lvl2="交通功能")
    lvl3_node = TaxonomyNode(lvl1="功能与社会", lvl2="交通功能", lvl3="人行通道")
    db_session.add_all([lvl1_node, lvl2_node, lvl3_node])
    db_session.flush()

    # Sanity: the three nodes have different UUIDs
    assert len({lvl1_node.id, lvl2_node.id, lvl3_node.id}) == 3

    # Call the endpoint logic directly
    from unittest.mock import MagicMock

    mock_deps = MagicMock()
    result = get_knowledge_tree(depth=None, db=db_session)

    lines = result.data["lines"]
    assert len(lines) == 1

    all_ids = []
    for line in lines:
        _collect_ids(line, all_ids)

    # The bug caused duplicates; after fix, all IDs must be unique
    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicate IDs found in tree: {all_ids}"
    )

    # Verify correct ID assignment
    line_node = lines[0]
    assert line_node["id"] == str(lvl1_node.id)
    assert line_node["name"] == "功能与社会"

    category_node = line_node["children"][0]
    assert category_node["id"] == str(lvl2_node.id)
    assert category_node["name"] == "交通功能"

    topic_node = category_node["children"][0]
    assert topic_node["id"] == str(lvl3_node.id)
    assert topic_node["name"] == "人行通道"


def test_tree_includes_knowledge_points_with_own_ids(db_session):
    """Knowledge points under lvl3 nodes must have their own IDs."""
    lvl1_node = TaxonomyNode(lvl1="形制与技术")
    lvl3_node = TaxonomyNode(lvl1="形制与技术", lvl2="结构体系", lvl3="拱桥结构")
    db_session.add_all([lvl1_node, lvl3_node])
    db_session.flush()

    kp = KnowledgePoint(
        name="石拱桥力学原理",
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
