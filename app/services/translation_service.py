"""Translation service — i18n Phases 3 & 4.

Split across two independent flows that share the same glossary injection and
LLM plumbing:

* **Admin-driven审校 flow** (Phase 3): :func:`generate_for_row`,
  :func:`batch_generate_for_field`, :func:`approve_review`, :func:`reject_review`.
  Populates ``translation_reviews`` rows; approvals write back to the business
  table in the same transaction.
* **Translate-around RAG** (Phase 4): :func:`translate_query_zh` and
  :func:`translate_answer_with_evidence` wrap the QA request/response in query
  translation + structured English answer generation. Evidence summaries
  generated in the answer call land in ``chunks.cached_en_summary`` as a
  fire-and-forget background write.

Phase C: all LLM chat dispatch goes through :func:`app.llm.chat_for_task` with
task_key ``"translation"``. The previous code toggled ``provider.chat_model``
between ``glm-4-flash`` (cheap) and ``glm-4.7`` (quality) per call — that
mutation on the shared provider instance was a cross-request race and has
been removed. Admins that want to split the cheap/quality backends can add
distinct task routes (e.g. ``translation_cheap`` / ``translation_quality``)
in Phase D once the admin UI ships; for now both paths share one route.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core.glossary import (
    GlossaryTerm,
    format_glossary_for_prompt,
    load_glossary,
    pick_relevant_terms,
)
from app.llm import ChatMessage, chat_for_task, chat_stream_for_task
from app.models import (
    Bridge,
    Chunk,
    Flashcard,
    KnowledgePoint,
    TaxonomyNode,
    TranslationReview,
)
from app.models.translation_review import (
    TRANSLATION_STATUS_AI_GENERATED,
    TRANSLATION_STATUS_HUMAN_REVIEWED,
    TRANSLATION_STATUS_PENDING_AI,
    TRANSLATION_STATUS_REJECTED,
)

logger = logging.getLogger(__name__)


TASK_KEY = "translation"

# Historical model constants — kept for backwards-compatible reads (system
# status page, tests that still reference them). Phase D will replace these
# with llm_task_routes lookups; for now both cheap/quality flows route via
# the single "translation" task_key, so these are informational only.
CHEAP_TRANSLATION_MODEL = "glm-4-flash"
QUALITY_ANSWER_MODEL = "glm-4.7"

# Advisory lock for batch AI translation. Picked as ingest_scheduler's base
# +1 to deliberately *not* collide with the ingest scheduler lock; a single
# translation_reviews scheduler thread will block on this lock while a
# concurrent ingest run holds its own (see RAG/CLAUDE.md ingest_scheduler
# section). These two are independent subsystems.
TRANSLATION_ADVISORY_LOCK_ID = 494956381

# Translatable business-field definitions. Keyed by ``table_name`` with the
# list of field pairs: (source zh column, target en column).
TRANSLATABLE_FIELDS: dict[str, list[tuple[str, str]]] = {
    # Bridge model's long-form column is ``summary`` (not ``description``);
    # the target *_en column is named ``description_en``. Asymmetric mapping
    # is deliberate — kept until a schema migration renames the source
    # column for symmetry. Pre-fix this triggered a 400 "bridges.description
    # is empty" on every "AI 翻译" click against bridges.description_en.
    "bridges": [("name", "name_en"), ("summary", "description_en")],
    "knowledge_points": [("name", "name_en"), ("summary", "summary_en")],
    "flashcards": [
        ("front_title", "front_title_en"),
        ("back_answer", "back_answer_en"),
    ],
    "taxonomy_nodes": [("lvl3", "name_en")],
    # v15 (2026-05-08): inline TranslationCell needs 要点 fields translatable
    # so admins can审校 each key_point in place on the KP detail page.
    "knowledge_point_key_points": [
        ("summary", "summary_en"),
        ("explanation", "explanation_en"),
    ],
}


def _model_registry() -> dict[str, Any]:
    """Dynamic table lookup — keeps the fn-level branch out of hot paths."""
    from app.models import KnowledgePointKeyPoint  # local to avoid cycles
    return {
        "bridges": Bridge,
        "knowledge_points": KnowledgePoint,
        "flashcards": Flashcard,
        "taxonomy_nodes": TaxonomyNode,
        "knowledge_point_key_points": KnowledgePointKeyPoint,
    }


# --- Query translation cache ---------------------------------------------


class _LRUCache:
    """Tiny in-process LRU — no external Redis dep for Phase 4.

    Chosen over ``functools.lru_cache`` so the cache key can be a truncated
    SHA-256 digest (for reproducible test assertions) rather than the raw
    query. Process-lifetime only; crash or restart loses everything, which is
    fine — the glm-4-flash re-translation is cheap.
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._store: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> str | None:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: str, value: str) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


