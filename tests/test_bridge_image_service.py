"""Unit tests for BridgeImageService — no DB or R2 required."""

import re
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.bridge_image_service import BridgeImageService


@pytest.fixture
def mock_r2():
    r2 = MagicMock()
    r2.generate_presigned_upload_url.return_value = "https://r2.example.com/upload?sig=abc"
    r2.generate_presigned_download_url.return_value = "https://r2.example.com/download?sig=xyz"
    return r2


@pytest.fixture
def svc(mock_r2):
    return BridgeImageService(mock_r2)


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Default: no existing images (max order_index query returns None)
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.scalar.return_value = None
    return db


def test_presign_upload_generates_correct_r2_key_pattern(svc, mock_db):
    """R2 key should follow: bridges/images/{bridge_id}/{uuid}.{ext}"""
    bridge_id = uuid.uuid4()

    image, upload_url = svc.presign_upload(
        mock_db, bridge_id, "photo.png", "image/png"
    )

    assert image.r2_key.startswith(f"bridges/images/{bridge_id}/")
    assert image.r2_key.endswith(".png")
    # Middle part should be a valid UUID
    parts = image.r2_key.split("/")
    filename = parts[-1]  # e.g. "xxxxxxxx-xxxx-....png"
    uuid_part = filename.rsplit(".", 1)[0]
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        uuid_part,
    )


def test_presign_upload_returns_presigned_url(svc, mock_db, mock_r2):
    bridge_id = uuid.uuid4()
    _, upload_url = svc.presign_upload(mock_db, bridge_id, "img.jpg", "image/jpeg")

    assert upload_url == "https://r2.example.com/upload?sig=abc"
    mock_r2.generate_presigned_upload_url.assert_called_once()


def test_presign_upload_default_ext_is_jpg(svc, mock_db):
    """If filename has no extension, default to jpg."""
    bridge_id = uuid.uuid4()
    image, _ = svc.presign_upload(mock_db, bridge_id, "noext", "image/jpeg")
    assert image.r2_key.endswith(".jpg")


def test_presign_upload_order_index_increments(svc, mock_db):
    """order_index should be max+1 when images already exist."""
    bridge_id = uuid.uuid4()
    # Simulate existing images with max order_index = 2
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.scalar.return_value = 2

    image, _ = svc.presign_upload(mock_db, bridge_id, "img.jpg", "image/jpeg")
    assert image.order_index == 3


@patch("app.services.bridge_image_service.settings")
def test_get_public_url_with_r2_public_url_configured(mock_settings):
    """When r2_public_url is set, return direct public URL."""
    mock_settings.r2_public_url = "https://cdn.example.com"

    url = BridgeImageService.get_public_url("bridges/images/abc/123.jpg")
    assert url == "https://cdn.example.com/bridges/images/abc/123.jpg"


@patch("app.services.bridge_image_service.settings")
@patch("app.services.bridge_image_service.R2StorageService")
def test_get_public_url_without_public_url_falls_back_to_presigned(
    mock_r2_class, mock_settings
):
    """When r2_public_url is empty, fall back to presigned GET URL."""
    mock_settings.r2_public_url = ""
    mock_r2_instance = MagicMock()
    mock_r2_instance.generate_presigned_download_url.return_value = (
        "https://r2.example.com/download?sig=fallback"
    )
    mock_r2_class.return_value = mock_r2_instance

    url = BridgeImageService.get_public_url("bridges/images/abc/123.jpg")
    assert url == "https://r2.example.com/download?sig=fallback"
    mock_r2_instance.generate_presigned_download_url.assert_called_once_with(
        "bridges/images/abc/123.jpg", expires=3600
    )


@patch("app.services.bridge_image_service.settings")
def test_get_public_url_strips_trailing_slash(mock_settings):
    """Trailing slash on r2_public_url should be stripped."""
    mock_settings.r2_public_url = "https://cdn.example.com/"

    url = BridgeImageService.get_public_url("bridges/images/abc/123.jpg")
    assert url == "https://cdn.example.com/bridges/images/abc/123.jpg"
