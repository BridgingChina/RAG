# Async Ingest Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the synchronous single-step ingest with an async multi-stage pipeline that uploads files to R2, parses PDFs via Zhipu, chunks with user confirmation, then indexes.

**Architecture:** New `ingest_tasks` DB table tracks task state across 6 stages. Frontend uploads directly to R2 via presigned URLs, then backend orchestrates parsing → chunking → user review (via existing ChunkEditor) → embedding/indexing via FastAPI BackgroundTasks. Three new backend services: `R2StorageService`, `FileParserProvider`, `IngestTaskService`.

**Tech Stack:** boto3 (R2/S3), httpx (Zhipu file parser API), FastAPI BackgroundTasks, React drag-and-drop file upload.

**Design doc:** `docs/plans/2026-02-21-async-ingest-design.md`

---

### Task 1: Add boto3 dependency and R2 config

**Files:**
- Modify: `pyproject.toml:6-20`
- Modify: `app/core/config.py:1-22`
- Modify: `.env.example:1-3`

**Step 1: Add boto3 to dependencies**

In `pyproject.toml`, add `"boto3>=1.34.0"` to the `dependencies` list:

```python
dependencies = [
    "boto3>=1.34.0",
    "click>=8.0.0",
    # ... rest unchanged
]
```

**Step 2: Add R2 settings to config**

In `app/core/config.py`, add after the Auth settings block (line 19):

```python
    # R2 storage settings
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "bridge-rag"
    r2_public_url: str = ""  # optional, for public access

    # Zhipu file parser settings
    zhipu_parser_tool_type: str = "expert"  # lite / expert / prime
```

**Step 3: Update .env.example**

Append to `.env.example`:

```
# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=bridge-rag
R2_PUBLIC_URL=

# Zhipu file parser
ZHIPU_PARSER_TOOL_TYPE=expert
```

**Step 4: Install new dependency**

Run: `pip install -e ".[dev]"`

**Step 5: Commit**

```bash
git add pyproject.toml app/core/config.py .env.example
git commit -m "feat: add boto3 dependency and R2/parser config"
```

---

### Task 2: Create IngestTask model and schema v6 migration

**Files:**
- Create: `app/models/ingest_task.py`
- Modify: `app/models/__init__.py:1-21`
- Modify: `app/core/database.py:14` (LATEST_SCHEMA_VERSION)
- Modify: `app/core/database.py:92-144` (verify_schema_compatibility)
- Modify: `app/core/database.py:233-267` (_migrate_schema)
- Modify: `app/core/database.py:356-357` (set_schema_version description)

**Step 1: Write the IngestTask model**

Create `app/models/ingest_task.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IngestTask(Base):
    __tablename__ = "ingest_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploading")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf / md
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    r2_raw_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    r2_parsed_prefix: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    zhipu_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=True
    )
    parsed_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

**Step 2: Register model in `__init__.py`**

In `app/models/__init__.py`, add import and export:

```python
from app.models.ingest_task import IngestTask
```

Add `"IngestTask"` to `__all__` list.

**Step 3: Add migration v5 → v6 in `_migrate_schema`**

In `app/core/database.py`, after the v4→v5 migration block (after line 267), add:

```python
    if current_version < 6:
        logger.info("Migrating schema v5 → v6: adding ingest_tasks table...")
        from app.models.ingest_task import IngestTask

        IngestTask.__table__.create(conn, checkfirst=True)
        set_schema_version(engine, 6, "Add ingest_tasks table", conn=conn)
        logger.info("Migration to v6 complete.")
```

**Step 4: Update LATEST_SCHEMA_VERSION to 6**

In `app/core/database.py` line 14:

```python
LATEST_SCHEMA_VERSION = 6
```

**Step 5: Add ingest_tasks to verify_schema_compatibility**

In `app/core/database.py`, add to the `required_schema` dict (after chunk_bridge_links):

```python
        "ingest_tasks": {
            "id",
            "status",
            "file_name",
            "file_type",
            "file_size",
            "r2_raw_key",
            "r2_parsed_prefix",
            "zhipu_task_id",
            "source_id",
            "parsed_content",
            "chunk_count",
            "image_count",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        },
```

**Step 6: Update fresh-init version stamp description**

In `app/core/database.py` line 356-357, update:

```python
            set_schema_version(
                engine, LATEST_SCHEMA_VERSION, "Schema v6 with ingest_tasks table", conn=conn
            )
```

**Step 7: Verify migration works**

Run: `python3 scripts/migrate_db.py --dry-run`
Expected: Shows planned changes including ingest_tasks creation.

Run: `python3 scripts/migrate_db.py`
Expected: Migration to v6 completes successfully.

**Step 8: Commit**

```bash
git add app/models/ingest_task.py app/models/__init__.py app/core/database.py
git commit -m "feat: add IngestTask model and schema v6 migration"
```

---

### Task 3: Create R2StorageService

**Files:**
- Create: `app/services/r2_storage.py`
- Create: `tests/test_r2_storage.py`

**Step 1: Write the failing test**

Create `tests/test_r2_storage.py`:

```python
"""Unit tests for R2StorageService (mocked boto3)."""
from unittest.mock import MagicMock, patch

import pytest


def test_r2_storage_service_instantiation():
    """Service can be created with config."""
    with patch("app.services.r2_storage.settings") as mock_settings:
        mock_settings.r2_account_id = "test_account"
        mock_settings.r2_access_key_id = "test_key"
        mock_settings.r2_secret_access_key = "test_secret"
        mock_settings.r2_bucket_name = "test-bucket"
        mock_settings.r2_public_url = ""

        from app.services.r2_storage import R2StorageService

        service = R2StorageService()
        assert service.bucket_name == "test-bucket"


