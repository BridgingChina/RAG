from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Term:
    zh: str
    en: str
    context: str
    notes: str = ""


# worktree 内读副本：<repo_root>/data/i18n/glossary.yaml
# 顶层 scripts/sync-glossary.sh 把顶层 docs/glossary.zh-en.yaml sync 到这里
# repo_root 指 worktree 或 main checkout 根（pyproject.toml 所在目录）
# app/core/glossary.py → app/core → app → RAG (worktree 根)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GLOSSARY_PATH = _REPO_ROOT / "data" / "i18n" / "glossary.yaml"


@lru_cache(maxsize=1)
def _load_raw() -> list[Term]:
    with GLOSSARY_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [Term(**t) for t in data["terms"]]


def load_glossary(context: str | None = None) -> list[Term]:
    terms = _load_raw()
    if context:
        return [t for t in terms if t.context == context]
    return terms


# Alias for consumers (translation_service.py) written before Phase 1 landed
# the canonical `Term` name. Both refer to the same frozen dataclass.
GlossaryTerm = Term


def pick_relevant_terms(text: str, limit: int = 10) -> list[Term]:
    """Pick glossary terms whose zh or en token appears in `text`.

    Simple substring match — good enough for LLM few-shot seeding. Returns at
    most `limit` hits in glossary order; falls back to first `limit` terms
    when `text` has no matches so the prompt always carries some context.
    """
    terms = _load_raw()
    hits = [t for t in terms if t.zh in text or (t.en and t.en.lower() in text.lower())]
    if hits:
        return hits[:limit]
    return terms[:limit]


def format_glossary_for_prompt(terms: list[Term]) -> str:
    """Render terms as a compact LLM-facing reference block.

    Format: `- 中文 → English  (context)  [notes]` per line. Empty input
    returns empty string so callers can unconditionally concatenate.
    """
    if not terms:
        return ""
    lines = []
    for t in terms:
        line = f"- {t.zh} → {t.en}"
        if t.context:
            line += f"  ({t.context})"
        if t.notes:
            line += f"  [{t.notes}]"
        lines.append(line)
    return "\n".join(lines)