_query_translation_cache = _LRUCache(maxsize=256)


def _cache_key(query_en: str) -> str:
    return hashlib.sha256(query_en.encode("utf-8")).hexdigest()[:16]


# --- Helpers --------------------------------------------------------------


def _strip_llm_wrapper(text: str) -> str:
    """Prompts that ask for raw output still get decorated occasionally with
    backticks or surrounding quotes — strip those so callers get the clean
    translation.
    """
    s = text.strip()
    # Strip ``` fenced code blocks
    if s.startswith("```") and s.endswith("```"):
        inner = s[3:-3]
        # Drop optional language hint on first line
        if "\n" in inner:
            first, rest = inner.split("\n", 1)
            if first.strip().isalpha():
                inner = rest
        s = inner.strip()
    # Strip symmetric wrapping quotes
    for pair in (("\"", "\""), ("\u201c", "\u201d"), ("'", "'")):
        if s.startswith(pair[0]) and s.endswith(pair[1]) and len(s) >= 2:
            s = s[1:-1].strip()
    return s


def _source_value_from_row(row: Any, field_name: str) -> str | None:
    return getattr(row, field_name, None)


def _source_field_for_review(table_name: str, field_name: str) -> str:
    """Given a translation_reviews.field_name (the *_en column), return the
    Chinese source column that should be translated. Callers fall back to
    ``field_name`` itself when the mapping is missing (e.g. a future table
    where source and target share a stem)."""
    for source, target in TRANSLATABLE_FIELDS.get(table_name, []):
        if target == field_name:
            return source
    return field_name


# --- Query translation (Phase 4 entry) -----------------------------------


async def translate_query_zh(
    query_en: str,
    *,
    glossary: list[GlossaryTerm] | None = None,
    cache: _LRUCache | None = None,
) -> str:
    """Translate an English user question into a Chinese retrieval query.

    Routes via ``chat_for_task("translation", ...)``. Caches by SHA-256 prefix
    of the input query for the process lifetime so repeat questions don't
    reburn tokens.

    Returns the unwrapped Chinese string ready to hand to
    :meth:`HybridRetriever.retrieve`. On LLM failure raises the provider's
    exception — callers are responsible for falling back (see :func:`qa.ask`).
    """
    if not query_en or not query_en.strip():
        return query_en
    active_cache = cache if cache is not None else _query_translation_cache
    key = _cache_key(query_en)
    cached = active_cache.get(key)
    if cached is not None:
        logger.debug("translate_query_zh cache hit key=%s", key)
        return cached

    terms = glossary if glossary is not None else pick_relevant_terms(query_en, limit=10)
    glossary_block = format_glossary_for_prompt(terms) if terms else ""

    prompt = (
        "You are a translator specializing in Chinese bridge architecture. "
        "Translate the user's English question into Chinese. Preserve any "
        "Chinese bridge names exactly as provided.\n"
    )
    if glossary_block:
        prompt += (
            "\nUse these professional term mappings when relevant:\n"
            + glossary_block
            + "\n"
        )
    prompt += (
        f"\nEnglish question: \"{query_en.strip()}\"\n"
        "Chinese translation (OUTPUT ONLY the Chinese query, no explanation, "
        "no surrounding quotes):"
    )

    resp = await chat_for_task(TASK_KEY, [ChatMessage(role="user", content=prompt)])

    translated = _strip_llm_wrapper(resp.content)
    if not translated:
        raise ValueError("Empty translation response from LLM")
    active_cache.put(key, translated)
    return translated


