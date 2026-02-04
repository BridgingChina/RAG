import json
from dataclasses import dataclass
from typing import Literal, Optional, TypeAlias

from app.providers import ChatMessage, LLMProvider
from app.services.hybrid_retriever import HybridRetrievalResult
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


ConfidenceLevel: TypeAlias = Literal["high", "medium", "low"]


@dataclass
class Confidence:
    """Confidence assessment for a generated answer."""
    level: ConfidenceLevel
    reason: str  # Explanation for the confidence level


@dataclass
class GenerationResultV2:
    """V2 generation result with confidence assessment."""
    summary: str
    details: str
    analogy: Optional[str]  # Analogy from similar bridges
    confidence: Confidence
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

    async def generate_v2(
        self,
        question: str,
        evidence: HybridRetrievalResult,
    ) -> GenerationResultV2:
        """Generate V2 answer with confidence assessment.

        Args:
            question: User question
            evidence: HybridRetrievalResult from HybridRetriever

        Returns:
            GenerationResultV2 with summary, details, analogy, and confidence
        """
        from app.services.hybrid_retriever import format_evidence_for_llm

        evidence_text = format_evidence_for_llm(evidence)

        prompt = f"""你是桥梁知识助手。根据以下证据回答问题。

{evidence_text}

问题：{question}

请按以下JSON格式回答（不要输出任何其他内容）：
{{
    "summary": "简要要点（1-3句话）",
    "details": "详细说明",
    "analogy": "类比案例说明（如果【类比案例】有相关内容，否则null）",
    "confidence": {{
        "level": "high|medium|low",
        "reason": "置信度理由"
    }}
}}

置信度判断标准：
- high: 【本桥资料】有直接相关内容
- medium: 【通用知识】有相关内容，但【本桥资料】不足
- low: 证据不足或只有间接相关内容
"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        # Build citations and sources from all chunks
        citations = []
        sources = []
        seen_sources = set()

        all_chunks = evidence.all_chunks()
        for i, chunk in enumerate(all_chunks, 1):
            source_title = chunk.bridge_name or f"来源{i}"
            citations.append(Citation(
                chunk_id=chunk.chunk_id,
                source_title=source_title,
                page_range=None,
            ))
            if source_title not in seen_sources:
                sources.append(source_title)
                seen_sources.add(source_title)

        return self._parse_v2_response(response.content, citations, sources)

    def _parse_v2_response(
        self,
        content: str,
        citations: list[Citation],
        sources: list[str],
    ) -> GenerationResultV2:
        """Parse LLM response into GenerationResultV2.

        Args:
            content: Raw LLM response (should be JSON)
            citations: List of citations from evidence chunks
            sources: List of unique source titles

        Returns:
            GenerationResultV2 object
        """
        try:
            # Try to extract JSON from the response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)

                raw_level = data.get("confidence", {}).get("level", "low")
                level: ConfidenceLevel
                if raw_level in ("high", "medium", "low"):
                    level = raw_level
                else:
                    level = "low"

                return GenerationResultV2(
                    summary=data.get("summary", ""),
                    details=data.get("details", ""),
                    analogy=data.get("analogy"),
                    confidence=Confidence(
                        level=level,
                        reason=data.get("confidence", {}).get("reason", "无法评估"),
                    ),
                    citations=citations,
                    sources=sources,
                )
            else:
                # Fallback if no JSON found
                return GenerationResultV2(
                    summary=content[:200],
                    details=content,
                    analogy=None,
                    confidence=Confidence(
                        level="low",
                        reason="无法解析LLM响应格式",
                    ),
                    citations=citations,
                    sources=sources,
                )
        except json.JSONDecodeError:
            # Fallback on JSON parse error
            return GenerationResultV2(
                summary=content[:200],
                details=content,
                analogy=None,
                confidence=Confidence(
                    level="low",
                    reason="LLM响应格式错误",
                ),
                citations=citations,
                sources=sources,
            )
