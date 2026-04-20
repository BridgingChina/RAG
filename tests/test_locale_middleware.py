"""Unit tests for locale resolution (i18n Phase 3)."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.core.locale_middleware import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
)


def _fake_request(*, cookies=None, query=None, headers=None):
    req = MagicMock()
    req.cookies = cookies or {}
    req.query_params = query or {}
    req.headers = headers or {}
    # starlette headers are case-insensitive — the implementation uses
    # `request.headers.get("accept-language")` so a plain dict with that
    # lowercase key suffices for the test.
    return req


def test_defaults_to_zh_cn_when_nothing_supplied():
    assert resolve_locale(_fake_request()) == "zh-CN"
    assert DEFAULT_LOCALE == "zh-CN"


def test_supported_locales_tuple_contents():
    assert SUPPORTED_LOCALES == ("zh-CN", "en-US")


def test_query_param_wins_over_cookie_and_header():
    req = _fake_request(
        query={"lang": "en-US"},
        cookies={"NEXT_LOCALE": "zh-CN"},
        headers={"accept-language": "zh-CN,en;q=0.5"},
    )
    assert resolve_locale(req) == "en-US"


def test_cookie_wins_over_header():
    req = _fake_request(
        cookies={"NEXT_LOCALE": "en-US"},
        headers={"accept-language": "zh-CN"},
    )
    assert resolve_locale(req) == "en-US"


def test_accept_language_header_used_when_no_cookie():
    req = _fake_request(headers={"accept-language": "en-US,zh;q=0.5"})
    assert resolve_locale(req) == "en-US"


def test_accept_language_case_normalization():
    """'en-us' (lowercase) should normalize to 'en-US'."""
    req = _fake_request(headers={"accept-language": "en-us"})
    assert resolve_locale(req) == "en-US"


def test_unknown_locale_falls_back():
    req = _fake_request(
        cookies={"NEXT_LOCALE": "fr-FR"},
        headers={"accept-language": "fr-FR"},
    )
    # Unknown locales skip through all sources — default wins.
    assert resolve_locale(req) == "zh-CN"


def test_accept_language_q_weights_honored():
    """Client preferring en-US with higher q wins over earlier-listed zh-TW."""
    req = _fake_request(
        headers={"accept-language": "zh-TW,en-US;q=0.9,zh-CN;q=0.5"},
    )
    # zh-TW is not supported so it's discarded; next highest q is en-US.
    assert resolve_locale(req) == "en-US"
