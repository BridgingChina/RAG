"""Unit tests for locale-aware public serializers (i18n Phase 3).

Lightweight — we stub model instances with SimpleNamespace so the tests do not
need a live Postgres. The real serializer only reads attributes off the model,
so this is sufficient for behavioural coverage.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.api.public.v1.serializers import (
    bridge_to_public,
    flashcard_to_public,
    knowledge_point_to_public,
    localized_meta,
    taxonomy_node_to_public,
)


def _make_bridge(**overrides):
    base = {
        "id": uuid4(),
        "name": "赵州桥",
        "name_en": None,
        "summary": "古代石拱桥典范",
        "description_en": None,
        "aliases": None,
        "bridge_type": "石拱桥",
        "era": "隋唐",
        "region": "河北",
        "latitude": 37.7,
        "longitude": 114.8,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_bridge_zh_locale_returns_zh_fields_no_meta():
    bridge = _make_bridge(name_en="Zhaozhou Bridge", description_en="A Sui-era stone arch bridge.")
    out = bridge_to_public(bridge, locale="zh-CN")
    assert out["name"] == "赵州桥"
    assert out["description"] == "古代石拱桥典范"
    # zh-CN does not emit _meta at all
    assert out["_meta"] is None


def test_bridge_en_locale_uses_en_fields_when_present():
    bridge = _make_bridge(
        name_en="Zhaozhou Bridge",
        description_en="A Sui-era stone arch bridge.",
    )
    out = bridge_to_public(bridge, locale="en-US")
    assert out["name"] == "Zhaozhou Bridge"
    assert out["description"] == "A Sui-era stone arch bridge."
    assert out["_meta"] == {"translation_fallback": False}


def test_bridge_en_locale_falls_back_when_en_missing():
    bridge = _make_bridge(name_en=None, description_en=None)
    out = bridge_to_public(bridge, locale="en-US")
    # falls back to Chinese values
    assert out["name"] == "赵州桥"
    assert out["description"] == "古代石拱桥典范"
    # and flags translation_fallback
    assert out["_meta"] == {"translation_fallback": True}


def test_bridge_en_locale_partial_translation_flags_fallback():
    """If only the name is translated but description is not, the response
    still flags ``translation_fallback=true`` so the UI renders the hint."""
    bridge = _make_bridge(name_en="Zhaozhou Bridge", description_en=None)
    out = bridge_to_public(bridge, locale="en-US")
    assert out["name"] == "Zhaozhou Bridge"
    # description falls back to zh
    assert out["description"] == "古代石拱桥典范"
    assert out["_meta"] == {"translation_fallback": True}


def test_knowledge_point_en_locale_prefers_english():
    kp = SimpleNamespace(
        id=uuid4(),
        name="拱桥结构",
        name_en="Arch bridge structure",
        summary="拱桥的核心结构",
        summary_en="Core structure of arch bridges",
        aliases=None,
        difficulty="medium",
    )
    out = knowledge_point_to_public(kp, locale="en-US")
    assert out["name"] == "Arch bridge structure"
    assert out["summary"] == "Core structure of arch bridges"
    assert out["_meta"] == {"translation_fallback": False}


def test_flashcard_en_locale_prefers_english_when_present():
    fc = SimpleNamespace(
        id=uuid4(),
        knowledge_point_id=uuid4(),
        card_type="concept",
        front_title="什么是券拱?",
        front_title_en="What is a voussoir arch?",
        front_hint=None,
        back_answer="由楔形拱石组成的拱结构",
        back_answer_en="Arch structure of wedge-shaped voussoirs",
        back_key_features=None,
    )
    out = flashcard_to_public(fc, locale="en-US")
    assert out["front"]["title"] == "What is a voussoir arch?"
    assert out["back"]["answer"] == "Arch structure of wedge-shaped voussoirs"
    assert out["_meta"] == {"translation_fallback": False}


def test_taxonomy_node_locale_uses_name_en_when_present():
    node = SimpleNamespace(
        id=uuid4(), lvl1="形制与技术", lvl2=None, lvl3=None,
        description=None, name_en="Form and Technology",
    )
    assert taxonomy_node_to_public(node, locale="en-US")["name"] == "Form and Technology"
    assert taxonomy_node_to_public(node, locale="zh-CN")["name"] == "形制与技术"


def test_localized_meta_hides_for_zh_cn():
    """zh-CN responses do not emit _meta to preserve wire format."""
    assert localized_meta(fell_back=True, locale="zh-CN") is None
    assert localized_meta(fell_back=False, locale="zh-CN") is None


def test_localized_meta_emits_for_en_us():
    assert localized_meta(fell_back=False, locale="en-US") == {"translation_fallback": False}
    assert localized_meta(fell_back=True, locale="en-US") == {"translation_fallback": True}
