"""Constants loading from YAML configuration files."""
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

# Embedding dimension (must match ZhipuProvider.embed() dimensions parameter)
EMBEDDING_DIM = 1024


@lru_cache
def load_taxonomy() -> dict[str, dict[str, list[str]]]:
    """Load taxonomy from YAML config.

    Returns:
        Nested dict: {lvl1: {lvl2: [lvl3, ...]}}
    """
    with open(CONFIG_DIR / "taxonomy.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["taxonomy"]


@lru_cache
def load_facets() -> dict[str, list[str]]:
    """Load facet enums from YAML config.

    Returns:
        Dict with keys: bridge_types, materials, eras, regions, functions
    """
    with open(CONFIG_DIR / "facets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy_lvl1() -> list[str]:
    """Get list of lvl1 taxonomy categories."""
    return list(load_taxonomy().keys())


def get_taxonomy_lvl2(lvl1: str) -> list[str]:
    """Get list of lvl2 categories for a given lvl1."""
    taxonomy = load_taxonomy()
    if lvl1 in taxonomy:
        return list(taxonomy[lvl1].keys())
    return []


def get_taxonomy_lvl3(lvl1: str, lvl2: str) -> list[str]:
    """Get list of lvl3 items for given lvl1 and lvl2."""
    taxonomy = load_taxonomy()
    if lvl1 in taxonomy and lvl2 in taxonomy[lvl1]:
        return taxonomy[lvl1][lvl2]
    return []
