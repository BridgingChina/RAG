from app.core.config import settings
from app.providers.base import ChatMessage, ChatResponse, LLMProvider
from app.providers.file_parser import FileParserProvider, ParseResult
from app.providers.zhipu import ZhipuProvider
from app.providers.zhipu_coding import ZhipuCodingProvider


def get_provider() -> LLMProvider:
    """Return the configured LLM provider instance."""
    if settings.use_coding_plan:
        return ZhipuCodingProvider()
    return ZhipuProvider()


__all__ = [
    "ChatMessage",
    "ChatResponse",
    "FileParserProvider",
    "LLMProvider",
    "ParseResult",
    "ZhipuCodingProvider",
    "ZhipuProvider",
    "get_provider",
]
