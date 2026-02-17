# Heading-Aware Chunker Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `SemanticChunker` to accept `list[Section]` and produce heading-aware chunks that preserve Markdown structure, fix text loss, and use `\n\n` after `[章节:]` prefix.

**Architecture:** The chunker receives parsed `Section[]` from `markdown_parser`, builds heading paths (breadcrumbs), merges short consecutive sections, and sub-splits long sections using the existing embedding similarity logic. `ingest.py` drops the text-flattening step and passes sections directly.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio

---

### Task 1: Write failing tests for new `chunk(sections)` API

**Files:**
- Modify: `tests/test_chunker.py`

**Step 1: Write the failing tests**

Replace the entire test file with tests targeting the new `Section[]` API. The `MockProvider` stays the same.

```python
import pytest

from app.core.constants import EMBEDDING_DIM
from app.services.chunker import SemanticChunker
from app.services.markdown_parser import Section


class MockProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        for i, text in enumerate(texts):
            base = [0.1] * EMBEDDING_DIM
            base[i % EMBEDDING_DIM] = 0.9
            embeddings.append(base)
        return embeddings

    async def chat(self, messages):
        pass


@pytest.fixture
def chunker():
    return SemanticChunker(
        provider=MockProvider(),
        min_chunk_size=50,
        max_chunk_size=200,
    )


@pytest.mark.asyncio
async def test_chunk_single_section(chunker):
    """A single section within size bounds becomes one chunk."""
    sections = [Section(title="概述", level=1, content="碧波廊桥位于浙江省丽水市山区，是一座典型的江南木拱廊桥。此桥以其精美的木雕闻名。")]
    chunks = await chunker.chunk(sections)

    assert len(chunks) == 1
    assert "[章节: 概述]\n\n" in chunks[0].content
    assert "碧波廊桥" in chunks[0].content
    assert chunks[0].section_title == "概述"


@pytest.mark.asyncio
async def test_chunk_heading_path(chunker):
    """Child sections get parent > child heading path."""
    sections = [
        Section(title="结构特点", level=1, content=""),
        Section(title="木拱构造", level=2, content="碧波廊桥采用编木拱结构，主拱由数十根圆木相互穿插编织而成，形成稳定的拱形承重系统。"),
    ]
    chunks = await chunker.chunk(sections)

    assert len(chunks) == 1
    assert chunks[0].section_title == "结构特点 > 木拱构造"
    assert "[章节: 结构特点 > 木拱构造]\n\n" in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_merges_short_sections(chunker):
    """Short consecutive sections under same parent are merged."""
    sections = [
        Section(title="结构特点", level=1, content=""),
        Section(title="木雕装饰", level=2, content="廊桥上的木雕极为精美。"),
        Section(title="始建背景", level=2, content="清代乾隆年间修建。"),
    ]
    # Both sub-sections are short (< min_chunk_size=50), should merge
    chunks = await chunker.chunk(sections)

    assert len(chunks) == 1
    assert "木雕装饰" in chunks[0].content
    assert "始建背景" in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_splits_long_section(chunker):
    """Section exceeding max_chunk_size is sub-split."""
    long_content = "。".join([f"这是第{i}句描述桥梁结构" for i in range(30)]) + "。"
    sections = [Section(title="详细描述", level=1, content=long_content)]
    chunks = await chunker.chunk(sections)

    assert len(chunks) > 1
    for chunk in chunks:
        assert "[章节: 详细描述]\n\n" in chunk.content
        assert chunk.section_title == "详细描述"


@pytest.mark.asyncio
async def test_chunk_flushes_on_higher_level_heading(chunker):
    """Merge buffer flushes when a higher-level heading appears."""
    sections = [
        Section(title="历史沿革", level=1, content=""),
        Section(title="始建", level=2, content="清代修建。"),
        Section(title="地理环境", level=1, content="横跨山间溪流。"),
    ]
    chunks = await chunker.chunk(sections)

    # "始建" and "地理环境" should NOT merge (different level-1 topics)
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_chunk_no_text_loss(chunker):
    """All original section content must appear in chunks."""
    sections = [
        Section(title="概述", level=1, content="第一段内容。"),
        Section(title="结构", level=1, content="第二段内容。"),
        Section(title="历史", level=1, content="第三段内容。"),
    ]
    chunks = await chunker.chunk(sections)
    all_content = "\n".join(c.content for c in chunks)

    assert "第一段内容" in all_content
    assert "第二段内容" in all_content
    assert "第三段内容" in all_content


@pytest.mark.asyncio
async def test_chunk_no_heading_document(chunker):
    """Document with no headings (level=0) still works."""
    sections = [Section(title="", level=0, content="纯文本内容，没有任何标题。这是第二句话。")]
    chunks = await chunker.chunk(sections)

    assert len(chunks) >= 1
    assert "纯文本内容" in chunks[0].content
    # No [章节:] prefix for untitled sections
    assert "[章节:" not in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_preserves_markdown_in_content(chunker):
    """Bullet lists and formatting are preserved in chunk content."""
    sections = [
        Section(title="特点", level=1, content="包括：\n- 花卉图案\n- 龙凤雕刻\n- 镂空花格"),
    ]
    chunks = await chunker.chunk(sections)

    assert "- 花卉图案" in chunks[0].content
    assert "- 龙凤雕刻" in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_empty_sections_skipped(chunker):
    """Empty parent sections produce no chunks on their own."""
    sections = [
        Section(title="空节", level=1, content=""),
        Section(title="有内容", level=2, content="这里有内容。"),
    ]
    chunks = await chunker.chunk(sections)

    assert len(chunks) == 1
    assert "空节" not in chunks[0].section_title or "有内容" in chunks[0].section_title
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chunker.py -v`
Expected: FAIL — `chunk()` still expects `str`, not `list[Section]`.

