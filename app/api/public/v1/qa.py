"""Public API: SSE pseudo-streaming QA endpoint.

Single LLM call + structured JSON split into sequential SSE events
(started -> outline -> detail* -> sources -> done). Not real token streaming.

i18n Phase 4 — when ``request.state.locale == 'en-US'`` the handler takes the
translate-around branch: query → ``translate_query_zh`` → Chinese hybrid search
∥ English embedding保底 search → RRF merge → ``translate_answer_with_evidence``
for a JSON-structured English answer + per-chunk English summaries. The
summaries are written back to ``chunks.cached_en_summary`` in an async task so
they don't block the SSE stream. On parse failure we degrade to the original
Chinese pipeline and mark ``done`` with ``degraded=true``.
"""
import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.qa import QARequest
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.rate_limit import limiter
from app.models.knowledge_point import KnowledgePoint
from app.providers import get_provider
from app.services.facet_extractor import FacetExtractor
from app.services.generator import Generator
from app.services.hybrid_retriever import (
    HybridRetriever,
    HybridRetrievalResult,
    RetrievedChunk,
    TaxonomyFilter,
)
from app.services.tokenizer import Tokenizer, default_user_dict_path
from app.services.translation_service import (
    cache_evidence_summaries,
    extract_evidence_summaries_async,
    translate_answer_stream,
    translate_answer_with_evidence,
    translate_query_zh,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-step timeout budgets (seconds).  Total worst-case ≈ 43s < 60s.
_PARALLEL_TIMEOUT = 10   # facet ∥ embed (flash ~4s, embed ~1s)
_RETRIEVE_TIMEOUT = 10   # DB queries after embedding is ready
_GENERATE_TIMEOUT = 25   # LLM generation with evidence


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_context(
    db: Session, request: QARequest,
) -> tuple[uuid.UUID | None, TaxonomyFilter | None]:
    """Resolve QA context to bridge_id or taxonomy_filter."""
    if not request.context or not request.context.type or not request.context.id:
        return None, None

    if request.context.type == "bridge":
        return request.context.id, None

    if request.context.type == "knowledge_point":
        kp = db.query(KnowledgePoint).filter(
            KnowledgePoint.id == request.context.id
        ).first()
        if not kp:
            logger.warning("QA context references non-existent knowledge_point %s", request.context.id)
            return None, None
        # Phase 3: KP carries lvl1 / lvl2 directly, and kp.name is the former
        # lvl3 label. No TaxonomyNode join needed.
        if not kp.lvl1:
            logger.warning("Knowledge point %s has no lvl1, ignoring context", kp.id)
            return None, None
        return None, TaxonomyFilter(
            lvl1=kp.lvl1,
            lvl2=kp.lvl2,
            lvl3=kp.name,
        )
    return None, None


async def _safe_extract_facet(extractor: FacetExtractor, question: str):
    """Extract facets, returning None on any failure."""
    try:
        return await extractor.extract(question)
    except Exception:
        logger.warning("Facet extraction failed, continuing without facets", exc_info=True)
        return None


def _rrf_merge_retrieved(
    zh_chunks: list[RetrievedChunk],
    en_chunks: list[RetrievedChunk],
    *,
    zh_weight: float = 0.7,
    en_weight: float = 0.3,
    limit: int = 10,
) -> list[RetrievedChunk]:
    """Weighted reciprocal-rank fusion over two ``RetrievedChunk`` lists.

    Preserves the chunk object from whichever list saw it first so downstream
    code retains the original ``content`` / ``bridge_name`` fields. Dedup by
    ``chunk_id``.
    """
    scores: dict[uuid.UUID, float] = {}
    objects: dict[uuid.UUID, RetrievedChunk] = {}
    for rank, chunk in enumerate(zh_chunks, 1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + zh_weight / (60 + rank)
        objects.setdefault(chunk.chunk_id, chunk)
    for rank, chunk in enumerate(en_chunks, 1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + en_weight / (60 + rank)
        objects.setdefault(chunk.chunk_id, chunk)

    ordered_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [objects[cid] for cid in ordered_ids[:limit]]


def _persist_en_summaries_in_background(summaries: list[dict]) -> None:
    """Run ``cache_evidence_summaries`` against a fresh ``SessionLocal`` so we
    don't race the request-scoped session, and swallow errors."""
    if not summaries:
        return
    db = SessionLocal()
    try:
        cache_evidence_summaries(db, summaries=summaries)
    except Exception:
        logger.exception("Failed to persist evidence summaries")
    finally:
        db.close()


@router.post("/ask")
@limiter.limit("10/minute")
async def ask_sse(
    request: Request,
    body: QARequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """SSE streaming QA endpoint.
    TODO: Upgrade to real LLM streaming.
    """
    locale = getattr(request.state, "locale", "zh-CN")

    async def event_stream():
        qa_id = str(uuid.uuid4())
        start_time = time.monotonic()
        last_event_time = start_time
        timeout_seconds = 60
        ping_interval = 15

        def _maybe_ping() -> str:
            nonlocal last_event_time
            now = time.monotonic()
            if now - last_event_time > ping_interval:
                last_event_time = now
                return _sse_event("ping", {})
            return ""

        def _mark_event() -> None:
            nonlocal last_event_time
            last_event_time = time.monotonic()

        started_payload: dict = {"qa_id": qa_id, "locale": locale}
        yield _sse_event("started", started_payload)
        _mark_event()

        try:
            # Phase C: every LLM chat call is task-routed via
            # ``chat_for_task(task_key, messages)`` — see app/llm. The old
            # ``provider.chat_model = settings.qa_chat_model`` monkey-patch
            # on the shared singleton was a cross-request race bug and is
            # gone. ``provider`` here is only used for ``embed()`` (locked to
            # Zhipu per design §2) inside HybridRetriever.
            provider = get_provider()

            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
            retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
            generator = Generator()
            facet_extractor = FacetExtractor()

            # ── English translate-around branch (i18n Phase 4) ──
            # Phase 5 rollback flag: when settings.i18n_enabled is False the
            # en-US branch is bypassed and the request falls through to the
            # Chinese pipeline. Users see Chinese answers instead of a 500 —
            # this is the declared safe degrade path.
            if locale == "en-US" and settings.i18n_enabled:
                final_meta = {"degraded": False, "reason": None}
                async for evt_type, evt_data in _run_en_qa_flow(
                    db=db,
                    body=body,
                    retriever=retriever,
                    provider=provider,
                    background_tasks=background_tasks,
                ):
                    if evt_type == "done_meta":
                        final_meta = evt_data
                        continue
                    yield _sse_event(evt_type, evt_data)
                    _mark_event()
                yield _sse_event("done", {
                    "qa_id": qa_id,
                    "locale": "en-US",
                    "degraded": final_meta["degraded"],
                    "reason": final_meta["reason"],
                })
                return

            target_bridge_id, taxonomy_filter = _resolve_context(db, body)

            if not target_bridge_id and not taxonomy_filter:
                from app.services.bridge_resolver import resolve_bridge_from_question
                target_bridge_id = resolve_bridge_from_question(db, body.question)

            # ── Phase 1: facet extraction ∥ query embedding (parallel) ──
            try:
                facet, embeddings = await asyncio.wait_for(
                    asyncio.gather(
                        _safe_extract_facet(facet_extractor, body.question),
                        provider.embed([body.question]),
                    ),
                    timeout=_PARALLEL_TIMEOUT,
                )
                query_embedding = embeddings[0]
            except asyncio.TimeoutError:
                logger.warning("Phase 1 (facet∥embed) timed out after %ds", _PARALLEL_TIMEOUT)
                # Facet is optional; embedding is required — try embed alone
                try:
                    embeddings = await asyncio.wait_for(
                        provider.embed([body.question]),
                        timeout=_PARALLEL_TIMEOUT,
                    )
                    query_embedding = embeddings[0]
                    facet = None
                except (asyncio.TimeoutError, Exception):
                    logger.error("Embedding timed out, cannot proceed")
                    yield _sse_event("error", {
                        "code": "TIMEOUT",
                        "message": "向量化超时，请稍后重试",
                    })
                    yield _sse_event("done", {"qa_id": qa_id})
                    return

            ping = _maybe_ping()
            if ping:
                yield ping

            # ── Phase 2: retrieval (with pre-computed embedding) ──
            try:
                evidence = await asyncio.wait_for(
                    retriever.retrieve(
                        db,
                        body.question,
                        target_bridge_id=target_bridge_id,
                        taxonomy_filter=taxonomy_filter,
                        facet=facet,
                        query_embedding=query_embedding,
                    ),
                    timeout=_RETRIEVE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("Retrieval timed out after %ds for question=%r", _RETRIEVE_TIMEOUT, body.question)
                yield _sse_event("error", {
                    "code": "TIMEOUT",
                    "message": "检索超时，请稍后重试",
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return
            except Exception:
                logger.error("Retrieval failed for question=%r", body.question, exc_info=True)
                yield _sse_event("error", {
                    "code": "RETRIEVAL_FAILED",
                    "message": "检索系统暂时不可用，请稍后重试",
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            ping = _maybe_ping()
            if ping:
                yield ping

            if not evidence.all_chunks():
                yield _sse_event("error", {
                    "code": "INSUFFICIENT_EVIDENCE",
                    "message": "未找到直接证据，建议换一种问法或缩小范围",
                    "fallback_actions": [],
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            # ── Phase 3: LLM generation ──
            from app.services.markdown_stream_parser import ParseDegradedError

            FIRST_TOKEN_TIMEOUT = 12
            INTER_TOKEN_TIMEOUT = 20
            stream_failed = False
            saw_degraded = False
            degraded_reason: str | None = None
            last_token_at = time.monotonic()

            async def _streaming_with_retry():
                nonlocal last_token_at, saw_degraded, degraded_reason
                for attempt in range(2):
                    stream_iter = generator.generate_streaming_v2(body.question, evidence)
                    try:
                        first_event = await asyncio.wait_for(
                            stream_iter.__anext__(),
                            timeout=FIRST_TOKEN_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        if attempt == 0:
                            logger.warning("First-token timeout, retrying once")
                            continue
                        raise
                    except StopAsyncIteration:
                        return
                    except ParseDegradedError as exc:
                        yield ("detail", exc.fallback_payload)
                        saw_degraded = True
                        degraded_reason = "parse_degraded"
                        return
                    last_token_at = time.monotonic()
                    yield first_event
                    try:
                        async for ev in stream_iter:
                            last_token_at = time.monotonic()
                            yield ev
                    except ParseDegradedError as exc:
                        yield ("detail", exc.fallback_payload)
                        saw_degraded = True
                        degraded_reason = "parse_degraded"
                    return

            if settings.qa_real_streaming_enabled:
                try:
                    async for event_type, data in _streaming_with_retry():
                        if time.monotonic() - last_token_at > INTER_TOKEN_TIMEOUT:
                            yield _sse_event("degraded", {"reason": "stream_broken"})
                            saw_degraded = True
                            degraded_reason = "stream_broken"
                            break
                        yield _sse_event(event_type, data)
                        _mark_event()
                        ping = _maybe_ping()
                        if ping:
                            yield ping
                    if saw_degraded and degraded_reason in ("parse_degraded",):
                        yield _sse_event("degraded", {"reason": degraded_reason})
                except asyncio.TimeoutError:
                    logger.warning(
                        "QA streaming failed twice on first-token; falling back to pseudo-streaming"
                    )
                    stream_failed = True
                except Exception:
                    logger.exception("QA streaming raised; falling back to pseudo-streaming")
                    stream_failed = True

            if (not settings.qa_real_streaming_enabled) or stream_failed:
                fallback_timeout = 45 if stream_failed else _GENERATE_TIMEOUT
                try:
                    events = await asyncio.wait_for(
                        generator.generate_streaming(body.question, evidence),
                        timeout=fallback_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Generation timed out after %ds for question=%r",
                        fallback_timeout,
                        body.question,
                    )
                    yield _sse_event("error", {"code": "TIMEOUT", "message": "生成超时，请稍后重试"})
                    yield _sse_event("done", {"qa_id": qa_id, "locale": locale})
                    return

                for event_type, data in events:
                    elapsed = time.monotonic() - start_time
                    if elapsed > timeout_seconds:
                        yield _sse_event("error", {"code": "TIMEOUT", "message": "请求超时"})
                        yield _sse_event("done", {"qa_id": qa_id, "locale": locale})
                        return
                    yield _sse_event(event_type, data)
                    _mark_event()

            yield _sse_event("done", {
                "qa_id": qa_id,
                "locale": locale,
                "degraded": saw_degraded,
                "reason": degraded_reason,
            })

        except Exception:
            logger.error("SSE QA stream failed", exc_info=True)
            yield _sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": "服务端内部错误，请稍后重试",
            })
            yield _sse_event("done", {"qa_id": qa_id, "locale": locale})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _build_sources_payload(merged, summary_by_chunk=None):
    """Construct the sources_payload list used by both streaming and legacy paths.

    ``summary_by_chunk`` is an optional ``{chunk_id_str: english_summary}`` map.
    Streaming path leaves it empty (summaries are generated async after the
    stream completes); the legacy fallback path passes the inline summaries.
    """
    summary_by_chunk = summary_by_chunk or {}
    payload = []
    for chunk in merged:
        cid_str = str(chunk.chunk_id)
        payload.append({
            "chunk_id": cid_str,
            "text_en": summary_by_chunk.get(cid_str, ""),
            "text_zh": chunk.content[:400] if chunk.content else "",
            "source_title": chunk.bridge_name or "",
        })
    return payload


async def _run_en_qa_flow(
    *,
    db: Session,
    body: QARequest,
    retriever: HybridRetriever,
    provider,
    background_tasks: BackgroundTasks,
):
    """Run the translate-around English QA flow as an async generator.

    Yields ``(event_type, payload)`` tuples. The final event is always
    ``('done_meta', {'degraded': bool, 'reason': str | None})`` — the caller
    converts that to the actual SSE ``done`` event including locale + qa_id.

    Phase 4.F emits a structured ``qa.en_metrics`` log line at the end with
    per-stage timings (query_translate / retrieval / generate / total) and
    the cached_en_summary hit rate, for offline P50/P95 aggregation. Task 9
    streams Step 3 via :func:`translate_answer_stream` + ``MarkdownStreamParser``;
    on stream failure we fall back to the legacy
    :func:`translate_answer_with_evidence` non-streaming path.
    """
    from app.services.markdown_stream_parser import (
        MarkdownStreamParser,
        ParseDegradedError,
    )

    question_en = body.question
    # Phase 4.F: per-stage stopwatch. Stored in ms (int) so JSON log lines
    # are friendly to grep / jq without float-precision nuisance.
    flow_start = time.monotonic()
    stage_ms: dict[str, int] = {}

    # Step 1 — query translation ∥ English保底 embedding retrieval
    stage1_start = time.monotonic()
    try:
        zh_query, english_chunks = await asyncio.wait_for(
            asyncio.gather(
                translate_query_zh(question_en),
                retriever.search_by_english_embedding(db, question_en, top_k=10),
                return_exceptions=False,
            ),
            timeout=12,
        )
    except (asyncio.TimeoutError, Exception):
        stage_ms["query_translate_ms"] = int((time.monotonic() - stage1_start) * 1000)
        stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
        logger.exception("qa.en_generation_failed stage=query_translate metrics=%s", stage_ms)
        yield ("error", {
            "code": "TIMEOUT",
            "message": "Query translation failed; please retry.",
        })
        yield ("done_meta", {"degraded": True, "reason": "query_translation_failed"})
        return
    stage_ms["query_translate_ms"] = int((time.monotonic() - stage1_start) * 1000)

    yield ("translated_query", {"zh": zh_query})

    # Step 2 — Chinese hybrid search on translated query
    stage2_start = time.monotonic()
    try:
        target_bridge_id, taxonomy_filter = _resolve_context(db, body)
        if not target_bridge_id and not taxonomy_filter:
            from app.services.bridge_resolver import resolve_bridge_from_question
            target_bridge_id = resolve_bridge_from_question(db, zh_query)
        zh_result = await asyncio.wait_for(
            retriever.retrieve(
                db,
                zh_query,
                target_bridge_id=target_bridge_id,
                taxonomy_filter=taxonomy_filter,
            ),
            timeout=_RETRIEVE_TIMEOUT,
        )
    except Exception:
        logger.exception("en-US Chinese-query retrieval failed")
        zh_result = HybridRetrievalResult(
            anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
        )
    stage_ms["retrieval_ms"] = int((time.monotonic() - stage2_start) * 1000)

    merged = _rrf_merge_retrieved(
        zh_result.all_chunks(),
        english_chunks,
        zh_weight=0.7,
        en_weight=0.3,
        limit=10,
    )

    if not merged:
        stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
        logger.info("qa.en_metrics reason=no_evidence metrics=%s", stage_ms)
        yield ("error", {
            "code": "INSUFFICIENT_EVIDENCE",
            "message": "No relevant evidence found. Try rephrasing.",
        })
        yield ("done_meta", {"degraded": True, "reason": "no_evidence"})
        return

    # Phase 4.F.3: cache hit rate accounting — Task 9 no longer pre-fetches
    # per-chunk cached_en_summary because summaries are generated async after
    # the stream completes (cache misses on first request are expected).
    # Keep counters at zero so the metrics line still emits all keys.
    stage_ms["cache_total"] = len(merged)
    stage_ms["cache_hits"] = 0

    # Step 3 — Stream the English answer.
    stage3_start = time.monotonic()
    parser = MarkdownStreamParser()
    try:
        async for token in translate_answer_stream(question_en, merged):
            for event in parser.feed(token):
                yield event
        for event in parser.flush():
            yield event
    except ParseDegradedError as exc:
        stage_ms["generate_ms"] = int((time.monotonic() - stage3_start) * 1000)
        stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
        logger.warning(
            "qa.en_generation_failed stage=translate_answer reason=parse_degraded metrics=%s",
            stage_ms,
        )
        yield ("detail", exc.fallback_payload)
        yield ("degraded", {"reason": "parse_degraded"})
        yield ("sources", {"sources": _build_sources_payload(merged)})
        yield ("done_meta", {"degraded": True, "reason": "translate_answer_failed"})
        return
    except Exception:
        logger.exception(
            "translate_answer_stream failed; falling back to legacy translate_answer_with_evidence"
        )
        # Legacy fallback — call the original synchronous translator.
        try:
            answer_result = await translate_answer_with_evidence(question_en, merged)
        except Exception:
            stage_ms["generate_ms"] = int((time.monotonic() - stage3_start) * 1000)
            stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
            logger.exception(
                "qa.en_generation_failed stage=translate_answer_legacy metrics=%s",
                stage_ms,
            )
            yield ("error", {
                "code": "ANSWER_FAILED",
                "message": "English answer generation failed.",
            })
            yield ("done_meta", {"degraded": True, "reason": "translate_answer_failed"})
            return
        stage_ms["generate_ms"] = int((time.monotonic() - stage3_start) * 1000)
        answer_text = answer_result.get("answer", "")
        summaries = answer_result.get("evidence_summaries", [])
        summary_by_chunk = {
            s["chunk_id"]: s["text_en"] for s in summaries if s.get("chunk_id")
        }
        outline_id = str(uuid.uuid4())
        yield ("outline", {"key_points": [{
            "id": outline_id,
            "summary": answer_text[:200] if answer_text else "",
            "order": 1,
        }]})
        yield ("detail", {
            "key_point_id": outline_id,
            "explanation": answer_text,
            "citations": list(range(1, len(merged) + 1)),
        })
        yield ("sources", {"sources": _build_sources_payload(merged, summary_by_chunk)})
        if summaries:
            background_tasks.add_task(_persist_en_summaries_in_background, summaries)
        stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
        logger.warning(
            "qa.en_metrics ok=0 reason=translate_answer_failed_legacy metrics=%s",
            stage_ms,
        )
        yield ("done_meta", {"degraded": True, "reason": "translate_answer_failed_legacy"})
        return

    stage_ms["generate_ms"] = int((time.monotonic() - stage3_start) * 1000)

    # Sources (post-stream success) — text_en empty until background task
    # writes summaries; subsequent requests will hit the cache.
    yield ("sources", {"sources": _build_sources_payload(merged)})

    # Background: generate evidence summaries (non-blocking) and cache them.
    background_tasks.add_task(
        extract_evidence_summaries_async,
        answer_text=parser.full_text(),
        merged=merged,
    )

    # Phase 4.F: emit the success-path structured metrics line.
    stage_ms["total_ms"] = int((time.monotonic() - flow_start) * 1000)
    logger.info("qa.en_metrics ok=1 metrics=%s", stage_ms)

    yield ("done_meta", {"degraded": False, "reason": None})
