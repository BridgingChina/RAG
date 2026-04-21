import pytest
from app.providers.config import ProviderConfig
from app.providers._secret import resolve_api_key
from app.providers.errors import ProviderConfigurationError


def test_config_is_frozen():
    c = ProviderConfig(
        provider_id="pid", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        c.base_url = "https://y"  # type: ignore


def test_config_default_extras():
    c = ProviderConfig(
        provider_id="pid", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    assert c.extra_headers == {}
    assert c.timeout_read == 90.0


def test_resolve_api_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_api_key("MISSING_KEY")
    assert "MISSING_KEY" in str(exc_info.value)


def test_resolve_api_key_returns_value(monkeypatch):
    monkeypatch.setenv("REAL_KEY", "sk-thisisalongenoughkey1234")
    assert resolve_api_key("REAL_KEY") == "sk-thisisalongenoughkey1234"