**Step 3: Commit**

```bash
git add tests/test_chunker.py
git commit -m "test: add failing tests for heading-aware chunker API"
```

---

### Task 2: Implement heading-aware `SemanticChunker`

**Files:**
- Modify: `app/services/chunker.py`

**Step 1: Rewrite chunker.py**

Replace the entire file with the new heading-aware implementation:

```python
import re
from dataclasses import dataclass

from app.services.markdown_parser import Section
from app.providers import LLMProvider


@dataclass
class ChunkResult:
    content: str
    section_title: str | None


class SemanticChunker:
    def __init__(
        self,
        provider: LLMProvider,
        min_chunk_size: int = 200,
        max_chunk_size: int = 500,
        similarity_threshold: float = 0.5,
    ):
        self.provider = provider
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.similarity_threshold = similarity_threshold

    async def chunk(self, sections: list[Section]) -> list[ChunkResult]:
        """Chunk sections using heading-aware strategy.

        Short sections are merged with neighbours; long sections are
        sub-split using sentence-level embedding similarity.
        """
        if not sections:
            return []

        # Build heading paths and filter empty sections
        items = self._prepare_sections(sections)
        if not items:
            return []

        # Group into chunks: merge short, split long
        chunks: list[ChunkResult] = []
        buffer_sections: list[tuple[str, str]] = []  # (heading_path, content)
        buffer_length = 0

        for heading_path, content in items:
            content_len = len(content)

            # Check if adding this section would exceed max
            if buffer_length > 0 and buffer_length + content_len > self.max_chunk_size:
                # Flush buffer first
                chunks.extend(self._flush_buffer(buffer_sections))
                buffer_sections = []
                buffer_length = 0

            # Check if this section alone exceeds max → sub-split
            if content_len > self.max_chunk_size:
                # Flush any pending buffer
                if buffer_sections:
                    chunks.extend(self._flush_buffer(buffer_sections))
                    buffer_sections = []
                    buffer_length = 0
                # Sub-split this long section
                sub_chunks = await self._semantic_subsplit(heading_path, content)
                chunks.extend(sub_chunks)
                continue

            # Add to buffer
            buffer_sections.append((heading_path, content))
            buffer_length += content_len

            # If buffer >= min_chunk_size, it's eligible to flush
            # Flush if we've reached a good size
            if buffer_length >= self.min_chunk_size:
                chunks.extend(self._flush_buffer(buffer_sections))
                buffer_sections = []
                buffer_length = 0

        # Flush remaining
        if buffer_sections:
            chunks.extend(self._flush_buffer(buffer_sections))

        return chunks

    def _prepare_sections(
        self, sections: list[Section]
    ) -> list[tuple[str, str]]:
        """Build heading paths and filter empty sections.

        Returns list of (heading_path, content) tuples.
        """
        parent_stack: list[tuple[int, str]] = []  # (level, title)
        items: list[tuple[str, str]] = []

        for section in sections:
            # Update parent stack
            if section.title:
                # Pop parents at same or deeper level
                while parent_stack and parent_stack[-1][0] >= section.level:
                    parent_stack.pop()
                parent_stack.append((section.level, section.title))

            # Skip empty sections
            if not section.content.strip():
                continue

            # Build heading path
            if parent_stack:
                heading_path = " > ".join(t for _, t in parent_stack)
            else:
                heading_path = ""

            items.append((heading_path, section.content))

        return items

    def _flush_buffer(
        self, buffer: list[tuple[str, str]]
    ) -> list[ChunkResult]:
        """Convert buffered sections into a single ChunkResult."""
        if not buffer:
            return []

        first_path = buffer[0][0]

        # Build content preserving Markdown headings
        parts: list[str] = []
        for heading_path, content in buffer:
            # If multiple sections merged, add sub-headings
            if len(buffer) > 1 and heading_path:
                # Extract the last heading component as a Markdown heading
                last_title = heading_path.split(" > ")[-1]
                parts.append(f"## {last_title}\n\n{content}")
            else:
                parts.append(content)

        body = "\n\n".join(parts)

        if first_path:
            full_content = f"[章节: {first_path}]\n\n{body}"
        else:
            full_content = body

        return [ChunkResult(
            content=full_content,
            section_title=first_path or None,
        )]

    async def _semantic_subsplit(
        self, heading_path: str, content: str
    ) -> list[ChunkResult]:
        """Sub-split a long section using sentence-level similarity."""
        sentences = self._split_into_sentences(content)

        if not sentences:
            return []

        # If only one sentence exceeds max, return it as-is
        if len(sentences) == 1:
            return self._make_chunks(heading_path, [sentences])

        embeddings = await self.provider.embed(sentences)

        groups: list[list[str]] = []
        current_group: list[str] = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            current_group.append(sentence)
            current_length += len(sentence)

            should_break = False

            if current_length >= self.max_chunk_size:
                should_break = True
            elif current_length >= self.min_chunk_size and i < len(sentences) - 1:
                sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
                if sim < self.similarity_threshold:
                    should_break = True

            if should_break:
                groups.append(current_group)
                current_group = []
                current_length = 0

        if current_group:
            groups.append(current_group)

        return self._make_chunks(heading_path, groups)

    def _make_chunks(
        self, heading_path: str, groups: list[list[str]]
    ) -> list[ChunkResult]:
        """Format sentence groups into ChunkResults."""
        chunks = []
        for group in groups:
            body = "\n".join(group)
            if heading_path:
                content = f"[章节: {heading_path}]\n\n{body}"
            else:
                content = body
            chunks.append(ChunkResult(
                content=content,
                section_title=heading_path or None,
            ))
        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using punctuation and newlines."""
        # Split on sentence-ending punctuation or double newlines
        pattern = r'(?<=[。！？.!?])\s*|\n\n+'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_chunker.py -v`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add app/services/chunker.py