# --- Admin审校 flow ------------------------------------------------------


def _get_or_create_review_row(
    session: Session,
    *,
    table_name: str,
    row_id: UUID,
    field_name: str,
    source_text: str,
) -> TranslationReview:
    existing = (
        session.query(TranslationReview)
        .filter(
            TranslationReview.table_name == table_name,
            TranslationReview.row_id == row_id,
            TranslationReview.field_name == field_name,
        )
        .one_or_none()
    )
    if existing is not None:
        # Keep the recorded source_text fresh in case the business row changed.
        if source_text and existing.source_text != source_text:
            existing.source_text = source_text
        return existing
    review = TranslationReview(
        table_name=table_name,
        row_id=row_id,
        field_name=field_name,
        source_text=source_text,
        status=TRANSLATION_STATUS_PENDING_AI,
    )
    session.add(review)
    session.flush()
    return review


async def _call_cheap_translator(
    *,
    source_text: str,
    context: str | None = None,
    glossary_terms: list[GlossaryTerm] | None = None,
) -> str:
    """Shared单条翻译 LLM call for admin审校 flow + batch generation."""
    terms = glossary_terms if glossary_terms is not None else pick_relevant_terms(source_text, limit=8)
    glossary_block = format_glossary_for_prompt(terms) if terms else ""

    prompt_parts = [
        "Translate the following Chinese text about bridge architecture into "
        "clear, natural English. Preserve proper nouns; when a term appears in "
        "the glossary below use the English mapping verbatim.",
    ]
    if context:
        prompt_parts.append(f"Context: {context}")
    if glossary_block:
        prompt_parts.append("Glossary:\n" + glossary_block)
    prompt_parts.append(f'Chinese source:\n"""\n{source_text.strip()}\n"""')
    prompt_parts.append(
        "Respond with ONLY the English translation, no quotes, no commentary."
    )
    prompt = "\n\n".join(prompt_parts)

    resp = await chat_for_task(TASK_KEY, [ChatMessage(role="user", content=prompt)])
    return _strip_llm_wrapper(resp.content)


async def generate_for_row(
    session: Session,
    *,
    table_name: str,
    row_id: UUID,
    field_name: str,
    source_text: str,
) -> TranslationReview:
    """Produce (or refresh) the AI translation for a single business row/field.

    Idempotent on the ``(table, row, field)`` triple — if a review已 reached
    ``human_reviewed`` or ``rejected`` we short-circuit and return it instead of
    overwriting审校 decisions.
    """
    review = _get_or_create_review_row(
        session,
        table_name=table_name,
        row_id=row_id,
        field_name=field_name,
        source_text=source_text,
    )

    # Only ``human_reviewed`` short-circuits — that decision is the reviewer's
    # final word and must not be overwritten by another AI pass. ``rejected``
    # used to short-circuit too, but that left rejected rows as a dead end:
    # the inline TranslationCell flow needs to be able to re-translate from
    # rejected (the reviewer's "this AI output is wrong, try again" signal).
    # See docs/plans/2026-05-08-inline-translation-review-design.md §7.
    if review.status == TRANSLATION_STATUS_HUMAN_REVIEWED:
        return review

    try:
        translation = await _call_cheap_translator(
            source_text=source_text,
            context=f"{table_name}.{field_name}",
        )
    except Exception:
        logger.exception(
            "AI translation failed for %s.%s row=%s — leaving status=pending_ai",
            table_name, field_name, row_id,
        )
        # Leave status at pending_ai so the UI / batch job can retry.
        return review

    review.ai_translation = translation
    review.status = TRANSLATION_STATUS_AI_GENERATED
    session.flush()
    return review


