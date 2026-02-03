# V1 Retrieval Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement contextual text enrichment, FTS search, and dual-channel (Anchor + Concept + Analogy) retrieval for the Bridge RAG system.

**Architecture:** Add three new layers: (1) Context enrichment during ingest, (2) PostgreSQL FTS with jieba tokenization, (3) HybridRetriever with three retrieval channels merged via RRF.

**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL + pgvector, jieba, SQLAlchemy

---

## Task 1: Add jieba dependency

**Files:**
- Modify: `pyproject.toml:6-16`

**Step 1: Add jieba to dependencies**

Edit `pyproject.toml` to add jieba:

```toml
dependencies = [
    "click>=8.0.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "psycopg>=3.1.0",
    "pgvector>=0.2.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.26.0",
    "jieba>=0.42.1",
]
```

**Step 2: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed jieba

**Step 3: Verify jieba works**

Run: `python -c "import jieba; print(list(jieba.cut('赵州桥是石拱桥')))"`
Expected: `['赵州桥', '是', '石拱桥']`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add jieba dependency for Chinese tokenization"
```

---

## Task 2: Create Tokenizer service

**Files:**
- Create: `app/services/tokenizer.py`
- Create: `tests/test_tokenizer.py`
- Create: `data/bridge_terms.txt`

**Step 1: Create bridge terms dictionary**

Create `data/bridge_terms.txt`:

```
敞肩式 n
实腹式 n
系杆拱 n
斜拉桥 n
悬索桥 n
梁桥 n
浮桥 n
索桥 n
石拱桥 n
木拱桥 n
铁桥 n
赵州桥 nr
卢沟桥 nr
广济桥 nr
安平桥 nr
洛阳桥 nr
风雨桥 nr
```

**Step 2: Write the failing test**

Create `tests/test_tokenizer.py`:

```python
import pytest


def test_tokenize_basic():
    from app.services.tokenizer import Tokenizer

    tokenizer = Tokenizer()
    result = tokenizer.tokenize("赵州桥是石拱桥")
    assert "赵州桥" in result
    assert "石拱桥" in result


def test_tokenize_with_custom_dict():
    from app.services.tokenizer import Tokenizer

    tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")
    result = tokenizer.tokenize("敞肩式石拱桥结构")
    assert "敞肩式" in result
    assert "石拱桥" in result


def test_to_tsquery():
    from app.services.tokenizer import Tokenizer

    tokenizer = Tokenizer()
    result = tokenizer.to_tsquery("赵州桥的结构特点")
    # Should be words joined by " & "
    assert " & " in result
    assert "赵州桥" in result


def test_to_tsvector_text():
    from app.services.tokenizer import Tokenizer

    tokenizer = Tokenizer()
    result = tokenizer.to_tsvector_text("赵州桥是石拱桥")
    # Should be space-separated words
    assert " " in result
    assert "赵州桥" in result
    # Single chars should be filtered out
    assert "是" not in result
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_tokenizer.py -v`
Expected: FAIL with "No module named 'app.services.tokenizer'"

**Step 4: Write minimal implementation**

Create `app/services/tokenizer.py`:

```python
import jieba


