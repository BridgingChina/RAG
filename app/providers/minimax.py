"""MiniMax adapter — OpenAI-compatible REST shape with base_resp envelope.

MiniMax wraps responses in {..., "base_resp": {"status_code": int, "status_msg": str}}.
status_code == 0 → success; non-zero → upstream error (mapped to
ProviderUnavailableError so the admin UI surfaces a sanitized reason).

Embedding is NOT implemented in Phase A — MiniMax's embedding endpoint uses
a different request shape and isn't on our current rollout. Callers that
route an embedding task to a MiniMax provider will get a loud
NotImplementedError rather than silent fallback.
"""
import logging

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from app.providers.base import ChatMessage, ChatResponse, ModelInfo
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError
from app.providers.openai_compat import (
    OpenAICompatProvider,
    _is_retryable_http_error,
    _rate_limit_aware_wait,
)

logger = logging.getLogger(__name__)


class MiniMaxProvider(OpenAICompatProvider):
    """MiniMax chat + list_models, with base_resp envelope handling.

    Inherits __init__, _headers() (including protected-header filter),
    _chat_timeout(), _embed_timeout(), _semaphore from OpenAICompatProvider.
    Overrides exactly three methods whose response format differs:
      - chat()         → unwrap base_resp before parsing choices
      - embed()        → raise NotImplementedError (out-of-scope for Phase A)
      - list_models()  → defensively unwrap base_resp if present
    """

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
        """Send chat completion via {base_url}/v1/chat/completions.

        HTTP 429 / 5xx retry via tenacity (same 8-attempt config as the parent).
        base_resp.status_code != 0 is a business-level error — we raise
        ProviderUnavailableError AFTER resp.raise_for_status(), which tenacity
        does NOT consider retryable (_is_retryable_http_error only matches
        httpx exceptions). Intentional: non-transient by definition.
        """
        if not model:
            raise ProviderConfigurationError(
                f"model= is required for MiniMaxProvider ({self._config.provider_id}); "
                "caller must pass an explicit model"
            )
        async with self._semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._config.base_url}/v1/chat/completions",
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

        # MiniMax-specific: check base_resp envelope for application-level errors.
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "unknown error")
            raise ProviderUnavailableError(
                f"MiniMax ({self._config.provider_id}) returned "
                f"base_resp.status_code={status_code}: {status_msg}"
            )

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

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """MiniMax embedding is NOT supported by this adapter in Phase A.

        Raised loudly to prevent silent fallback — the Phase C Registry
        should reject any task route that targets MiniMax for embedding.
        """
        raise NotImplementedError(
            "MiniMax embedding is not supported by this adapter in Phase A. "
            "Route embedding tasks to a Zhipu / OpenAI-compat provider instead. "
            "If you need MiniMax embed support, override this method in a subclass."
        )

    async def list_models(self) -> list[ModelInfo]:
        """GET {base_url}/v1/models.

        MiniMax may or may not wrap /v1/models in base_resp — handle both.
        No automatic retry (same policy as ZhipuProvider.list_models /
        OpenAICompatProvider.list_models). Failures map to
        ProviderUnavailableError so the admin "refresh models" button
        surfaces them immediately.
        """
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._config.base_url}/v1/models",
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

        # Defensively unwrap if wrapped with base_resp.
        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict):
            status_code = base_resp.get("status_code", 0)
            if status_code != 0:
                raise ProviderUnavailableError(
                    f"MiniMax ({self._config.provider_id}) list_models "
                    f"base_resp.status_code={status_code}: "
                    f"{base_resp.get('status_msg', 'unknown error')}"
                )
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
