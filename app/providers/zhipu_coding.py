"""ZhipuAI Coding Plan provider -- same as ZhipuProvider but routes
chat completions through the Coding Plan endpoint."""

from app.providers.zhipu import ZhipuProvider


class ZhipuCodingProvider(ZhipuProvider):
    CHAT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
