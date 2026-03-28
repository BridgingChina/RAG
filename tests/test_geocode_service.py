"""Tests for GeocodeService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.geocode_service import GeocodeService


@pytest.fixture
def svc():
    """GeocodeService with a fake API key."""
    with patch("app.services.geocode_service.settings") as mock_settings:
        mock_settings.amap_api_key = "test-key"
        service = GeocodeService()
    return service


@pytest.fixture
def svc_no_key():
    """GeocodeService without an API key."""
    with patch("app.services.geocode_service.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        service = GeocodeService()
    return service


@pytest.mark.asyncio
async def test_amap_geocode_parses_response(svc):
    """Should parse Amap response and return (lat, lng) — note lng/lat swap."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "1",
        "geocodes": [{"location": "116.397428,39.90923", "level": "城市"}],
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.geocode_service.httpx.AsyncClient", return_value=mock_client):
        result = await svc._amap_geocode("北京")

    assert result is not None
    lat, lng = result
    # Amap returns "lng,lat" — we swap to (lat, lng)
    assert lat == pytest.approx(39.90923)
    assert lng == pytest.approx(116.397428)

    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args
    assert call_kwargs[1]["params"]["address"] == "北京"


@pytest.mark.asyncio
async def test_amap_geocode_returns_none_on_empty(svc):
    """Should return None when Amap returns no geocode results."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "1", "geocodes": []}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.geocode_service.httpx.AsyncClient", return_value=mock_client):
        result = await svc._amap_geocode("不存在的地方xyz")

    assert result is None


@pytest.mark.asyncio
async def test_amap_geocode_skips_if_no_api_key(svc_no_key):
    """Should return None immediately if no API key is configured."""
    result = await svc_no_key._amap_geocode("北京")
    assert result is None


def test_import_csv_matches_by_name():
    """Should match CSV rows to bridges by exact name."""
    # Create mock bridges
    bridge1 = MagicMock()
    bridge1.name = "赵州桥"
    bridge1.latitude = None
    bridge1.longitude = None
    bridge1.geocode_source = None

    bridge2 = MagicMock()
    bridge2.name = "卢沟桥"
    bridge2.latitude = None
    bridge2.longitude = None
    bridge2.geocode_source = None

    # Mock DB session
    mock_db = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()

        def filter_side_effect(condition):
            mock_filtered = MagicMock()
            # Extract the name being searched from the condition
            # We need to check what name is being queried
            return mock_filtered

        mock_query.filter = filter_side_effect
        return mock_query

    # Simpler approach: track filter calls
    bridges_by_name = {"赵州桥": bridge1, "卢沟桥": bridge2}

    def mock_first_for_name(name):
        return bridges_by_name.get(name)

    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first = MagicMock(side_effect=[bridge1, None, bridge2])
    mock_query.filter = MagicMock(return_value=mock_filter)
    mock_db.query = MagicMock(return_value=mock_query)

    csv_content = "name,latitude,longitude\n赵州桥,37.771,114.775\n未知桥,30.0,120.0\n卢沟桥,39.843,116.217\n"

    with patch("app.services.geocode_service.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        svc = GeocodeService()

    result = svc.import_from_csv(mock_db, csv_content)

    assert result["matched"] == 2
    assert result["unmatched"] == ["未知桥"]

    # Verify coordinates were set on matched bridges
    assert bridge1.latitude == 37.771
    assert bridge1.longitude == 114.775
    assert bridge1.geocode_source == "csv"

    assert bridge2.latitude == 39.843
    assert bridge2.longitude == 116.217
    assert bridge2.geocode_source == "csv"

    mock_db.commit.assert_called_once()
