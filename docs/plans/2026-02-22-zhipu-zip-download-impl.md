# Zhipu ZIP 下载解析 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PDF 入库失败 — 从智谱返回的 zip 包中提取 markdown 内容，并将 zip 存档到 R2。

**Architecture:** 修改 `_parse_pdf` 优先从 `download_url` 获取内容。`_download_and_store_parsed_assets` 下载 zip，存档到 R2，提取 `result.md` 和图片，返回 markdown 文本。

**Tech Stack:** Python, httpx, zipfile, R2 (boto3/S3)

---

### Task 1: 测试 — zip 下载解析正常路径

**Files:**
- Modify: `tests/test_ingest_task_service.py`

**Step 1: 写测试**

在文件末尾添加：

```python
@pytest.mark.asyncio
async def test_parse_pdf_with_download_url_extracts_markdown():
    """PDF parsing via download_link: download zip, archive to R2, extract markdown."""
    import io
    import zipfile
    from unittest.mock import call
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
    mock_parse_result.download_url = "https://example.com/result.zip"
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=10,
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

            with patch("httpx.AsyncClient") as mock_httpx_cls:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.content = zip_bytes
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_httpx_cls.return_value = mock_client

                await service.sync_and_parse(task_id=10)

    # Verify parsed_content came from zip
    assert task.parsed_content == "# Extracted\n\nContent from zip"
    assert task.status == "chunked"

    # Verify R2 uploads: archive.zip + images/fig1.png + result.md
    upload_keys = [c.args[0] for c in mock_r2.upload.call_args_list]
    assert "parsed/10/archive.zip" in upload_keys
    assert "parsed/10/images/fig1.png" in upload_keys
    assert "parsed/10/result.md" in upload_keys
```

**Step 2: 跑测试确认失败**

Run: `pytest tests/test_ingest_task_service.py::test_parse_pdf_with_download_url_extracts_markdown -v`
Expected: FAIL（`_download_and_store_parsed_assets` 是 pass，返回 None）

**Step 3: Commit 测试**

```bash
git add tests/test_ingest_task_service.py
git commit -m "test: add zip download extraction test for PDF ingest"
```

---

### Task 2: 测试 — zip 中无 markdown 文件时报错

**Files:**
- Modify: `tests/test_ingest_task_service.py`

**Step 1: 写测试**

```python
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
    mock_parse_result.download_url = "https://example.com/result.zip"
    mock_file_parser.poll_until_done.return_value = mock_parse_result

    task = IngestTask(
        id=11,
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

    with patch("httpx.AsyncClient") as mock_httpx_cls:
        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        await service.sync_and_parse(task_id=11)

    assert task.status == "failed"
    assert "No markdown file" in task.error_message
```

**Step 2: 跑测试确认失败**

Run: `pytest tests/test_ingest_task_service.py::test_parse_pdf_zip_without_markdown_fails -v`
Expected: FAIL

**Step 3: Commit 测试**

```bash
git add tests/test_ingest_task_service.py
git commit -m "test: add zip-without-markdown error case for PDF ingest"
```

---

### Task 3: 实现 `_download_and_store_parsed_assets`

**Files:**
- Modify: `app/services/ingest_task_service.py:122-129`（替换 TODO 方法）
- Modify: `app/services/ingest_task_service.py:1`（添加 import）

**Step 1: 添加 imports**

在文件顶部 imports 区域添加：

```python
import io
import zipfile

import httpx
```

**Step 2: 实现方法**

替换 `_download_and_store_parsed_assets` 方法（当前第 122-129 行）：

```python
    async def _download_and_store_parsed_assets(
        self, task: IngestTask, download_url: str
    ) -> str:
        """Download zip from Zhipu, archive to R2, extract markdown and images."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(download_url, timeout=120.0)
            resp.raise_for_status()
            zip_bytes = resp.content

        # Archive raw zip to R2
        self.r2.upload(
            f"parsed/{task.id}/archive.zip",
            zip_bytes,
            "application/zip",
        )

        # Extract markdown and images
        parsed_md = ""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_files:
                raise ValueError("No markdown file found in Zhipu zip archive")
            parsed_md = zf.read(md_files[0]).decode("utf-8")

            for name in zf.namelist():
                if "/" in name and not name.endswith("/"):
                    dirname = name.split("/")[0]
                    if dirname == "images":
                        self.r2.upload(
                            f"parsed/{task.id}/{name}",
                            zf.read(name),
                            "image/png",
                        )

        return parsed_md
```

**Step 3: 修改 `_parse_pdf` 调用逻辑**

将 `_parse_pdf` 中当前的逻辑（约第 109-120 行）：

```python
        parsed_md = result.content or ""

        if result.download_url:
            await self._download_and_store_parsed_assets(task, result.download_url)

        task.parsed_content = parsed_md
```

替换为：

```python
        if result.download_url:
            parsed_md = await self._download_and_store_parsed_assets(
                task, result.download_url
            )
        elif result.content:
            parsed_md = result.content
        else:
            raise ValueError(
                "Zhipu returned neither content nor download_url"
            )

        task.parsed_content = parsed_md
```

**Step 4: 跑所有测试**

Run: `pytest tests/test_ingest_task_service.py -v`
Expected: 全部 PASS（含 Task 1 和 Task 2 的新测试）

**Step 5: 也要确认既有 PDF 测试仍然通过**

既有测试 `test_sync_and_parse_pdf_calls_zhipu` 使用 `content="# Parsed PDF..."` + `download_url=None`，走 `elif result.content` 分支，应该不受影响。

**Step 6: Commit**

```bash
git add app/services/ingest_task_service.py
git commit -m "feat: implement Zhipu zip download, archive to R2, extract markdown"
```

---

### Task 4: 修复既有测试适配

**注意：** 既有测试 `test_sync_and_parse_pdf_calls_zhipu` 中 `mock_parse_result.download_url = None`，新逻辑走 `elif result.content` 分支，应该无需改动。但如果测试因 import 变化等原因失败，在此 task 修复。

**Step 1: 跑全量测试**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 2: Commit（如有改动）**

```bash
git commit -am "fix: adjust existing tests for zip download changes"
```

---

### Task 5: 服务器端验证

**Step 1: 部署到服务器**

Push 到 main 触发自动部署（或手动部署）。

**Step 2: 创建新的 PDF 入库任务测试**

通过前端上传一个 PDF 文件，观察 task 状态从 `syncing → parsing → chunked`。

**Step 3: 验证 R2 存档**

SSH 到服务器确认 R2 中新 task 的 `parsed/{id}/archive.zip` 和 `parsed/{id}/result.md` 都存在。

**Step 4: 可选 — 重试 task #4**

如果需要，可以手动将 task #4 状态重置为 `pending` 并重新触发。
