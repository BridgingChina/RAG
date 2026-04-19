"""DB-backed taxonomy loader with in-process cache.

Replaces the yaml-based @lru_cache approach in constants.py.
The cache is a module-level dict invalidated manually after CRUD operations.
"""
from sqlalchemy.orm import Session

from app.models.taxonomy import TaxonomyNode

# Module-level cache
_cache: dict[str, dict[str, list[str]]] | None = None


def invalidate_taxonomy_cache() -> None:
    """Clear the in-process taxonomy cache. Call after any CRUD op."""
    global _cache
    _cache = None


def load_taxonomy_from_db(db: Session) -> dict[str, dict[str, list[str]]]:
    """Load full taxonomy tree from DB.

    Returns:
        Nested dict: {lvl1: {lvl2: [lvl3, ...]}}
    """
    global _cache
    if _cache is not None:
        return _cache

    nodes = db.query(TaxonomyNode).all()
    tree: dict[str, dict[str, list[str]]] = {}

    for node in nodes:
        if node.lvl1 not in tree:
            tree[node.lvl1] = {}
        if node.lvl2 and node.lvl2 not in tree[node.lvl1]:
            tree[node.lvl1][node.lvl2] = []
        if node.lvl2 and node.lvl3:
            tree[node.lvl1][node.lvl2].append(node.lvl3)

    _cache = tree
    return tree


def get_taxonomy_lvl1_from_db(db: Session) -> list[str]:
    """Get list of lvl1 taxonomy categories from DB."""
    return list(load_taxonomy_from_db(db).keys())


def get_taxonomy_lvl2_from_db(db: Session, lvl1: str) -> list[str]:
    """Get list of lvl2 categories for a given lvl1 from DB."""
    taxonomy = load_taxonomy_from_db(db)
    if lvl1 in taxonomy:
        return list(taxonomy[lvl1].keys())
    return []


def get_taxonomy_lvl3_from_db(db: Session, lvl1: str, lvl2: str) -> list[str]:
    """Get list of lvl3 items for given lvl1 and lvl2 from DB."""
    taxonomy = load_taxonomy_from_db(db)
    if lvl1 in taxonomy and lvl2 in taxonomy[lvl1]:
        return taxonomy[lvl1][lvl2]
    return []


def load_taxonomy_snapshot(db: Session) -> dict[str, dict[str, list[str]]]:
    """Fresh SELECT of the taxonomy tree, bypassing ``_cache``.

    Why a second reader: ingest tasks must see admin taxonomy edits the
    instant they commit, even across worker boundaries where
    ``invalidate_taxonomy_cache`` may not have fired. The cached
    ``load_taxonomy_from_db`` remains appropriate for request handlers
    where a slightly stale read is acceptable.
    """
    nodes = db.query(TaxonomyNode).all()
    tree: dict[str, dict[str, list[str]]] = {}
    for node in nodes:
        if node.lvl1 not in tree:
            tree[node.lvl1] = {}
        if node.lvl2 and node.lvl2 not in tree[node.lvl1]:
            tree[node.lvl1][node.lvl2] = []
        if node.lvl2 and node.lvl3:
            tree[node.lvl1][node.lvl2].append(node.lvl3)
    return tree
