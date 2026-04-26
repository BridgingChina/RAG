"""OpenAI-compatible provider — DeepSeek, Moonshot, 阿里百炼, OpenRouter, etc.

One class, many providers. Distinguished by ProviderConfig (base_url,
api_key_env, extra_headers). Key is read at call time via
resolve_api_key; NEVER cached on the instance (see _secret.py invariants).

Unlike ZhipuProvider, this class has NO default chat_model / embedding_model.
Every chat() / embed() call MUST pass an explicit model — the task router
(Phase C) is responsible for that.
"""
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

from app.providers._secret import resolve_api_key
from app.providers.base import ChatMessage, ChatResponse, LLMProvider, ModelInfo
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TEMPORARY: duplicate of zhipu.py helpers to keep A6+A7 scope tight.
# Extract to app/providers/_retry.py in a follow-up (Phase A cleanup or
# early Phase B) so both providers share one source of truth instead of
# drifting. Tracked as: "consolidate retry helpers across zhipu.py /
# openai_compat.py".
# ---------------------------------------------------------------------------


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for transient upstream/network errors worth retrying.

    Same policy as ZhipuProvider: 429, 5xx, and any httpx TransportError.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _rate_limit_aware_wait(retry_state: RetryCallState) -> float:
    """Adaptive wait: short for transport/5xx, long for 429.

    Mirrors zhipu.py — 30×attempt with jitter for 429, exponential for
    transport/5xx.
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

    base = min(2 ** attempt, 30)
    jitter = random.uniform(1, 5)
    return base + jitter


# --- end duplicated block ---


class OpenAICompatProvider(LLMProvider):
    """Adapter for OpenAI-compatible endpoints (DeepSeek / Moonshot / OpenRouter / custom).

    Config-driven: one class instance per ProviderConfig. Every chat() /
    embed() call MUST pass an explicit model — there is no fallback
    default. The task router (Phase C) owns model selection.
    """

    def __init__(self, config: ProviderConfig):
        self._config = config
        # Per-instance concurrency gate. Different upstream providers have
        # different rate budgets; one global semaphore would throttle fast
        # providers unnecessarily.
        self._semaphore = asyncio.Semaphore(3)

    def _headers(self) -> dict:
        """Build request headers with key read fresh from env (never cached).

        Invariant: do NOT store the resolved key on self — keeping it off
        instance state prevents leakage via repr() / logs / serialization.
        See app/providers/_secret.py.
        """
        # Defense-in-depth: protected headers can't be overridden via config.extra_headers
        # (admin writes are already gated in Phase D; this closes the boundary).
        _PROTECTED = {"authorization", "content-type"}
        safe_extras = {
            k: v for k, v in self._config.extra_headers.items()
            if k.lower() not in _PROTECTED
        }
        return {
            "Authorization": f"Bearer {resolve_api_key(self._config.api_key_env)}",
            "Content-Type": "application/json",
            **safe_extras,
        }

    def _chat_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=10.0,
            read=self._config.timeout_read,
            write=10.0,
            pool=10.0,
        )

    def _embed_timeout(self) -> httpx.Timeout:
        # Embeddings are fast; cap read at 20s regardless of config timeout_read.
        return httpx.Timeout(
            connect=10.0,
            read=min(20.0, self._config.timeout_read),
            write=10.0,
            pool=10.0,
        )

    @retry(
        stop=stop_after_attempt(8),
        wait=_rate_limit_aware_wait,
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatResponse:
        """Send chat completion via OpenAI-standard {base_url}/v1/chat/completions.

        Empty-string model is treated as unspecified; since this provider has
        no fallback default, empty/None both raise ProviderConfigurationError.
        """
        if not model:
            raise ProviderConfigurationError(
                f"model= is required for OpenAICompatProvider ({self._config.provider_id}); "
                "caller must pass an explicit model"
            )
        async with self._semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._config.base_url.rstrip('/')}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": model,
                        "messages": [
                            {"role": m.role, "content": m.content} for m in messages
                        ],
                    },
                    timeout=self._chat_timeout(),
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
            model=model,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ):
        """Streaming not implemented for generic OpenAI-compat / MiniMax routes.

        Loud NotImplementedError mirrors the embed() decision in MiniMaxProvider.
        QA streaming routes via chat_stream_for_task("qa_generation"), which is
        seeded to Zhipu in llm_task_routes (schema v13). If a future migration
        routes a streaming task to an OpenAI-compat provider, implement here
        following the same SSE shape used in ZhipuProvider.chat_stream.
        """
        raise NotImplementedError(
            "chat_stream is not implemented for OpenAI-compatible providers; "
            "route streaming tasks to a provider that supports it."
        )
        if False:  # marker for type checkers — keeps function as async generator
            yield ""

    @retry(
        stop=stop_after_attempt(8),
        wait=_rate_limit_aware_wait,
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings via OpenAI-standard {base_url}/v1/embeddings.

        Empty-string model is treated as unspecified; since this provider has
        no fallback default, empty/None both raise ProviderConfigurationError.
        """
        if not model:
            raise ProviderConfigurationError(
                f"model= is required for OpenAICompatProvider ({self._config.provider_id}); "
                "caller must pass an explicit model"
            )
        if not texts:
            return []
        async with self._semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._config.base_url.rstrip('/')}/embeddings",
                    headers=self._headers(),
                    json={"model": model, "input": texts},
                    timeout=self._embed_timeout(),
                )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data") or []
        if not isinstance(rows, list):
            raise TypeError(
                f"Invalid embeddings response: expected list in data, got {type(rows).__name__}"
            )
        if rows and isinstance(rows[0], dict) and "index" in rows[0]:
            rows = sorted(rows, key=lambda r: r.get("index", 0))
        if len(rows) != len(texts):
            raise ValueError(
                f"Invalid embeddings response: expected {len(texts)} rows, got {len(rows)}"
            )
        return [row["embedding"] for row in rows]

    async def list_models(self) -> list[ModelInfo]:
        """GET {base_url}/v1/models — OpenAI-standard catalog.

        No automatic retry (same policy as ZhipuProvider.list_models).
        Failures map 1:1 to ProviderUnavailableError so the admin
        "refresh models" button surfaces them immediately.

        OpenAI-style responses do not tag kind explicitly, so every row
        gets kind="chat" as a best-effort default. Phase D's UI model
        picker will need a heuristic refinement later.
        """
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._config.base_url.rstrip('/')}/models",
                    headers=self._headers(),
                    timeout=httpx.Timeout(
                        connect=10.0, read=20.0, write=10.0, pool=10.0
                    ),
                )
                resp.raise_for_status()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                raise ProviderUnavailableError(
                    f"{self._config.provider_id} list_models failed: {e}"
                ) from e
        data = resp.json()
        rows = data.get("data") or []
        return [
            ModelInfo(
                id=row["id"],
                display_name=row["id"],
                kind="chat",
                context_window=row.get("context_window"),
                extra={k: v for k, v in row.items() if k != "id"},
            )
            for row in rows
            if "id" in row
        ]
