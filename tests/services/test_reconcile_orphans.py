"""Unit tests for reconcile_orphans."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import reconcile_orphans


@pytest.mark.asyncio
async def test_user_exists_returns_true_on_200():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    client = MagicMock()
    client.head = AsyncMock(return_value=fake_resp)

    with patch("app.services.reconcile_orphans.settings") as mock_settings:
        mock_settings.auth_worker_base_url = "https://auth.example"
        result = await reconcile_orphans._user_exists(client, "u1")

    assert result is True
    client.head.assert_awaited_once_with(
        "https://auth.example/api/auth/users/u1/exists", timeout=10.0
    )


@pytest.mark.asyncio
async def test_user_exists_returns_false_on_404():
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    client = MagicMock()
    client.head = AsyncMock(return_value=fake_resp)

    with patch("app.services.reconcile_orphans.settings") as mock_settings:
        mock_settings.auth_worker_base_url = "https://auth.example"
        result = await reconcile_orphans._user_exists(client, "missing")

    assert result is False


@pytest.mark.asyncio
async def test_user_exists_returns_none_on_transport_error():
    """Transport failures must never masquerade as 'user gone'."""
    client = MagicMock()
    client.head = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch("app.services.reconcile_orphans.settings") as mock_settings:
        mock_settings.auth_worker_base_url = "https://auth.example"
        result = await reconcile_orphans._user_exists(client, "u")

    assert result is None


@pytest.mark.asyncio
async def test_reconcile_skips_when_auth_worker_unconfigured():
    """No auth worker URL → cron is inert, returns 0 without DB access."""
    with patch("app.services.reconcile_orphans.settings") as mock_settings:
        mock_settings.auth_worker_base_url = ""
        purged = await reconcile_orphans.reconcile_once()
    assert purged == 0
