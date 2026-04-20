"""
单元测试 LocaleMiddleware 的 cookie + Accept-Language 优先级。

JWT claim preferred_locale 覆盖的集成测试放在 tests/integration/
（需要 mock JWKS 或实际 JWT fixture），本文件只测 middleware 自身逻辑。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.locale_middleware import LocaleMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)

    @app.get("/echo-locale")
    def echo(request):  # type: ignore[no-untyped-def]
        return {"locale": request.state.locale}

    # FastAPI 需要 Request 类型
    from starlette.requests import Request as StarletteRequest

    app.router.routes.clear()

    @app.get("/echo-locale")
    def echo2(request: StarletteRequest):
        return {"locale": request.state.locale}

    return app


def test_default_when_no_signal():
    client = TestClient(_app())
    r = client.get("/echo-locale")
    assert r.status_code == 200
    assert r.json()["locale"] == "zh-CN"


def test_accept_language_zh_cn():
    client = TestClient(_app())
    r = client.get("/echo-locale", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert r.json()["locale"] == "zh-CN"


def test_accept_language_en_us():
    client = TestClient(_app())
    r = client.get("/echo-locale", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert r.json()["locale"] == "en-US"


def test_accept_language_first_supported_wins():
    # 不支持的 fr-FR 排在前，后面是 en-US → 取 en-US
    client = TestClient(_app())
    r = client.get(
        "/echo-locale", headers={"Accept-Language": "fr-FR,en-US;q=0.8,zh;q=0.6"}
    )
    assert r.json()["locale"] == "en-US"


def test_unsupported_accept_language_falls_back_to_default():
    client = TestClient(_app())
    r = client.get("/echo-locale", headers={"Accept-Language": "ja-JP,ko-KR;q=0.9"})
    assert r.json()["locale"] == "zh-CN"


def test_cookie_beats_accept_language():
    client = TestClient(_app())
    r = client.get(
        "/echo-locale",
        headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        cookies={"NEXT_LOCALE": "en-US"},
    )
    assert r.json()["locale"] == "en-US"


def test_invalid_cookie_falls_through_to_accept_language():
    client = TestClient(_app())
    r = client.get(
        "/echo-locale",
        headers={"Accept-Language": "en-US"},
        cookies={"NEXT_LOCALE": "fr-FR"},  # 非法，应忽略
    )
    assert r.json()["locale"] == "en-US"


def test_empty_accept_language_uses_default():
    client = TestClient(_app())
    r = client.get("/echo-locale", headers={"Accept-Language": ""})
    assert r.json()["locale"] == "zh-CN"
