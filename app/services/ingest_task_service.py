"""Ingest task orchestration service.

Coordinates R2 storage, Zhipu file parsing, chunking, and indexing
across the async multi-stage ingest pipeline.
"""
import io
import mimetypes
import posixpath
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.core.constants import EMBEDDING_DIM
from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.taxonomy_loader import load_taxonomy_snapshot
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.ingest_task import RUNNING_STATUSES, IngestTask
from app.providers.base import LLMProvider
from app.providers.file_parser import FileParserProvider
from app.services.audit_service import AuditService
from app.services.bridge_linker import BridgeLinker
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.kp_resolver import resolve_knowledge_point_id
from app.services.markdown_parser import parse_markdown
from app.services.r2_storage import R2StorageService
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path


STALE_UPLOADING_HOURS = 2
"""Tasks stuck in 'uploading' status longer than this are marked failed."""


def cleanup_stale_uploading_tasks(db: Session) -> int:
    """Mark uploading tasks older than STALE_UPLOADING_HOURS as failed.

    Returns the number of tasks cleaned up.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_UPLOADING_HOURS)
    stale_tasks = (
        db.query(IngestTask)
        .filter(
            IngestTask.status == "uploading",
            IngestTask.created_at < cutoff,
        )
        .all()
    )

    for task in stale_tasks:
        task.status = "failed"
        task.error_message = (
            f"Upload not completed within {STALE_UPLOADING_HOURS} hours"
        )

    if stale_tasks:
        db.commit()
        logger.info(
            "Cleaned up %d stale uploading task(s) older than %d hours",
            len(stale_tasks),
            STALE_UPLOADING_HOURS,
        )

    return len(stale_tasks)


def cleanup_stale_running_tasks(db: Session, max_age_minutes: int = 60) -> int:
    """Mark tasks stuck in RUNNING_STATUSES longer than ``max_age_minutes``
    as failed so the ingest scheduler can reclaim their capacity slot.

    A task can get stuck if the dispatched async runner crashed or was
    killed without writing back ``task.status``. Left alone these tasks
    block the global concurrency budget and starve queued work. Issue #152.

    ``max_age_minutes`` defaults to 60 — 2x the observed real-world p95
    (程阳永济桥 took 32.8 min to completion with retries).

    Returns the number of tasks cleaned up.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    stale_tasks = (
        db.query(IngestTask)
        .filter(
            IngestTask.status.in_(RUNNING_STATUSES),
            IngestTask.updated_at < cutoff,
        )
        .all()
    )

    for task in stale_tasks:
        previous_status = task.status
        previous_updated_at = task.updated_at
        task.status = "failed"
        task.error_message = (
            f"Task exceeded max runtime of {max_age_minutes} minutes "
            f"(stuck in '{previous_status}' since {previous_updated_at.isoformat()})"
        )

    if stale_tasks:
        db.commit()
        logger.info(
            "Cleaned up %d stale running task(s) older than %d minutes",
            len(stale_tasks),
            max_age_minutes,
        )

    return len(stale_tasks)


