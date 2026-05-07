"""MiniMax adapter — OpenAI-compatible REST shape with base_resp envelope.

MiniMax wraps responses in {..., "base_resp": {"status_code": int, "status_msg": str}}.
status_code == 0 → success; non-zero → upstream error (mapped to
ProviderUnavailableError so the admin UI surfaces a sanitized reason).

Embedding is NOT implemented in Phase A — MiniMax's embedding endpoint uses
a different request shape and isn't on our current rollout. Callers that
route an embedding task to a MiniMax provider will get a loud
NotImplementedError rather than silent fallback.
"""
import json
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
        extra_params: dict | None = None,
    ) -> ChatResponse:
        """Send chat completion via {base_url}/v1/chat/completions.

        HTTP 429 / 5xx retry via tenacity (same 8-attempt config as the parent).
        base_resp.status_code != 0 is a business-level error — we raise
        ProviderUnavailableError AFTER resp.raise_for_status(), which tenacity
        does NOT consider retryable (_is_retryable_http_error only matches
        httpx exceptions). Intentional: non-transient by definition.

        ``extra_params`` is merged before ``model`` / ``messages``, so per-task
        knobs cannot override routing.
        """
        if not model:
            raise ProviderConfigurationError(
                f"model= is required for MiniMaxProvider ({self._config.provider_id}); "
                "caller must pass an explicit model"
            )
        payload: dict = {**(extra_params or {})}
        payload["model"] = model
        payload["messages"] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        async with self._semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._config.base_url.rstrip('/')}/chat/completions",
                    headers=self._headers(),
                    json=payload,
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

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        extra_params: dict | None = None,
    ):
        """Stream MiniMax chat completion, surfacing base_resp business-level errors.

        Inherits the OpenAI-compatible SSE shape from OpenAICompatProvider.chat_stream
        (delta.content fields), but additionally inspects each frame's optional
        base_resp envelope. A frame with status_code != 0 is a business-level error
        (insufficient quota, model offline, etc.) — abort the stream with
        ProviderUnavailableError, mirroring the non-streaming chat() behavior.

        ``extra_params`` follows the merge-before-override contract from
        :meth:`chat`.

        No tenacity retry: async generators are incompatible with tenacity. Retry
        semantics live at the call site (see qa.py:_streaming_with_retry).
        """
        if not model:
            raise ProviderConfigurationError(
                f"model= is required for MiniMaxProvider ({self._config.provider_id}); "
                "caller must pass an explicit model"
            )
        payload: dict = {**(extra_params or {})}
        payload["model"] = model
        payload["messages"] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        payload["stream"] = True
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self._chat_timeout()) as client:
                async with client.stream(
                    "POST",
                    f"{self._config.base_url.rstrip('/')}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            logger.warning(
                                "MiniMax stream (%s): dropping unparseable line: %r",
                                self._config.provider_id,
                                raw[:200],
                            )
                            continue

                        # MiniMax-specific: surface base_resp business errors BEFORE
                        # extracting delta — a malformed frame must not yield content
                        # before raising. status_code == 0 and absent base_resp both
                        # mean "OK" and pass through silently.
                        base_resp = chunk.get("base_resp") or {}
                        status_code = base_resp.get("status_code", 0)
                        if status_code != 0:
                            status_msg = base_resp.get("status_msg", "unknown error")
                            raise ProviderUnavailableError(
                                f"MiniMax ({self._config.provider_id}) stream returned "
                                f"base_resp.status_code={status_code}: {status_msg}"
                            )

                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta

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