class Tokenizer:
    """Chinese tokenizer using jieba, with optional custom dictionary."""

    def __init__(self, user_dict_path: str | None = None):
        if user_dict_path:
            jieba.load_userdict(user_dict_path)

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text, return list of words."""
        return list(jieba.cut_for_search(text))

    def to_tsquery(self, text: str) -> str:
        """Convert text to PostgreSQL tsquery format (AND joined)."""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        return " & ".join(words)

    def to_tsvector_text(self, text: str) -> str:
        """Convert text to space-separated words for tsvector storage."""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        return " ".join(words)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_tokenizer.py -v`
Expected: 4 passed

**Step 6: Commit**

```bash
git add app/services/tokenizer.py tests/test_tokenizer.py data/bridge_terms.txt
git commit -m "feat: add Tokenizer service with jieba Chinese tokenization"
```

---

## Task 3: Update Chunk model with new fields

**Files:**
- Modify: `app/models/chunk.py`
- Create: `tests/test_chunk_new_fields.py`

**Step 1: Write the failing test**

Create `tests/test_chunk_new_fields.py`:

```python
import pytest


def test_chunk_has_contextual_text_field():
    from app.models.chunk import Chunk

    # Verify field exists on model
    assert hasattr(Chunk, "contextual_text")


def test_chunk_has_search_text_field():
    from app.models.chunk import Chunk

    assert hasattr(Chunk, "search_text")


def test_chunk_has_tsv_field():
    from app.models.chunk import Chunk

    assert hasattr(Chunk, "tsv")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chunk_new_fields.py -v`
Expected: FAIL with "AssertionError"

**Step 3: Write minimal implementation**

Modify `app/models/chunk.py`:

```python
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    content: Mapped[str] = mapped_column(Text)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bridges.id"), nullable=True
    )
    page_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(2048))

    # New V1 fields
    contextual_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tsv: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("ix_chunks_taxonomy", "lvl1", "lvl2", "lvl3"),
        Index("ix_chunks_bridge", "bridge_id"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chunk_new_fields.py -v`
Expected: 3 passed

**Step 5: Run all existing tests to ensure no regressions**

Run: `pytest tests/ -v`
Expected: All tests pass (some may need DB recreation due to schema change)

**Step 6: Commit**

```bash
git add app/models/chunk.py tests/test_chunk_new_fields.py
git commit -m "feat: add contextual_text, search_text, tsv fields to Chunk model"
```

---

## Task 4: Create facets constants

**Files:**
- Create: `app/constants/__init__.py`
- Create: `app/constants/facets.py`
- Create: `tests/test_facets.py`

**Step 1: Write the failing test**

Create `tests/test_facets.py`:

```python
def test_bridge_types_defined():
    from app.constants.facets import BRIDGE_TYPES

    assert isinstance(BRIDGE_TYPES, list)
    assert "石拱桥" in BRIDGE_TYPES
    assert len(BRIDGE_TYPES) >= 5


def test_materials_defined():
    from app.constants.facets import MATERIALS

    assert isinstance(MATERIALS, list)
    assert "石" in MATERIALS


def test_eras_defined():
    from app.constants.facets import ERAS

    assert isinstance(ERAS, list)
    assert "隋唐" in ERAS


def test_regions_defined():
    from app.constants.facets import REGIONS

    assert isinstance(REGIONS, list)
    assert "华东" in REGIONS


def test_functions_defined():
    from app.constants.facets import FUNCTIONS

    assert isinstance(FUNCTIONS, list)
    assert "交通" in FUNCTIONS
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_facets.py -v`
Expected: FAIL with "No module named 'app.constants'"

**Step 3: Write minimal implementation**

Create `app/constants/__init__.py`:

```python
from app.constants.facets import (
    BRIDGE_TYPES,
    ERAS,
    FUNCTIONS,
    MATERIALS,
    REGIONS,
)

__all__ = ["BRIDGE_TYPES", "MATERIALS", "ERAS", "REGIONS", "FUNCTIONS"]
```

Create `app/constants/facets.py`:

```python
"""Predefined facet values for bridge attributes."""

BRIDGE_TYPES = [
    "石拱桥",
    "木拱桥",
    "铁桥",
    "悬索桥",
    "斜拉桥",
    "梁桥",
    "浮桥",
    "索桥",
]

MATERIALS = [
    "石",
    "木",
    "铁",
    "钢",
    "钢筋混凝土",
    "竹",
    "砖",
]

ERAS = [
    "先秦",
    "秦汉",
    "魏晋南北朝",
    "隋唐",
    "宋元",
    "明清",
    "近现代",
    "当代",
]

REGIONS = [
    "华北",
    "华东",
    "华南",
    "华中",
    "西南",
    "西北",
    "东北",
    "港澳台",
]

FUNCTIONS = [
    "交通",
    "军事",
    "景观",
    "水利",
    "铁路",
    "公路",
    "人行",
]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_facets.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add app/constants/__init__.py app/constants/facets.py tests/test_facets.py
git commit -m "feat: add facet constants for bridge attributes"
```

---

## Task 5: Create RRF ranker

**Files:**
- Create: `app/services/ranker.py`
- Create: `tests/test_ranker.py`

**Step 1: Write the failing test**

Create `tests/test_ranker.py`:

```python
def test_rrf_merge_basic():
    from app.services.ranker import rrf_merge

    vec_results = [1, 2, 3]
    fts_results = [2, 4, 1]
    merged = rrf_merge(vec_results, fts_results, k=60)

    # chunk 2 appears in both, should rank highest
    assert merged[0][0] == 2
    # Returns list of (chunk_id, score) tuples
    assert len(merged) == 4  # unique ids: 1, 2, 3, 4


def test_rrf_merge_empty_inputs():
    from app.services.ranker import rrf_merge

    merged = rrf_merge([], [], k=60)
    assert merged == []


def test_rrf_merge_single_source():
    from app.services.ranker import rrf_merge

    vec_results = [1, 2, 3]
    merged = rrf_merge(vec_results, [], k=60)
    assert len(merged) == 3
    assert merged[0][0] == 1  # first in vec should be first


def test_apply_diversity():
    from app.services.ranker import ChunkScore, apply_diversity

    chunks = [
        ChunkScore(chunk_id=1, bridge_id=10, score=0.9),
        ChunkScore(chunk_id=2, bridge_id=10, score=0.8),  # same bridge
        ChunkScore(chunk_id=3, bridge_id=20, score=0.7),
        ChunkScore(chunk_id=4, bridge_id=20, score=0.6),  # same bridge
    ]
    result = apply_diversity(chunks, max_per_bridge=1)

    # Should keep only 1 per bridge
    assert len(result) == 2
    bridge_ids = [c.bridge_id for c in result]
    assert len(set(bridge_ids)) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ranker.py -v`
Expected: FAIL with "No module named 'app.services.ranker'"

**Step 3: Write minimal implementation**

Create `app/services/ranker.py`:

```python
from dataclasses import dataclass


@dataclass
class ChunkScore:
    """Chunk with its retrieval score."""

    chunk_id: int
    bridge_id: int | None
    score: float


def rrf_merge(
    vec_results: list[int],
    fts_results: list[int],
    k: int = 60,
) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion to merge two ranked lists.

    Args:
        vec_results: chunk_ids from vector search, ordered by relevance
        fts_results: chunk_ids from FTS search, ordered by relevance
        k: RRF constant (typically 60)

    Returns:
        List of (chunk_id, rrf_score) tuples, sorted by score descending
    """
    scores: dict[int, float] = {}

    for rank, chunk_id in enumerate(vec_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)

    for rank, chunk_id in enumerate(fts_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)

    return sorted(scores.items(), key=lambda x: -x[1])


def apply_diversity(
    chunks: list[ChunkScore],
    max_per_bridge: int = 1,
) -> list[ChunkScore]:
    """
    Apply diversity constraint: max N chunks per bridge.

    Args:
        chunks: List of ChunkScore, assumed sorted by score descending
        max_per_bridge: Maximum chunks to keep per bridge_id

    Returns:
        Filtered list respecting diversity constraint
    """
    seen_bridges: dict[int | None, int] = {}
    result: list[ChunkScore] = []

    for chunk in chunks:
        bid = chunk.bridge_id
        count = seen_bridges.get(bid, 0)
        if count < max_per_bridge:
            result.append(chunk)
            seen_bridges[bid] = count + 1

    return result
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ranker.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/services/ranker.py tests/test_ranker.py
git commit -m "feat: add RRF ranker with diversity constraint"
```

---

## Task 6: Create ContextEnricher service

**Files:**
- Create: `app/services/context_enricher.py`
- Create: `tests/test_context_enricher.py`

**Step 1: Write the failing test**

Create `tests/test_context_enricher.py`:

```python
import pytest