async def batch_generate_for_field(
    session: Session,
    *,
    table_name: str,
    field_name: str,
    limit: int = 100,
) -> dict[str, int]:
    """Kick off AI translation for up to ``limit`` business rows that lack an
    ``_en`` value.

    Uses ``pg_try_advisory_xact_lock(TRANSLATION_ADVISORY_LOCK_ID)`` so two
    concurrent batch runs (cron + admin click) can't double-translate the same
    rows; the losing call returns ``started=0`` with ``already_queued`` reflecting
    the work the winner will do.

    This function runs the translations *inline* (one LLM call per row). Callers
    that want background dispatch should wrap it in ``asyncio.create_task``.
    """
    if table_name not in TRANSLATABLE_FIELDS:
        raise ValueError(f"Unknown translatable table: {table_name}")
    model_cls = _model_registry().get(table_name)
    if model_cls is None:
        raise ValueError(f"No model class registered for table: {table_name}")

    source_field = _source_field_for_review(table_name, field_name)

    # Try to acquire the advisory lock. If another batch holds it, back off with
    # started=0 — the caller can report "already running" to the admin UI.
    acquired = session.execute(
        text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
        {"lock_id": TRANSLATION_ADVISORY_LOCK_ID},
    ).scalar_one()

    # Pending count — rows where the target *_en column is NULL.
    target_col = getattr(model_cls, field_name)
    source_col = getattr(model_cls, source_field)
    base_query = (
        session.query(model_cls)
        .filter(target_col.is_(None))
        .filter(source_col.isnot(None))
    )
    total_pending = base_query.count()

    if not acquired:
        return {"started": 0, "already_queued": total_pending, "total_pending": total_pending}

    rows = base_query.limit(limit).all()

    started = 0
    already_queued = 0
    for row in rows:
        source_text = _source_value_from_row(row, source_field)
        if not source_text:
            continue
        existing = (
            session.query(TranslationReview)
            .filter(
                TranslationReview.table_name == table_name,
                TranslationReview.row_id == row.id,
                TranslationReview.field_name == field_name,
            )
            .one_or_none()
        )
        if existing is not None and existing.status != TRANSLATION_STATUS_PENDING_AI:
            already_queued += 1
            continue

        await generate_for_row(
            session,
            table_name=table_name,
            row_id=row.id,
            field_name=field_name,
            source_text=source_text,
        )
        started += 1

    return {
        "started": started,
        "already_queued": already_queued,
        "total_pending": total_pending,
    }


def _write_back_to_business_table(
    session: Session,
    *,
    table_name: str,
    row_id: UUID,
    field_name: str,
    value: str,
) -> None:
    model_cls = _model_registry().get(table_name)
    if model_cls is None:
        raise ValueError(f"No model class registered for table: {table_name}")
    session.execute(
        update(model_cls)
        .where(model_cls.id == row_id)
        .values({field_name: value})
    )


async def approve_review(
    session: Session,
    *,
    review_id: UUID,
    reviewer_id: str,
    reviewed_translation: str | None = None,
) -> TranslationReview:
    """Flip a review to ``human_reviewed`` and write the approved translation
    back to the business table.

    Transactional contract:
        - Caller owns ``session.commit()``. This function stages two writes
          (review update + business-table UPDATE) in the caller's transaction;
          rolling back discards both atomically.

    :param reviewed_translation: Overrides the AI output when the reviewer
        edited the text. When ``None``, the AI translation is approved verbatim.
    """
    review = session.query(TranslationReview).filter(
        TranslationReview.id == review_id
    ).one_or_none()
    if review is None:
        raise ValueError(f"translation_review {review_id} not found")

    final_text = reviewed_translation if reviewed_translation is not None else review.ai_translation
    if not final_text:
        raise ValueError(
            f"Cannot approve review {review_id}: no translation text available"
        )

    _write_back_to_business_table(
        session,
        table_name=review.table_name,
        row_id=review.row_id,
        field_name=review.field_name,
        value=final_text,
    )

    review.reviewed_translation = final_text
    review.status = TRANSLATION_STATUS_HUMAN_REVIEWED
    review.reviewed_by = reviewer_id
    review.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    return review


