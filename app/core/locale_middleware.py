"""Locale resolution middleware for the public C-end API.

Sets ``request.state.locale`` to one of :data:`SUPPORTED_LOCALES` on every
request. Resolution order (highest priority first):

1. Authenticated user's ``preferred_locale`` JWT claim — **not implemented here**;
   individual endpoints that depend on JWT (favorites/review/history) do not need
   locale-aware data today, so this upstream source is wired from the API layer
   when added.
2. Query parameter ``?lang=en-US`` / ``?lang=zh-CN`` — debug override, useful for
   testing without cookies.
3. Cookie ``NEXT_LOCALE`` — set by the ``web/`` language switcher.
4. ``Accept-Language`` header — standard content negotiation, first matching
   supported locale wins.
5. :data:`DEFAULT_LOCALE` fallback (``zh-CN``).

Non-whitelist values are discarded silently and fall through to the next source.
That's "fallback永不静默" in the plan §4 table — but the quiet part is at the
*resolution* layer; serializers emit ``response.meta.translation_fallback=true``
when the resolved locale lacks data.
"""
from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SUPPORTED_LOCALES: tuple[str, ...] = ("zh-CN", "en-US")
DEFAULT_LOCALE: str = "zh-CN"

# Only public (C-end) routes need locale resolution. Admin /api/v1/* stays
# zh-CN only per the design (§1.2). /health / /internal skip the whole thing.
_LOCALE_AWARE_PREFIXES: tuple[str, ...] = ("/v1/",)


def _first_supported(candidates: Iterable[str]) -> str | None:
    for raw in candidates:
        if not raw:
            continue
        normalized = _normalize(raw)
        if normalized in SUPPORTED_LOCALES:
            return normalized
    return None


def _normalize(value: str) -> str:
    """Case-normalize ``en-us`` → ``en-US`` before membership check."""
    value = value.strip()
    if "-" not in value:
        return value
    head, tail = value.split("-", 1)
    return f"{head.lower()}-{tail.upper()}"


def _parse_accept_language(header: str) -> list[str]:
    """Return the locales listed in an ``Accept-Language`` header, ordered by
    the client's declared ``q=`` weights (highest first).
    """
    if not header:
        return []
    parts: list[tuple[float, str]] = []
    for token in header.split(","):
        token = token.strip()
        if not token:
            continue
        if ";" in token:
            locale, params = token.split(";", 1)
            q = 1.0
            for param in params.split(";"):
                param = param.strip()
                if param.startswith("q="):
                    try:
                        q = float(param[2:])
                    except ValueError:
                        q = 0.0
            parts.append((q, locale.strip()))
        else:
            parts.append((1.0, token))
    parts.sort(key=lambda p: p[0], reverse=True)
    return [locale for _, locale in parts]


def resolve_locale(request: Request) -> str:
    """Pure function — pick the best-supported locale for this request.

    Exposed on its own so unit tests don't need a full ASGI Starlette scope.
    """
    # 2. ?lang= override (debug)
    lang_query = request.query_params.get("lang")
    picked = _first_supported([lang_query] if lang_query else [])
    if picked:
        return picked

    # 3. Cookie
    cookie = request.cookies.get("NEXT_LOCALE")
    picked = _first_supported([cookie] if cookie else [])
    if picked:
        return picked

    # 4. Accept-Language
    header = request.headers.get("accept-language") or ""
    picked = _first_supported(_parse_accept_language(header))
    if picked:
        return picked

    return DEFAULT_LOCALE


class LocaleMiddleware(BaseHTTPMiddleware):
    """Populate ``request.state.locale`` for C-end requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _LOCALE_AWARE_PREFIXES):
            request.state.locale = resolve_locale(request)
        else:
            # Admin / internal / health: deterministic default so any code that
            # *does* read request.state.locale (e.g. shared serializer utility)
            # still finds something sane.
            request.state.locale = DEFAULT_LOCALE
        return await call_next(request)
