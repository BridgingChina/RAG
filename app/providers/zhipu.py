import httpx

from app.core.config import settings
from app.providers.base import ChatMessage, ChatResponse, LLMProvider


class ZhipuProvider(LLMProvider):
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.embedding_model = settings.embedding_model
        self.chat_model = settings.chat_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            embeddings = []
            for text in texts:
                resp = await client.post(
                    f"{self.BASE_URL}/embeddings",
                    headers=self._headers(),
                    json={"model": self.embedding_model, "input": text},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings.append(data["data"][0]["embedding"])
            return embeddings

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.chat_model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return ChatResponse(
                content=data["choices"][0]["message"]["content"],
                usage=data.get("usage", {}),
            )
