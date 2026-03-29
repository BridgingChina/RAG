import json
import logging
import uuid
from dataclasses import dataclass
from typing import Literal, Optional, TypeAlias

from app.providers import ChatMessage, LLMProvider
from app.services.hybrid_retriever import HybridRetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    chunk_id: uuid.UUID
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

    async def generate_streaming(
        self,
        question: str,
        evidence: HybridRetrievalResult,
    ) -> list[tuple[str, dict]]:
        """Single LLM call + pseudo-streaming split into SSE events.

        Returns list of (event_type, data) tuples:
        - ("outline", {"key_points": [...]})
        - ("detail", {"key_point_id": ..., "explanation": ..., "citations": [...]})
        - ("deep_dive", {...})  -- if present
        - ("sources", {"sources": [...]})

        TODO: Upgrade to real LLM streaming with async generator.
        """
        from app.services.hybrid_retriever import format_evidence_for_llm

        evidence_text = format_evidence_for_llm(evidence)

        prompt = f"""你是桥梁知识助手。根据以下证据回答问题。

{evidence_text}

问题：{question}

请按以下JSON格式回答（不要输出任何其他内容）：
{{
    "key_points": [
        {{"summary": "要点摘要", "explanation": "详细解释", "citations": [1, 2]}}
    ],
    "deep_dive": null,
    "confidence": {{
        "level": "high|medium|low",
        "reason": "置信度理由"
    }}
}}

要求：
- key_points 包含 3~7 个要点，每个有 summary（一句话）和 explanation（展开说明）
- citations 引用证据编号（从1开始）
- deep_dive 如有比较或争议可填写，否则 null
- 置信度按证据充分程度判断"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        if not response.content:
            logger.warning("LLM returned empty content for streaming QA")
            return [("error", {"code": "EMPTY_LLM_RESPONSE", "message": "LLM返回了空响应"})]

        return self._parse_streaming_response(response.content, evidence)

    def _parse_streaming_response(
        self,
        content: str,
        evidence: HybridRetrievalResult,
    ) -> list[tuple[str, dict]]:
        """Parse LLM JSON response into a list of SSE events."""
        events: list[tuple[str, dict]] = []

        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start < 0 or json_end <= json_start:
                raise json.JSONDecodeError("No JSON found", content, 0)

            data = json.loads(content[json_start:json_end])
            key_points = data.get("key_points", [])

            kp_entries = []
            for i, kp in enumerate(key_points, 1):
                kp_id = str(uuid.uuid4())
                kp_entries.append({
                    "id": kp_id,
                    "summary": kp.get("summary", ""),
                    "order": i,
                    "_explanation": kp.get("explanation", ""),
                    "_citations": kp.get("citations", []),
                })

            events.append(("outline", {
                "key_points": [
                    {"id": kp["id"], "summary": kp["summary"], "order": kp["order"]}
                    for kp in kp_entries
                ],
            }))

            for kp in kp_entries:
                events.append(("detail", {
                    "key_point_id": kp["id"],
                    "explanation": kp["_explanation"],
                    "citations": kp["_citations"],
                }))

            deep_dive = data.get("deep_dive")
            if deep_dive:
                events.append(("deep_dive", deep_dive))

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse streaming LLM response, falling back to raw text: %s", e)
            fallback_id = str(uuid.uuid4())
            events.append(("outline", {
                "key_points": [{"id": fallback_id, "summary": content[:200], "order": 1}],
            }))
            events.append(("detail", {
                "key_point_id": fallback_id,
                "explanation": content,
                "citations": [],
            }))

        # Sources event — contiguous IDs for deduplicated sources
        all_chunks = evidence.all_chunks()
        sources = []
        seen_sources: set[str] = set()
        for chunk in all_chunks:
            source_title = chunk.bridge_name or f"来源"
            if source_title not in seen_sources:
                sources.append({
                    "id": len(sources) + 1,
                    "title": source_title,
                    "author": None,
                    "type": None,
                    "excerpt": chunk.content[:100] if chunk.content else None,
                    "location": None,
                })
                seen_sources.add(source_title)
        events.append(("sources", {"sources": sources}))

        return events