class MockProvider:
    async def chat(self, messages):
        from app.providers import ChatResponse

        return ChatResponse(
            content='{"contextual_text": "来自《中国古桥》的片段，介绍赵州桥的敞肩式结构特点。", "entities": ["赵州桥", "敞肩式"], "resolved_references": {"该桥": "赵州桥"}}',
            usage={"total_tokens": 100},
        )


@pytest.mark.asyncio
async def test_enrich_basic():
    from app.services.context_enricher import ContextEnricher

    enricher = ContextEnricher(provider=MockProvider())
    result = await enricher.enrich(
        content="该桥采用敞肩式结构，主拱跨度37米。",
        source_title="中国古桥",
        section_title="第三章 石拱桥",
        page_range="45-46",
    )

    assert result.contextual_text is not None
    assert len(result.contextual_text) > 0
    assert "赵州桥" in result.entities or "敞肩式" in result.entities


@pytest.mark.asyncio
async def test_enrich_with_surrounding_context():
    from app.services.context_enricher import ContextEnricher

    enricher = ContextEnricher(provider=MockProvider())
    result = await enricher.enrich(
        content="它的主拱跨度达37米。",
        source_title="中国古桥",
        section_title="第三章",
        page_range="46",
        surrounding_chunks=["赵州桥是我国著名的古代石拱桥。"],
    )

    assert result.contextual_text is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_context_enricher.py -v`
Expected: FAIL with "No module named 'app.services.context_enricher'"

**Step 3: Write minimal implementation**

Create `app/services/context_enricher.py`:

```python
import json
from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider


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
            # Try to extract JSON from response
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

        # Fallback: use raw content as contextual_text
        return ContextResult(
            contextual_text=content[:160],
            entities=[],
            resolved_references={},
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_context_enricher.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add app/services/context_enricher.py tests/test_context_enricher.py
git commit -m "feat: add ContextEnricher service for chunk context generation"
```

---

## Task 7: Create FacetExtractor service

**Files:**
- Create: `app/services/facet_extractor.py`
- Create: `tests/test_facet_extractor.py`

**Step 1: Write the failing test**

Create `tests/test_facet_extractor.py`:

```python
import pytest


class MockProvider:
    async def chat(self, messages):
        from app.providers import ChatResponse

        return ChatResponse(
            content='{"bridge_type": "石拱桥", "material": "石", "era": ["隋唐", "宋元"], "region": null, "function": null}',
            usage={"total_tokens": 50},
        )


@pytest.mark.asyncio
async def test_extract_facet_basic():
    from app.services.facet_extractor import FacetExtractor

    extractor = FacetExtractor(provider=MockProvider())
    facet = await extractor.extract("古代石拱桥有什么特点")

    assert facet.bridge_type == "石拱桥" or facet.bridge_type == ["石拱桥"]
    assert facet.material == "石" or facet.material == ["石"]


@pytest.mark.asyncio
async def test_extract_facet_multi_era():
    from app.services.facet_extractor import FacetExtractor

    extractor = FacetExtractor(provider=MockProvider())
    facet = await extractor.extract("古桥的建造工艺")

    # Should return multiple eras for "古桥"
    assert facet.era is not None
    if isinstance(facet.era, list):
        assert len(facet.era) >= 1


def test_facet_to_lists():
    from app.services.facet_extractor import Facet

    facet = Facet(
        bridge_type="石拱桥",
        material=["石", "木"],
        era=None,
        region="华东",
        function=None,
    )

    # to_lists should normalize all to lists
    lists = facet.to_lists()
    assert lists["bridge_type"] == ["石拱桥"]
    assert lists["material"] == ["石", "木"]
    assert lists["era"] == []
    assert lists["region"] == ["华东"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_facet_extractor.py -v`
Expected: FAIL with "No module named 'app.services.facet_extractor'"

**Step 3: Write minimal implementation**

Create `app/services/facet_extractor.py`:

```python
import json
from dataclasses import dataclass, field

from app.constants.facets import (
    BRIDGE_TYPES,
    ERAS,
    FUNCTIONS,
    MATERIALS,
    REGIONS,
)
from app.providers import ChatMessage, LLMProvider


@dataclass
class Facet:
    """Extracted facets from a query."""

    bridge_type: str | list[str] | None = None
    material: str | list[str] | None = None
    era: str | list[str] | None = None
    region: str | list[str] | None = None
    function: str | list[str] | None = None

    def to_lists(self) -> dict[str, list[str]]:
        """Normalize all facets to lists for SQL queries."""
        result = {}
        for key in ["bridge_type", "material", "era", "region", "function"]:
            value = getattr(self, key)
            if value is None:
                result[key] = []
            elif isinstance(value, list):
                result[key] = value
            else:
                result[key] = [value]
        return result

    def is_empty(self) -> bool:
        """Check if all facets are empty."""
        lists = self.to_lists()
        return all(len(v) == 0 for v in lists.values())


class FacetExtractor:
    """Extract query facets using LLM with enum constraints."""

    PROMPT_TEMPLATE = """分析以下关于桥梁的问题，提取涉及的桥梁属性。

【问题】{query}

【枚举值约束 - 只能从以下选项中选择，可多选】
- bridge_type: {bridge_types}
- material: {materials}
- era: {eras}
- region: {regions}
- function: {functions}

输出 JSON（无关维度填 null，相关维度可以是单值或数组）：
{{
  "bridge_type": "石拱桥" 或 ["石拱桥", "木拱桥"] 或 null,
  "material": null,
  "era": null,
  "region": null,
  "function": null
}}
"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def extract(self, query: str) -> Facet:
        """Extract facets from a query."""
        prompt = self.PROMPT_TEMPLATE.format(
            query=query,
            bridge_types=", ".join(BRIDGE_TYPES),
            materials=", ".join(MATERIALS),
            eras=", ".join(ERAS),
            regions=", ".join(REGIONS),
            functions=", ".join(FUNCTIONS),
        )

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> Facet:
        """Parse LLM response into Facet."""
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)
                return Facet(
                    bridge_type=self._validate_facet(data.get("bridge_type"), BRIDGE_TYPES),
                    material=self._validate_facet(data.get("material"), MATERIALS),
                    era=self._validate_facet(data.get("era"), ERAS),
                    region=self._validate_facet(data.get("region"), REGIONS),
                    function=self._validate_facet(data.get("function"), FUNCTIONS),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        return Facet()

    def _validate_facet(
        self, value: str | list[str] | None, allowed: list[str]
    ) -> str | list[str] | None:
        """Validate facet value against allowed list."""
        if value is None:
            return None
        if isinstance(value, list):
            return [v for v in value if v in allowed] or None
        if value in allowed:
            return value
        return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_facet_extractor.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add app/services/facet_extractor.py tests/test_facet_extractor.py
git commit -m "feat: add FacetExtractor service with enum constraints"
```

---

## Task 8: Create HybridRetriever service

**Files:**
- Create: `app/services/hybrid_retriever.py`
- Create: `tests/test_hybrid_retriever.py`

**Step 1: Write the failing test**

Create `tests/test_hybrid_retriever.py`:

```python
import pytest
from dataclasses import dataclass


@dataclass
class MockChunk:
    id: int
    content: str
    bridge_id: int | None
    embedding: list[float]


class MockProvider:
    async def embed(self, texts):
        return [[0.1] * 2048 for _ in texts]

    async def chat(self, messages):
        from app.providers import ChatResponse

        return ChatResponse(
            content='{"bridge_type": null, "material": null, "era": null, "region": null, "function": null}',
            usage={"total_tokens": 50},
        )


def test_hybrid_retrieval_result_structure():
    from app.services.hybrid_retriever import HybridRetrievalResult

    result = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[],
    )
    assert hasattr(result, "anchor_chunks")
    assert hasattr(result, "concept_chunks")
    assert hasattr(result, "analogy_chunks")


def test_retrieval_quota_default():
    from app.services.hybrid_retriever import DEFAULT_QUOTA

    assert DEFAULT_QUOTA == (6, 2, 2)


def test_format_evidence_for_llm():
    from app.services.hybrid_retriever import (
        HybridRetrievalResult,
        RetrievedChunk,
        format_evidence_for_llm,
    )

    result = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="赵州桥是石拱桥", bridge_id=1, bridge_name="赵州桥", score=0.9),
        ],
        concept_chunks=[
            RetrievedChunk(chunk_id=2, content="石拱桥的定义", bridge_id=None, bridge_name=None, score=0.8),
        ],
        analogy_chunks=[
            RetrievedChunk(chunk_id=3, content="卢沟桥也是石拱桥", bridge_id=2, bridge_name="卢沟桥", score=0.7),
        ],
    )

    formatted = format_evidence_for_llm(result)
    assert "## 本桥证据" in formatted
    assert "## 通用概念" in formatted
    assert "## 类比参考" in formatted
    assert "[1]" in formatted
    assert "卢沟桥" in formatted
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_retriever.py -v`
Expected: FAIL with "No module named 'app.services.hybrid_retriever'"

**Step 3: Write minimal implementation**

Create `app/services/hybrid_retriever.py`:

```python
from dataclasses import dataclass

from app.providers import LLMProvider
from app.services.facet_extractor import FacetExtractor
from app.services.ranker import ChunkScore, apply_diversity, rrf_merge
from app.services.tokenizer import Tokenizer


DEFAULT_QUOTA = (6, 2, 2)  # anchor, concept, analogy


@dataclass
class RetrievedChunk:
    """A chunk retrieved with its metadata."""

    chunk_id: int
    content: str
    bridge_id: int | None
    bridge_name: str | None
    score: float


@dataclass
class HybridRetrievalResult:
    """Result of hybrid retrieval with three channels."""

    anchor_chunks: list[RetrievedChunk]
    concept_chunks: list[RetrievedChunk]
    analogy_chunks: list[RetrievedChunk]

    def all_chunks(self) -> list[RetrievedChunk]:
        """Get all chunks in citation order."""
        return self.anchor_chunks + self.concept_chunks + self.analogy_chunks


def format_evidence_for_llm(result: HybridRetrievalResult) -> str:
    """Format retrieval result for LLM prompt."""
    output = []
    idx = 1

    output.append("## 本桥证据")
    for chunk in result.anchor_chunks:
        output.append(f"[{idx}] {chunk.content}")
        idx += 1

    output.append("\n## 通用概念")
    for chunk in result.concept_chunks:
        output.append(f"[{idx}] {chunk.content}")
        idx += 1

    output.append("\n## 类比参考（其他相似桥）")
    for chunk in result.analogy_chunks:
        bridge_name = chunk.bridge_name or "未知桥"
        output.append(f"[{idx}] ({bridge_name}) {chunk.content}")
        idx += 1

    return "\n".join(output)


class HybridRetriever:
    """
    Dual-channel hybrid retriever.

    Retrieves from three channels:
    - Anchor: chunks for the target bridge
    - Concept: general knowledge chunks (bridge_id is NULL)
    - Analogy: chunks from similar bridges
    """

    def __init__(
        self,
        provider: LLMProvider,
        tokenizer: Tokenizer | None = None,
    ):
        self.provider = provider
        self.tokenizer = tokenizer or Tokenizer()
        self.facet_extractor = FacetExtractor(provider)

    async def retrieve(
        self,
        db,  # SQLAlchemy Session
        query: str,
        target_bridge_id: int | None = None,
        quota: tuple[int, int, int] = DEFAULT_QUOTA,
    ) -> HybridRetrievalResult:
        """
        Retrieve chunks using hybrid strategy.

        Args:
            db: Database session
            query: User query
            target_bridge_id: ID of the target bridge (for Anchor channel)
            quota: (anchor, concept, analogy) chunk limits

        Returns:
            HybridRetrievalResult with three channel results
        """
        import asyncio

        anchor_quota, concept_quota, analogy_quota = quota

        # Step 1: Parallel - embed query and extract facets
        embed_task = self.provider.embed([query])
        facet_task = self.facet_extractor.extract(query)

        embeddings, facet = await asyncio.gather(embed_task, facet_task)
        query_embedding = embeddings[0]

        # Step 2: Select candidate bridges for Analogy channel
        candidate_bridge_ids = []
        if not facet.is_empty():
            candidate_bridge_ids = await self._select_candidate_bridges(
                db, facet, target_bridge_id, limit=5
            )

        # Step 3: Three-channel retrieval (can be parallelized)
        anchor_chunks = await self._retrieve_channel(
            db, query_embedding, query, bridge_id=target_bridge_id, limit=anchor_quota * 2
        ) if target_bridge_id else []

        concept_chunks = await self._retrieve_channel(
            db, query_embedding, query, bridge_id_is_null=True, limit=concept_quota * 2
        )

        analogy_chunks = []
        if candidate_bridge_ids:
            analogy_chunks = await self._retrieve_channel(
                db, query_embedding, query, bridge_ids=candidate_bridge_ids, limit=analogy_quota * 3
            )

        # Step 4: Apply quotas and diversity
        anchor_result = anchor_chunks[:anchor_quota]
        concept_result = concept_chunks[:concept_quota]

        # Apply diversity to analogy: max 1 chunk per bridge
        analogy_scored = [
            ChunkScore(chunk_id=c.chunk_id, bridge_id=c.bridge_id, score=c.score)
            for c in analogy_chunks
        ]
        diverse_analogy = apply_diversity(analogy_scored, max_per_bridge=1)
        analogy_result = [
            c for c in analogy_chunks
            if c.chunk_id in {d.chunk_id for d in diverse_analogy}
        ][:analogy_quota]

        # Step 5: Deduplicate across channels
        seen_ids = set()
        for chunk in anchor_result:
            seen_ids.add(chunk.chunk_id)

        concept_result = [c for c in concept_result if c.chunk_id not in seen_ids]
        for chunk in concept_result:
            seen_ids.add(chunk.chunk_id)

        analogy_result = [c for c in analogy_result if c.chunk_id not in seen_ids]

        return HybridRetrievalResult(
            anchor_chunks=anchor_result,
            concept_chunks=concept_result,
            analogy_chunks=analogy_result,
        )

    async def _retrieve_channel(
        self,
        db,
        query_embedding: list[float],
        query: str,
        bridge_id: int | None = None,
        bridge_id_is_null: bool = False,
        bridge_ids: list[int] | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        """Retrieve from a single channel using vector + FTS."""
        # Vector search
        vec_results = await self._vector_search(
            db, query_embedding, bridge_id, bridge_id_is_null, bridge_ids, limit
        )

        # FTS search
        fts_results = await self._fts_search(
            db, query, bridge_id, bridge_id_is_null, bridge_ids, limit
        )

        # RRF merge
        vec_ids = [r.chunk_id for r in vec_results]
        fts_ids = [r.chunk_id for r in fts_results]
        merged = rrf_merge(vec_ids, fts_ids)

        # Build result with RRF scores
        chunk_map = {r.chunk_id: r for r in vec_results + fts_results}
        result = []
        for chunk_id, score in merged:
            if chunk_id in chunk_map:
                c = chunk_map[chunk_id]
                result.append(RetrievedChunk(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    bridge_id=c.bridge_id,
                    bridge_name=c.bridge_name,
                    score=score,
                ))
        return result[:limit]

    async def _vector_search(
        self,
        db,
        query_embedding: list[float],
        bridge_id: int | None,
        bridge_id_is_null: bool,
        bridge_ids: list[int] | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Vector similarity search."""
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        sql = """
            SELECT c.id, c.content, c.bridge_id, b.name as bridge_name,
                   1 - (c.embedding <=> %s::vector) as score
            FROM chunks c
            LEFT JOIN bridges b ON c.bridge_id = b.id
        """

        conditions = []
        args = [embedding_str]

        if bridge_id is not None:
            conditions.append("c.bridge_id = %s")
            args.append(bridge_id)
        elif bridge_id_is_null:
            conditions.append("c.bridge_id IS NULL")
        elif bridge_ids:
            conditions.append("c.bridge_id = ANY(%s)")
            args.append(bridge_ids)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY c.embedding <=> %s::vector LIMIT %s"
        args.extend([embedding_str, limit])

        cursor.execute(sql, args)
        rows = cursor.fetchall()
        cursor.close()

        return [
            RetrievedChunk(
                chunk_id=row[0],
                content=row[1],
                bridge_id=row[2],
                bridge_name=row[3],
                score=row[4],
            )
            for row in rows
        ]

    async def _fts_search(
        self,
        db,
        query: str,
        bridge_id: int | None,
        bridge_id_is_null: bool,
        bridge_ids: list[int] | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Full-text search using tsvector."""
        tsquery_text = self.tokenizer.to_tsvector_text(query)
        if not tsquery_text:
            return []

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        sql = """
            SELECT c.id, c.content, c.bridge_id, b.name as bridge_name,
                   ts_rank(c.tsv, plainto_tsquery('simple', %s)) as score
            FROM chunks c
            LEFT JOIN bridges b ON c.bridge_id = b.id
            WHERE c.tsv @@ plainto_tsquery('simple', %s)
        """

        args = [tsquery_text, tsquery_text]

        if bridge_id is not None:
            sql += " AND c.bridge_id = %s"
            args.append(bridge_id)
        elif bridge_id_is_null:
            sql += " AND c.bridge_id IS NULL"
        elif bridge_ids:
            sql += " AND c.bridge_id = ANY(%s)"
            args.append(bridge_ids)

        sql += " ORDER BY score DESC LIMIT %s"
        args.append(limit)

        try:
            cursor.execute(sql, args)
            rows = cursor.fetchall()
        except Exception:
            rows = []
        finally:
            cursor.close()

        return [
            RetrievedChunk(
                chunk_id=row[0],
                content=row[1],
                bridge_id=row[2],
                bridge_name=row[3],
                score=row[4],
            )
            for row in rows
        ]

    async def _select_candidate_bridges(
        self,
        db,
        facet,
        target_bridge_id: int | None,
        limit: int,
    ) -> list[int]:
        """Select candidate bridges based on facet matching."""
        lists = facet.to_lists()

        conditions = []
        args = []

        if lists["bridge_type"]:
            conditions.append("bridge_type = ANY(%s)")
            args.append(lists["bridge_type"])
        if lists["material"]:
            conditions.append("material = ANY(%s)")
            args.append(lists["material"])
        if lists["era"]:
            conditions.append("era = ANY(%s)")
            args.append(lists["era"])
        if lists["region"]:
            conditions.append("location ILIKE ANY(%s)")
            # Wrap regions for ILIKE
            args.append([f"%{r}%" for r in lists["region"]])

        if not conditions:
            return []

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        sql = f"""
            SELECT id FROM bridges
            WHERE ({" OR ".join(conditions)})
        """

        if target_bridge_id:
            sql += " AND id != %s"
            args.append(target_bridge_id)

        sql += " LIMIT %s"
        args.append(limit)

        try:
            cursor.execute(sql, args)
            rows = cursor.fetchall()
        except Exception:
            rows = []
        finally:
            cursor.close()

        return [row[0] for row in rows]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_retriever.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add app/services/hybrid_retriever.py tests/test_hybrid_retriever.py
git commit -m "feat: add HybridRetriever with three-channel retrieval"
```

---

## Task 9: Update Generator with confidence output

**Files:**
- Modify: `app/services/generator.py`
- Modify: `tests/test_generator.py`

**Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
@pytest.mark.asyncio
async def test_generate_with_confidence():
    from app.services.generator import Generator, GenerationResult
    from app.services.hybrid_retriever import HybridRetrievalResult, RetrievedChunk

    class MockProviderV2:
        async def chat(self, messages):
            from app.providers import ChatResponse
            return ChatResponse(
                content='{"summary": "要点", "details": "详细", "analogy": null, "confidence": {"level": "high", "reason": "证据充分"}}',
                usage={"total_tokens": 100},
            )

    generator = Generator(provider=MockProviderV2())

    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="测试内容", bridge_id=1, bridge_name="赵州桥", score=0.9),
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )

    result = await generator.generate_v2("测试问题", evidence)

    assert hasattr(result, "confidence")
    assert result.confidence.level in ["high", "medium", "low"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_generator.py::test_generate_with_confidence -v`
Expected: FAIL

**Step 3: Update implementation**

Modify `app/services/generator.py` to add:

```python
import json
from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider
from app.services.retriever import RetrievalResult


@dataclass
class Citation:
    chunk_id: int
    source_title: str
    page_range: str | None


@dataclass
class Confidence:
    level: str  # "high" | "medium" | "low"
    reason: str


@dataclass
class GenerationResult:
    summary: str
    details: str
    citations: list[Citation]
    sources: list[str]


@dataclass
class GenerationResultV2:
    """V2 result with confidence and analogy support."""

    summary: str
    details: str
    analogy: str | None
    citations: list[Citation]
    sources: list[str]
    confidence: Confidence


class Generator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(
        self,
        question: str,
        evidence: list[RetrievalResult],
    ) -> GenerationResult:
        """Generate answer based on retrieved evidence (V1 API)."""
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
        evidence,  # HybridRetrievalResult
    ) -> GenerationResultV2:
        """Generate answer with confidence (V2 API for hybrid retrieval)."""
        from app.services.hybrid_retriever import format_evidence_for_llm

        all_chunks = evidence.all_chunks()
        if not all_chunks:
            return GenerationResultV2(
                summary="未找到相关证据。",
                details="知识库中没有与您问题相关的内容。",
                analogy=None,
                citations=[],
                sources=[],
                confidence=Confidence(level="low", reason="无相关证据"),
            )

        evidence_text = format_evidence_for_llm(evidence)

        prompt = f"""你是桥梁知识问答助手。请根据以下证据回答问题。

【问题】{question}

【证据】
{evidence_text}

【回答要求】
1. 先答本桥：优先使用「本桥证据」回答，引用格式 [1][2]
2. 再做类比：如有需要，使用「类比参考」补充说明其他桥的做法
3. 概念补充：如需解释术语，可引用「通用概念」
4. 如果本桥证据不足，明确告知「本桥相关资料有限」
5. 无证据支撑的内容标注为「常识性补充」

请按以下 JSON 格式输出：
{{
  "summary": "要点（带引用）",
  "details": "详细说明",
  "analogy": "类比参考（如无则 null）",
  "confidence": {{
    "level": "high 或 medium 或 low",
    "reason": "简要说明判断依据"
  }}
}}

confidence 判断标准：
- high: 本桥证据充分，能完整回答问题
- medium: 本桥证据部分覆盖，需借助类比或通用概念补充
- low: 本桥证据极少或无，主要依赖类比推断
"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        # Build citations
        citations = []
        sources = []
        seen_sources = set()

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

        # Parse JSON response
        return self._parse_v2_response(response.content, citations, sources)

    def _parse_v2_response(
        self,
        content: str,
        citations: list[Citation],
        sources: list[str],
    ) -> GenerationResultV2:
        """Parse V2 JSON response."""
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                confidence_data = data.get("confidence", {})
                confidence = Confidence(
                    level=confidence_data.get("level", "low"),
                    reason=confidence_data.get("reason", "解析失败"),
                )

                return GenerationResultV2(
                    summary=data.get("summary", ""),
                    details=data.get("details", ""),
                    analogy=data.get("analogy"),
                    citations=citations,
                    sources=sources,
                    confidence=confidence,
                )
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback
        return GenerationResultV2(
            summary=content[:200],
            details=content,
            analogy=None,
            citations=citations,
            sources=sources,
            confidence=Confidence(level="low", reason="响应解析失败"),
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_generator.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add app/services/generator.py tests/test_generator.py
git commit -m "feat: add generate_v2 with confidence output"
```

---

## Task 10: Update API schemas

**Files:**
- Modify: `app/api/schemas.py`
- Create: `tests/test_schemas_v2.py`

**Step 1: Write the failing test**

Create `tests/test_schemas_v2.py`:

```python
def test_ask_request_has_target_bridge_id():
    from app.api.schemas import AskRequest

    req = AskRequest(question="测试", target_bridge_id=42)
    assert req.target_bridge_id == 42


def test_confidence_schema():
    from app.api.schemas import ConfidenceResponse

    conf = ConfidenceResponse(level="high", reason="证据充分")
    assert conf.level == "high"


def test_ask_response_v2_has_new_fields():
    from app.api.schemas import AskResponseV2, ConfidenceResponse

    resp = AskResponseV2(
        summary="要点",
        details="详细",
        analogy="类比",
        citations=[],
        sources=[],
        confidence=ConfidenceResponse(level="high", reason="测试"),
        evidence_groups=None,
        degraded=None,
    )
    assert resp.analogy == "类比"
    assert resp.confidence.level == "high"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas_v2.py -v`
Expected: FAIL

**Step 3: Update implementation**

Modify `app/api/schemas.py`:

```python
from pydantic import BaseModel


class AskContext(BaseModel):
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    question: str
    context: AskContext | None = None
    target_bridge_id: int | None = None  # V2: explicit target bridge


class CitationResponse(BaseModel):
    chunk_id: int
    source_title: str
    page_range: str | None


class AskResponse(BaseModel):
    """V1 response format."""

    summary: str
    details: str
    citations: list[CitationResponse]
    sources: list[str]


# V2 schemas

class ConfidenceResponse(BaseModel):
    level: str  # "high" | "medium" | "low"
    reason: str


class ChunkSummary(BaseModel):
    chunk_id: int
    preview: str
    bridge_name: str | None = None


class EvidenceGroupsResponse(BaseModel):
    anchor: list[ChunkSummary]
    concept: list[ChunkSummary]
    analogy: list[ChunkSummary]


class AskResponseV2(BaseModel):
    """V2 response with confidence and evidence groups."""

    summary: str
    details: str
    analogy: str | None
    citations: list[CitationResponse]
    sources: list[str]
    confidence: ConfidenceResponse
    evidence_groups: EvidenceGroupsResponse | None = None
    degraded: list[str] | None = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas_v2.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add app/api/schemas.py tests/test_schemas_v2.py
git commit -m "feat: add V2 API schemas with confidence and evidence groups"
```

---

## Task 11: Add /ask/v2 endpoint

**Files:**
- Modify: `app/api/ask.py`
- Create: `tests/test_api_ask_v2.py`

**Step 1: Write the failing test**

Create `tests/test_api_ask_v2.py`:

```python
import pytest
from fastapi.testclient import TestClient


def test_ask_v2_endpoint_exists():
    from app.main import app

    client = TestClient(app)

    # Just check the endpoint exists (will fail without DB, but route should exist)
    response = client.post("/ask/v2", json={"question": "测试"})
    # Should not be 404
    assert response.status_code != 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_ask_v2.py -v`
Expected: FAIL with 404

**Step 3: Update implementation**

Modify `app/api/ask.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import (
    AskRequest,
    AskResponse,
    AskResponseV2,
    ChunkSummary,
    CitationResponse,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator, Retriever, RetrievalContext
from app.services.hybrid_retriever import HybridRetriever
from app.services.tokenizer import Tokenizer

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    """V1 endpoint - simple vector retrieval."""
    provider = ZhipuProvider()
    retriever = Retriever(provider=provider)
    generator = Generator(provider=provider)

    # Build retrieval context
    context = None
    if request.context:
        context = RetrievalContext(
            bridge_id=request.context.bridge_id,
            lvl1=request.context.lvl1,
            lvl2=request.context.lvl2,
            lvl3=request.context.lvl3,
        )

    # Retrieve evidence
    evidence = await retriever.retrieve(db, request.question, context)

    # Generate answer
    result = await generator.generate(request.question, evidence)

    return AskResponse(
        summary=result.summary,
        details=result.details,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                source_title=c.source_title,
                page_range=c.page_range,
            )
            for c in result.citations
        ],
        sources=result.sources,
    )


@router.post("/ask/v2", response_model=AskResponseV2)
async def ask_v2(request: AskRequest, db: Session = Depends(get_db)):
    """V2 endpoint - hybrid retrieval with confidence."""
    provider = ZhipuProvider()
    tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")
    retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
    generator = Generator(provider=provider)

    degraded: list[str] = []

    # Get target bridge ID
    target_bridge_id = request.target_bridge_id
    if not target_bridge_id and request.context:
        target_bridge_id = request.context.bridge_id

    # Retrieve evidence
    try:
        evidence = await retriever.retrieve(
            db, request.question, target_bridge_id=target_bridge_id
        )
    except Exception as e:
        # Fallback to empty result
        from app.services.hybrid_retriever import HybridRetrievalResult
        evidence = HybridRetrievalResult(
            anchor_chunks=[], concept_chunks=[], analogy_chunks=[]
        )
        degraded.append("retrieval")

    # Generate answer
    result = await generator.generate_v2(request.question, evidence)

    # Build evidence groups for response
    evidence_groups = EvidenceGroupsResponse(
        anchor=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
                bridge_name=c.bridge_name,
            )
            for c in evidence.anchor_chunks
        ],
        concept=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
                bridge_name=None,
            )
            for c in evidence.concept_chunks
        ],
        analogy=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
                bridge_name=c.bridge_name,
            )
            for c in evidence.analogy_chunks
        ],
    )

    return AskResponseV2(
        summary=result.summary,
        details=result.details,
        analogy=result.analogy,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                source_title=c.source_title,
                page_range=c.page_range,
            )
            for c in result.citations
        ],
        sources=result.sources,
        confidence=ConfidenceResponse(
            level=result.confidence.level,
            reason=result.confidence.reason,
        ),
        evidence_groups=evidence_groups,
        degraded=degraded if degraded else None,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_ask_v2.py -v`
Expected: PASS (route exists)

**Step 5: Commit**

```bash
git add app/api/ask.py tests/test_api_ask_v2.py
git commit -m "feat: add /ask/v2 endpoint with hybrid retrieval"
```

---

## Task 12: Export new services from __init__.py

**Files:**
- Modify: `app/services/__init__.py`

**Step 1: Update exports**

Modify `app/services/__init__.py`:

```python
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher, ContextResult
from app.services.facet_extractor import Facet, FacetExtractor
from app.services.generator import (
    Citation,
    Confidence,
    GenerationResult,
    GenerationResultV2,
    Generator,
)
from app.services.hybrid_retriever import (
    DEFAULT_QUOTA,
    HybridRetrievalResult,
    HybridRetriever,
    RetrievedChunk,
    format_evidence_for_llm,
)
from app.services.ranker import ChunkScore, apply_diversity, rrf_merge
from app.services.retriever import RetrievalContext, RetrievalResult, Retriever
from app.services.tagger import MetadataTagger, TagResult
from app.services.tokenizer import Tokenizer

