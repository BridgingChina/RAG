"""Service for chunk editing operations (content update, split, merge)."""
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.constants import EMBEDDING_DIM
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


def split_chunk(
    *,
    db: Session,
    chunk: Chunk,
    position: int,
    tokenizer: Tokenizer,
) -> list[Chunk]:
    """Split a chunk at the given character position. Returns [chunk_a, chunk_b]."""
    content = chunk.content
    if position <= 0 or position >= len(content):
        raise ValueError(f"position must be between 1 and {len(content) - 1}, got {position}")

    content_a = content[:position]
    content_b = content[position:]

    # Inherit metadata from original
    shared_attrs = dict(
        source_id=chunk.source_id,
        section_title=chunk.section_title,
        lvl1=chunk.lvl1,
        lvl2=chunk.lvl2,
        lvl3=chunk.lvl3,
        bridge_id=chunk.bridge_id,
        bridge_binding_status=chunk.bridge_binding_status,
        page_range=chunk.page_range,
        needs_reindex=True,
    )

    zero_embedding = [0.0] * EMBEDDING_DIM

    chunk_a = Chunk(content=content_a, embedding=zero_embedding, **shared_attrs)
    chunk_b = Chunk(content=content_b, embedding=zero_embedding, **shared_attrs)

    # Compute search_text for each (include contextual_text if inherited)
    for new_chunk in (chunk_a, chunk_b):
        if chunk.contextual_text:
            new_chunk.search_text = f"{chunk.contextual_text}\n\n{new_chunk.content}"
        else:
            new_chunk.search_text = new_chunk.content
        db.add(new_chunk)
    db.flush()

    # Compute tsv for each
    for new_chunk in (chunk_a, chunk_b):
        tsv_text = tokenizer.to_tsvector_text(new_chunk.search_text)
        db.execute(
            sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
            {"tsv_text": tsv_text, "id": new_chunk.id},
        )

    # Copy bridge_links from original to both new chunks
    original_links = (
        db.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.chunk_id == chunk.id)
        .all()
    )
    for link in original_links:
        for new_chunk in (chunk_a, chunk_b):
            db.add(ChunkBridgeLink(
                chunk_id=new_chunk.id,
                bridge_id=link.bridge_id,
                role=link.role,
                confidence=link.confidence,
                method=link.method,
            ))

    # Delete original chunk and its links
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk.id).delete()
    db.delete(chunk)
    db.flush()

    return [chunk_a, chunk_b]


def merge_chunks(
    *,
    db: Session,
    chunk_ids: list[int],
    tokenizer: Tokenizer,
) -> Chunk:
    """Merge multiple chunks into the first one. Deletes the rest."""
    if len(chunk_ids) < 2:
        raise ValueError("At least 2 chunk_ids required for merge")

    chunks = []
    for cid in chunk_ids:
        c = db.query(Chunk).filter(Chunk.id == cid).first()
        if c is None:
            raise ValueError(f"Chunk {cid} not found")
        chunks.append(c)

    # Validate same source
    source_ids = {c.source_id for c in chunks}
    if len(source_ids) > 1:
        raise ValueError("All chunks must belong to the same source")

    # Merge into the first chunk
    primary = chunks[0]
    primary.content = "\n\n".join(c.content for c in chunks)

    # Recompute search_text
    if primary.contextual_text:
        primary.search_text = f"{primary.contextual_text}\n\n{primary.content}"
    else:
        primary.search_text = primary.content

    primary.needs_reindex = True
    db.flush()

    # Recompute tsv
    tsv_text = tokenizer.to_tsvector_text(primary.search_text)
    db.execute(
        sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": primary.id},
    )

    # Delete the other chunks and their bridge links
    other_ids = [c.id for c in chunks[1:]]
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id.in_(other_ids)).delete()
    for c in chunks[1:]:
        db.delete(c)

    db.flush()
    return primary
