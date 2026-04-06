import logging

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.providers.base import ChatMessage, ChatResponse, LLMProvider

logger = logging.getLogger(__name__)


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for 429 (rate limit) and 5xx (server) errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


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
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
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
                    timeout=30.0,
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
                timeout=60.0,
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
