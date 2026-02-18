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


def replace_bridge_links(
    *,
    db: Session,
    chunk: Chunk,
    links: list[dict],
) -> Chunk:
    """Replace all bridge links for a chunk. Updates chunk.bridge_id from primary link."""
    # Delete existing links
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk.id).delete()

    # Insert new links
    primary_bridge_id = None
    for link_data in links:
        db.add(ChunkBridgeLink(
            chunk_id=chunk.id,
            bridge_id=link_data["bridge_id"],
            role=link_data["role"],
            confidence=link_data["confidence"],
            method=link_data.get("method", "manual"),
        ))
        if link_data["role"] == "primary" and primary_bridge_id is None:
            primary_bridge_id = link_data["bridge_id"]

    # Sync chunk.bridge_id and binding_status
    if primary_bridge_id is not None:
        chunk.bridge_id = primary_bridge_id
        chunk.bridge_binding_status = "primary"
    elif links:
        chunk.bridge_id = None
        chunk.bridge_binding_status = "ambiguous"
    else:
        chunk.bridge_id = None
        chunk.bridge_binding_status = "none"

    db.flush()
    return chunk
