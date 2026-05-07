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


# i18n Phase B (2026-05-08): hard-coded zh→en map for lvl1 and lvl2 taxonomy
# names. lvl1/lvl2 are a fixed enum (4 + 13 entries today, plus a placeholder
# for the optional "艺术与文化" lvl1 admins sometimes add). This avoids needing
# a separate translation flow for the taxonomy enum — public endpoints fall
# back to ``taxonomy_nodes.name_en`` first, then this map, then the zh
# original. Keep aligned with config/taxonomy.yaml when new枝 are added.
TAXONOMY_NAME_EN: dict[str, str] = {
    # lvl1 (五大主线)
    "形制与技术": "Form & Technique",
    "地域与环境": "Region & Environment",
    "功能与社会": "Function & Society",
    "历史与演变": "History & Evolution",
    "艺术与文化": "Art & Culture",
    # lvl2 — 形制与技术
    "结构体系": "Structural System",
    "构造细部": "Construction Details",
    "材料工艺": "Material & Craft",
    "建造技术": "Construction Techniques",
    # lvl2 — 地域与环境
    "水文地形": "Hydrology & Terrain",
    "气候特征": "Climate Characteristics",
    "地质条件": "Geological Conditions",
    # lvl2 — 功能与社会
    "交通功能": "Transportation Function",
    "公共生活与集会": "Public Life & Assembly",
    "军事防御": "Military Defense",
    "景观价值": "Landscape Value",
    "泄洪功能": "Flood Discharge Function",
    # lvl2 — 历史与演变
    "建造年代": "Construction Era",
    "修缮记录": "Restoration Records",
    "变迁历史": "Historical Changes",
    # lvl2 — 艺术与文化
    "哲学意境": "Philosophical Conception",
    "文辞墨痕": "Literary Inscriptions",
    "民俗文化": "Folk Culture",
}
