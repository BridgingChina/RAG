from app.models import Bridge
from app.services.vision_recognition import (
    VisionFreeForm,
    VisionResult,
    build_bridge_catalog,
    parse_vision_json,
    route_candidates,
)


def test_catalog_csv_format(db_session):
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.add(Bridge(name="南京长江大桥", region="江苏", era="现代", bridge_type="公铁两用桁架桥"))
    db_session.flush()

    csv = build_bridge_catalog(db_session)

    assert csv.splitlines()[0] == "name,region,era,bridge_type"
    assert "赵州桥,河北,隋唐,石拱桥" in csv
    assert "南京长江大桥,江苏,现代,公铁两用桁架桥" in csv


def test_catalog_handles_null_columns(db_session):
    db_session.add(Bridge(name="X 桥", region=None, era=None, bridge_type=None))
    db_session.flush()
    csv = build_bridge_catalog(db_session)
    assert "X 桥,,," in csv


def test_parse_matched_name():
    r = parse_vision_json('{"matched_name": "赵州桥", "free_form": null}')
    assert r.matched_name == "赵州桥"
    assert r.free_form is None


def test_parse_free_form_only():
    raw = '{"matched_name": null, "free_form": {"bridge_name": "某桥", "region": "X 省", "bridge_type": "拱桥", "hints": ["a", "b"]}}'
    r = parse_vision_json(raw)
    assert r.matched_name is None
    assert r.free_form.bridge_name == "某桥"
    assert r.free_form.hints == ["a", "b"]


def test_parse_all_null_means_not_a_bridge():
    r = parse_vision_json('{"matched_name": null, "free_form": null}')
    assert r.matched_name is None
    assert r.free_form is None


def test_parse_invalid_json_returns_empty():
    """Don't 5xx the user — degrade to fallback branch."""
    r = parse_vision_json("not json at all {")
    assert r.matched_name is None
    assert r.free_form is None


def test_parse_partial_json_with_extra_text():
    """Some models prepend 'Sure, here is...' before JSON. Extract first {...} block."""
    raw = 'Sure! Here is the result:\n{"matched_name": "赵州桥", "free_form": null}\nDone.'
    r = parse_vision_json(raw)
    assert r.matched_name == "赵州桥"


def test_parse_empty_string():
    r = parse_vision_json("")
    assert r.matched_name is None
    assert r.free_form is None


def test_parse_strips_whitespace_in_matched_name():
    r = parse_vision_json('{"matched_name": "  赵州桥  ", "free_form": null}')
    assert r.matched_name == "赵州桥"


def test_parse_empty_matched_name_becomes_none():
    r = parse_vision_json('{"matched_name": "   ", "free_form": null}')
    assert r.matched_name is None


def test_parse_free_form_with_empty_bridge_name_becomes_none():
    """If LLM returns free_form but bridge_name is empty, treat the whole free_form as missing."""
    raw = '{"matched_name": null, "free_form": {"bridge_name": "", "region": "X", "bridge_type": "y", "hints": []}}'
    r = parse_vision_json(raw)
    assert r.free_form is None


def test_parse_free_form_filters_non_string_hints():
    raw = '{"matched_name": null, "free_form": {"bridge_name": "X", "region": "", "bridge_type": "", "hints": ["good", 42, null, "ok"]}}'
    r = parse_vision_json(raw)
    assert r.free_form.hints == ["good", "ok"]


def test_parse_free_form_handles_non_string_region():
    raw = '{"matched_name": null, "free_form": {"bridge_name": "X", "region": true, "bridge_type": "y", "hints": []}}'
    r = parse_vision_json(raw)
    assert r.free_form is not None
    assert r.free_form.region == ""


def test_parse_free_form_handles_non_string_bridge_type():
    raw = '{"matched_name": null, "free_form": {"bridge_name": "X", "region": "Y", "bridge_type": 42, "hints": []}}'
    r = parse_vision_json(raw)
    assert r.free_form is not None
    assert r.free_form.bridge_type == ""


def test_parse_free_form_string_hints_does_not_iterate_chars():
    """If hints comes back as a string instead of list, treat as empty (not char-by-char)."""
    raw = '{"matched_name": null, "free_form": {"bridge_name": "X", "region": "Y", "bridge_type": "z", "hints": "abcd"}}'
    r = parse_vision_json(raw)
    assert r.free_form.hints == []


def test_route_branch_exact(db_session):
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(matched_name="赵州桥", free_form=None)

    candidates, fallback, branch = route_candidates(res, db_session)

    assert branch == "exact"
    assert len(candidates) == 1
    assert candidates[0].name == "赵州桥"
    assert candidates[0].confidence_hints == ["LLM 命中已知桥梁名录"]
    assert fallback is None


def test_route_branch_fuzzy(db_session):
    db_session.add(Bridge(name="安济桥（赵州桥）", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(
        matched_name=None,
        free_form=VisionFreeForm(bridge_name="赵州", region="河北", bridge_type="石拱桥", hints=["跨度大", "唐代"]),
    )

    candidates, fallback, branch = route_candidates(res, db_session)

    assert branch == "fuzzy"
    assert any("安济桥" in c.name for c in candidates)
    assert candidates[0].confidence_hints == ["跨度大", "唐代"]
    assert fallback is None


def test_route_branch_fuzzy_uses_default_hint_when_llm_provides_none(db_session):
    db_session.add(Bridge(name="洛阳桥", region="福建", era="北宋", bridge_type="梁桥"))
    db_session.flush()
    res = VisionResult(
        matched_name=None,
        free_form=VisionFreeForm(bridge_name="洛阳", region="", bridge_type="", hints=[]),
    )
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "fuzzy"
    assert candidates[0].confidence_hints == ["LLM 自由识别匹配"]


def test_route_branch_fallback_unknown_bridge(db_session):
    res = VisionResult(
        matched_name=None,
        free_form=VisionFreeForm(bridge_name="不存在桥", region="火星", bridge_type="", hints=[]),
    )
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "fallback"
    assert candidates == []
    assert fallback.search_hint == "不存在桥"
    assert fallback.region_hint == "火星"


def test_route_branch_fallback_not_a_bridge(db_session):
    res = VisionResult(matched_name=None, free_form=None)
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "fallback"
    assert candidates == []
    assert fallback is None


def test_route_matched_name_no_db_match_falls_through_to_fuzzy(db_session):
    """matched_name set but DB has nothing → degrade to fuzzy on the same name."""
    db_session.add(Bridge(name="安济桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(matched_name="安济", free_form=None)  # close but not exact
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "fuzzy"
    assert any("安济桥" in c.name for c in candidates)


def test_route_exact_via_name_en(db_session):
    db_session.add(Bridge(name="赵州桥", name_en="Zhaozhou Bridge", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(matched_name="Zhaozhou Bridge", free_form=None)
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "exact"
    assert candidates[0].name == "赵州桥"
