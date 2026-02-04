"""Tests for constants loading module."""
import pytest


def test_load_taxonomy_returns_dict():
    """Test that load_taxonomy returns a nested dict."""
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()

    assert isinstance(taxonomy, dict)
    assert "形制与技术" in taxonomy
    assert "地域与环境" in taxonomy
    assert "功能与社会" in taxonomy
    assert "历史与演变" in taxonomy


def test_load_taxonomy_has_three_levels():
    """Test that taxonomy has lvl1 -> lvl2 -> lvl3 structure."""
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()

    # lvl1 -> lvl2 -> [lvl3]
    assert "结构体系" in taxonomy["形制与技术"]
    assert isinstance(taxonomy["形制与技术"]["结构体系"], list)
    assert "拱桥结构" in taxonomy["形制与技术"]["结构体系"]


def test_load_facets_returns_dict():
    """Test that load_facets returns facet enums."""
    from app.core.constants import load_facets

    facets = load_facets()

    assert isinstance(facets, dict)
    assert "bridge_types" in facets
    assert "materials" in facets
    assert "eras" in facets
    assert "regions" in facets
    assert "functions" in facets


def test_load_facets_bridge_types():
    """Test bridge_types facet values."""
    from app.core.constants import load_facets

    facets = load_facets()

    assert "石拱桥" in facets["bridge_types"]
    assert "木拱桥" in facets["bridge_types"]
    assert "悬索桥" in facets["bridge_types"]


def test_get_taxonomy_lvl1():
    """Test helper to get lvl1 list."""
    from app.core.constants import get_taxonomy_lvl1

    lvl1_list = get_taxonomy_lvl1()

    assert lvl1_list == ["形制与技术", "地域与环境", "功能与社会", "历史与演变"]


def test_get_taxonomy_lvl2():
    """Test helper to get lvl2 list for a given lvl1."""
    from app.core.constants import get_taxonomy_lvl2

    lvl2_list = get_taxonomy_lvl2("形制与技术")

    assert "结构体系" in lvl2_list
    assert "构造细部" in lvl2_list


def test_get_taxonomy_lvl3():
    """Test helper to get lvl3 list for given lvl1 and lvl2."""
    from app.core.constants import get_taxonomy_lvl3

    lvl3_list = get_taxonomy_lvl3("形制与技术", "结构体系")

    assert "拱桥结构" in lvl3_list
    assert "梁桥结构" in lvl3_list
