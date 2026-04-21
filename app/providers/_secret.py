"""API key resolver — sole entry point for reading provider secrets from env.

Invariants for callers (enforced by convention, not by type):
  1. Call `resolve_api_key(env_name)` fresh inside each `Provider._headers()`
     call — do NOT cache the returned value on `self.api_key` or similar.
     Keeping keys off instance state prevents leakage via `repr()`, logs, or
     accidental serialization.
  2. Never log the return value. If a caller wants to log which env was
     consulted, log only `env_name`, not `key`.
  3. Failures raise `ProviderConfigurationError` — the message contains the
     env var NAME (ops-debuggable) but never the value.
"""
import os
from app.providers.errors import ProviderConfigurationError


def resolve_api_key(env_name: str) -> str:
    key = (os.environ.get(env_name) or "").strip()
    if not key:
        raise ProviderConfigurationError(
            f"env var {env_name} not set; refusing to call provider with empty key"
        )
    return key
