# FastAPI i18n 最小化实现：
# - 消息源：app/locales/{zh_cn,en_us}.py，flat key + dot notation
# - 查找 fallback 链：目标 locale → DEFAULT_LOCALE → 返回 key 自身
# - 未知 locale 统一 resolve 为 DEFAULT_LOCALE（不抛异常）
# - 参数替换使用 str.format（支持 named 参数）
#
# 用法：
#     from app.core.i18n import t
#     raise HTTPException(404, detail=t("bridges.not_found", locale=request.state.locale))
#     raise HTTPException(409, detail=t("bridges.exists", locale=locale, name="赵州桥"))

from __future__ import annotations

import logging
from typing import Final

from app.locales import en_us, zh_cn

log = logging.getLogger(__name__)

SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("zh-CN", "en-US")
DEFAULT_LOCALE: Final[str] = "zh-CN"

_REGISTRY: Final[dict[str, dict[str, str]]] = {
    "zh-CN": zh_cn.MESSAGES,
    "en-US": en_us.MESSAGES,
}


def resolve_locale(requested: str | None) -> str:
    """把任意输入收敛到白名单内的 locale；不在则返回默认。"""
    if requested and requested in SUPPORTED_LOCALES:
        return requested
    return DEFAULT_LOCALE


def t(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """
    查询翻译。
    - 命中目标 locale 的 key → 返回 format 后的字符串
    - 目标 locale 无 key，但默认 locale 有 → fallback 到默认 locale（WARN 日志）
    - 两种 locale 都无 key → 返回 key 自身（WARN 日志），调用方 UI 不会白屏
    """
    effective = resolve_locale(locale)
    template = _REGISTRY[effective].get(key)

    if template is None and effective != DEFAULT_LOCALE:
        template = _REGISTRY[DEFAULT_LOCALE].get(key)
        if template is not None:
            log.warning(
                "i18n.missing_key",
                extra={"key": key, "locale": effective, "fell_back_to": DEFAULT_LOCALE},
            )

    if template is None:
        log.warning("i18n.missing_key_all_locales", extra={"key": key})
        return key

    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError) as exc:
        log.error(
            "i18n.format_error",
            extra={"key": key, "locale": effective, "params": list(params.keys())},
            exc_info=exc,
        )
        return template