def test_generate_presigned_upload_url():
    """Presigned URL is generated with correct parameters."""
    with patch("app.services.r2_storage.settings") as mock_settings:
        mock_settings.r2_account_id = "test_account"
        mock_settings.r2_access_key_id = "test_key"
        mock_settings.r2_secret_access_key = "test_secret"
        mock_settings.r2_bucket_name = "test-bucket"
        mock_settings.r2_public_url = ""

        from app.services.r2_storage import R2StorageService

        service = R2StorageService()
        service._client = MagicMock()
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_r2_storage.py -v`
Expected: FAIL (module not found)

**Step 3: Write the R2StorageService**

Create `app/services/r2_storage.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_r2_storage.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add app/services/r2_storage.py tests/test_r2_storage.py
git commit -m "feat: add R2StorageService with presigned URL support"
```

---

### Task 4: Create FileParserProvider

**Files:**
- Create: `app/providers/file_parser.py`
- Modify: `app/providers/__init__.py:1-4`
- Create: `tests/test_file_parser_provider.py`

**Step 1: Write the failing test**

Create `tests/test_file_parser_provider.py`:

```python
"""Unit tests for FileParserProvider (mocked httpx)."""
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_create_task_returns_task_id():
    """create_task sends file to Zhipu and returns task_id."""
    with patch("app.providers.file_parser.settings") as mock_settings:
        mock_settings.zhipu_api_key = "test-key"
        mock_settings.zhipu_parser_tool_type = "expert"

        from app.providers.file_parser import FileParserProvider

        provider = FileParserProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "task_id": "zhipu-task-123",
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.providers.file_parser.httpx.AsyncClient", return_value=mock_client):
            task_id = await provider.create_task(
                file_bytes=b"fake-pdf-content",
                file_name="test.pdf",
                file_type="pdf",
            )

        assert task_id == "zhipu-task-123"


@pytest.mark.asyncio
async def test_get_result_returns_parse_result():
    """get_result returns parsed content when status is succeeded."""
    with patch("app.providers.file_parser.settings") as mock_settings:
        mock_settings.zhipu_api_key = "test-key"
        mock_settings.zhipu_parser_tool_type = "expert"

        from app.providers.file_parser import FileParserProvider, ParseResult

        provider = FileParserProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "status": "succeeded",
                "content": "# Parsed markdown",
                "parsing_result_url": "https://download.url/result.zip",
            }
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.providers.file_parser.httpx.AsyncClient", return_value=mock_client):
            result = await provider.get_result("zhipu-task-123", format_type="text")

        assert result.status == "succeeded"
        assert result.content == "# Parsed markdown"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_file_parser_provider.py -v`
Expected: FAIL (module not found)

**Step 3: Write the FileParserProvider**

Create `app/providers/file_parser.py`:

```python
"""Zhipu file parsing service provider."""
import asyncio
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class ParseResult:
    status: str  # "processing" | "succeeded" | "failed"
    content: str | None = None  # text content (format_type=text)
    download_url: str | None = None  # download link (format_type=download_link)
    message: str | None = None  # error message on failure


class FileParserProvider:
    """Zhipu file parsing API wrapper.

    Independent from LLMProvider — different API surface, shared API key.
    """

    BASE_URL = "https://open.bigmodel.cn/api/paas/v4/files/parser"

    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.tool_type = settings.zhipu_parser_tool_type

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def create_task(
        self,
        file_bytes: bytes,
        file_name: str,
        file_type: str = "pdf",
        tool_type: str | None = None,
    ) -> str:
        """Upload file and create a parsing task. Returns zhipu task_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/create",
                headers=self._headers(),
                files={"file": (file_name, file_bytes)},
                data={
                    "tool_type": tool_type or self.tool_type,
                    "file_type": file_type.upper(),
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

            task_id = data.get("task_id")
            if not task_id:
                raise ValueError(f"Zhipu file parser returned no task_id: {data}")
            return task_id

    async def get_result(
        self, task_id: str, format_type: str = "download_link"
    ) -> ParseResult:
        """Query parsing result for a given task_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/result/{task_id}/{format_type}",
                headers=self._headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            body = resp.json()

            data = body.get("data", body)
            return ParseResult(
                status=data.get("status", "unknown"),
                content=data.get("content"),
                download_url=data.get("parsing_result_url"),
                message=data.get("message"),
            )

    async def poll_until_done(
        self,
        task_id: str,
        format_type: str = "download_link",
        timeout: float = 600,
        interval: float = 3,
    ) -> ParseResult:
        """Poll until parsing completes, fails, or times out."""
        elapsed = 0.0
        while elapsed < timeout:
            result = await self.get_result(task_id, format_type)
            if result.status == "succeeded":
                return result
            if result.status not in ("processing",):
                raise RuntimeError(
                    f"Zhipu parsing failed: status={result.status}, message={result.message}"
                )
            await asyncio.sleep(interval)
            elapsed += interval

        raise TimeoutError(f"Zhipu parsing timed out after {timeout}s for task {task_id}")
```

**Step 4: Register in providers `__init__.py`**

In `app/providers/__init__.py`, add:

```python
from app.providers.file_parser import FileParserProvider, ParseResult
```

And add `"FileParserProvider"`, `"ParseResult"` to `__all__`.

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_file_parser_provider.py -v`
Expected: 2 passed

**Step 6: Commit**

```bash
git add app/providers/file_parser.py app/providers/__init__.py tests/test_file_parser_provider.py
git commit -m "feat: add FileParserProvider for Zhipu document parsing"
```

---

### Task 5: Create API schemas for ingest-tasks

**Files:**
- Create: `app/api/v1/schemas/ingest_task.py`
- Modify: `app/api/v1/schemas/__init__.py`

