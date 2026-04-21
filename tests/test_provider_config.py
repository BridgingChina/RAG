import pytest
from app.providers.config import ProviderConfig
from app.providers._secret import resolve_api_key
from app.providers.errors import ProviderConfigurationError


def test_config_is_frozen():
    from dataclasses import FrozenInstanceError
    c = ProviderConfig(
        provider_id="pid", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    with pytest.raises(FrozenInstanceError):
        c.base_url = "https://y"  # type: ignore


def test_config_default_extras():
    c1 = ProviderConfig(
        provider_id="pid1", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    c2 = ProviderConfig(
        provider_id="pid2", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    assert c1.extra_headers == {}
    assert c1.timeout_read == 90.0
    # Mutable-default trap regression: two instances must get separate dicts
    assert c1.extra_headers is not c2.extra_headers


def test_resolve_api_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_api_key("MISSING_KEY")
    assert "MISSING_KEY" in str(exc_info.value)


def test_resolve_api_key_returns_value(monkeypatch):
    monkeypatch.setenv("REAL_KEY", "sk-thisisalongenoughkey1234")
    assert resolve_api_key("REAL_KEY") == "sk-thisisalongenoughkey1234"


def test_resolve_api_key_raises_on_whitespace_only(monkeypatch):
    monkeypatch.setenv("WHITESPACE_KEY", "   ")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_api_key("WHITESPACE_KEY")
    assert "WHITESPACE_KEY" in str(exc_info.value)
