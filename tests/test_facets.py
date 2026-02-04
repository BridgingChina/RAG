"""Tests for facet constants."""

def test_bridge_types_defined():
    from app.constants.facets import BRIDGE_TYPES
    assert isinstance(BRIDGE_TYPES, list)
    assert "石拱桥" in BRIDGE_TYPES
    assert len(BRIDGE_TYPES) >= 5

def test_materials_defined():
    from app.constants.facets import MATERIALS
    assert isinstance(MATERIALS, list)
    assert "石" in MATERIALS

def test_eras_defined():
    from app.constants.facets import ERAS
    assert isinstance(ERAS, list)
    assert "隋唐" in ERAS

def test_regions_defined():
    from app.constants.facets import REGIONS
    assert isinstance(REGIONS, list)
    assert "华东" in REGIONS

def test_functions_defined():
    from app.constants.facets import FUNCTIONS
    assert isinstance(FUNCTIONS, list)
    assert "交通" in FUNCTIONS
