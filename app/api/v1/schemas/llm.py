"""Admin API schemas for /api/v1/llm/* routing endpoints (Phase D).

Zero-key-exposure invariant: the response schemas in this module MUST NOT
carry ``api_key``, ``api_key_env``, or ``extra_headers``. The admin UI gets
a boolean ``has_api_key_configured`` derived at handler time from
``os.environ[api_key_env]`` — the env var name itself never leaves the
process. See ``docs/plans/2026-04-21-multi-provider-model-routing-design.md``
§9 (Security) for the full rationale.

Input schemas (``ProviderCreate`` / ``ProviderUpdate``) DO accept
``api_key_env`` because the admin is setting up the routing, but the
uppercase regex refuses anything that looks like an api_key literal.
Protected headers (``Authorization``, ``x-api-key``, etc.) are stripped from
``extra_headers`` in the input validator — they'd duplicate / clobber the
key auth the Provider's ``_headers()`` installs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


ProviderKind = Literal["zhipu", "openai_compat", "minimax"]

# Lowercase-compared: ``extra_headers`` values are untrusted user input, so
# case-insensitive comparison on the key name is the right defensive choice.
_PROTECTED_HEADERS: frozenset[str] = frozenset({
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "cookie",
    "set-cookie",
})


def _strip_protected_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove protected headers (case-insensitive) from a header dict."""
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in _PROTECTED_HEADERS
    }


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class ProviderCreate(BaseModel):
    """Payload for ``POST /api/v1/llm/providers``."""

    name: str = Field(min_length=1, max_length=64)
    kind: ProviderKind
    # base_url: the FULL endpoint prefix — caller is responsible for any
    # versioning path like `/v1` (OpenAI-style) or `/api/paas/v4` (Zhipu).
    # We validate as URL for correctness but store as str; trailing slash is
    # stripped so `{base_url}/models` never produces `//models`.
    base_url: str = Field(min_length=1, max_length=512)
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout_read: float = Field(default=90.0, ge=5.0, le=600.0)

    @field_validator("base_url", mode="after")
    @classmethod
    def _normalize_base_url(cls, v: str) -> str:
        # Validate as URL (raises if malformed) but return cleaned string
        AnyHttpUrl(v)
        return v.rstrip("/")

    @field_validator("extra_headers", mode="after")
    @classmethod
    def _filter_protected(cls, v: dict[str, str]) -> dict[str, str]:
        return _strip_protected_headers(v)


class ProviderUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/llm/providers/{id}``.

    All fields optional — only the provided keys get updated. ``kind`` is
    deliberately excluded; re-interpreting an existing row as a different
    provider kind is the wrong mental model. Create a new provider instead.
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    extra_headers: dict[str, str] | None = None
    enabled: bool | None = None
    timeout_read: float | None = Field(default=None, ge=5.0, le=600.0)

    @field_validator("base_url", mode="after")
    @classmethod
    def _normalize_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        AnyHttpUrl(v)
        return v.rstrip("/")

    @field_validator("extra_headers", mode="after")
    @classmethod
    def _filter_protected(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return None
        return _strip_protected_headers(v)


class TaskRouteUpdate(BaseModel):
    """Single-entry payload for ``PUT /tasks/{task_key}`` and batch items."""

    task_key: str
    provider_id: UUID
    model_id: str = Field(min_length=1, max_length=128)


class TaskRouteBatchUpdate(BaseModel):
    """Payload for ``POST /tasks/batch-update``."""

    updates: list[TaskRouteUpdate] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Response schemas (WHITELIST — zero-key-exposure)
# ---------------------------------------------------------------------------


class ProviderPublic(BaseModel):
    """Public projection of ``llm_providers``.

    Omits ``api_key_env`` and ``extra_headers`` by design. The boolean
    ``has_api_key_configured`` is the only fact the admin UI needs to
    surface a health indicator — whether the env var is set and non-empty.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: ProviderKind
    base_url: str
    enabled: bool
    timeout_read: float
    has_api_key_configured: bool
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None
    model_count: int
    created_at: datetime
    updated_at: datetime


class ModelInfoPublic(BaseModel):
    """One row of ``llm_provider_models`` — cached output of ``list_models()``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: str
    display_name: str
    kind: str
    context_window: int | None
    fetched_at: datetime


class ProviderTestResult(BaseModel):
    """Response for ``POST /providers/{id}/test``.

    On success: ``status="ok"`` and ``model_count`` is the number of models
    just refreshed. On failure: ``status="fail"`` and ``reason`` is the
    output of :func:`app.providers._sanitize.sanitize_error` (truncated,
    keys redacted).
    """

    status: Literal["ok", "fail"]
    model_count: int = 0
    reason: str | None = None


class TaskRoutePublic(BaseModel):
    """Joined view of ``llm_task_routes`` + provider name + description."""

    model_config = ConfigDict(from_attributes=True)

    task_key: str
    description: str
    provider_id: UUID
    provider_name: str
    model_id: str
    updated_at: datetime
    updated_by: UUID | None


__all__ = [
    "ModelInfoPublic",
    "ProviderCreate",
    "ProviderKind",
    "ProviderPublic",
    "ProviderTestResult",
    "ProviderUpdate",
    "TaskRouteBatchUpdate",
    "TaskRoutePublic",
    "TaskRouteUpdate",
]
