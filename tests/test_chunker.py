import pytest
import pathlib

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
    assert "有内容" in chunks[0].section_title
