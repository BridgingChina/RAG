from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    kind: str
    base_url: str
    api_key_env: str
    extra_headers: dict = field(default_factory=dict)
    timeout_read: float = 90.0