**Step 1: Create the schema file**

Create `app/api/v1/schemas/ingest_task.py`:

```python
"""Schemas for ingest task endpoints."""
from pydantic import BaseModel


class PresignRequest(BaseModel):
    file_name: str
    file_type: str  # "pdf" | "md"
    file_size: int  # bytes
    content_type: str  # MIME type


class PresignResponse(BaseModel):
    upload_url: str
    r2_key: str


class IngestTaskCreate(BaseModel):
    file_name: str
    file_type: str
    file_size: int
    r2_key: str


class IngestTaskDetail(BaseModel):
    id: int
    status: str
    file_name: str
    file_type: str
    file_size: int | None
    source_id: int | None
    chunk_count: int | None
    image_count: int
    error_message: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class IngestTaskListItem(BaseModel):
    id: int
    status: str
    file_name: str
    file_type: str
    file_size: int | None
    source_id: int | None
    chunk_count: int | None
    image_count: int
    error_message: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
```

**Step 2: Register in schemas `__init__.py`**

In `app/api/v1/schemas/__init__.py`, add the import block and `__all__` entries:

```python
# IngestTask schemas
from .ingest_task import (
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
)
```

Add to `__all__`:
```python
    # IngestTask
    "IngestTaskCreate",
    "IngestTaskDetail",
    "IngestTaskListItem",
    "PresignRequest",
    "PresignResponse",
```

**Step 3: Commit**

```bash
git add app/api/v1/schemas/ingest_task.py app/api/v1/schemas/__init__.py
git commit -m "feat: add Pydantic schemas for ingest-tasks endpoints"
```

---

### Task 6: Create IngestTaskService

**Files:**
- Create: `app/services/ingest_task_service.py`
- Create: `tests/test_ingest_task_service.py`

**Step 1: Write the failing test**

Create `tests/test_ingest_task_service.py`:

```python
"""Unit tests for IngestTaskService (all external services mocked)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.ingest_task import IngestTask


@pytest.mark.asyncio
async def test_sync_and_parse_md_skips_zhipu():
    """Markdown files skip Zhipu parsing, go directly to chunking."""
    from app.services.ingest_task_service import IngestTaskService

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"# Test\n\nContent here"

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [[0.1] * 1024]

    mock_chunker_cls = MagicMock()
    mock_chunk_result = MagicMock()
    mock_chunk_result.content = "Content here"
    mock_chunk_result.section_title = "Test"
    mock_chunker_instance = AsyncMock()
    mock_chunker_instance.chunk.return_value = [mock_chunk_result]
    mock_chunker_cls.return_value = mock_chunker_instance

    task = IngestTask(
        id=1,
        status="syncing",
        file_name="test.md",
        file_type="md",
        file_size=100,
        r2_raw_key="raw/1/test.md",
    )

    # Make db.get return the task
    mock_db.get.return_value = task
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=mock_provider,
    )

    with patch("app.services.ingest_task_service.SemanticChunker", mock_chunker_cls):
        with patch("app.services.ingest_task_service.parse_markdown") as mock_parse:
            mock_doc = MagicMock()
            mock_doc.sections = [MagicMock(title="Test", level=1, content="Content here")]
            mock_doc.frontmatter = {"title": "Test"}
            mock_parse.return_value = mock_doc

            await service.sync_and_parse(task_id=1)

    # Should NOT call file parser (it's an md file)
    assert task.status == "chunked"
    assert task.parsed_content is not None


@pytest.mark.asyncio
async def test_sync_and_parse_pdf_calls_zhipu():
    """PDF files go through Zhipu parsing."""
    from app.services.ingest_task_service import IngestTaskService

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"fake-pdf-bytes"
    mock_r2.upload = MagicMock()

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [[0.1] * 1024]

    mock_file_parser = AsyncMock()
    mock_file_parser.create_task.return_value = "zhipu-task-123"

    mock_parse_result = MagicMock()
    mock_parse_result.status = "succeeded"
    mock_parse_result.content = "# Parsed PDF\n\nParsed content"
    mock_parse_result.download_url = None
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=2,
        status="syncing",
        file_name="test.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/2/test.pdf",
    )
    mock_db.get.return_value = task
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=mock_provider,
        file_parser=mock_file_parser,
    )

    mock_chunker_cls = MagicMock()
    mock_chunk_result = MagicMock()
    mock_chunk_result.content = "Parsed content"
    mock_chunk_result.section_title = "Parsed PDF"
    mock_chunker_instance = AsyncMock()
    mock_chunker_instance.chunk.return_value = [mock_chunk_result]
    mock_chunker_cls.return_value = mock_chunker_instance

    with patch("app.services.ingest_task_service.SemanticChunker", mock_chunker_cls):
        with patch("app.services.ingest_task_service.parse_markdown") as mock_parse:
            mock_doc = MagicMock()
            mock_doc.sections = [MagicMock(title="Parsed PDF", level=1, content="Parsed content")]
            mock_doc.frontmatter = {"title": "Parsed PDF"}
            mock_parse.return_value = mock_doc

            await service.sync_and_parse(task_id=2)

    mock_file_parser.create_task.assert_called_once()
    mock_file_parser.poll_until_done.assert_called_once_with("zhipu-task-123")
    assert task.status == "chunked"
    assert task.zhipu_task_id == "zhipu-task-123"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingest_task_service.py -v`
Expected: FAIL (module not found)

**Step 3: Write IngestTaskService**

Create `app/services/ingest_task_service.py`:

