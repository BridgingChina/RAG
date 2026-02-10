"""End-to-end test for EMBEDDING_DIM-dim embedding creation and retrieval."""
import asyncio
from app.core.database import get_db
from app.models import Chunk, Source
from app.core.constants import EMBEDDING_DIM


async def run_test():
    print("=" * 50)
    print("E2E EMBEDDING TEST")
    print("=" * 50)
    print()

    # Create a source
    db = next(get_db())
    try:
        source = Source(type="test", title="E2E Test")
        db.add(source)
        db.flush()
        print(f"✅ Created test source (id={source.id})")

        # Create a mock EMBEDDING_DIM-dim embedding (using zeros for testing)
        print(f"Creating mock {EMBEDDING_DIM}-dim embedding...")
        embedding = [0.1] * EMBEDDING_DIM

        print(f"Embedding dimension: {len(embedding)}")
        assert len(embedding) == EMBEDDING_DIM, f"Expected {EMBEDDING_DIM}, got {len(embedding)}"
        print(f"✅ Embedding dimension is {EMBEDDING_DIM}")

        # Create a chunk
        print("Creating chunk with embedding...")
        chunk = Chunk(
            source_id=source.id,
            content="测试文本：赵州桥是中国现存最古老的石拱桥",
            embedding=embedding,
            lvl1="测试"
        )
        db.add(chunk)
        db.commit()
        print(f"✅ Created chunk (id={chunk.id})")

        # Retrieve and verify
        print("Retrieving chunk...")
        retrieved = db.query(Chunk).filter_by(id=chunk.id).first()
        assert retrieved is not None, "Chunk not found"
        assert (
            len(retrieved.embedding) == EMBEDDING_DIM
        ), f"Expected {EMBEDDING_DIM}, got {len(retrieved.embedding)}"
        print(f"✅ Retrieved chunk embedding dimension: {len(retrieved.embedding)}")

        # Verify content
        assert retrieved.content == chunk.content, "Content mismatch"
        print(f"✅ Content matches")

        # Verify embedding values (sample check)
        assert abs(retrieved.embedding[0] - 0.1) < 0.001, "Embedding value mismatch"
        assert abs(retrieved.embedding[100] - 0.1) < 0.001, "Embedding value mismatch"
        print(f"✅ Embedding values match")

        print()
        print("=" * 50)
        print("✅ E2E EMBEDDING TEST PASSED")
        print("=" * 50)

    finally:
        db.rollback()  # Clean up test data
        db.close()


if __name__ == "__main__":
    asyncio.run(run_test())
