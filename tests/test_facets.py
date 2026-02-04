"""Tests for facet constants."""
from app.core.constants import load_facets


def test_bridge_types_defined():
    facets = load_facets()
    assert isinstance(facets["bridge_types"], list)
    assert "石拱桥" in facets["bridge_types"]
    assert len(facets["bridge_types"]) >= 5

def test_materials_defined():
    facets = load_facets()
    assert isinstance(facets["materials"], list)
    assert "石" in facets["materials"]

def test_eras_defined():
    facets = load_facets()
    assert isinstance(facets["eras"], list)
    assert "隋唐" in facets["eras"]

def test_regions_defined():
    facets = load_facets()
    assert isinstance(facets["regions"], list)
    assert "华东" in facets["regions"]

def test_functions_defined():
    facets = load_facets()
    assert isinstance(facets["functions"], list)
    assert "交通" in facets["functions"]
