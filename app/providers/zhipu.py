import asyncio
import logging
import random

import httpx
from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.providers.base import ChatMessage, ChatResponse, LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global concurrency limiter for Zhipu API calls (P1 fix).
#
# Even with ingest_max_concurrent=1 a single task fires 3+ LLM calls per
# chunk (enricher, tagger, bridge_linker) plus embed.  When upstream is
# slow the burst can pile up.  This semaphore ensures at most N concurrent
# HTTP requests reach Zhipu at any instant, preventing burst-429s when
# multiple indexing tasks run (future max_concurrent > 1) or when the
# reindex cron overlaps with a live ingest.
# ---------------------------------------------------------------------------
_zhipu_semaphore = asyncio.Semaphore(3)


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for transient upstream/network errors worth retrying.

    Covers three categories:
    1. 429 rate limit responses.
    2. 5xx server errors (upstream overload, partial outage).
    3. httpx transport errors -- ConnectError, ConnectTimeout, ReadTimeout,
       WriteTimeout, PoolTimeout, RemoteProtocolError, ReadError. These are
       common during batch ingest when the upstream LB bounces or a connection
       drops mid-stream.

    Note: retrying ReadTimeout alone is not enough if every call hits the same
    timeout ceiling -- the ``timeout`` passed to ``httpx.AsyncClient`` must
    actually be large enough for the slowest real response. See
    ``settings.chat_read_timeout`` / ``embed_read_timeout``.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _rate_limit_aware_wait(retry_state: RetryCallState) -> float:
    """Adaptive wait: short for transport/5xx, long for 429.

    429 means the rate-limit window hasn't reset — retrying in 2-8s just
    wastes an attempt.  We wait 30×attempt (30 → 60 → 90 → 120 cap) with
    jitter so the cooldown actually elapses.

    Transport errors (ReadTimeout, ConnectError) and 5xx are transient
    blips — standard exponential 2→4→8→16→30 is fine.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    attempt = retry_state.attempt_number

    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        base = min(30 * attempt, 120)
        jitter = random.uniform(2, 10)
        wait = base + jitter
        logger.info(
            "429 rate-limited — backing off %.1fs (attempt %d)",
            wait,
            attempt,
        )
        return wait

    # Transport errors / 5xx: short exponential (same as before)
    base = min(2 ** attempt, 30)
    jitter = random.uniform(1, 5)
    return base + jitter


def _chat_timeout() -> httpx.Timeout:
    """httpx timeout for chat completions.

    Only ``read`` needs the long ceiling -- connect / write / pool are fast
    and keeping them short surfaces real network issues quickly instead of
    hiding them behind a blanket timeout.
    """
    return httpx.Timeout(
        connect=10.0,
        read=settings.chat_read_timeout,
        write=10.0,
        pool=10.0,
    )


def _embed_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=10.0,
        read=settings.embed_read_timeout,
        write=10.0,
        pool=10.0,
    )


class ZhipuProvider(LLMProvider):
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    CHAT_BASE_URL: str | None = None  # override to route chat to a different endpoint
    MAX_EMBED_BATCH = 64

    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.embedding_model = settings.embedding_model
        self.chat_model = settings.chat_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(
        # 8 attempts (was 6) — Zhipu's slow-response periods can burn
        # through attempts on ReadTimeouts alone before a 429 hits. Bumping
        # to 8 plus 90s read timeout gives real resilience during load.
        # Per-chunk LLM fallbacks downstream (see ingest_task_service)
        # prevent any single call's exhaustion from killing the whole task.
        stop=stop_after_attempt(8),
        # Adaptive wait: 429 → 30×attempt (long), transport/5xx → 2^n (short).
        wait=_rate_limit_aware_wait,
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for the given texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (dimension determined by EMBEDDING_DIM constant)
        """
        if not texts:
            return []

        async with httpx.AsyncClient() as client:
            embeddings: list[list[float]] = []
            for start in range(0, len(texts), self.MAX_EMBED_BATCH):
                batch = texts[start : start + self.MAX_EMBED_BATCH]
                async with _zhipu_semaphore:
                    resp = await client.post(
                        f"{self.BASE_URL}/embeddings",
                        headers=self._headers(),
                        json={
                            "model": self.embedding_model,
                            "input": batch,
                            "dimensions": EMBEDDING_DIM,
                        },
                        timeout=_embed_timeout(),
                    )
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("data", [])
                if not isinstance(rows, list):
                    raise TypeError(
                        f"Invalid embeddings response: expected list in data, got {type(rows).__name__}"
                    )
                if rows and isinstance(rows[0], dict) and "index" in rows[0]:
                    rows = sorted(rows, key=lambda r: r.get("index", 0))
                if len(rows) != len(batch):
                    raise ValueError(
                        f"Invalid embeddings response: expected {len(batch)} rows, got {len(rows)}"
                    )
                for row in rows:
                    embeddings.append(row["embedding"])

            return embeddings

    @retry(
        # 8 attempts (was 6) — Zhipu's slow-response periods can burn
        # through attempts on ReadTimeouts alone before a 429 hits. Bumping
        # to 8 plus 90s read timeout gives real resilience during load.
        # Per-chunk LLM fallbacks downstream (see ingest_task_service)
        # prevent any single call's exhaustion from killing the whole task.
        stop=stop_after_attempt(8),
        # Adaptive wait: 429 → 30×attempt (long), transport/5xx → 2^n (short).
        wait=_rate_limit_aware_wait,
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        base = self.CHAT_BASE_URL or self.BASE_URL
        async with _zhipu_semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": self.chat_model,
                        "messages": [{"role": m.role, "content": m.content} for m in messages],
                    },
                    timeout=_chat_timeout(),
                )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Empty response from LLM provider")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("Empty content from LLM provider")
        return ChatResponse(
            content=content,
            usage=data.get("usage", {}),
        )
