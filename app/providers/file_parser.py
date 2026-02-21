"""Zhipu file parsing service provider."""
import asyncio
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class ParseResult:
    status: str  # "processing" | "succeeded" | "failed"
    content: str | None = None
    download_url: str | None = None
    message: str | None = None


class FileParserProvider:
    """Zhipu file parsing API wrapper.

    Independent from LLMProvider -- different API surface, shared API key.
    """

    BASE_URL = "https://open.bigmodel.cn/api/paas/v4/files/parser"

    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.tool_type = settings.zhipu_parser_tool_type

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def create_task(
        self,
        file_bytes: bytes,
        file_name: str,
        file_type: str = "pdf",
        tool_type: str | None = None,
    ) -> str:
        """Upload file and create a parsing task. Returns zhipu task_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/create",
                headers=self._headers(),
                files={"file": (file_name, file_bytes)},
                data={
                    "tool_type": tool_type or self.tool_type,
                    "file_type": file_type.upper(),
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

            task_id = data.get("task_id")
            if not task_id:
                raise ValueError(f"Zhipu file parser returned no task_id: {data}")
            return task_id

    async def get_result(
        self, task_id: str, format_type: str = "download_link"
    ) -> ParseResult:
        """Query parsing result for a given task_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/result/{task_id}/{format_type}",
                headers=self._headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            body = resp.json()

            data = body.get("data", body)
            return ParseResult(
                status=data.get("status", "unknown"),
                content=data.get("content"),
                download_url=data.get("parsing_result_url"),
                message=data.get("message"),
            )

    async def poll_until_done(
        self,
        task_id: str,
        format_type: str = "download_link",
        timeout: float = 600,
        interval: float = 3,
    ) -> ParseResult:
        """Poll until parsing completes, fails, or times out."""
        elapsed = 0.0
        while elapsed < timeout:
            result = await self.get_result(task_id, format_type)
            if result.status == "succeeded":
                return result
            if result.status not in ("processing",):
                raise RuntimeError(
                    f"Zhipu parsing failed: status={result.status}, message={result.message}"
                )
            await asyncio.sleep(interval)
            elapsed += interval

        raise TimeoutError(
            f"Zhipu parsing timed out after {timeout}s for task {task_id}"
        )
