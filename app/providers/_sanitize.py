"""Exception-message sanitizer — third line of the zero-key-exposure defense.

Layer 1 (authoritative): `register_sensitive_key()` — exact-value blacklist
populated at app startup and after provider config changes. This is the
real defense.

Layer 2 (best-effort): regex fallbacks for Bearer / sk- / api_key=/token=.
Covers the dominant provider-SDK leak shapes but not bare JWTs, Basic auth,
or lowercase `bearer`. If a key isn't registered in layer 1, don't rely on
these regexes to catch it.

Layer 3: 300-char truncation, runs after replacements.
"""
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

    for k in tuple(_SENSITIVE_KEYS):  # snapshot tolerant of concurrent .add()
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
