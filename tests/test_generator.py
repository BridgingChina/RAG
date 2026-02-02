import pytest

from app.models import Chunk
from app.providers import ChatMessage, ChatResponse
from app.services.generator import Generator
from app.services.retriever import RetrievalResult


class MockProvider:
    async def embed(self, texts):
        return [[0.1] * 2048 for _ in texts]

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(
            content="""## 要点
- 赵州桥是石拱桥 [1]
- 采用敞肩式结构 [1]

## 详细说明
赵州桥是中国著名的石拱桥，位于河北省赵县。它采用了独特的敞肩式结构，这种设计减轻了桥身重量。[1]""",
            usage={},
        )


@pytest.fixture
def generator():
    return Generator(provider=MockProvider())


@pytest.fixture
def mock_evidence():
    chunk = Chunk(
        id=1,
        source_id=1,
        content="赵州桥是一座石拱桥，采用敞肩式结构。",
        lvl1="形制与技术",
        embedding=[0.1] * 2048,
    )
    return [RetrievalResult(chunk=chunk, score=0.9)]


@pytest.mark.asyncio
async def test_generate_with_evidence(generator, mock_evidence):
    result = await generator.generate("赵州桥是什么结构？", mock_evidence)

    assert result.summary
    assert result.details
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == 1


@pytest.mark.asyncio
async def test_generate_without_evidence(generator):
    result = await generator.generate("问题", [])

    assert "未找到" in result.summary
    assert len(result.citations) == 0


def test_citation_structure():
    from app.services.generator import Citation

    citation = Citation(chunk_id=1, source_title="来源", page_range="10-12")
    assert citation.chunk_id == 1
    assert citation.page_range == "10-12"