```python
"""Ingest task orchestration service.

Coordinates R2 storage, Zhipu file parsing, chunking, and indexing
across the async multi-stage ingest pipeline.
"""
import re

from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.ingest_task import IngestTask
from app.providers.base import LLMProvider
from app.providers.file_parser import FileParserProvider
from app.services.bridge_linker import BridgeLinker
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.r2_storage import R2StorageService
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path


def _get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


class IngestTaskService:
    """Orchestrates the multi-stage ingest pipeline."""

    def __init__(
        self,
        db: Session,
        r2: R2StorageService,
        provider: LLMProvider,
        file_parser: FileParserProvider | None = None,
    ):
        self.db = db
        self.r2 = r2
        self.provider = provider
        self.file_parser = file_parser or FileParserProvider()

    def _get_task(self, task_id: int) -> IngestTask:
        task = self.db.get(IngestTask, task_id)
        if task is None:
            raise ValueError(f"IngestTask {task_id} not found")
        return task

    def _fail(self, task: IngestTask, error: str) -> None:
        task.status = "failed"
        task.error_message = error
        self.db.commit()
        logger.error(f"IngestTask {task.id} failed: {error}")

    async def sync_and_parse(self, task_id: int) -> None:
        """Stage: syncing → parsing → chunked.

        For PDF: download from R2 → submit to Zhipu → poll → chunk.
        For MD: download from R2 → chunk directly.
        """
        task = self._get_task(task_id)

        try:
            # Download file from R2
            task.status = "syncing"
            self.db.commit()

            file_bytes = self.r2.download(task.r2_raw_key)

            if task.file_type == "pdf":
                await self._parse_pdf(task, file_bytes)
            else:
                # Markdown: use directly
                task.parsed_content = file_bytes.decode("utf-8")
                task.r2_parsed_prefix = f"parsed/{task.id}/"
                self.r2.upload(
                    f"parsed/{task.id}/result.md",
                    task.parsed_content.encode("utf-8"),
                    "text/markdown",
                )

            # Chunk the parsed content
            await self._chunk(task)

            task.status = "chunked"
            self.db.commit()

        except Exception as e:
            self._fail(task, str(e))

    async def _parse_pdf(self, task: IngestTask, file_bytes: bytes) -> None:
        """Submit PDF to Zhipu and poll for result."""
        task.status = "parsing"
        self.db.commit()

        zhipu_task_id = await self.file_parser.create_task(
            file_bytes=file_bytes,
            file_name=task.file_name,
            file_type="pdf",
        )
        task.zhipu_task_id = zhipu_task_id
        self.db.commit()

        # Poll with text format for simplicity (Expert supports download_link too)
        result = await self.file_parser.poll_until_done(zhipu_task_id)

        parsed_md = result.content or ""

        # If download_link format, we'd download the archive and extract images.
        # For now, use text content directly. Image handling can be added later
        # when download_link parsing is implemented.
        if result.download_url:
            await self._download_and_store_parsed_assets(task, result.download_url)

        task.parsed_content = parsed_md
        task.r2_parsed_prefix = f"parsed/{task.id}/"
        self.r2.upload(
            f"parsed/{task.id}/result.md",
            parsed_md.encode("utf-8"),
            "text/markdown",
        )

    async def _download_and_store_parsed_assets(
        self, task: IngestTask, download_url: str
    ) -> None:
        """Download parsed assets (images, markdown) from Zhipu and store in R2.

        TODO: Implement archive download, image extraction, and URL rewriting.
        This is a placeholder for the download_link format handling.
        """
        pass

    async def _chunk(self, task: IngestTask) -> None:
        """Parse markdown and create chunks (without embedding)."""
        doc = parse_markdown(task.parsed_content)
        title = doc.frontmatter.get("title", task.file_name)

        chunker = SemanticChunker(
            provider=self.provider,
            min_chunk_size=200,
            max_chunk_size=500,
            similarity_threshold=0.5,
        )

        chunk_results = await chunker.chunk(doc.sections)
        if not chunk_results:
            raise ValueError("No chunks generated from parsed content")

        # Create source record
        source = Source(type=task.file_type, title=title)
        self.db.add(source)
        self.db.flush()
        task.source_id = source.id

        # Create chunks without embedding (will be filled in indexing stage)
        for chunk_result in chunk_results:
            chunk = Chunk(
                source_id=source.id,
                content=chunk_result.content,
                section_title=chunk_result.section_title,
            )
            self.db.add(chunk)

        self.db.flush()
        task.chunk_count = len(chunk_results)

    async def start_indexing(self, task_id: int) -> None:
        """Stage: indexing → completed.

        After user confirms chunks via ChunkEditor, run embedding + tagging + tsv + bridge linking.
        """
        task = self._get_task(task_id)

        try:
            task.status = "indexing"
            self.db.commit()

            # Get all chunks for this source
            chunks = (
                self.db.query(Chunk)
                .filter(Chunk.source_id == task.source_id)
                .all()
            )

            if not chunks:
                raise ValueError(f"No chunks found for source {task.source_id}")

            context_enricher = ContextEnricher(provider=self.provider)
            tagger = MetadataTagger(
                provider=self.provider, taxonomy_lvl2=_get_taxonomy_lvl2_map()
            )
            bridge_linker = BridgeLinker(provider=self.provider)
            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())

            # Extract bridge hints from parsed content frontmatter
            doc = parse_markdown(task.parsed_content or "")
            bridge_hints = []
            bridge_val = doc.frontmatter.get("bridge")
            if isinstance(bridge_val, str) and bridge_val.strip():
                bridge_hints.append(bridge_val.strip())
            bridges_val = doc.frontmatter.get("bridges")
            if isinstance(bridges_val, list):
                bridge_hints.extend(
                    [b.strip() for b in bridges_val if isinstance(b, str) and b.strip()]
                )

            for i, chunk in enumerate(chunks):
                # Context enrichment
                contextual_text = ""
                try:
                    surrounding = [chunks[i - 1].content] if i > 0 else None
                    ctx = await context_enricher.enrich(
                        content=chunk.content,
                        source_title=doc.frontmatter.get("title", task.file_name),
                        section_title=chunk.section_title,
                        page_range=None,
                        surrounding_chunks=surrounding,
                    )
                    contextual_text = (ctx.contextual_text or "").strip()
                except Exception:
                    pass

                search_text = chunk.content
                if contextual_text:
                    search_text = f"{contextual_text}\n\n{chunk.content}"

                # Tagging
                tag_result = await tagger.tag(chunk.content)

                # Bridge linking
                link_result = await bridge_linker.link_chunk(
                    db=self.db,
                    content=chunk.content,
                    hint_bridge_names=bridge_hints,
                )
                primary_link = next(
                    (l for l in link_result.links if l.role == "primary"), None
                )

                # Embedding
                embeddings = await self.provider.embed([search_text])
                if not embeddings or len(embeddings[0]) != EMBEDDING_DIM:
                    raise ValueError(
                        f"Invalid embedding for chunk {chunk.id}: "
                        f"expected dim {EMBEDDING_DIM}"
                    )

                # Update chunk
                chunk.contextual_text = contextual_text
                chunk.search_text = search_text
                chunk.lvl1 = tag_result.lvl1
                chunk.lvl2 = tag_result.lvl2
                chunk.lvl3 = tag_result.lvl3
                chunk.bridge_id = primary_link.bridge_id if primary_link else None
                chunk.bridge_binding_status = link_result.binding_status
                chunk.embedding = embeddings[0]

                # Bridge links
                for link in link_result.links:
                    self.db.add(
                        ChunkBridgeLink(
                            chunk_id=chunk.id,
                            bridge_id=link.bridge_id,
                            role=link.role,
                            confidence=link.confidence,
                            method=link.method,
                        )
                    )

            self.db.flush()

            # Populate tsvector
            mappings = [
                {
                    "id": c.id,
                    "tsv_text": tokenizer.to_tsvector_text(c.search_text or c.content),
                }
                for c in chunks
            ]
            self.db.execute(
                sql_text(
                    "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
                ),
                mappings,
            )

            task.status = "completed"
            self.db.commit()

        except Exception as e:
            self._fail(task, str(e))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingest_task_service.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add app/services/ingest_task_service.py tests/test_ingest_task_service.py
git commit -m "feat: add IngestTaskService for multi-stage ingest orchestration"
```

