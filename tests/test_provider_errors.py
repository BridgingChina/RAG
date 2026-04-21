import pytest
from app.providers.errors import (
    ProviderError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    ModelNotFoundError,
    TaskRouteNotFoundError,
)


def test_all_errors_subclass_provider_error():
    assert issubclass(ProviderConfigurationError, ProviderError)
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(ModelNotFoundError, ProviderError)
    assert issubclass(TaskRouteNotFoundError, ProviderError)


def test_provider_error_carries_message():
    exc = ProviderConfigurationError("env var missing")
    assert "env var missing" in str(exc)
