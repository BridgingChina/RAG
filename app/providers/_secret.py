import os
from app.providers.errors import ProviderConfigurationError


def resolve_api_key(env_name: str) -> str:
    key = os.environ.get(env_name)
    if not key:
        raise ProviderConfigurationError(
            f"env var {env_name} not set; refusing to call provider with empty key"
        )
    return key