---

### Task 7: Create ingest-tasks API endpoints

**Files:**
- Create: `app/api/v1/ingest_tasks.py`
- Modify: `app/api/v1/__init__.py:1-36`
- Create: `tests/test_api_v1_ingest_tasks.py`

**Step 1: Write the smoke test**

Create `tests/test_api_v1_ingest_tasks.py`:

```python
"""Smoke tests for ingest-tasks API endpoints."""
from app.main import app


def test_ingest_tasks_endpoints_exist():
    """Verify ingest-task routes are registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ingest-tasks/presign" in route_paths
    assert "/api/v1/ingest-tasks" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/confirm" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_ingest_tasks.py -v`
Expected: FAIL (routes not found)

**Step 3: Write the API endpoints**

Create `app/api/v1/ingest_tasks.py`:

```python
"""Ingest tasks API endpoints — async multi-stage ingest pipeline."""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas import PaginatedResponse
from app.api.v1.schemas.ingest_task import (
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
)
from app.core.database import get_db
from app.models import User
from app.models.ingest_task import IngestTask
from app.providers import ZhipuProvider
from app.providers.file_parser import FileParserProvider
from app.services.audit_service import AuditService
from app.services.ingest_task_service import IngestTaskService
from app.services.r2_storage import R2StorageService

router = APIRouter(prefix="/ingest-tasks")

ALLOWED_FILE_TYPES = {"pdf", "md"}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "md": "text/markdown",
}


def _get_r2() -> R2StorageService:
    if not R2StorageService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="R2 storage is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env",
        )
    return R2StorageService()


def _run_sync_and_parse(task_id: int, db_url: str):
    """BackgroundTask entry: run sync_and_parse in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        file_parser = FileParserProvider()
        service = IngestTaskService(db=db, r2=r2, provider=provider, file_parser=file_parser)
        asyncio.run(service.sync_and_parse(task_id))
    finally:
        db.close()


def _run_indexing(task_id: int, db_url: str):
    """BackgroundTask entry: run start_indexing in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        service = IngestTaskService(db=db, r2=r2, provider=provider)
        asyncio.run(service.start_indexing(task_id))
    finally:
        db.close()


def _task_to_detail(task: IngestTask) -> dict:
    return {
        "id": task.id,
        "status": task.status,
        "file_name": task.file_name,
        "file_type": task.file_type,
        "file_size": task.file_size,
        "source_id": task.source_id,
        "chunk_count": task.chunk_count,
        "image_count": task.image_count,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.post("/presign", response_model=PresignResponse)
def presign(
    body: PresignRequest,
    r2: R2StorageService = Depends(_get_r2),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a presigned URL for direct file upload to R2."""
    if body.file_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(400, f"Unsupported file_type: {body.file_type}. Allowed: {ALLOWED_FILE_TYPES}")

    # Create task record first to get an ID for the R2 key
    task = IngestTask(
        status="uploading",
        file_name=body.file_name,
        file_type=body.file_type,
        file_size=body.file_size,
        created_by=current_user.id,
    )
    db.add(task)
    db.flush()

    r2_key = f"raw/{task.id}/{body.file_name}"
    task.r2_raw_key = r2_key
    db.commit()

    upload_url = r2.generate_presigned_upload_url(
        r2_key, body.content_type
    )

    return PresignResponse(upload_url=upload_url, r2_key=r2_key)


@router.post("", response_model=IngestTaskDetail)
def create_ingest_task(
    body: IngestTaskCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm upload complete and start parsing. Called after frontend finishes R2 upload."""
    # Find existing task by r2_key
    task = (
        db.query(IngestTask)
        .filter(
            IngestTask.r2_raw_key == body.r2_key,
            IngestTask.created_by == current_user.id,
        )
        .first()
    )

    if task is None:
        raise HTTPException(404, "No matching upload task found for this r2_key")

    if task.status != "uploading":
        raise HTTPException(400, f"Task is in '{task.status}' state, expected 'uploading'")

    task.status = "syncing"
    db.commit()

    AuditService.log(
        db,
        action=AuditService.INGEST,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name, "file_type": task.file_type},
        ip_address=get_client_ip(request),
    )
    db.commit()

    from app.core.config import settings

    background_tasks.add_task(_run_sync_and_parse, task.id, settings.database_url)

    return IngestTaskDetail(**_task_to_detail(task))


@router.get("", response_model=PaginatedResponse[IngestTaskListItem])
def list_ingest_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ingest tasks for current user."""
    query = db.query(IngestTask).filter(IngestTask.created_by == current_user.id)

    if status:
        query = query.filter(IngestTask.status == status)

    total = query.count()
    tasks = (
        query.order_by(IngestTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedResponse(
        items=[IngestTaskListItem(**_task_to_detail(t)) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{task_id}", response_model=IngestTaskDetail)
def get_ingest_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ingest task detail (used for polling status)."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")
    return IngestTaskDetail(**_task_to_detail(task))


@router.post("/{task_id}/confirm", response_model=IngestTaskDetail)
def confirm_ingest_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """User confirms chunks are ready — start indexing (embedding + tagging)."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")

    if task.status != "chunked":
        raise HTTPException(400, f"Task is in '{task.status}' state, expected 'chunked'")

    task.status = "indexing"
    db.commit()

    AuditService.log(
        db,
        action="confirm_ingest",
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        ip_address=get_client_ip(request),
    )
    db.commit()

    from app.core.config import settings

    background_tasks.add_task(_run_indexing, task.id, settings.database_url)

    return IngestTaskDetail(**_task_to_detail(task))


@router.delete("/{task_id}")
def delete_ingest_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel/delete an ingest task."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")

    if task.status in ("syncing", "parsing", "indexing"):
        raise HTTPException(400, f"Cannot delete task in '{task.status}' state — wait for completion or failure")

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name},
        ip_address=get_client_ip(request),
    )
    db.delete(task)
    db.commit()

    # Clean up R2 files (best-effort)
    try:
        if R2StorageService.is_configured():
            r2 = R2StorageService()
            if task.r2_raw_key:
                r2.delete_prefix(f"raw/{task.id}/")
            if task.r2_parsed_prefix:
                r2.delete_prefix(task.r2_parsed_prefix)
    except Exception:
        pass  # R2 cleanup is best-effort

    return {"ok": True}
```

