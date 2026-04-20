"""
LocaleMiddleware — 为每个请求在 ``request.state.locale`` 写入解析后的 locale。

优先级（Phase 1 实现的头两档；JWT claim 优先级由 endpoint dependency 在
``get_current_user`` 里追加覆盖，见 ``app/api/v1/dependencies.py``）：

    JWT.preferred_locale > cookie NEXT_LOCALE > Accept-Language > DEFAULT_LOCALE

这里只处理 cookie + header：middleware 不应 async 调 ``verify_jwt``
（每请求开销大、且未鉴权路由并不需要 JWT 解析）。

用法：
    # app/main.py
    from app.core.locale_middleware import LocaleMiddleware
    app.add_middleware(LocaleMiddleware)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, resolve_locale

COOKIE_NAME = "NEXT_LOCALE"


def _parse_accept_language(header: str | None) -> str:
    """
    解析 Accept-Language header。取第一个命中 SUPPORTED_LOCALES 的语言标签。
    不在支持列表内返回 DEFAULT_LOCALE。
    """
    if not header:
        return DEFAULT_LOCALE
    for lang_part in header.split(","):
        # "zh-CN;q=0.9" → "zh-CN"
        tag = lang_part.split(";")[0].strip()
        if tag in SUPPORTED_LOCALES:
            return tag
    return DEFAULT_LOCALE


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Cookie 优先（用户明确选过语言）
        cookie_locale = request.cookies.get(COOKIE_NAME)
        if cookie_locale and cookie_locale in SUPPORTED_LOCALES:
            request.state.locale = cookie_locale
        else:
            # 2. Accept-Language header
            request.state.locale = _parse_accept_language(
                request.headers.get("accept-language")
            )

        # JWT.preferred_locale 的覆盖在 endpoint dependency 里做
        # （middleware 层不 async 解 JWT，避免每请求多一次 JWKS 验签）

        return await call_next(request)
