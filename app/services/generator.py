import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Literal, Optional, TypeAlias

from app.llm import ChatMessage, chat_for_task, chat_stream_for_task
from app.services.hybrid_retriever import HybridRetrievalResult
from app.services.json_stream_parser import (
    JSONStreamParser,
    ParseDegradedError,
)

logger = logging.getLogger(__name__)


_JSON_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*\n?", re.IGNORECASE)
_JSON_FENCE_CLOSE_RE = re.compile(r"\n?\s*```\s*$", re.IGNORECASE)


def _strip_json_fences(text: str) -> str:
    """Remove leading ``` / ```json fence + trailing ``` from an LLM response.

    GLM-4.7-Flash via OpenRouter sometimes wraps JSON output in a markdown
    fence even when the prompt forbids it. Strip both ends so downstream
    ``find('{')..rfind('}')`` still works on responses that have stray
    characters before/after the fence.
    """
    if not text:
        return text
    stripped = _JSON_FENCE_OPEN_RE.sub("", text, count=1)
    stripped = _JSON_FENCE_CLOSE_RE.sub("", stripped, count=1)
    return stripped


_STREAMING_V2_PROMPT = """你是桥梁知识助手。根据以下证据回答问题，严格按 JSON 格式输出。

{evidence_text}

问题：{question}

只输出一个 JSON 对象，字段顺序严格如下；不要输出任何 markdown、代码块（```）、自然语言前后缀：

{{
  "summaries": [
    "第一个要点摘要 [1,3]",
    "第二个要点摘要 [2]"
  ],
  "details": [
    {{"explanation": "第一个要点的展开段落，引用证据写作 [1] [3] 这样的内联标记。", "citations": [1, 3]}},
    {{"explanation": "第二个要点的展开段落。", "citations": [2]}}
  ]
}}

要求：
- summaries 数组先输出，3-7 个简短中文要点，每个末尾用 [N] 或 [N,M] 标注引用证据编号（从 1 开始）
- details 数组与 summaries 一一对应，按相同顺序排列，长度必须一致
- citations 是整数数组，对应该要点引用的证据编号
- 不要 deep_dive、confidence 等额外字段
- 不要包裹任何 ``` 代码块标记，直接以 {{ 开头、以 }} 结尾"""


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
    """Answer generator — Phase C routes LLM via ``chat_for_task('qa_generation')``.

    No injected provider — the task router picks the backend. Instantiation is
    still a class (rather than module-level functions) so future state (per-
    request retry budget, streaming cursor) has a natural home.
    """

    TASK_KEY = "qa_generation"

    def __init__(self) -> None:
        pass

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
        response = await chat_for_task(self.TASK_KEY, messages)

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
        response = await chat_for_task(self.TASK_KEY, messages)

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

        # Strip ```json ... ``` fences before brace search — issue #185 P1
        # showed GLM via OpenRouter wrapping its JSON output in a fence
        # which made find('{')..rfind('}') still match the JSON, but downstream
        # newer schemas with leading text-before-fence broke. Strip first.
        cleaned = _strip_json_fences(content)

        try:
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}") + 1
            if json_start < 0 or json_end <= json_start:
                raise json.JSONDecodeError("No JSON found", cleaned, 0)

            data = json.loads(cleaned[json_start:json_end])
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
            # Issue #185 P1: don't dump entire raw JSON into outline.summary;
            # truncate hard so the UI doesn't show a wall of `{...}` text.
            raw_for_summary = cleaned.strip().splitlines()[0][:120] if cleaned.strip() else "(空响应)"
            raw_for_explanation = cleaned.strip()[:600] if cleaned.strip() else "(空响应)"
            events.append(("outline", {
                "key_points": [{"id": fallback_id, "summary": raw_for_summary, "order": 1}],
            }))
            events.append(("detail", {
                "key_point_id": fallback_id,
                "explanation": raw_for_explanation,
                "citations": [],
            }))
            events.append(("degraded", {"reason": "legacy_parse_failed"}))

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

    async def generate_streaming_v2(
        self,
        question: str,
        evidence: HybridRetrievalResult,
    ):
        """True-streaming generator. Yields (event_type, payload) tuples.

        Raises ParseDegradedError when the LLM produces text without recognizable
        JSON structure — caller should yield a single fallback `detail` event
        from `exc.fallback_payload` plus a `degraded` event.
        """
        from app.services.hybrid_retriever import format_evidence_for_llm

        prompt = _STREAMING_V2_PROMPT.format(
            evidence_text=format_evidence_for_llm(evidence),
            question=question,
        )
        messages = [ChatMessage(role="user", content=prompt)]

        parser = JSONStreamParser()
        async for token in chat_stream_for_task(self.TASK_KEY, messages):
            for event in parser.feed(token):
                yield event
        for event in parser.flush():
            yield event