__all__ = [
    # Chunker
    "SemanticChunker",
    # Context Enricher
    "ContextEnricher",
    "ContextResult",
    # Facet Extractor
    "Facet",
    "FacetExtractor",
    # Generator
    "Citation",
    "Confidence",
    "GenerationResult",
    "GenerationResultV2",
    "Generator",
    # Hybrid Retriever
    "DEFAULT_QUOTA",
    "HybridRetrievalResult",
    "HybridRetriever",
    "RetrievedChunk",
    "format_evidence_for_llm",
    # Ranker
    "ChunkScore",
    "apply_diversity",
    "rrf_merge",
    # Retriever
    "RetrievalContext",
    "RetrievalResult",
    "Retriever",
    # Tagger
    "MetadataTagger",
    "TagResult",
    # Tokenizer
    "Tokenizer",
]
```

**Step 2: Verify imports work**

Run: `python -c "from app.services import HybridRetriever, Tokenizer, FacetExtractor; print('OK')"`
Expected: OK

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add app/services/__init__.py
git commit -m "chore: export new V1 services from __init__.py"
```

---

## Task 13: Final integration test

**Files:**
- Create: `tests/test_integration_v2.py`

**Step 1: Write integration test**

Create `tests/test_integration_v2.py`:

```python
import pytest


class MockProvider:
    async def embed(self, texts):
        return [[0.1] * 2048 for _ in texts]

    async def chat(self, messages):
        from app.providers import ChatResponse

        content = messages[0].content

        if "枚举值约束" in content:
            # Facet extraction
            return ChatResponse(
                content='{"bridge_type": "石拱桥", "material": null, "era": null, "region": null, "function": null}',
                usage={"total_tokens": 50},
            )
        else:
            # Generation
            return ChatResponse(
                content='{"summary": "测试要点", "details": "测试详细", "analogy": null, "confidence": {"level": "medium", "reason": "测试"}}',
                usage={"total_tokens": 100},
            )


def test_tokenizer_integration():
    from app.services import Tokenizer

    tokenizer = Tokenizer()
    words = tokenizer.tokenize("赵州桥是著名的石拱桥")
    tsquery = tokenizer.to_tsquery("赵州桥是著名的石拱桥")

    assert len(words) > 0
    assert " & " in tsquery


@pytest.mark.asyncio
async def test_facet_extractor_integration():
    from app.services import FacetExtractor

    extractor = FacetExtractor(provider=MockProvider())
    facet = await extractor.extract("石拱桥的结构特点")

    assert facet is not None
    assert facet.bridge_type == "石拱桥"


def test_rrf_merge_integration():
    from app.services import rrf_merge

    result = rrf_merge([1, 2, 3], [2, 3, 4])
    assert len(result) == 4
    # Chunk 2 and 3 appear in both, should be ranked higher
    top_ids = [r[0] for r in result[:2]]
    assert 2 in top_ids


def test_hybrid_retrieval_result_structure():
    from app.services import HybridRetrievalResult, RetrievedChunk

    result = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="测试", bridge_id=1, bridge_name="赵州桥", score=0.9)
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )

    all_chunks = result.all_chunks()
    assert len(all_chunks) == 1


@pytest.mark.asyncio
async def test_generator_v2_integration():
    from app.services import Generator, HybridRetrievalResult, RetrievedChunk

    generator = Generator(provider=MockProvider())

    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=1, content="赵州桥是石拱桥", bridge_id=1, bridge_name="赵州桥", score=0.9)
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )

    result = await generator.generate_v2("赵州桥是什么结构", evidence)

    assert result.confidence is not None
    assert result.confidence.level in ["high", "medium", "low"]
```

**Step 2: Run integration tests**

Run: `pytest tests/test_integration_v2.py -v`
Expected: All tests pass

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_integration_v2.py
git commit -m "test: add V2 integration tests"
```

---

## Summary

This plan implements the V1 retrieval enhancement in 13 tasks:

1. Add jieba dependency
2. Create Tokenizer service
3. Update Chunk model with new fields
4. Create facets constants
5. Create RRF ranker
6. Create ContextEnricher service
7. Create FacetExtractor service
8. Create HybridRetriever service
9. Update Generator with confidence output
10. Update API schemas
11. Add /ask/v2 endpoint
12. Export new services
13. Final integration tests

Each task follows TDD with test-first approach, frequent commits, and clear verification steps.
