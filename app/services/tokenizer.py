import re
from pathlib import Path

import jieba

_TSQUERY_OPERATOR_RE = re.compile(r'[&|!<>():]')


def default_user_dict_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "data" / "bridge_terms.txt")


class Tokenizer:
    """Chinese tokenizer using jieba, with optional custom dictionary."""

    def __init__(self, user_dict_path: str | None = None):
        if user_dict_path:
            jieba.load_userdict(user_dict_path)

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text, return list of words."""
        return list(jieba.cut_for_search(text))

    def to_tsquery(self, text: str) -> str:
        """Convert text to PostgreSQL tsquery format (AND joined)."""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        safe_words = [w for w in (_TSQUERY_OPERATOR_RE.sub('', w) for w in words) if w]
        return " & ".join(safe_words)

    def to_tsvector_text(self, text: str) -> str:
        """Convert text to space-separated words for tsvector storage."""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        return " ".join(words)