class IngestTaskService:
    """Orchestrates the multi-stage ingest pipeline."""

    def __init__(
        self,
        db: Session,
        r2: R2StorageService,
        provider: LLMProvider,
        file_parser: FileParserProvider | None = None,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ):
        self.db = db
        self.r2 = r2
        self.provider = provider
        self.file_parser = file_parser or FileParserProvider()
        self.user_id = user_id
        self.ip_address = ip_address

    def _get_task(self, task_id: uuid.UUID) -> IngestTask:
        task = self.db.get(IngestTask, task_id)
        if task is None:
            raise ValueError(f"IngestTask {task_id} not found")
        return task

    @staticmethod
    def _format_exception(exc: BaseException) -> str:
        """Build a non-empty, typed error message for ``task.error_message``.

        ``str(httpx.ReadTimeout())`` and some other httpx exceptions return
        an empty string — writing that to ``task.error_message`` leaves
        the admin UI showing a blank failure reason. Always prefix with
        the exception class name so the message is never empty.
        """
        body = str(exc).strip()
        cls = type(exc).__name__
        return f"{cls}: {body}" if body else cls

    def _fail(self, task: IngestTask, error: str | BaseException) -> None:
        """Mark a task as failed, with a last-ditch raw-UPDATE recovery path.

        Split into two commits so a failure persisting the audit log does
        not un-mark the task:

        1. Primary commit: task.status = 'failed' + error_message. If this
           fails (DB blip, deadlock, stale session), a fresh SessionLocal
           runs a raw ``UPDATE`` as a last-ditch recovery. Capacity is
           reclaimed even in the worst case.
        2. Audit commit: best-effort. A failure here does NOT re-raise or
           un-fail the task — just logs a warning.

        Without (1) the #153 silent-failure review's C2 finding bites us:
        a single ``db.commit()`` failure leaves the task perpetually stuck
        in a running state until the 60-min stale reaper intervenes.
        """
        error_msg = (
            self._format_exception(error)
            if isinstance(error, BaseException)
            else (error or "Unknown error")
        )
        primary_committed = False
        try:
            task.status = "failed"
            task.error_message = error_msg
            self.db.commit()
            primary_committed = True
        except Exception:
            self.db.rollback()
            logger.exception(
                "IngestTask %s: primary fail-commit raised; "
                "attempting out-of-band raw UPDATE recovery",
                task.id,
            )

        if not primary_committed:
            # Last-ditch recovery: brand-new session, raw SQL, no ORM state.
            try:
                recovery_db = SessionLocal()
                try:
                    recovery_db.execute(
                        sql_text(
                            "UPDATE ingest_tasks "
                            "SET status = 'failed', "
                            "    error_message = :msg, "
                            "    updated_at = now() "
                            "WHERE id = :id"
                        ),
                        {"msg": error_msg[:1000], "id": task.id},
                    )
                    recovery_db.commit()
                    logger.error(
                        "IngestTask %s recovered via out-of-band UPDATE: %s",
                        task.id,
                        error_msg,
                    )
                finally:
                    recovery_db.close()
            except Exception:
                # The stale reaper (cleanup_stale_running_tasks) is the
                # last backstop — a task left in running state for 60min
                # will eventually be reclaimed.
                logger.exception(
                    "IngestTask %s: out-of-band recovery ALSO failed; "
                    "stale reaper is the final backstop",
                    task.id,
                )
            return

        # Primary commit succeeded — audit log is best-effort.
        try:
            self._audit(task, AuditService.INGEST_FAILED, {"error": error_msg[:500]})
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception(
                "IngestTask %s: audit log failed (task already marked failed)",
                task.id,
            )
        logger.error("IngestTask %s failed: %s", task.id, error_msg)

    def _audit(self, task: IngestTask, action: str, detail: dict | None = None) -> None:
        """Log an audit event for this task."""
        AuditService.log(
            self.db,
            action=action,
            resource_type="ingest_task",
            user_id=self.user_id or task.created_by,
            resource_id=str(task.id),
            detail=detail,
            ip_address=self.ip_address,
        )

    async def sync_and_parse(self, task_id: uuid.UUID) -> None:
        """Stage: syncing -> parsing -> chunked.

        For PDF: download from R2 -> submit to Zhipu -> poll -> chunk.
        For MD: download from R2 -> chunk directly.
        """
        task = self._get_task(task_id)

        try:
            task.status = "syncing"
            self.db.commit()

            file_bytes = self.r2.download(task.r2_raw_key)

            if task.file_type == "pdf":
                await self._parse_pdf(task, file_bytes)
            else:
                task.parsed_content = file_bytes.decode("utf-8")
                task.r2_parsed_prefix = f"parsed/{task.id}/"
                self.r2.upload(
                    f"parsed/{task.id}/result.md",
                    task.parsed_content.encode("utf-8"),
                    "text/markdown",
                )

            await self._chunk(task)

            task.status = "chunked"
            self.db.commit()

            self._audit(task, AuditService.INGEST_PARSE_DONE, {"chunk_count": task.chunk_count})
            self.db.commit()

        except Exception as e:
            self._fail(task, e)

    async def _parse_pdf(self, task: IngestTask, file_bytes: bytes) -> None:
        """Submit PDF to Zhipu and poll for result."""
        task.status = "parsing"
        self.db.commit()

        self._audit(task, AuditService.INGEST_PARSE_START)
        self.db.commit()

        zhipu_task_id = await self.file_parser.create_task(
            file_bytes=file_bytes,
            file_name=task.file_name,
            file_type="pdf",
        )
        task.zhipu_task_id = zhipu_task_id
        self.db.commit()

        result = await self.file_parser.poll_until_done(zhipu_task_id)

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
        task.r2_parsed_prefix = f"parsed/{task.id}/"
        self.r2.upload(
            f"parsed/{task.id}/result.md",
            parsed_md.encode("utf-8"),
            "text/markdown",
        )

    async def _download_and_store_parsed_assets(
        self, task: IngestTask, download_url: str
    ) -> str:
        """Download zip from Zhipu, archive to R2, extract markdown and images."""
        ALLOWED_ZHIPU_HOSTS = {
            "open.bigmodel.cn",
            "cdn.bigmodel.cn",
            "file-extract.cn-wlcb.ufileos.com",
        }
        parsed = urlparse(download_url)
        if parsed.scheme not in ("https", "http") or parsed.hostname not in ALLOWED_ZHIPU_HOSTS:
            raise ValueError(f"Untrusted download_url: scheme={parsed.scheme} host={parsed.hostname}")

        logger.info("IngestTask %s: downloading zip from Zhipu", task.id)
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
        logger.info("IngestTask %s: zip archived (%d bytes)", task.id, len(zip_bytes))

        # Extract markdown and images
        parsed_md = ""
        image_count = 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_files:
                raise ValueError("No markdown file found in Zhipu zip archive")
            parsed_md = zf.read(md_files[0]).decode("utf-8")

            for name in zf.namelist():
                # Sanitize zip entry path to prevent Zip Slip attacks
                safe_name = posixpath.normpath(name)
                if safe_name.startswith("..") or safe_name.startswith("/"):
                    logger.warning("IngestTask %s: skipping suspicious zip entry: %s", task.id, name)
                    continue
                if "/" in safe_name and not safe_name.endswith("/"):
                    dirname = safe_name.split("/")[0]
                    if dirname == "images":
                        content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
                        self.r2.upload(
                            f"parsed/{task.id}/{safe_name}",
                            zf.read(name),
                            content_type,
                        )
                        image_count += 1

        task.image_count = image_count
        logger.info(
            "IngestTask %s: extracted %s, %d images",
            task.id, md_files[0], image_count,
        )
        return parsed_md

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

        source = Source(type="document", title=title)
        self.db.add(source)
        self.db.flush()
        task.source_id = source.id

        # Use a zero vector as placeholder; real embedding is set during indexing.
        placeholder_embedding = [0.0] * EMBEDDING_DIM

        for chunk_result in chunk_results:
            chunk = Chunk(
                source_id=source.id,
                content=chunk_result.content,
                section_title=chunk_result.section_title,
                embedding=placeholder_embedding,
                needs_reindex=True,
            )
            self.db.add(chunk)

        self.db.flush()
        task.chunk_count = len(chunk_results)

    async def start_indexing(self, task_id: uuid.UUID) -> None:
        """Stage: indexing -> completed.

        After user confirms chunks via ChunkEditor, run embedding + tagging
        + tsv + bridge linking.
        """
        task = self._get_task(task_id)

        try:
            task.status = "indexing"
            self.db.commit()

            chunks = (
                self.db.query(Chunk)
                .filter(Chunk.source_id == task.source_id)
                .order_by(Chunk.id)
                .all()
            )

            if not chunks:
                raise ValueError(f"No chunks found for source {task.source_id}")

            context_enricher = ContextEnricher()
            # Fresh taxonomy per task: admin edits committed before this call
            # are visible immediately. Bypasses _cache so there is no cross-
            # worker staleness window.
            tagger = MetadataTagger(
                taxonomy=load_taxonomy_snapshot(self.db),
            )
            bridge_linker = BridgeLinker()
            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())

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

            # Per-chunk commit pattern: each chunk's ORM changes + tsv UPDATE
            # live in their own short transaction. This avoids the long-txn
            # trap where Postgres ``now()`` returns transaction-start time,
            # causing ``updated_at`` to lie about the real commit wall-clock —
            # which in turn caused ``cleanup_stale_running_tasks`` to target
            # tasks that were actively making progress. See #158 RCA:
            # a 1.5h single transaction let the stale reaper flip the task
            # to 'failed' mid-flight, then the runner's final commit
            # overwrote status='completed' but left the reaper's error_message
            # in place, producing a zombie "completed-with-error" row.
            for i, chunk in enumerate(chunks):
                # Track whether any LLM enrichment step degraded to fallback.
                # Degraded chunks get ``needs_reindex=True`` so the daily
                # reindex cron picks them up once Zhipu is healthy.
                chunk_degraded = False

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
                except Exception as e:
                    logger.warning(
                        "Context enrichment failed for chunk %d/%d (task %s): %s",
                        i + 1,
                        len(chunks),
                        task.id,
                        e,
                    )
                    chunk_degraded = True

                search_text = chunk.content
                if contextual_text:
                    search_text = f"{contextual_text}\n\n{chunk.content}"

                # Tagger failure → null taxonomy. Chunk is still searchable
                # via vector + FTS, just not filterable by lvl1/lvl2/lvl3.
                # Reindex cron will retry when Zhipu recovers.
                try:
                    tag_result = await tagger.tag(chunk.content)
                except Exception as e:
                    logger.warning(
                        "Tagger failed for chunk %d/%d (task %s): %s — continuing with null taxonomy",
                        i + 1, len(chunks), task.id, e,
                    )
                    from app.services.tagger import TagResult
                    tag_result = TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
                    chunk_degraded = True

                # Bridge linker failure → no bridge binding. Chunk becomes
                # orphan content until reindex. Still searchable.
                try:
                    link_result = await bridge_linker.link_chunk(
                        db=self.db,
                        content=chunk.content,
                        hint_bridge_names=bridge_hints,
                    )
                except Exception as e:
                    logger.warning(
                        "Bridge linker failed for chunk %d/%d (task %s): %s — continuing without bridge binding",
                        i + 1, len(chunks), task.id, e,
                    )
                    from app.services.bridge_linker import BridgeLinkingResult
                    link_result = BridgeLinkingResult(
                        primary_bridge_name=None,
                        secondary_bridge_names=[],
                        candidate_bridge_names=[],
                        binding_status="none",
                        auto_created_bridge_names=[],
                        links=[],
                    )
                    chunk_degraded = True

                primary_link = next(
                    (l for l in link_result.links if l.role == "primary"), None
                )

                embeddings = await self.provider.embed([search_text])
                if not embeddings or len(embeddings[0]) != EMBEDDING_DIM:
                    raise ValueError(
                        f"Invalid embedding for chunk {chunk.id}: "
                        f"expected dim {EMBEDDING_DIM}"
                    )

                chunk.contextual_text = contextual_text
                chunk.search_text = search_text
                chunk.lvl1 = tag_result.lvl1
                chunk.lvl2 = tag_result.lvl2
                chunk.lvl3 = tag_result.lvl3
                chunk.knowledge_point_id = resolve_knowledge_point_id(
                    self.db, tag_result.lvl1, tag_result.lvl2, tag_result.lvl3,
                )
                chunk.bridge_id = primary_link.bridge_id if primary_link else None
                chunk.bridge_binding_status = link_result.binding_status
                chunk.embedding = embeddings[0]
                if chunk_degraded:
                    chunk.needs_reindex = True

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

                # Flush ORM changes, then update tsv in the same transaction.
                self.db.flush()
                self.db.execute(
                    sql_text(
                        "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) "
                        "WHERE id = :id"
                    ),
                    {
                        "id": chunk.id,
                        "tsv_text": tokenizer.to_tsvector_text(
                            chunk.search_text or chunk.content
                        ),
                    },
                )
                # Commit per chunk: bounds the transaction to <1 min rather
                # than accumulating over all chunks. A subsequent chunk's
                # failure no longer rolls back prior progress — and a retry
                # after failure will re-run via ``_cleanup_task_data`` which
                # wipes chunks and starts fresh.
                self.db.commit()

            # Final status transition — own short transaction.
            task.status = "completed"
            task.parsed_content = None  # Clear plaintext to reduce exposure (R2 has raw file)
            self.db.commit()

            self._audit(task, AuditService.INGEST_INDEX_DONE, {"chunk_count": task.chunk_count})
            self.db.commit()

        except Exception as e:
            self._fail(task, e)
