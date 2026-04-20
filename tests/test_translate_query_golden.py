"""Query-translation golden-set scaffolding (i18n Phase 4.A.2).

Phase 4 backend session only lays the track: 3–5 seed examples + the parametrize
harness. Expanding to 20 entries and running live is deferred to a session that
has ``ZHIPU_API_KEY`` populated. The live integration test is marked with
``pytest.skip`` when the env var is missing so ``pytest tests/``静默 passes.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from app.core.config import settings


# Each entry: (english_query, {keywords_required, forbidden}).
# Keep small and curated — this seeds the table; adding more is welcome.
GOLDEN_SET: list[tuple[str, dict]] = [
    (
        "What is the arch structure of Zhaozhou Bridge?",
        {"keywords_required": ["赵州桥", "拱"], "forbidden": []},
    ),
    (
        "How did Tang dynasty wooden bridges evolve?",
        {"keywords_required": ["唐", "木", "桥"], "forbidden": []},
    ),
    (
        "Tell me about the Dong minority covered bridges.",
        {"keywords_required": ["侗", "桥"], "forbidden": []},
    ),
    (
        "What is a voussoir arch in ancient stone bridges?",
        {"keywords_required": ["券拱", "石"], "forbidden": []},
    ),
    (
        "Explain dougong bracket systems.",
        {"keywords_required": ["斗拱"], "forbidden": []},
    ),
]


@pytest.fixture(scope="module")
def _require_live_llm():
    """Skip the whole module unless the developer opted into live LLM calls."""
    if not os.getenv("RAG_GOLDEN_SET_LIVE"):
        pytest.skip(
            "Golden-set live runs are opt-in — set RAG_GOLDEN_SET_LIVE=1 "
            "and ZHIPU_API_KEY to exercise."
        )
    if not settings.zhipu_api_key or settings.zhipu_api_key == "your_api_key_here":
        pytest.skip("ZHIPU_API_KEY not set; skipping live golden run.")


@pytest.mark.parametrize("en_query, expect", GOLDEN_SET)
def test_golden_set_seed_entries_have_keywords(en_query, expect, _require_live_llm):
    """When the gate is opened, translate each seed query and assert on the
    produced Chinese string.

    This is the scaffolding — full 20-entry coverage and regression are Phase
    4.A.2 follow-up work per ``docs/plans/2026-04-20-i18n-phase4-qa.md``.
    """
    from app.providers import get_provider
    from app.services.translation_service import translate_query_zh

    provider = get_provider()
    translated = asyncio.run(translate_query_zh(
        en_query, zhipu_client=provider,
    ))
    for kw in expect["keywords_required"]:
        assert kw in translated, (
            f"Missing required keyword {kw!r} in translation: {translated!r}"
        )
    for kw in expect["forbidden"]:
        assert kw not in translated, (
            f"Forbidden keyword {kw!r} appeared in translation: {translated!r}"
        )


def test_golden_set_has_minimum_coverage():
    """Sanity check on the seed data — ensures we don't lose examples."""
    assert len(GOLDEN_SET) >= 3, "Golden set should keep at least 3 seed examples"
    assert len(GOLDEN_SET) <= 5, (
        "Expansion to 20 entries is Phase 4.A.2 follow-up — if you're growing "
        "this list beyond 5, also wire up the live runner and remove this cap."
    )
