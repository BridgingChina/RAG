"""Unit tests for the Phase D /api/v1/llm/* Pydantic schemas.

Mostly zero-leak guards: the ``*Public`` response models must never carry
``api_key``, ``api_key_env``, or ``extra_headers``. These are the single
authoritative source of truth that the admin console serializes — a
regression here leaks straight to the browser.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.llm import (
    ModelInfoPublic,
    ProviderCreate,
    ProviderPublic,
    ProviderTestResult,
    ProviderUpdate,
    TaskRoutePublic,
    TaskRouteBatchUpdate,
    TaskRouteUpdate,
)


# ---------------------------------------------------------------------------
# Zero-key-exposure — static model inspection
# ---------------------------------------------------------------------------


def test_provider_public_has_no_api_key_fields():
    """ProviderPublic must NOT expose secret-adjacent fields."""
    names = set(ProviderPublic.model_fields.keys())
    forbidden = {"api_key", "api_key_env", "extra_headers"}
    leaked = names & forbidden
    assert not leaked, f"ProviderPublic leaks secret-adjacent fields: {leaked}"


def test_task_route_public_has_no_secret_fields():
    names = set(TaskRoutePublic.model_fields.keys())
    forbidden = {"api_key", "api_key_env", "extra_headers"}
    leaked = names & forbidden
    assert not leaked


def test_model_info_public_has_no_secret_fields():
    names = set(ModelInfoPublic.model_fields.keys())
    forbidden = {"api_key", "api_key_env", "extra_headers"}
    leaked = names & forbidden
    assert not leaked


def test_provider_test_result_has_no_secret_fields():
    names = set(ProviderTestResult.model_fields.keys())
    forbidden = {"api_key", "api_key_env", "extra_headers"}
    leaked = names & forbidden
    assert not leaked


# ---------------------------------------------------------------------------
# ProviderCreate validation
# ---------------------------------------------------------------------------


def test_provider_create_accepts_valid_payload():
    p = ProviderCreate(
        name="Zhipu Test",
        kind="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
    )
    assert p.api_key_env == "ZHIPU_API_KEY"
    assert p.timeout_read == 90.0
    assert p.enabled is True
    assert p.extra_headers == {}


def test_provider_create_validates_env_pattern_uppercase_only():
    """api_key_env must match ^[A-Z][A-Z0-9_]{0,63}$ — lowercase rejected."""
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="https://x.example.com",
            api_key_env="zhipu_api_key",  # lowercase
        )


def test_provider_create_validates_env_pattern_starts_with_letter():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="https://x.example.com",
            api_key_env="1_NUMBER_FIRST",
        )


def test_provider_create_rejects_env_too_long():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="https://x.example.com",
            api_key_env="A" * 65,  # 65 chars > 64
        )


def test_provider_create_validates_timeout_range_low():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="https://x.example.com",
            api_key_env="ZHIPU_API_KEY",
            timeout_read=4.9,
        )


def test_provider_create_validates_timeout_range_high():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="https://x.example.com",
            api_key_env="ZHIPU_API_KEY",
            timeout_read=600.1,
        )


def test_provider_create_accepts_timeout_boundaries():
    low = ProviderCreate(
        name="low", kind="zhipu",
        base_url="https://x.example.com",
        api_key_env="K", timeout_read=5.0,
    )
    high = ProviderCreate(
        name="high", kind="zhipu",
        base_url="https://x.example.com",
        api_key_env="K", timeout_read=600.0,
    )
    assert low.timeout_read == 5.0
    assert high.timeout_read == 600.0


def test_provider_create_strips_protected_headers():
    """Authorization / x-api-key / cookie etc. in extra_headers must be stripped."""
    p = ProviderCreate(
        name="t",
        kind="openai_compat",
        base_url="https://api.example.com",
        api_key_env="MY_KEY",
        extra_headers={
            "Authorization": "Bearer leaked",
            "x-api-key": "leaked-too",
            "X-Tenant-Id": "retained",
            "Cookie": "session=leaked",
            "User-Agent": "retained-ua",
        },
    )
    # lowercase match — preserved-name casing stays as provided
    assert "Authorization" not in p.extra_headers
    assert "x-api-key" not in p.extra_headers
    assert "Cookie" not in p.extra_headers
    assert p.extra_headers.get("X-Tenant-Id") == "retained"
    assert p.extra_headers.get("User-Agent") == "retained-ua"


def test_provider_create_rejects_invalid_kind():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="anthropic",  # not in Literal
            base_url="https://x.example.com",
            api_key_env="K",
        )


def test_provider_create_rejects_non_http_base_url():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="bad",
            kind="zhipu",
            base_url="not-a-url",
            api_key_env="K",
        )


# ---------------------------------------------------------------------------
# ProviderUpdate — all-optional, strips headers
# ---------------------------------------------------------------------------


def test_provider_update_all_optional():
    p = ProviderUpdate()
    # No fields set; model_dump(exclude_unset) yields empty dict.
    assert p.model_dump(exclude_unset=True) == {}


def test_provider_update_strips_protected_headers_when_present():
    p = ProviderUpdate(extra_headers={"Authorization": "Bearer X", "Keep": "me"})
    assert "Authorization" not in p.extra_headers
    assert p.extra_headers == {"Keep": "me"}


def test_provider_update_leaves_extra_headers_none_alone():
    p = ProviderUpdate()
    assert p.extra_headers is None


# ---------------------------------------------------------------------------
# TaskRouteUpdate + batch
# ---------------------------------------------------------------------------


def test_task_route_update_requires_model_id():
    import uuid

    with pytest.raises(ValidationError):
        TaskRouteUpdate(
            task_key="qa_generation",
            provider_id=uuid.uuid4(),
            model_id="",  # empty fails min_length=1
        )


def test_task_route_batch_requires_non_empty():
    with pytest.raises(ValidationError):
        TaskRouteBatchUpdate(updates=[])
