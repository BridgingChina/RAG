import json
import logging
from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ContextResult:
    """Result of context enrichment."""
    contextual_text: str
    entities: list[str]
    resolved_references: dict[str, str]


class ContextEnricher:
    """Generate contextual text for chunks to improve embedding quality."""

    PROMPT_TEMPLATE = """你是桥梁知识整理助手。请为以下文本片段生成一段上下文描述（80-160字）。

【来源】{source_title}
【章节】{section_title}
【页码】{page_range}
【前文摘要】{prev_summary}
【文本片段】
{content}

请输出 JSON：
{{
  "contextual_text": "该片段来自《xxx》第x章，主要介绍...",
  "entities": ["桥名", "术语1", "术语2"],
  "resolved_references": {{"该桥": "具体桥名", "它": "具体桥名"}}
}}

要求：
1. contextual_text 需包含：来源位置、主题概述、关键术语
2. 如有「该桥/它/此结构」等指代，明确写出指代对象
3. 如无法确定指代对象，写 "unknown"
"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def enrich(
        self,
        content: str,
        source_title: str,
        section_title: str | None,
        page_range: str | None,
        surrounding_chunks: list[str] | None = None,
    ) -> ContextResult:
        """Generate contextual text for a chunk."""
        prev_summary = ""
        if surrounding_chunks:
            prev_summary = surrounding_chunks[0][:200] + "..."

        prompt = self.PROMPT_TEMPLATE.format(
            source_title=source_title or "未知来源",
            section_title=section_title or "未知章节",
            page_range=page_range or "未知页码",
            prev_summary=prev_summary or "无",
            content=content,
        )

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> ContextResult:
        """Parse LLM response into ContextResult."""
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)
                return ContextResult(
                    contextual_text=data.get("contextual_text", ""),
                    entities=data.get("entities", []),
                    resolved_references=data.get("resolved_references", {}),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: return empty contextual_text to avoid polluting index
        logger.warning(
            "Failed to parse ContextEnricher LLM response as JSON, "
            "returning empty contextual_text. Raw response: %.200s",
            content,
        )
        return ContextResult(
            contextual_text="",
            entities=[],
            resolved_references={},
        )
