"""ZhipuAI Coding Plan provider — same as ZhipuProvider but routes
chat completions through the Coding Plan endpoint."""

from app.providers.zhipu import ZhipuProvider


class ZhipuCodingProvider(ZhipuProvider):
    CHAT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

    async def chat(self, messages):
        """Chat via Coding Plan endpoint; embedding still uses standard API."""
        import httpx

        from app.providers.base import ChatResponse

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.CHAT_BASE_URL}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.chat_model,
                    "messages": [
                        {"role": m.role, "content": m.content} for m in messages
                    ],
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise ValueError("Empty response from LLM provider")
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("Empty content from LLM provider")
            return ChatResponse(
                content=content,
                usage=data.get("usage", {}),
            )
