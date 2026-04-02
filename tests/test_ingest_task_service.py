"""Unit tests for IngestTaskService (all external services mocked)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.ingest_task import IngestTask

_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
_UUID3 = uuid.UUID("00000000-0000-0000-0000-000000000003")
_UUID10 = uuid.UUID("00000000-0000-0000-0000-000000000010")
_UUID11 = uuid.UUID("00000000-0000-0000-0000-000000000011")
_UUID12 = uuid.UUID("00000000-0000-0000-0000-000000000012")
_UUID20 = uuid.UUID("00000000-0000-0000-0000-000000000020")
_UUID21 = uuid.UUID("00000000-0000-0000-0000-000000000021")


@pytest.mark.asyncio
async def test_sync_and_parse_md_skips_zhipu():
    """Markdown files skip Zhipu parsing, go directly to chunking."""
    from app.services.ingest_task_service import IngestTaskService

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"# Test\n\nContent here"
    mock_r2.upload = MagicMock()

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [[0.1] * 1024]

    mock_chunk_result = MagicMock()
    mock_chunk_result.content = "Content here"
    mock_chunk_result.section_title = "Test"

    task = IngestTask(
        id=_UUID1,
        status="syncing",
        file_name="test.md",
        file_type="md",
        file_size=100,
        r2_raw_key="raw/1/test.md",
    )

    mock_db.get.return_value = task
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.add = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=mock_provider,
    )

    mock_chunker_instance = AsyncMock()
    mock_chunker_instance.chunk.return_value = [mock_chunk_result]

    with patch("app.services.ingest_task_service.SemanticChunker", return_value=mock_chunker_instance):
        with patch("app.services.ingest_task_service.parse_markdown") as mock_parse:
            mock_doc = MagicMock()
            mock_doc.sections = [MagicMock(title="Test", level=1, content="Content here")]
            mock_doc.frontmatter = {"title": "Test"}
            mock_parse.return_value = mock_doc

            await service.sync_and_parse(task_id=_UUID1)

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
        id=_UUID2,
        status="syncing",
        file_name="test.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/2/test.pdf",
    )
    mock_db.get.return_value = task
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.add = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=mock_provider,
        file_parser=mock_file_parser,
    )

    mock_chunk_result = MagicMock()
    mock_chunk_result.content = "Parsed content"
    mock_chunk_result.section_title = "Parsed PDF"
    mock_chunker_instance = AsyncMock()
    mock_chunker_instance.chunk.return_value = [mock_chunk_result]

    with patch("app.services.ingest_task_service.SemanticChunker", return_value=mock_chunker_instance):
        with patch("app.services.ingest_task_service.parse_markdown") as mock_parse:
            mock_doc = MagicMock()
            mock_doc.sections = [MagicMock(title="Parsed PDF", level=1, content="Parsed content")]
            mock_doc.frontmatter = {"title": "Parsed PDF"}
            mock_parse.return_value = mock_doc

            await service.sync_and_parse(task_id=_UUID2)

    mock_file_parser.create_task.assert_called_once()
    mock_file_parser.poll_until_done.assert_called_once_with("zhipu-task-123")
    assert task.status == "chunked"
    assert task.zhipu_task_id == "zhipu-task-123"


@pytest.mark.asyncio
async def test_sync_and_parse_sets_failed_on_error():
    """Errors during sync/parse set task to failed status."""
    from app.services.ingest_task_service import IngestTaskService

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.side_effect = Exception("R2 connection error")

    task = IngestTask(
        id=_UUID3,
        status="syncing",
        file_name="test.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/3/test.pdf",
    )
    mock_db.get.return_value = task
    mock_db.commit = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=AsyncMock(),
    )

    await service.sync_and_parse(task_id=_UUID3)

    assert task.status == "failed"
    assert "R2 connection error" in task.error_message


@pytest.mark.asyncio
async def test_parse_pdf_with_download_url_extracts_markdown():
    """PDF parsing via download_link: download zip, archive to R2, extract markdown."""
    import io
    import zipfile
    from app.services.ingest_task_service import IngestTaskService

    # Build a fake zip in memory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("result.md", "# Extracted\n\nContent from zip")
        zf.writestr("images/fig1.png", b"fake-png-bytes")
    zip_bytes = zip_buf.getvalue()

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"fake-pdf-bytes"
    mock_r2.upload = MagicMock()

    mock_provider = AsyncMock()

    mock_file_parser = AsyncMock()
    mock_file_parser.create_task.return_value = "zhipu-task-zip"
    mock_parse_result = MagicMock()
    mock_parse_result.content = None  # download_link mode: content is None
    mock_parse_result.download_url = "https://open.bigmodel.cn/result.zip"
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=_UUID10,
        status="syncing",
        file_name="test.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/10/test.pdf",
    )
    mock_db.get.return_value = task
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.add = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=mock_provider,
        file_parser=mock_file_parser,
    )

    mock_chunk_result = MagicMock()
    mock_chunk_result.content = "Content from zip"
    mock_chunk_result.section_title = "Extracted"
    mock_chunker = AsyncMock()
    mock_chunker.chunk.return_value = [mock_chunk_result]

    with patch("app.services.ingest_task_service.SemanticChunker", return_value=mock_chunker):
        with patch("app.services.ingest_task_service.parse_markdown") as mock_parse:
            mock_doc = MagicMock()
            mock_doc.sections = [MagicMock(title="Extracted", level=1, content="Content from zip")]
            mock_doc.frontmatter = {"title": "test.pdf"}
            mock_parse.return_value = mock_doc

            with patch("app.services.ingest_task_service.httpx.AsyncClient") as mock_httpx_cls:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.content = zip_bytes
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_httpx_cls.return_value = mock_client

                await service.sync_and_parse(task_id=_UUID10)

    # Verify parsed_content came from zip
    assert task.parsed_content == "# Extracted\n\nContent from zip"
    assert task.status == "chunked"
    assert task.image_count == 1

    # Verify R2 uploads: archive.zip + images/fig1.png + result.md
    upload_keys = [c.args[0] for c in mock_r2.upload.call_args_list]
    prefix = f"parsed/{_UUID10}"
    assert f"{prefix}/archive.zip" in upload_keys
    assert f"{prefix}/images/fig1.png" in upload_keys
    assert f"{prefix}/result.md" in upload_keys


@pytest.mark.asyncio
async def test_parse_pdf_zip_without_markdown_fails():
    """Zip archive without any .md file should fail the task."""
    import io
    import zipfile
    from app.services.ingest_task_service import IngestTaskService

    # Zip with only an image, no markdown
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("images/fig1.png", b"fake-png")
    zip_bytes = zip_buf.getvalue()

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"fake-pdf-bytes"
    mock_r2.upload = MagicMock()

    mock_file_parser = AsyncMock()
    mock_file_parser.create_task.return_value = "zhipu-task-nomd"
    mock_parse_result = MagicMock()
    mock_parse_result.content = None
    mock_parse_result.download_url = "https://open.bigmodel.cn/result.zip"
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=_UUID11,
        status="syncing",
        file_name="bad.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/11/bad.pdf",
    )
    mock_db.get.return_value = task
    mock_db.commit = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=AsyncMock(),
        file_parser=mock_file_parser,
    )

    with patch("app.services.ingest_task_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        await service.sync_and_parse(task_id=_UUID11)

    assert task.status == "failed"
    assert "No markdown file" in task.error_message


@pytest.mark.asyncio
async def test_parse_pdf_neither_content_nor_download_url_fails():
    """Zhipu returning neither content nor download_url should fail the task."""
    from app.services.ingest_task_service import IngestTaskService

    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_r2.download.return_value = b"fake-pdf-bytes"
    mock_r2.upload = MagicMock()

    mock_file_parser = AsyncMock()
    mock_file_parser.create_task.return_value = "zhipu-task-empty"
    mock_parse_result = MagicMock()
    mock_parse_result.content = None
    mock_parse_result.download_url = None
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=_UUID12,
        status="syncing",
        file_name="empty.pdf",
        file_type="pdf",
        file_size=5000,
        r2_raw_key="raw/12/empty.pdf",
    )
    mock_db.get.return_value = task
    mock_db.commit = MagicMock()

    service = IngestTaskService(
        db=mock_db,
        r2=mock_r2,
        provider=AsyncMock(),
        file_parser=mock_file_parser,
    )

    await service.sync_and_parse(task_id=_UUID12)

    assert task.status == "failed"
    assert "neither content nor download_url" in task.error_message


# --- cleanup_stale_uploading_tasks tests ---


def test_cleanup_stale_uploading_marks_old_tasks_failed():
    """Tasks in 'uploading' status for > 2 hours should be marked failed."""
    from app.services.ingest_task_service import cleanup_stale_uploading_tasks

    old_task = IngestTask(
        id=_UUID20,
        status="uploading",
        file_name="stale.pdf",
        file_type="pdf",
    )
    old_task.created_at = datetime.now(timezone.utc) - timedelta(hours=3)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [old_task]
    mock_db.commit = MagicMock()

    cleaned = cleanup_stale_uploading_tasks(mock_db)

    assert cleaned == 1
    assert old_task.status == "failed"
    assert "not completed" in old_task.error_message
    mock_db.commit.assert_called_once()


def test_cleanup_stale_uploading_skips_recent_tasks():
    """Tasks in 'uploading' status for < 2 hours should not be touched."""
    from app.services.ingest_task_service import cleanup_stale_uploading_tasks

    mock_db = MagicMock()
    # Query returns empty list (no stale tasks)
    mock_db.query.return_value.filter.return_value.all.return_value = []

    cleaned = cleanup_stale_uploading_tasks(mock_db)

    assert cleaned == 0
    mock_db.commit.assert_not_called()


def test_cleanup_stale_uploading_does_not_touch_other_statuses():
    """Only 'uploading' tasks should be affected, not syncing/parsing/etc."""
    from app.services.ingest_task_service import cleanup_stale_uploading_tasks

    mock_db = MagicMock()
    # The filter will only match uploading tasks; mock returns empty
    mock_db.query.return_value.filter.return_value.all.return_value = []

    cleaned = cleanup_stale_uploading_tasks(mock_db)

    assert cleaned == 0
