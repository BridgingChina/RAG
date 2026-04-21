import os
import re

_SENSITIVE_KEYS: set[str] = set()


def _reset() -> None:  # test helper
    _SENSITIVE_KEYS.clear()


def register_sensitive_key(env_name: str) -> None:
    """Add current env value to the sanitize blacklist. Idempotent."""
    v = os.environ.get(env_name)
    if v and len(v) >= 16:
        _SENSITIVE_KEYS.add(v)


def sanitize_error(exc: BaseException) -> str:
    raw = f"{type(exc).__name__}: {exc}"
    if exc.__cause__:
        raw += f" (cause: {type(exc.__cause__).__name__}: {exc.__cause__})"

    for k in _SENSITIVE_KEYS:
        raw = raw.replace(k, "***KEY***")

    raw = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}", "Bearer ***KEY***", raw)
    raw = re.sub(r"sk-[A-Za-z0-9_\-]{20,}", "sk-***KEY***", raw)
    raw = re.sub(
        r"(api[_-]?key|token)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}[\"']?",
        r"\1=***KEY***",
        raw,
        flags=re.IGNORECASE,
    )
    return raw[:300]
