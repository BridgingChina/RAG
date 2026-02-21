"""Cloudflare R2 storage service (S3-compatible)."""
import boto3

from app.core.config import settings


class R2StorageService:
    """Cloudflare R2 file storage using S3-compatible API."""

    def __init__(self):
        self.bucket_name = settings.r2_bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    @staticmethod
    def is_configured() -> bool:
        """Check if R2 credentials are configured."""
        return bool(
            settings.r2_account_id
            and settings.r2_access_key_id
            and settings.r2_secret_access_key
        )

    def generate_presigned_upload_url(
        self, key: str, content_type: str, expires: int = 3600
    ) -> str:
        """Generate a presigned PUT URL for direct browser upload."""
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires,
        )

    def generate_presigned_download_url(self, key: str, expires: int = 3600) -> str:
        """Generate a presigned GET URL."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires,
        )

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """Upload data to R2 from server side."""
        self._client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def download(self, key: str) -> bytes:
        """Download file from R2."""
        resp = self._client.get_object(Bucket=self.bucket_name, Key=key)
        return resp["Body"].read()

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects under a prefix."""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                self._client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )
