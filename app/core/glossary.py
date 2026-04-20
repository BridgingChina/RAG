"""Glossary loader — single-source-of-truth for zh→en term mappings used by
the translation LLM prompts.

The canonical file lives in the umbrella root at ``docs/glossary.zh-en.yaml``.
For tests / containers where the umbrella layout isn't mounted we fall back to
``config/glossary.zh-en.yaml`` inside the RAG subrepo. Callers get back the
parsed term list via :func:`load_glossary`, which is ``@lru_cache``'d.

The glossary is injected as few-shot reference into three prompts:

1. ``translate_query_zh`` — English question → Chinese query (query-translate)
2. ``translate_answer_with_evidence`` — answer + evidence summaries (en QA)
3. ``generate_for_row`` /  ``batch_generate_for_field`` — batch field translation

:func:`pick_relevant_terms` implements a cheap substring scorer so prompt size
stays bounded — every call picks the top-K terms whose zh or en surface forms
appear in the query or evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlossaryTerm:
    """A single zh→en term mapping."""
    zh: str
    en: str
    context: str | None = None
    notes: str | None = None


# Candidate paths to resolve the glossary file, in priority order. The umbrella
# path wins for normal dev; the in-repo fallback supports Docker images that
# ship only the RAG subtree.
_CANDIDATE_PATHS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[3] / "docs" / "glossary.zh-en.yaml",
    Path(__file__).resolve().parents[2] / "config" / "glossary.zh-en.yaml",
)


def _resolve_glossary_path() -> Path | None:
    for candidate in _CANDIDATE_PATHS:
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def load_glossary() -> list[GlossaryTerm]:
    """Return the parsed glossary terms, or an empty list if the file is missing.

    Missing file is logged at WARNING but not raised — translation still works
    without glossary injection, just with lower专业 term fidelity.
    """
    path = _resolve_glossary_path()
    if path is None:
        logger.warning(
            "Glossary YAML not found in any of %s — translation prompts will omit "
            "glossary injection.",
            [str(p) for p in _CANDIDATE_PATHS],
        )
        return []

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("Failed to parse glossary YAML at %s", path)
        return []

    raw_terms = data.get("terms") or []
    terms: list[GlossaryTerm] = []
    for item in raw_terms:
        if not isinstance(item, dict):
            continue
        zh = item.get("zh")
        en = item.get("en")
        if not zh or not en:
            continue
        terms.append(GlossaryTerm(
            zh=str(zh), en=str(en),
            context=item.get("context"),
            notes=item.get("notes"),
        ))
    return terms


def pick_relevant_terms(
    text: str, *, limit: int = 10, terms: Iterable[GlossaryTerm] | None = None,
) -> list[GlossaryTerm]:
    """Return up to ``limit`` glossary terms that appear to be relevant to
    ``text``.

    Relevance heuristic: a term matches when its ``zh`` or ``en`` surface form
    (case-insensitive) occurs as a substring of ``text``. Longer matches win so
    "开腹式拱" outranks "拱". If zero terms match we return the first ``limit``
    terms of the glossary — better to inject something than nothing for
    vocabulary-light questions.
    """
    pool = list(terms) if terms is not None else load_glossary()
    if not pool or not text:
        return pool[:limit]

    haystack = text.lower()
    scored: list[tuple[int, GlossaryTerm]] = []
    for term in pool:
        zh_match = term.zh and term.zh in text
        en_match = term.en and term.en.lower() in haystack
        if not (zh_match or en_match):
            continue
        # Longer surface = more specific; prefer zh length because the input is
        # typically mixed-case English/Chinese and zh terms are punctuation-free.
        score = max(len(term.zh or ""), len(term.en or ""))
        scored.append((score, term))

    if not scored:
        return pool[:limit]

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [term for _, term in scored[:limit]]


def format_glossary_for_prompt(terms: Iterable[GlossaryTerm]) -> str:
    """Render glossary terms as a compact bullet list for LLM prompt injection.

    Format:
        - 券拱 -> voussoir arch (structural; 古代石拱桥的拱石单元...)
        - 桥墩 -> pier
    """
    lines: list[str] = []
    for term in terms:
        suffix = ""
        ctx_parts: list[str] = []
        if term.context:
            ctx_parts.append(term.context)
        if term.notes:
            ctx_parts.append(term.notes)
        if ctx_parts:
            suffix = f" ({'; '.join(ctx_parts)})"
        lines.append(f"- {term.zh} -> {term.en}{suffix}")
    return "\n".join(lines)
