from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider
from app.services.retriever import RetrievalResult


@dataclass
class Citation:
    chunk_id: int
    source_title: str
    page_range: str | None


@dataclass
class GenerationResult:
    summary: str
    details: str
    citations: list[Citation]
    sources: list[str]


class Generator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(
        self,
        question: str,
        evidence: list[RetrievalResult],
    ) -> GenerationResult:
        """Generate answer based on retrieved evidence."""
        if not evidence:
            return GenerationResult(
                summary="未找到相关证据。",
                details="知识库中没有与您问题相关的内容。",
                citations=[],
                sources=[],
            )

        # Build evidence text with citation markers
        evidence_text = ""
        for i, result in enumerate(evidence, 1):
            evidence_text += f"[{i}] {result.chunk.content}\n\n"

        prompt = f"""你是桥梁知识助手。根据以下证据回答问题。

证据：
{evidence_text}

问题：{question}

要求：
1. 优先基于证据回答，在关键信息后标注引用编号如[1][2]
2. 若证据不足以完整回答，明确说明"未找到直接证据"
3. 可附加常识性解释，但要标注为"（非引用）"

请按以下格式回答：

## 要点
- 要点1 [引用编号]
- 要点2 [引用编号]
...

## 详细说明
详细展开解释...
"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        # Build citations and sources
        citations = []
        sources = []
        seen_sources = set()

        for i, result in enumerate(evidence):
            citations.append(Citation(
                chunk_id=result.chunk.id,
                source_title=f"来源{i+1}",
                page_range=result.chunk.page_range,
            ))
            source_key = f"来源{i+1}"
            if source_key not in seen_sources:
                sources.append(source_key)
                seen_sources.add(source_key)

        # Parse response into summary and details
        content = response.content
        summary = ""
        details = content

        if "## 要点" in content and "## 详细说明" in content:
            parts = content.split("## 详细说明")
            summary_part = parts[0].replace("## 要点", "").strip()
            summary = summary_part
            details = parts[1].strip() if len(parts) > 1 else ""

        return GenerationResult(
            summary=summary,
            details=details,
            citations=citations,
            sources=sources,
        )
