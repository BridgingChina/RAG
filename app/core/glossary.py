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