git commit -m "feat: rewrite SemanticChunker with heading-aware section-based splitting"
```

---

### Task 3: Update ingest.py to pass sections directly

**Files:**
- Modify: `app/api/v1/ingest.py:116-121`

**Step 1: Write the change**

In `ingest.py`, find the text reconstruction block (lines ~116-121) and the chunker call (line ~145). Replace:

```python
        # OLD: Combine sections into text with headings
        text_parts = []
        for section in doc.sections:
            heading = "#" * section.level + " " + section.title
            text_parts.append(f"{heading}\n\n{section.content}")
        text_content = "\n\n".join(text_parts)

        if not text_content.strip():
            raise HTTPException(
                status_code=400,
                detail="No content found in document",
            )
```

With:

```python
        # NEW: Validate sections have content
        has_content = any(s.content.strip() for s in doc.sections)
        if not has_content:
            raise HTTPException(
                status_code=400,
                detail="No content found in document",
            )
```

And change the chunker call from:

```python
        chunk_results = await chunker.chunk(text_content)
```

To:

```python
        chunk_results = await chunker.chunk(doc.sections)
```

**Step 2: Run the existing ingest test to verify it still passes**

Run: `pytest tests/test_api_v1_ingest.py -v -k "not e2e"`
Expected: All non-e2e tests PASS (e2e tests need a running DB).

**Step 3: Commit**

```bash
git add app/api/v1/ingest.py
git commit -m "refactor: pass sections directly to chunker instead of flattened text"
```

---

### Task 4: Update ingest e2e test for new chunker behavior

**Files:**
- Modify: `tests/test_api_v1_ingest.py`

**Step 1: Verify e2e test still works**

The existing `test_ingest_v1_e2e_writes_chunks_and_tsv` uses a markdown doc with `# 第一节` and long text. The new chunker receives this as `[Section(title="第一节", level=1, content=...)]` which should still work — it's a single long section that gets sub-split.