def reject_review(
    session: Session,
    *,
    review_id: UUID,
    reviewer_id: str,
) -> TranslationReview:
    """Mark a review as ``rejected`` without touching the business table."""
    review = session.query(TranslationReview).filter(
        TranslationReview.id == review_id
    ).one_or_none()
    if review is None:
        raise ValueError(f"translation_review {review_id} not found")
    review.status = TRANSLATION_STATUS_REJECTED
    review.reviewed_by = reviewer_id
    review.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    return review


# --- Translate-around answer generation (Phase 4) ------------------------


def _format_evidence_for_en_prompt(evidence_chunks: list[Any]) -> str:
    """Render evidence chunks with a deterministic numbering the LLM can cite.

    Accepts either ``RetrievedChunk`` dataclasses or raw dicts with
    ``{chunk_id, content}`` keys so tests can skip constructing DB-backed
    objects.
    """
    lines: list[str] = []
    for idx, chunk in enumerate(evidence_chunks, 1):
        chunk_id = getattr(chunk, "chunk_id", None) or (chunk.get("chunk_id") if isinstance(chunk, dict) else None)
        content = getattr(chunk, "content", None) or (chunk.get("content") if isinstance(chunk, dict) else None)
        bridge_name = getattr(chunk, "bridge_name", None) or (chunk.get("bridge_name") if isinstance(chunk, dict) else None)
        bridge_label = f"（{bridge_name}）" if bridge_name else ""
        lines.append(f"[{idx}] chunk_id={chunk_id}{bridge_label}\n{content}")
    return "\n\n".join(lines)


def _extract_json_object(content: str) -> dict[str, Any] | None:
    """Pull the first balanced JSON object out of an LLM response.

    Returns ``None`` when parsing fails. Uses the same ``find('{')..rfind('}')``
    heuristic the existing :class:`Generator` uses, so answers wrapped in
    markdown fences or preamble still parse.
    """
    if not content:
        return None
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


async def translate_answer_with_evidence(
    question_original: str,
    evidence_chunks: list[Any],
    *,
    glossary: list[GlossaryTerm] | None = None,
) -> dict[str, Any]:
    """One LLM call that emits the English answer + per-chunk English summaries.

    Returns::

        {
            "answer": str,
            "evidence_summaries": [{"chunk_id": str, "text_en": str}, ...],
            "degraded": bool,
        }

    ``degraded=True`` means the JSON parse failed — callers should surface a
    Chinese fallback and set ``response.meta.degraded=true`` per design §4.
    """
    if not evidence_chunks:
        return {
            "answer": "",
            "evidence_summaries": [],
            "degraded": True,
        }

    terms = glossary if glossary is not None else pick_relevant_terms(
        question_original, limit=10,
    )
    glossary_block = format_glossary_for_prompt(terms) if terms else ""
    evidence_text = _format_evidence_for_en_prompt(evidence_chunks)

    prompt = (
        "You are a Chinese bridge architecture expert. Read the Chinese source "
        "excerpts below and answer the user's question entirely in English. "
        "Also provide a concise one-paragraph English summary for every source "
        "you cite.\n\n"
        f"User question (English): {question_original}\n\n"
        "Sources (Chinese):\n"
        f"{evidence_text}\n"
    )
    if glossary_block:
        prompt += "\nUse these term mappings verbatim when they appear:\n" + glossary_block + "\n"
    prompt += (
        "\nRespond with a single JSON object of the exact form:\n"
        "{\n"
        '  "answer": "English answer — no Chinese characters in the body",\n'
        '  "evidence_summaries": [\n'
        '    {"chunk_id": "<as given above>", "text_en": "One-paragraph English summary"}\n'
        "  ]\n"
        "}\n"
        "Do NOT include any commentary outside the JSON object."
    )

    try:
        resp = await chat_for_task(
            TASK_KEY, [ChatMessage(role="user", content=prompt)]
        )
    except Exception:
        logger.exception("translate_answer_with_evidence LLM call failed")
        return {
            "answer": "",
            "evidence_summaries": [],
            "degraded": True,
        }

    parsed = _extract_json_object(resp.content)
    if not parsed or "answer" not in parsed:
        logger.warning("translate_answer_with_evidence: JSON parse failed; degrading")
        return {
            "answer": "",
            "evidence_summaries": [],
            "degraded": True,
        }

    summaries_raw = parsed.get("evidence_summaries") or []
    summaries: list[dict[str, str]] = []
    for item in summaries_raw:
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id")
        text_en = item.get("text_en") or ""
        if not chunk_id or not text_en:
            continue
        summaries.append({"chunk_id": str(chunk_id), "text_en": str(text_en)})

    return {
        "answer": str(parsed.get("answer") or "").strip(),
        "evidence_summaries": summaries,
        "degraded": False,
    }


