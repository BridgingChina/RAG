"""Service for chunk editing operations (content update, split, merge)."""
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models import Chunk, ChunkBridgeLink
from app.services.tokenizer import Tokenizer


def update_chunk_content(
    *,
    db: Session,
    chunk: Chunk,
    new_content: str,
    tokenizer: Tokenizer,
) -> Chunk:
    """Update chunk content and recompute search_text + tsv. Sets needs_reindex=True."""
    chunk.content = new_content

    # Recompute search_text: contextual_text + content
    if chunk.contextual_text:
        chunk.search_text = f"{chunk.contextual_text}\n\n{new_content}"
    else:
        chunk.search_text = new_content

    # Recompute tsv
    tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
    db.execute(
        sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": chunk.id},
    )

    chunk.needs_reindex = True
    db.flush()
    return chunk
