import pytest

from app.core.constants import EMBEDDING_DIM
from app.services.chunker import SemanticChunker


class MockProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Return mock embeddings - similar sentences get similar vectors
        embeddings = []
        for i, text in enumerate(texts):
            # Simple mock: use text hash to create pseudo-embedding
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
async def test_chunk_simple_text(chunker):
    text = "这是第一句话。这是第二句话。这是第三句话。"
    chunks = await chunker.chunk(text)

    assert len(chunks) >= 1
    assert all(c.content for c in chunks)


@pytest.mark.asyncio
async def test_chunk_with_section_title(chunker):
    text = "## 结构特点\n这座桥采用了石拱结构。跨度达到37米。"
    chunks = await chunker.chunk(text)

    assert len(chunks) >= 1
    assert "[章节:" in chunks[0].content
    assert "结构特点" in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_respects_max_size(chunker):
    # Create text longer than max_chunk_size
    text = "这是一个很长的句子。" * 50
    chunks = await chunker.chunk(text)

    assert len(chunks) > 1
    for chunk in chunks:
        # Allow some overflow due to sentence boundaries
        assert len(chunk.content) <= chunker.max_chunk_size * 2


def test_extract_section_title():
    chunker = SemanticChunker(provider=MockProvider())

    title, text = chunker._extract_section_title("## 结构特点\n内容")
    assert title == "## 结构特点"
    assert text == "内容"

    title, text = chunker._extract_section_title("普通文本")
    assert title is None
    assert text == "普通文本"