# --- Streaming variant + async-summary helpers (Task 8) ------------------
#
# Splits the en-US QA path into two non-blocking phases so the SSE channel
# can flush answer tokens as they arrive instead of waiting for the full
# JSON-shaped response of :func:`translate_answer_with_evidence`:
#
#   1. :func:`translate_answer_stream` — yields markdown answer tokens.
#   2. :func:`extract_evidence_summaries_async` — runs from a BackgroundTask
#      after the stream completes; never raises (errors logged + swallowed)
#      so it can never break the SSE response that already returned.
#
# Both helpers reuse ``TASK_KEY = "translation"`` for routing consistency
# with the existing ``translate_answer_with_evidence`` (no new task_key
# needed in ``llm_task_routes`` — schema v13 seed already covers it).


_STREAMING_ANSWER_PROMPT = """You are a Chinese bridge architecture expert. Answer the user's question entirely in English using the Chinese source excerpts below. Cite sources inline as [1], [2] etc. matching the numbered evidence. Output a single JSON object — no markdown, no code fences, no preamble.

Sources (Chinese):
{evidence_text}

User question (English): {question}

Output format (strict, no commentary outside the JSON):

{{
  "summaries": [
    "First key point summary [1,3]",
    "Second key point summary [2]"
  ],
  "details": [
    {{"explanation": "First key point's expanded paragraph in English, citing evidence as [1] [3].", "citations": [1, 3]}},
    {{"explanation": "Second key point's expanded paragraph in English.", "citations": [2]}}
  ]
}}

Rules:
- The summaries array MUST come first in the output (do not reorder fields).
- 3-7 short English summaries, each ending with [N] or [N,M] referencing source numbers.
- details length MUST equal summaries length and order MUST match.
- Body must be entirely in English — no Chinese characters in summary or explanation.
- Do not wrap the output in ``` fences. Start with `{{` and end with `}}`."""


_EVIDENCE_SUMMARIES_PROMPT = """You are a Chinese bridge architecture expert. The English answer below was generated from the numbered Chinese sources. For EACH source that was cited, produce a one-paragraph English summary capturing the relevant content.

English answer:
{answer_text}

Sources (Chinese):
{evidence_text}

Respond with a single JSON object of the exact form:
{{
  "evidence_summaries": [
    {{"chunk_id": "<as given above>", "text_en": "One-paragraph English summary"}}
  ]
}}

Do NOT include any commentary outside the JSON object. Include one entry per source you can summarize."""


async def translate_answer_stream(
    question_en: str,
    merged: list[Any],
):
    """Stream English markdown answer tokens for the en-US QA path.

    Routes via ``chat_stream_for_task("translation", ...)`` so model selection
    stays consistent with :func:`translate_answer_with_evidence`. Evidence
    summaries are intentionally NOT produced here — they're generated in a
    second pass by :func:`extract_evidence_summaries_async`, scheduled as a
    BackgroundTask so SSE flushing isn't blocked.

    :param question_en: The user's English question (already translated upstream
        if the original was Chinese — caller decides).
    :param merged: List of ``RetrievedChunk`` (or dict-shaped) evidence chunks
        post-RRF. Empty list is allowed; the prompt will still be issued and the
        LLM is expected to respond with an "insufficient evidence" markdown
        block. Callers that want to short-circuit on empty evidence should do
        so before calling this generator.
    """
    evidence_text = _format_evidence_for_en_prompt(merged)
    prompt = _STREAMING_ANSWER_PROMPT.format(
        evidence_text=evidence_text,
        question=question_en,
    )
    messages = [ChatMessage(role="user", content=prompt)]
    async for token in chat_stream_for_task(TASK_KEY, messages):
        yield token