**Step 4: Register router in `app/api/v1/__init__.py`**

Add import (after line 10):

```python
from app.api.v1.ingest_tasks import router as ingest_tasks_router
```

Add to protected block (after line 28):

```python
protected.include_router(ingest_tasks_router)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_v1_ingest_tasks.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/api/v1/ingest_tasks.py app/api/v1/__init__.py tests/test_api_v1_ingest_tasks.py
git commit -m "feat: add ingest-tasks API endpoints with background processing"
```

---

### Task 8: Add frontend TypeScript types and API functions

**Files:**
- Modify: `web/src/lib/types.ts:44-71` (add after existing Ingest section)
- Modify: `web/src/lib/api.ts` (add new functions)

**Step 1: Add TypeScript types**

In `web/src/lib/types.ts`, add after the `IngestResponse` interface (after line 71):

```typescript
// --- Ingest Tasks ---

export type IngestTaskStatus =
  | "uploading"
  | "syncing"
  | "parsing"
  | "chunked"
  | "indexing"
  | "completed"
  | "failed"

export interface IngestTaskItem {
  id: number
  status: IngestTaskStatus
  file_name: string
  file_type: string
  file_size: number | null
  source_id: number | null
  chunk_count: number | null
  image_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface PresignRequest {
  file_name: string
  file_type: string
  file_size: number
  content_type: string
}

export interface PresignResponse {
  upload_url: string
  r2_key: string
}

export interface IngestTaskCreateRequest {
  file_name: string
  file_type: string
  file_size: number
  r2_key: string
}
```

**Step 2: Add API functions**

In `web/src/lib/api.ts`, add after the `ingestDocument` function (after line 214):

```typescript
// --- Ingest Tasks ---

export function presignIngestUpload(
  data: PresignRequest,
): Promise<PresignResponse> {
  return post<PresignResponse>("/ingest-tasks/presign", data)
}

export function createIngestTask(
  data: IngestTaskCreateRequest,
): Promise<IngestTaskItem> {
  return post<IngestTaskItem>("/ingest-tasks", data)
}

export function fetchIngestTasks(params?: {
  page?: number
  page_size?: number
  status?: string
}): Promise<PaginatedResponse<IngestTaskItem>> {
  return get<PaginatedResponse<IngestTaskItem>>("/ingest-tasks", params)
}

export function fetchIngestTask(id: number): Promise<IngestTaskItem> {
  return get<IngestTaskItem>(`/ingest-tasks/${id}`)
}

export function confirmIngestTask(id: number): Promise<IngestTaskItem> {
  return post<IngestTaskItem>(`/ingest-tasks/${id}/confirm`, {})
}

export function deleteIngestTask(id: number): Promise<void> {
  return del(`/ingest-tasks/${id}`)
}

export async function uploadFileToR2(
  url: string,
  file: File,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    xhr.setRequestHeader("Content-Type", contentType)

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100))
        }
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        reject(new Error(`Upload failed: HTTP ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error("Upload failed: network error"))
    xhr.send(file)
  })
}
```

Also add the new type imports at the top of `api.ts`:

```typescript
import type {
  // ... existing imports ...
  IngestTaskCreateRequest,
  IngestTaskItem,
  PresignRequest,
  PresignResponse,
} from "./types"
```

**Step 3: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts
git commit -m "feat: add ingest task types and API functions to frontend"
```

