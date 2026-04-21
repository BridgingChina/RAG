import httpx
import pytest
from app.providers._sanitize import register_sensitive_key, sanitize_error, _reset


@pytest.fixture(autouse=True)
def reset():
    _reset()
    yield
    _reset()


def test_strips_registered_key(monkeypatch):
    monkeypatch.setenv("FAKE_KEY", "sk-abc123def456ghi789jkl012")
    register_sensitive_key("FAKE_KEY")
    exc = RuntimeError("401 Bearer sk-abc123def456ghi789jkl012 invalid")
    out = sanitize_error(exc)
    assert "sk-abc123def456ghi789jkl012" not in out
    assert "***KEY***" in out


def test_regex_fallback_strips_bearer_token():
    exc = RuntimeError("got Bearer qwertyuiopasdfghjkl1234567 back")
    out = sanitize_error(exc)
    assert "qwertyuiopasdfghjkl" not in out
    assert "***KEY***" in out


def test_regex_fallback_strips_sk_prefix():
    exc = RuntimeError("api_key=sk-abcdefghijklmnopqrstuvwx expired")
    out = sanitize_error(exc)
    assert "sk-abcdefghijklmnopqrstuvwx" not in out


def test_truncates_to_300_chars():
    exc = RuntimeError("x" * 1000)
    assert len(sanitize_error(exc)) <= 300


def test_includes_cause_chain():
    cause = ValueError("underlying")
    exc = RuntimeError("wrapper")
    exc.__cause__ = cause
    out = sanitize_error(exc)
    assert "underlying" in out
    assert "wrapper" in out


def test_short_env_values_not_registered(monkeypatch):
    # values < 16 chars aren't treated as keys (false-positive guard)
    monkeypatch.setenv("SHORT", "dev")
    register_sensitive_key("SHORT")
    exc = RuntimeError("running in dev mode")
    assert "dev" in sanitize_error(exc)


def test_sanitize_tolerates_concurrent_key_registration(monkeypatch):
    """Regression guard for I2 — sanitize_error must snapshot _SENSITIVE_KEYS
    so that concurrent register_sensitive_key() calls cannot raise
    'Set changed size during iteration'."""
    import threading
    from app.providers._sanitize import _SENSITIVE_KEYS

    # Pre-populate with realistic values so iteration does work
    for i in range(50):
        _SENSITIVE_KEYS.add(f"pre_registered_key_value_long_enough_{i:04d}")

    errors: list[BaseException] = []
    stop_event = threading.Event()

    def mutate():
        i = 0
        while not stop_event.is_set():
            _SENSITIVE_KEYS.add(f"new_key_value_long_enough_{i:06d}")
            _SENSITIVE_KEYS.discard(f"pre_registered_key_value_long_enough_{(i % 50):04d}")
            i += 1

    def sanitize_loop():
        try:
            for _ in range(500):
                sanitize_error(RuntimeError("probe"))
        except RuntimeError as e:
            errors.append(e)

    t_mutate = threading.Thread(target=mutate, daemon=True)
    t_sanitize = threading.Thread(target=sanitize_loop)
    t_mutate.start()
    t_sanitize.start()
    t_sanitize.join(timeout=5)
    stop_event.set()
    t_mutate.join(timeout=1)

    assert not errors, f"sanitize_error raised during concurrent writes: {errors!r}"
