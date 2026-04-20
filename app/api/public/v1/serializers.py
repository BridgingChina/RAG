"""Locale-aware serializers for C-end public-API responses.

These helpers centralise the "if locale == en-US and *_en IS NOT NULL, use it;
else fall back to the zh-CN source column and flag
``response.meta.translation_fallback=true``" pattern so each endpoint doesn't
reimplement the logic.

The admin ``/api/v1/*`` surface does **not** use these — admin is zh-CN only
per design §1.2.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.bridge import Bridge
from app.models.flashcard import Flashcard
from app.models.knowledge_point import KnowledgePoint
from app.models.taxonomy import TaxonomyNode


def _pick(en_value: Any, zh_value: Any, use_en: bool) -> tuple[Any, bool]:
    """Return (chosen_value, fell_back_to_zh)."""
    if use_en and en_value:
        return en_value, False
    return zh_value, use_en  # fell_back_to_zh is true iff caller asked for en


def localized_meta(fell_back: bool, locale: str) -> dict | None:
    """Build the standard ``_meta`` block for en-US serializers. Returns None
    for zh-CN so the response shape stays unchanged for existing consumers."""
    if locale != "en-US":
        return None
    return {"translation_fallback": fell_back}


def bridge_to_public(bridge: Bridge, locale: str = "zh-CN") -> dict[str, Any]:
    """Serialize a Bridge for the C-end, honouring ``locale``.

    When ``locale == 'en-US'`` and the English column is populated we use it;
    otherwise we fall back to the Chinese source value and flag
    ``_meta.translation_fallback = True`` so the front-end can render a
    "Translating…" hint.
    """
    use_en = locale == "en-US"
    name, fb_name = _pick(bridge.name_en, bridge.name, use_en)
    # Source schema uses bridges.summary as the long-form description field;
    # the _en pair is description_en per the design spec (§3.2 DB schema).
    description, fb_desc = _pick(bridge.description_en, bridge.summary, use_en)
    fell_back = bool(fb_name or fb_desc)
    return {
        "id": str(bridge.id),
        "name": name,
        "description": description,
        "aliases": bridge.aliases,
        "bridge_type": bridge.bridge_type,
        "era": bridge.era,
        "region": bridge.region,
        "latitude": bridge.latitude,
        "longitude": bridge.longitude,
        "_meta": localized_meta(fell_back, locale),
    }


def knowledge_point_to_public(kp: KnowledgePoint, locale: str = "zh-CN") -> dict[str, Any]:
    """Serialize a KnowledgePoint with locale-aware name / summary."""
    use_en = locale == "en-US"
    name, fb_name = _pick(kp.name_en, kp.name, use_en)
    summary, fb_sum = _pick(kp.summary_en, kp.summary, use_en)
    fell_back = bool(fb_name or fb_sum)
    return {
        "id": str(kp.id),
        "name": name,
        "summary": summary,
        "aliases": kp.aliases.split(",") if kp.aliases else [],
        "difficulty": kp.difficulty,
        "_meta": localized_meta(fell_back, locale),
    }


def flashcard_to_public(fc: Flashcard, locale: str = "zh-CN") -> dict[str, Any]:
    """Serialize a Flashcard with locale-aware front/back text."""
    use_en = locale == "en-US"
    front_title, fb_front = _pick(fc.front_title_en, fc.front_title, use_en)
    back_answer, fb_back = _pick(fc.back_answer_en, fc.back_answer, use_en)
    fell_back = bool(fb_front or fb_back)
    return {
        "id": str(fc.id),
        "knowledge_point_id": str(fc.knowledge_point_id),
        "card_type": fc.card_type,
        "front": {"title": front_title, "hint": fc.front_hint},
        "back": {
            "answer": back_answer,
            "key_features": fc.back_key_features or [],
            "example_bridge": None,  # filled by caller
        },
        "_meta": localized_meta(fell_back, locale),
    }


def localize_taxonomy_name(node: TaxonomyNode, locale: str = "zh-CN") -> tuple[str | None, bool]:
    """Return (display_name, fell_back). The canonical zh label is
    the *most specific* non-NULL level (lvl3 > lvl2 > lvl1)."""
    zh_name = node.lvl3 or node.lvl2 or node.lvl1
    use_en = locale == "en-US"
    if use_en and node.name_en:
        return node.name_en, False
    return zh_name, use_en


def taxonomy_node_to_public(
    node: TaxonomyNode, *, name_override: str | None = None, locale: str = "zh-CN",
) -> dict[str, Any]:
    """Serialize a single taxonomy node. Pass ``name_override`` when the caller
    already resolved the display label (e.g. tree traversal that uses the lvl1
    string directly)."""
    use_en = locale == "en-US"
    resolved, fell_back = (name_override, False) if name_override else localize_taxonomy_name(node, locale)
    if name_override and use_en and node.name_en:
        resolved = node.name_en
        fell_back = False
    elif name_override and use_en:
        fell_back = True
    return {
        "id": str(node.id),
        "name": resolved,
        "_meta": localized_meta(fell_back, locale),
    }


__all__ = [
    "bridge_to_public",
    "flashcard_to_public",
    "knowledge_point_to_public",
    "localize_taxonomy_name",
    "localized_meta",
    "taxonomy_node_to_public",
]