---

### Task 9: Redesign IngestPage with file upload and task list

**Files:**
- Rewrite: `web/src/pages/IngestPage.tsx`
- Create: `web/src/components/ingest/FileUploadZone.tsx`
- Create: `web/src/components/ingest/IngestTaskList.tsx`
- Keep: `web/src/components/ingest/IngestPanel.tsx` (unchanged, used if R2 not configured)

**Step 1: Create FileUploadZone component**

Create `web/src/components/ingest/FileUploadZone.tsx`:

```tsx
import { useCallback, useState } from "react"
import { Upload, Loader2 } from "lucide-react"
import {
  presignIngestUpload,
  createIngestTask,
  uploadFileToR2,
} from "@/lib/api"
import type { IngestTaskItem } from "@/lib/types"

const ALLOWED_EXTENSIONS = [".pdf", ".md"]
const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB

interface FileUploadZoneProps {
  onTaskCreated: (task: IngestTaskItem) => void
}

export function FileUploadZone({ onTaskCreated }: FileUploadZoneProps) {
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const getFileType = (name: string): string | null => {
    const ext = name.toLowerCase().slice(name.lastIndexOf("."))
    if (ext === ".pdf") return "pdf"
    if (ext === ".md") return "md"
    return null
  }

  const getContentType = (fileType: string): string => {
    return fileType === "pdf" ? "application/pdf" : "text/markdown"
  }

  const handleFile = useCallback(async (file: File) => {
    const fileType = getFileType(file.name)
    if (!fileType) {
      setError(`不支持的文件格式。支持: ${ALLOWED_EXTENSIONS.join(", ")}`)
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setError("文件过大，最大支持 100MB")
      return
    }

    setUploading(true)
    setProgress(0)
    setError(null)

    try {
      // 1. Get presigned URL
      const contentType = getContentType(fileType)
      const presign = await presignIngestUpload({
        file_name: file.name,
        file_type: fileType,
        file_size: file.size,
        content_type: contentType,
      })

      // 2. Upload to R2
      await uploadFileToR2(presign.upload_url, file, contentType, setProgress)

      // 3. Notify backend
      const task = await createIngestTask({
        file_name: file.name,
        file_type: fileType,
        file_size: file.size,
        r2_key: presign.r2_key,
      })

      onTaskCreated(task)
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败")
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }, [onTaskCreated])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = "" // reset so same file can be re-selected
  }

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors ${
          dragOver
            ? "border-orange-400 bg-orange-50"
            : "border-slate-200 hover:border-slate-300 bg-white"
        }`}
      >
        <input
          type="file"
          accept=".pdf,.md"
          onChange={handleInputChange}
          className="hidden"
          disabled={uploading}
        />
        {uploading ? (
          <>
            <Loader2 className="h-8 w-8 text-orange-500 animate-spin mb-2" />
            <p className="text-sm text-slate-600">
              上传中 {progress > 0 ? `${progress}%` : ""}
            </p>
          </>
        ) : (
          <>
            <Upload className="h-8 w-8 text-slate-400 mb-2" />
            <p className="text-sm text-slate-600">
              拖拽 PDF 或 Markdown 文件到此处，或点击选择
            </p>
            <p className="text-xs text-slate-400 mt-1">
              支持 .pdf .md 格式，最大 100MB
            </p>
          </>
        )}
      </label>
      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}
    </div>
  )
}
```

**Step 2: Create IngestTaskList component**

Create `web/src/components/ingest/IngestTaskList.tsx`:

```tsx
import { useEffect, useRef } from "react"
import { useNavigate } from "react-router"
import { Loader2, CheckCircle2, XCircle, PenLine, RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { IngestTaskItem, IngestTaskStatus } from "@/lib/types"
import { deleteIngestTask } from "@/lib/api"

interface IngestTaskListProps {
  tasks: IngestTaskItem[]
  onRefresh: () => void
}

const STATUS_LABELS: Record<IngestTaskStatus, string> = {
  uploading: "上传中",
  syncing: "同步中",
  parsing: "解析中",
  chunked: "待确认",
  indexing: "标识中",
  completed: "已完成",
  failed: "失败",
}

function isInProgress(status: IngestTaskStatus): boolean {
  return ["uploading", "syncing", "parsing", "indexing"].includes(status)
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return ""
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function formatTime(isoStr: string): string {
  const d = new Date(isoStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000

  if (diff < 60) return "刚刚"
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return d.toLocaleDateString("zh-CN")
}

function TaskStatusBadge({ status }: { status: IngestTaskStatus }) {
  if (isInProgress(status)) {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-orange-600">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "chunked") {
    return (
      <span className="text-sm font-medium text-blue-600">
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-green-600">
        <CheckCircle2 className="h-3.5 w-3.5" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  // failed
  return (
    <span className="inline-flex items-center gap-1 text-sm text-red-600">
      <XCircle className="h-3.5 w-3.5" />
      {STATUS_LABELS[status]}
    </span>
  )
}

function TaskRow({ task, onRefresh }: { task: IngestTaskItem; onRefresh: () => void }) {
  const navigate = useNavigate()

  async function handleDelete() {
    if (!confirm("确定删除此任务？")) return
    await deleteIngestTask(task.id)
    onRefresh()
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-800 truncate">
            {task.file_name}
          </span>
          <TaskStatusBadge status={task.status} />
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-400">
          <span>{formatTime(task.created_at)}</span>
          {task.file_size && (
            <>
              <span>·</span>
              <span>{formatSize(task.file_size)}</span>
            </>
          )}
          {task.chunk_count !== null && (
            <>
              <span>·</span>
              <span>{task.chunk_count} 个知识块</span>
            </>
          )}
          {task.image_count > 0 && (
            <>
              <span>·</span>
              <span>{task.image_count} 张图</span>
            </>
          )}
        </div>
        {task.status === "failed" && task.error_message && (
          <p className="text-xs text-red-500 mt-1 truncate">{task.error_message}</p>
        )}
      </div>

      <div className="flex items-center gap-2 ml-4 shrink-0">
        {task.status === "chunked" && task.source_id && (
          <Button
            size="sm"
            variant="outline"
            className="gap-1"
            onClick={() => navigate(`/sources/${task.source_id}/chunks/edit`)}
          >
            <PenLine className="h-3 w-3" />
            去校对
          </Button>
        )}
        {task.status === "failed" && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleDelete}
            className="gap-1 text-red-600 hover:text-red-700"
          >
            <RotateCw className="h-3 w-3" />
            删除
          </Button>
        )}
      </div>
    </div>
  )
}

export function IngestTaskList({ tasks, onRefresh }: IngestTaskListProps) {
  // Auto-poll when any task is in progress
  const hasInProgress = tasks.some((t) => isInProgress(t.status))
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (hasInProgress) {
      intervalRef.current = setInterval(onRefresh, 3000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [hasInProgress, onRefresh])

  if (tasks.length === 0) {
    return (
      <div className="text-center text-sm text-slate-400 py-8">
        暂无入库任务
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white divide-y divide-slate-100">
      {tasks.map((task) => (
        <TaskRow key={task.id} task={task} onRefresh={onRefresh} />
      ))}
    </div>
  )
}
```

**Step 3: Rewrite IngestPage**

Rewrite `web/src/pages/IngestPage.tsx`:

```tsx
import { useCallback, useState, useEffect } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { FileUploadZone } from "@/components/ingest/FileUploadZone"
import { IngestTaskList } from "@/components/ingest/IngestTaskList"
import { fetchIngestTasks } from "@/lib/api"
import type { IngestTaskItem } from "@/lib/types"

export function Component() {
  const [tasks, setTasks] = useState<IngestTaskItem[]>([])
  const [loading, setLoading] = useState(true)

  const loadTasks = useCallback(async () => {
    try {
      const res = await fetchIngestTasks({ page: 1, page_size: 50 })
      setTasks(res.items)
    } catch {
      // silent — page still functional
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  const handleTaskCreated = (task: IngestTaskItem) => {
    setTasks((prev) => [task, ...prev])
  }

  return (
    <>
      <PageHeader title="入库" description="上传文档到知识库" />
      <main className="p-6 space-y-6">
        <FileUploadZone onTaskCreated={handleTaskCreated} />

        <div>
          <h2 className="text-sm font-medium text-slate-700 mb-3">入库任务</h2>
          {loading ? (
            <div className="text-center text-sm text-slate-400 py-8">加载中…</div>
          ) : (
            <IngestTaskList tasks={tasks} onRefresh={loadTasks} />
          )}
        </div>
      </main>
    </>
  )
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 5: Verify build succeeds**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add web/src/pages/IngestPage.tsx web/src/components/ingest/FileUploadZone.tsx web/src/components/ingest/IngestTaskList.tsx
git commit -m "feat: redesign IngestPage with file upload and async task tracking"
```

---

### Task 10: Update CLAUDE.md and migration script

**Files:**
- Modify: `CLAUDE.md`
- Modify: `scripts/migrate_db.py`

**Step 1: Update CLAUDE.md**

Add to the "Database Schema Management" section:
- Update "Current version: 5" → "Current version: 6 — v6 (ingest_tasks)"

Add to the "Data Model" section:
- `ingest_tasks` — 异步入库任务（status/file_name/file_type/r2_raw_key/zhipu_task_id/source_id）

Add to the "API Endpoints" section:
- CRUD: `/api/v1/ingest-tasks`（presign, create, list, detail, confirm, delete）

Add to the "Gotchas" section:
- `IngestTaskService` background tasks 使用独立的 `SessionLocal()` — 不能复用请求级的 db session
- R2 presigned URL 有效期 1 小时 — 前端需在获取后尽快完成上传

**Step 2: Add v6 migration to `scripts/migrate_db.py`**

Add to the migration phases, after Phase 2 (add columns), a new step to ensure `ingest_tasks` table exists:

```python
# In Phase 1 (after create_all), the table is already created.
# In _stamp_schema_version, bump to version 6 if not already.
```

The migration script calls `Base.metadata.create_all()` which will handle the new table.
Just update `_stamp_schema_version` calls to support version 6.

**Step 3: Commit**

```bash
git add CLAUDE.md scripts/migrate_db.py
git commit -m "docs: update CLAUDE.md for async ingest pipeline and schema v6"
```

---

### Task 11: End-to-end verification

**Step 1: Run all unit tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All pass

**Step 2: Run TypeScript check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Run frontend build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Start backend and verify migration**

Run: `uvicorn app.main:app --reload`
Expected: Schema migrates to v6, startup succeeds.

**Step 5: Verify API docs**

Navigate to `http://localhost:8000/docs` and confirm `/api/v1/ingest-tasks/*` endpoints appear.

**Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address issues found in e2e verification"
```
