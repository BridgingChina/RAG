"""Tests for app.main startup hooks."""
import pytest


@pytest.mark.asyncio
async def test_startup_registers_known_env_keys(monkeypatch):
    """A9: the startup hook must seed _SENSITIVE_KEYS with known env secrets
    so future exception messages can be sanitized even if the key leaks."""
    from app.providers._sanitize import _SENSITIVE_KEYS, _reset
    _reset()
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-long-enough-zhipu-token-1234")

    # Import the startup function directly to avoid side-effects of app creation
    from app.main import on_startup_register_keys
    await on_startup_register_keys()

    assert "sk-long-enough-zhipu-token-1234" in _SENSITIVE_KEYS
    _reset()


@pytest.mark.asyncio
async def test_startup_hook_is_idempotent(monkeypatch):
    """Calling on_startup_register_keys twice must not raise or duplicate
    (sets are naturally dedup'd but we want the function call to be safe)."""
    from app.providers._sanitize import _SENSITIVE_KEYS, _reset
    _reset()
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-idempotent-test-value-123")

    from app.main import on_startup_register_keys
    await on_startup_register_keys()
    await on_startup_register_keys()

    assert "sk-idempotent-test-value-123" in _SENSITIVE_KEYS
    _reset()


@pytest.mark.asyncio
async def test_startup_skips_empty_env(monkeypatch):
    """If an env var isn't set, the hook must not raise — it's a seed-only op."""
    from app.providers._sanitize import _SENSITIVE_KEYS, _reset
    _reset()
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)

    from app.main import on_startup_register_keys
    await on_startup_register_keys()  # must not raise

    # _SENSITIVE_KEYS may be empty or contain pre-seeded values; what matters
    # is that the call didn't blow up when an env was missing.
    _reset()
