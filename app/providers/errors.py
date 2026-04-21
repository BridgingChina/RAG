class ProviderError(Exception):
    """Base class for all provider-layer exceptions."""


class ProviderConfigurationError(ProviderError):
    """Missing env var, invalid base_url, unknown kind. → HTTP 400."""


class ProviderUnavailableError(ProviderError):
    """Upstream 429/5xx/network failure. → HTTP 502, message sanitized."""


class ModelNotFoundError(ProviderError):
    """Routed model_id no longer present in list_models(). → HTTP 409."""


class TaskRouteNotFoundError(ProviderError):
    """task_key has no row in llm_task_routes. → HTTP 500 (bug)."""
