from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResponse:
    content: str
    usage: dict
    model: str = ""  # actual model used; default "" for back-compat with callers


@dataclass
class ModelInfo:
    id: str
    display_name: str
    kind: str                             # "chat" | "embedding" | "multimodal"
    context_window: int | None = None
    extra: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings for texts.

        model: None → provider falls back to its configured default
        (e.g. self.embedding_model). Phase C will tighten to required.
        """

    @abstractmethod
    async def chat(
        self, messages: list[ChatMessage], *, model: str | None = None
    ) -> ChatResponse:
        """Generate chat completion.

        model: None → provider falls back to self.chat_model. Phase C
        will tighten to required (kwarg, no default).
        """

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Fetch upstream-available models.

        Must raise `ProviderUnavailableError` on HTTP 429/5xx/network
        failures so the admin API can surface them with a sanitized
        reason. Must not cache on the Provider instance — caching is
        the router/DB's responsibility (llm_provider_models table).
        """
