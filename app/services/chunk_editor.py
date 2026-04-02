"""Service for chunk editing operations (content update, split, merge, reindex)."""
import uuid
from datetime import datetime
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger
from app.models import Chunk, ChunkBridgeLink
from app.services.tokenizer import Tokenizer, default_user_dict_path


def check_optimistic_lock(chunk, expected: datetime | None) -> None:
    """Raise 409 if chunk was modified since the expected timestamp."""
    if expected is None:
        return
    if chunk.updated_at != expected:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Chunk has been modified by another user",
                "current_updated_at": chunk.updated_at.isoformat(),
                "chunk_id": chunk.id,
            },
        )


@lru_cache(maxsize=1)
def get_tokenizer() -> Tokenizer:
    """Get or create cached tokenizer instance (shared across endpoints)."""
    return Tokenizer(user_dict_path=default_user_dict_path())


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
        contextual_text=chunk.contextual_text,
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
    chunk_ids: list[uuid.UUID],
    tokenizer: Tokenizer,
) -> Chunk:
    """Merge multiple chunks into the first one. Deletes the rest."""
    if len(chunk_ids) < 2:
        raise ValueError("At least 2 chunk_ids required for merge")

    chunk_map = {
        c.id: c
        for c in db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
    }
    # Validate all exist and preserve caller's ordering
    chunks = []
    for cid in chunk_ids:
        c = chunk_map.get(cid)
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


async def reindex_source_chunks(
    *,
    db: Session,
    source_id: uuid.UUID,
    tokenizer: Tokenizer,
    provider,  # LLMProvider | None — None skips embedding recomputation
    force: bool = False,
) -> dict:
    """Reindex chunks for a source. Returns {source_id, chunks_reindexed, chunks_failed}.

    Two-phase approach:
      Phase 1 — Update search_text + tsv for each chunk (per-chunk savepoints).
      Phase 2 — Batch-embed all successful chunks in one provider.embed() call,
                then assign embeddings back (per-chunk savepoints).
    """
    query = db.query(Chunk).filter(Chunk.source_id == source_id)
    if not force:
        query = query.filter(Chunk.needs_reindex == True)  # noqa: E712

    chunks = query.all()
    failed = []

    # --- Phase 1: update search_text + tsv ---
    phase1_ok: list[Chunk] = []  # chunks that passed phase 1
    for chunk in chunks:
        savepoint = db.begin_nested()
        try:
            # Recompute search_text
            if chunk.contextual_text:
                chunk.search_text = f"{chunk.contextual_text}\n\n{chunk.content}"
            else:
                chunk.search_text = chunk.content

            # Recompute tsv
            tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
            db.execute(
                sql_text(
                    "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
                ),
                {"tsv_text": tsv_text, "id": chunk.id},
            )

            savepoint.commit()
            phase1_ok.append(chunk)
        except Exception:
            savepoint.rollback()
            chunk.needs_reindex = True
            logger.warning("Failed to reindex chunk %s (phase 1), will retry on next run", chunk.id, exc_info=True)
            failed.append(chunk.id)

    # --- Phase 2: batch embed + assign ---
    if provider is not None and phase1_ok:
        texts = [c.search_text for c in phase1_ok]
        try:
            embeddings = await provider.embed(texts)
        except Exception:
            logger.warning(
                "Batch embed failed for source %s (%d chunks), marking all as needs_reindex",
                source_id, len(texts), exc_info=True,
            )
            for chunk in phase1_ok:
                chunk.needs_reindex = True
            failed.extend(c.id for c in phase1_ok)
            phase1_ok = []
            embeddings = []

        # Assign embeddings per-chunk with savepoints
        still_ok: list[Chunk] = []
        for chunk, emb in zip(phase1_ok, embeddings):
            savepoint = db.begin_nested()
            try:
                chunk.embedding = emb
                chunk.needs_reindex = False
                savepoint.commit()
                still_ok.append(chunk)
            except Exception:
                savepoint.rollback()
                chunk.needs_reindex = True
                logger.warning("Failed to assign embedding for chunk %s, will retry on next run", chunk.id, exc_info=True)
                failed.append(chunk.id)
        phase1_ok = still_ok
    else:
        # No provider — just mark phase1_ok chunks as done
        for chunk in phase1_ok:
            savepoint = db.begin_nested()
            try:
                chunk.needs_reindex = False
                savepoint.commit()
            except Exception:
                savepoint.rollback()
                chunk.needs_reindex = True
                failed.append(chunk.id)

    reindexed = len(phase1_ok)

    db.flush()
    return {
        "source_id": source_id,
        "chunks_reindexed": reindexed,
        "chunks_failed": failed,
    }
