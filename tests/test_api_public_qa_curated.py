"""Tests for curated direct-answer public QA questions."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _event_types(raw_sse: str) -> list[str]:
    return [
        line.removeprefix("event: ")
        for line in raw_sse.splitlines()
        if line.startswith("event: ")
    ]


def test_curated_question_short_circuits_to_authored_answer():
    client = TestClient(app, raise_server_exceptions=False)

    with (
        patch("app.api.public.v1.qa.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
        patch("app.api.public.v1.qa.get_provider") as provider_mock,
    ):
        response = client.post(
            "/v1/qa/ask",
            json={"question": "人行通道在城市中的作用"},
        )

    assert response.status_code == 200
    assert _event_types(response.text) == [
        "started",
        "outline",
        "detail",
        "detail",
        "detail",
        "sources",
        "done",
    ]
    assert "人行通道在城市中具有重要的交通补充功能" in response.text
    assert "八里桥作为古桥和全国重点文物保护单位" in response.text
    sleep_mock.assert_awaited_once()
    delay = sleep_mock.await_args.args[0]
    assert 0.5 <= delay <= 2.0
    provider_mock.assert_not_called()


def test_curated_question_tolerates_surrounding_whitespace():
    client = TestClient(app, raise_server_exceptions=False)

    with patch("app.api.public.v1.qa.asyncio.sleep", new_callable=AsyncMock):
        response = client.post(
            "/v1/qa/ask",
            json={"question": "  人行通道在城市中的作用  "},
        )

    assert response.status_code == 200
    assert "安澜索桥连接二王庙及伏龙观" in response.text
