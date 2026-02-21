"""Unit tests for R2StorageService (mocked boto3)."""
from unittest.mock import MagicMock, patch

import pytest


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_r2_storage_service_instantiation(mock_settings, mock_boto3):
    """Service can be created with config."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()
    assert service.bucket_name == "test-bucket"
    mock_boto3.client.assert_called_once_with(
        "s3",
        endpoint_url="https://testaccount.r2.cloudflarestorage.com",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
        region_name="auto",
    )


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_generate_presigned_upload_url(mock_settings, mock_boto3):
    """Presigned URL is generated with correct parameters."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()
    service._client.generate_presigned_url.return_value = "https://presigned.url"

    url = service.generate_presigned_upload_url("raw/1/test.pdf", "application/pdf")
    assert url == "https://presigned.url"
    service._client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "test-bucket",
            "Key": "raw/1/test.pdf",
            "ContentType": "application/pdf",
        },
        ExpiresIn=3600,
    )


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_generate_presigned_download_url(mock_settings, mock_boto3):
    """Presigned download URL is generated with correct parameters."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()
    service._client.generate_presigned_url.return_value = "https://download.url"

    url = service.generate_presigned_download_url("raw/1/test.pdf")
    assert url == "https://download.url"
    service._client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={
            "Bucket": "test-bucket",
            "Key": "raw/1/test.pdf",
        },
        ExpiresIn=3600,
    )


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_upload(mock_settings, mock_boto3):
    """Upload sends data with correct parameters."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()

    service.upload("raw/1/test.pdf", b"pdf-data", "application/pdf")
    service._client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="raw/1/test.pdf",
        Body=b"pdf-data",
        ContentType="application/pdf",
    )


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_download(mock_settings, mock_boto3):
    """Download returns file bytes."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()
    mock_body = MagicMock()
    mock_body.read.return_value = b"file-content"
    service._client.get_object.return_value = {"Body": mock_body}

    data = service.download("raw/1/test.pdf")
    assert data == b"file-content"
    service._client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="raw/1/test.pdf"
    )


@patch("app.services.r2_storage.boto3")
@patch("app.services.r2_storage.settings")
def test_delete_prefix(mock_settings, mock_boto3):
    """delete_prefix removes all objects under a prefix."""
    mock_settings.r2_account_id = "testaccount"
    mock_settings.r2_access_key_id = "test_key"
    mock_settings.r2_secret_access_key = "test_secret"
    mock_settings.r2_bucket_name = "test-bucket"
    mock_settings.r2_public_url = ""

    from app.services.r2_storage import R2StorageService

    service = R2StorageService()

    mock_paginator = MagicMock()
    service._client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "raw/1/a.pdf"}, {"Key": "raw/1/b.pdf"}]},
    ]

    service.delete_prefix("raw/1/")
    service._client.delete_objects.assert_called_once_with(
        Bucket="test-bucket",
        Delete={"Objects": [{"Key": "raw/1/a.pdf"}, {"Key": "raw/1/b.pdf"}]},
    )


def test_is_configured_returns_false_when_missing():
    """is_configured() returns False when R2 credentials are empty."""
    with patch("app.services.r2_storage.settings") as mock_settings:
        mock_settings.r2_account_id = ""
        mock_settings.r2_access_key_id = ""
        mock_settings.r2_secret_access_key = ""
        mock_settings.r2_bucket_name = "test-bucket"
        mock_settings.r2_public_url = ""

        from app.services.r2_storage import R2StorageService

        assert R2StorageService.is_configured() is False


def test_is_configured_returns_true_when_set():
    """is_configured() returns True when all R2 credentials are set."""
    with patch("app.services.r2_storage.settings") as mock_settings:
        mock_settings.r2_account_id = "acct"
        mock_settings.r2_access_key_id = "key"
        mock_settings.r2_secret_access_key = "secret"
        mock_settings.r2_bucket_name = "bucket"
        mock_settings.r2_public_url = ""

        from app.services.r2_storage import R2StorageService

        assert R2StorageService.is_configured() is True
