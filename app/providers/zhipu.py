import logging

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.providers.base import ChatMessage, ChatResponse, LLMProvider

logger = logging.getLogger(__name__)


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
        # 5 attempts so the exponential schedule can cover Zhipu's 60-120s
        # 429 cooldown window at least once.
        stop=stop_after_attempt(5),
        # Deterministic exponential floor + small random jitter.
        # ``wait_exponential(multiplier=4, max=120)`` produces a monotonic
        # schedule: 4 → 8 → 16 → 32 → 64 → 120 seconds. Adding
        # ``wait_random(1, 5)`` prevents thundering-herd re-collision
        # without letting the total drop below the exponential floor.
        #
        # NOTE: the previous ``wait_random_exponential(multiplier=2, max=120)``
        # was observed in production (log sample 2026-04-11 20:34-35) to pick
        # sleeps as short as 0.1 s — completely useless against a 60 s rate-limit
        # cooldown. ``wait_random_exponential`` samples uniformly from
        # ``(0, multiplier * 2^attempt)``, so ~half the samples fall below
        # any useful floor. Use exponential + random as an additive combo
        # instead.
        wait=wait_exponential(multiplier=4, max=120) + wait_random(min=1, max=5),
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
        # 5 attempts so the exponential schedule can cover Zhipu's 60-120s
        # 429 cooldown window at least once.
        stop=stop_after_attempt(5),
        # Deterministic exponential floor + small random jitter.
        # ``wait_exponential(multiplier=4, max=120)`` produces a monotonic
        # schedule: 4 → 8 → 16 → 32 → 64 → 120 seconds. Adding
        # ``wait_random(1, 5)`` prevents thundering-herd re-collision
        # without letting the total drop below the exponential floor.
        #
        # NOTE: the previous ``wait_random_exponential(multiplier=2, max=120)``
        # was observed in production (log sample 2026-04-11 20:34-35) to pick
        # sleeps as short as 0.1 s — completely useless against a 60 s rate-limit
        # cooldown. ``wait_random_exponential`` samples uniformly from
        # ``(0, multiplier * 2^attempt)``, so ~half the samples fall below
        # any useful floor. Use exponential + random as an additive combo
        # instead.
        wait=wait_exponential(multiplier=4, max=120) + wait_random(min=1, max=5),
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        base = self.CHAT_BASE_URL or self.BASE_URL
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
