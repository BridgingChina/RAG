from app.core.glossary import load_glossary, Term


def test_load_glossary_returns_typed_terms():
    terms = load_glossary()
    assert len(terms) >= 50
    assert any(t.zh == "桥梁" and t.en == "bridge" for t in terms)


def test_filter_by_context():
    terms = load_glossary(context="structural")
    assert all(t.context == "structural" for t in terms)
    assert any(t.zh == "拱" for t in terms)


def test_filter_by_unknown_context_returns_empty():
    assert load_glossary(context="nonexistent_ctx") == []


def test_term_is_hashable_frozen_dataclass():
    # 允许放进 set（frozen=True 必须）
    t = Term(zh="x", en="y", context="general")
    {t}  # 不应抛 TypeError
