from dataclasses import dataclass

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

        # Build the SQL query with pgvector distance calculation
        # Using raw DBAPI connection directly
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Get raw psycopg connection
        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        # Build query string with %s placeholders for psycopg
        base_sql = (
            "SELECT id, content, section_title, lvl1, lvl2, lvl3, bridge_id, "
            "page_range, source_id, created_at, embedding, "
            "1 - (embedding <=> %s::vector) as score "
            "FROM chunks"
        )

        conditions = []
        args = [embedding_str]

        if context:
            if context.bridge_id is not None:
                conditions.append("bridge_id = %s")
                args.append(context.bridge_id)
            if context.lvl1:
                conditions.append("lvl1 = %s")
                args.append(context.lvl1)
            if context.lvl2:
                conditions.append("lvl2 = %s")
                args.append(context.lvl2)
            if context.lvl3:
                conditions.append("lvl3 = %s")
                args.append(context.lvl3)

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)

        base_sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        args.append(embedding_str)  # For ORDER BY
        args.append(self.top_k)

        cursor.execute(base_sql, args)
        rows = cursor.fetchall()
        cursor.close()

        results = []
        for row in rows:
            chunk = Chunk(
                id=row[0],
                content=row[1],
                section_title=row[2],
                lvl1=row[3],
                lvl2=row[4],
                lvl3=row[5],
                bridge_id=row[6],
                page_range=row[7],
                source_id=row[8],
                embedding=list(row[10]) if row[10] else [],
            )
            score = row[11]
            results.append(RetrievalResult(chunk=chunk, score=score))

        return results
