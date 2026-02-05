import json
from dataclasses import dataclass
from typing import Literal, Optional, TypeAlias

from app.providers import ChatMessage, LLMProvider
from app.services.hybrid_retriever import HybridRetrievalResult


@dataclass
class Citation:
    chunk_id: int
    source_title: str
    page_range: str | None


ConfidenceLevel: TypeAlias = Literal["high", "medium", "low"]


@dataclass
class Confidence:
    """Confidence assessment for a generated answer."""
    level: ConfidenceLevel
    reason: str  # Explanation for the confidence level


@dataclass
class GenerationResult:
    """Generation result with confidence assessment."""
    summary: str
    details: str
    analogy: Optional[str]  # Analogy from similar bridges
    confidence: Confidence
    citations: list[Citation]
    sources: list[str]


# Alias for backwards compatibility
GenerationResultV2 = GenerationResult


class Generator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate_v2(
        self,
        question: str,
        evidence: HybridRetrievalResult,
    ) -> GenerationResult:
        """Generate answer with confidence assessment.

        Args:
            question: User question
            evidence: HybridRetrievalResult from HybridRetriever

        Returns:
            GenerationResult with summary, details, analogy, and confidence
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

        return self._parse_response(response.content, citations, sources)

    def _parse_response(
        self,
        content: str,
        citations: list[Citation],
        sources: list[str],
    ) -> GenerationResult:
        """Parse LLM response into GenerationResult.

        Args:
            content: Raw LLM response (should be JSON)
            citations: List of citations from evidence chunks
            sources: List of unique source titles

        Returns:
            GenerationResult object
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

                return GenerationResult(
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
                return GenerationResult(
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
            return GenerationResult(
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
