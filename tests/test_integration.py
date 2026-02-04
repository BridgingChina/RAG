"""Integration tests for the full RAG pipeline."""
import pytest

from app.models import Bridge, Chunk, Source
from app.services import Generator, Retriever, RetrievalContext


class MockProvider:
    """Mock provider for integration tests without real API calls."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Return consistent embeddings based on text content
        embeddings = []
        for text in texts:
            if "赵州桥" in text or "石拱" in text:
                embeddings.append([0.1] * 2048)
            elif "卢沟桥" in text:
                embeddings.append([0.3] * 2048)
            else:
                embeddings.append([0.15] * 2048)
        return embeddings

    async def chat(self, messages):
        from app.providers import ChatResponse
        return ChatResponse(
            content="""## 要点
- 赵州桥是石拱桥 [1]

## 详细说明
赵州桥是中国著名的石拱桥。[1]""",
            usage={},
        )


@pytest.fixture
def seeded_db_session(db_session):
    bridge = Bridge(name="赵州桥", location="河北赵县")
    db_session.add(bridge)
    db_session.flush()

    source = Source(type="note", title="Test")
    db_session.add(source)
    db_session.flush()

    chunks = [
        Chunk(
            source_id=source.id,
            content="赵州桥是一座石拱桥，跨度37米。",
            lvl1="形制与技术",
            bridge_id=bridge.id,
            embedding=[0.1] * 2048,
        ),
        Chunk(
            source_id=source.id,
            content="赵州桥建于隋代。",
            lvl1="历史与演变",
            bridge_id=bridge.id,
            embedding=[0.12] * 2048,
        ),
    ]
    db_session.add_all(chunks)
    db_session.flush()
    return db_session


@pytest.mark.asyncio
async def test_full_rag_pipeline(seeded_db_session):
    """Test the complete RAG pipeline: retrieve -> generate."""
    provider = MockProvider()
    retriever = Retriever(provider=provider, top_k=5)
    generator = Generator(provider=provider)

    # Retrieve
    results = await retriever.retrieve(seeded_db_session, "赵州桥是什么结构？")
    assert len(results) >= 1

    # Generate
    answer = await generator.generate("赵州桥是什么结构？", results)
    assert answer.summary
    assert answer.details
    assert len(answer.citations) >= 1


@pytest.mark.asyncio
async def test_filtered_retrieval(seeded_db_session):
    """Test retrieval with context filters."""
    provider = MockProvider()
    retriever = Retriever(provider=provider, top_k=5)

    # Filter by lvl1
    context = RetrievalContext(lvl1="形制与技术")
    results = await retriever.retrieve(seeded_db_session, "桥梁结构", context)

    assert len(results) >= 1
    assert all(r.chunk.lvl1 == "形制与技术" for r in results)