async def extract_evidence_summaries_async(
    *,
    answer_text: str,
    merged: list[Any],
) -> None:
    """Generate per-chunk English summaries given a finished answer + chunks,
    then persist via :func:`cache_evidence_summaries`.

    Designed to be added to ``BackgroundTasks`` after the SSE answer stream
    has fully flushed. Opens its own ``SessionLocal()`` (cannot reuse the
    request-scoped session — by the time a BackgroundTask runs, the request
    session is closed). All exceptions are logged and swallowed so a failure
    here cannot poison the response that has already returned to the client;
    a swallowed failure simply means the next request for the same evidence
    will re-translate (cache miss).
    """
    try:
        if not merged:
            return

        evidence_text = _format_evidence_for_en_prompt(merged)
        prompt = _EVIDENCE_SUMMARIES_PROMPT.format(
            answer_text=answer_text,
            evidence_text=evidence_text,
        )
        messages = [ChatMessage(role="user", content=prompt)]
        resp = await chat_for_task(TASK_KEY, messages)

        parsed = _extract_json_object(resp.content)
        if not parsed:
            logger.warning(
                "extract_evidence_summaries_async: JSON parse failed; "
                "skipping cache write",
            )
            return

        summaries_raw = parsed.get("evidence_summaries") or []
        summaries: list[dict[str, str]] = []
        for item in summaries_raw:
            if not isinstance(item, dict):
                continue
            chunk_id = item.get("chunk_id")
            text_en = item.get("text_en") or ""
            if not chunk_id or not text_en:
                continue
            summaries.append({
                "chunk_id": str(chunk_id),
                "text_en": str(text_en),
            })

        if not summaries:
            return

        # Open a fresh session — request-scoped session is closed by the time
        # a BackgroundTask runs. Mirrors the pattern in qa.py
        # ``_persist_en_summaries_in_background``.
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            cache_evidence_summaries(db, summaries=summaries)
        finally:
            db.close()
    except Exception:
        logger.exception("extract_evidence_summaries_async failed")


def cache_evidence_summaries(
    session: Session, *, summaries: list[dict[str, str]],
) -> int:
    """Persist evidence summaries to ``chunks.cached_en_summary``.

    Returns the number of rows updated. Intended to be called from an
    ``asyncio.create_task`` so SSE streaming isn't blocked — failures are logged
    but swallowed (cache misses just force a re-translation next request).
    """
    if not summaries:
        return 0
    updated = 0
    now = datetime.now(timezone.utc)
    for entry in summaries:
        try:
            chunk_id = UUID(entry["chunk_id"])
        except (KeyError, ValueError, TypeError):
            logger.warning(
                "cache_evidence_summaries: skipping entry with invalid chunk_id %r",
                entry,
            )
            continue
        result = session.execute(
            update(Chunk)
            .where(Chunk.id == chunk_id)
            .values(
                cached_en_summary=entry["text_en"],
                cached_en_summary_at=now,
            )
        )
        updated += result.rowcount or 0
    try:
        session.commit()
    except Exception:
        logger.exception("cache_evidence_summaries commit failed")
        session.rollback()
        return 0
    return updated


__all__ = [
    "CHEAP_TRANSLATION_MODEL",
    "QUALITY_ANSWER_MODEL",
    "TRANSLATABLE_FIELDS",
    "TRANSLATION_ADVISORY_LOCK_ID",
    "approve_review",
    "batch_generate_for_field",
    "cache_evidence_summaries",
    "extract_evidence_summaries_async",
    "generate_for_row",
    "reject_review",
    "translate_answer_stream",
    "translate_answer_with_evidence",
    "translate_query_zh",
]