Run: `pytest tests/test_api_v1_ingest.py::test_ingest_v1_e2e_writes_chunks_and_tsv -v` (requires DB)

If it passes, no changes needed. If it fails, adjust the test to match the new `[章节: ...]` format (the content now uses `\n\n` separator instead of space).

**Step 2: Commit (if changes needed)**

```bash
git add tests/test_api_v1_ingest.py
git commit -m "test: update ingest e2e test for heading-aware chunker format"
```

---

### Task 5: Integration test with 碧波廊桥.md

**Files:**
- Modify: `tests/test_chunker.py` (append a new test)

**Step 1: Write integration test using real document**

Add to `tests/test_chunker.py`:

```python
import pathlib

@pytest.mark.asyncio
async def test_chunk_bibolangqiao_no_text_loss():
    """Integration test: 碧波廊桥.md chunks preserve all content."""
    from app.services.markdown_parser import parse_markdown

    doc_path = pathlib.Path("data/seed/documents/碧波廊桥.md")
    if not doc_path.exists():
        pytest.skip("Seed document not available")

    doc = parse_markdown(doc_path.read_text())

    chunker = SemanticChunker(
        provider=MockProvider(),
        min_chunk_size=200,
        max_chunk_size=500,
    )
    chunks = await chunker.chunk(doc.sections)

    # Verify no text loss: all section content appears in chunks
    all_chunk_text = "\n".join(c.content for c in chunks)
    for section in doc.sections:
        if section.content.strip():
            # Each line of content should appear in some chunk
            for line in section.content.strip().split("\n"):
                line = line.strip()
                if line:
                    assert line in all_chunk_text, f"Lost text: {line!r}"

    # Verify [章节:] prefix has \n\n separator
    for chunk in chunks:
        if "[章节:" in chunk.content:
            assert "]\n\n" in chunk.content, f"Missing newline after [章节:] in: {chunk.content[:80]}"

    # Verify we got reasonable number of chunks
    assert len(chunks) >= 2
    assert len(chunks) <= 5
```

**Step 2: Run the test**

Run: `pytest tests/test_chunker.py::test_chunk_bibolangqiao_no_text_loss -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_chunker.py
git commit -m "test: add 碧波廊桥 integration test verifying no text loss"
```

---

### Task 6: Final verification and cleanup

**Step 1: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All tests PASS.

**Step 2: Verify the seed document chunks correctly**

Run a quick manual check:

```bash
python3 -c "
import asyncio
from app.services.markdown_parser import parse_markdown
from app.services.chunker import SemanticChunker

class MockProvider:
    async def embed(self, texts):
        return [[0.1]*1024 for _ in texts]

async def main():
    with open('data/seed/documents/碧波廊桥.md') as f:
        doc = parse_markdown(f.read())
    chunker = SemanticChunker(provider=MockProvider(), min_chunk_size=200, max_chunk_size=500)
    chunks = await chunker.chunk(doc.sections)
    for i, c in enumerate(chunks):
        print(f'=== Chunk {i+1} (section: {c.section_title}) ===')
        print(c.content)
        print()

asyncio.run(main())
"
```

Verify:
- No text from original doc is missing
- `[章节: ...]` has `\n\n` after it
- Chunks follow heading structure
- Bullet lists preserved

**Step 3: Commit all together**

```bash
git add -A
git commit -m "feat: heading-aware chunker redesign — fixes text loss, Markdown rendering, and heading structure"
```
