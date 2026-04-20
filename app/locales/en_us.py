# English (US) message dictionary.
# Key set must stay in sync with zh_cn.py; missing keys fall back to zh-CN
# (with a warning log in dev).

MESSAGES: dict[str, str] = {
    # ── bridges
    "bridges.not_found": "Bridge not found",
    "bridges.exists": 'Bridge "{name}" already exists',
    "bridges.invalid_id": "Invalid bridge ID format",
    # ── chunks
    "chunks.not_found": "Chunk not found",
    "chunks.conflict": "Chunk was modified by someone else — please refresh and retry",
    # ── knowledge
    "knowledge.point_not_found": "Knowledge point not found",
    "knowledge.no_evidence": "No relevant evidence found",
    # ── auth
    "auth.invalid_token": "Authentication failed, please sign in again",
    "auth.forbidden": "You do not have permission to perform this action",
    # ── qa
    "qa.no_evidence": "No relevant evidence found",
    "qa.degraded_chinese_fallback": "(English answer generation failed, falling back to Chinese)",
    # ── translation / i18n
    "translation.pending": "Translating…",
    "translation.fallback_notice": "(Translation pending — showing original Chinese)",
    # ── ingest
    "ingest.task_not_found": "Ingest task not found",
    "ingest.upload_failed": "File upload failed",
    # ── generic
    "error.internal": "Internal server error",
    "error.rate_limited": "Too many requests, please try again later",
    "error.validation": "Invalid request parameters",
}
