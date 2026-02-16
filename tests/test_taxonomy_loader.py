"""Tests for taxonomy loader (DB-backed)."""
from app.core.taxonomy_loader import (
    load_taxonomy_from_db,
    get_taxonomy_lvl1_from_db,
    get_taxonomy_lvl2_from_db,
    get_taxonomy_lvl3_from_db,
    invalidate_taxonomy_cache,
)


def test_taxonomy_loader_imports():
    """Verify the module and its public API exist."""
    assert callable(load_taxonomy_from_db)
    assert callable(get_taxonomy_lvl1_from_db)
    assert callable(get_taxonomy_lvl2_from_db)
    assert callable(get_taxonomy_lvl3_from_db)
    assert callable(invalidate_taxonomy_cache)
