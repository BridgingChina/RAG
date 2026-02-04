from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Chunk
from app.providers import LLMProvider


@dataclass
class RetrievalContext:
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, provider: LLMProvider, top_k: int = 5):
        self.provider = provider
        self.top_k = top_k

    async def retrieve(
        self,
        db: Session,
        query: str,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks for a query."""
        # Get query embedding
        embeddings = await self.provider.embed([query])
        query_embedding = embeddings[0]

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        base_sql = """
            SELECT
                id,
                content,
                section_title,
                lvl1,
                lvl2,
                lvl3,
                bridge_id,
                page_range,
                source_id,
                embedding,
                1 - (embedding <=> (:embedding)::vector) AS score
            FROM chunks
        """
        conditions: list[str] = []
        params: dict[str, object] = {"embedding": embedding_str, "limit": self.top_k}

        if context:
            if context.bridge_id is not None:
                conditions.append("bridge_id = :bridge_id")
                params["bridge_id"] = context.bridge_id
            if context.lvl1:
                conditions.append("lvl1 = :lvl1")
                params["lvl1"] = context.lvl1
            if context.lvl2:
                conditions.append("lvl2 = :lvl2")
                params["lvl2"] = context.lvl2
            if context.lvl3:
                conditions.append("lvl3 = :lvl3")
                params["lvl3"] = context.lvl3

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions) + "\n"

        base_sql += " ORDER BY embedding <=> (:embedding)::vector LIMIT :limit"
        rows = db.execute(text(base_sql), params).all()

        results = []
        for row in rows:
            m = row._mapping
            embedding_value = m.get("embedding")
            chunk = Chunk(
                id=m["id"],
                content=m["content"],
                section_title=m["section_title"],
                lvl1=m["lvl1"],
                lvl2=m["lvl2"],
                lvl3=m["lvl3"],
                bridge_id=m["bridge_id"],
                page_range=m["page_range"],
                source_id=m["source_id"],
                embedding=(
                    embedding_value
                    if isinstance(embedding_value, list)
                    else list(embedding_value) if embedding_value else []
                ),
            )
            score = m["score"]
            results.append(RetrievalResult(chunk=chunk, score=score))

        return results
