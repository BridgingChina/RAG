"""V1 Ingest API endpoint."""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas import (
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)
from app.core.constants import EMBEDDING_DIM
from app.core.database import get_db
from app.core.taxonomy_loader import load_taxonomy_snapshot
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.current_user import CurrentUser
from app.services.audit_service import AuditService
from app.providers import get_provider
from app.services.bridge_linker import BridgeLinker
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.kp_resolver import resolve_knowledge_point_id
from app.services.markdown_parser import parse_markdown
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path

router = APIRouter()

_tokenizer_cache: dict[str | None, Tokenizer] = {}


def _get_tokenizer() -> Tokenizer:
    key = default_user_dict_path()
    tokenizer = _tokenizer_cache.get(key)
    if tokenizer is None:
        tokenizer = Tokenizer(user_dict_path=key)
        _tokenizer_cache[key] = tokenizer
    return tokenizer


def _extract_bridge_hints(frontmatter: dict, request_candidates: list[str] | None) -> list[str]:
    names: list[str] = []

    bridge = frontmatter.get("bridge")
    if isinstance(bridge, str) and bridge.strip():
        names.append(bridge.strip())

    bridges = frontmatter.get("bridges")
    if isinstance(bridges, str):
        names.extend([p.strip() for p in re.split(r"[,\n，、;；|]+", bridges) if p.strip()])
    elif isinstance(bridges, list):
        for item in bridges:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())

    if request_candidates:
        for item in request_candidates:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


# DEPRECATED: This synchronous ingest endpoint is superseded by the async
# /api/v1/ingest-tasks pipeline, which supports R2 upload, Zhipu file parsing,
# and multi-stage task tracking. Use /ingest-tasks for all new integrations.
@router.post("/ingest", response_model=IngestResponse, deprecated=True)
async def ingest(
    body: IngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    provider=Depends(get_provider),
    tokenizer: Tokenizer = Depends(_get_tokenizer),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Ingest a Markdown document.

    .. deprecated::
        Use the async ``/api/v1/ingest-tasks`` pipeline instead, which supports
        R2 upload, Zhipu file parsing, and multi-stage task tracking.

    Parses Markdown with YAML front matter, chunks the content, enriches with
    context, tags with taxonomy, links chunk-level bridge entities, and stores in DB.

    Front matter fields:
    - bridge: Primary bridge hint (optional)
    - bridges: Bridge hint list (optional)
    - title: Document title
    - source_type: Override for source type (default from request)
    """
    # Parse markdown
    doc = parse_markdown(body.content)

    # Extract metadata from front matter
    title = doc.frontmatter.get("title", "导入资料")
    source_type = doc.frontmatter.get("source_type", body.source_type)
    bridge_hints = _extract_bridge_hints(doc.frontmatter, body.bridge_candidates)

    # Validate sections have content
    has_content = any(s.content.strip() for s in doc.sections)
    if not has_content:
        raise HTTPException(
            status_code=400,
            detail="No content found in document",
        )

    # Initialize services
    context_enricher = ContextEnricher(provider=provider)
    chunker = SemanticChunker(
        provider=provider,
        min_chunk_size=200,
        max_chunk_size=500,
        similarity_threshold=0.5,
    )
    tagger = MetadataTagger(provider=provider, taxonomy=load_taxonomy_snapshot(db))
    bridge_linker = BridgeLinker(
        provider=provider,
        min_primary_confidence=body.min_primary_confidence,
        enable_auto_bridge_detection=body.enable_auto_bridge_detection,
    )

    # Chunk the text
    chunk_results = await chunker.chunk(doc.sections)

    if not chunk_results:
        raise HTTPException(
            status_code=400,
            detail="Failed to chunk document - no chunks generated",
        )

    # Create source
    source = Source(type=source_type, title=title)
    db.add(source)
    db.flush()

    # Process each chunk
    chunk_summaries: list[IngestedChunkSummary] = []
    chunk_rows: list[Chunk] = []
    primary_bridge_names: set[str] = set()
    auto_created_bridges: set[str] = set()
    ambiguous_chunk_count = 0

    for i, chunk_result in enumerate(chunk_results):
        # Context enrichment (best-effort)
        contextual_text = ""
        try:
            surrounding_chunks = None
            if i > 0:
                surrounding_chunks = [chunk_results[i - 1].content]
            context_result = await context_enricher.enrich(
                content=chunk_result.content,
                source_title=title,
                section_title=chunk_result.section_title,
                page_range=None,
                surrounding_chunks=surrounding_chunks,
            )
            contextual_text = (context_result.contextual_text or "").strip()
        except Exception:
            pass  # Fall back to no contextual text

        search_text = chunk_result.content
        if contextual_text:
            search_text = f"{contextual_text}\n\n{chunk_result.content}"

        # Tag with metadata
        tag_result = await tagger.tag(chunk_result.content)

        # Link bridges at chunk level
        bridge_link_result = await bridge_linker.link_chunk(
            db=db,
            content=chunk_result.content,
            hint_bridge_names=bridge_hints,
            bridge_candidates=body.bridge_candidates,
            min_primary_confidence=body.min_primary_confidence,
            enable_auto_bridge_detection=body.enable_auto_bridge_detection,
        )
        auto_created_bridges.update(bridge_link_result.auto_created_bridge_names)
        if bridge_link_result.binding_status == "ambiguous":
            ambiguous_chunk_count += 1
        if bridge_link_result.primary_bridge_name:
            primary_bridge_names.add(bridge_link_result.primary_bridge_name)

        primary_link = next(
            (link for link in bridge_link_result.links if link.role == "primary"),
            None,
        )
        chunk_bridge_id = primary_link.bridge_id if primary_link else None

        # Get embedding
        embeddings = await provider.embed([search_text])
        if not embeddings:
            raise HTTPException(
                status_code=502,
                detail="Embedding provider returned no embeddings",
            )

        chunk_embedding_raw = embeddings[0]
        if not isinstance(chunk_embedding_raw, (list, tuple)):
            raise HTTPException(
                status_code=502,
                detail=f"Invalid embedding type: expected list[float], got {type(chunk_embedding_raw).__name__}",
            )

        chunk_embedding = list(chunk_embedding_raw)
        if len(chunk_embedding) != EMBEDDING_DIM:
            raise HTTPException(
                status_code=502,
                detail=f"Invalid embedding dimension: expected {EMBEDDING_DIM}, got {len(chunk_embedding)}",
            )

        # Create chunk (Phase-1 double-write: populate knowledge_point_id
        # alongside the legacy lvl3 string).
        chunk = Chunk(
            source_id=source.id,
            content=chunk_result.content,
            section_title=chunk_result.section_title,
            contextual_text=contextual_text,
            search_text=search_text,
            lvl1=tag_result.lvl1,
            lvl2=tag_result.lvl2,
            lvl3=tag_result.lvl3,
            knowledge_point_id=resolve_knowledge_point_id(
                db, tag_result.lvl1, tag_result.lvl2, tag_result.lvl3,
            ),
            bridge_id=chunk_bridge_id,
            bridge_binding_status=bridge_link_result.binding_status,
            embedding=chunk_embedding,
        )
        db.add(chunk)
        db.flush()

        for link in bridge_link_result.links:
            db.add(
                ChunkBridgeLink(
                    chunk_id=chunk.id,
                    bridge_id=link.bridge_id,
                    role=link.role,
                    confidence=link.confidence,
                    method=link.method,
                )
            )
        chunk_rows.append(chunk)

        # Build summary
        preview = chunk_result.content[:100]
        if len(chunk_result.content) > 100:
            preview += "..."
        chunk_summaries.append(
            IngestedChunkSummary(
                content_preview=preview,
                lvl1=tag_result.lvl1,
                lvl2=tag_result.lvl2,
                binding_status=bridge_link_result.binding_status,
                primary_bridge_name=bridge_link_result.primary_bridge_name,
                secondary_bridge_names=bridge_link_result.secondary_bridge_names,
            )
        )

    # Populate tsvector for FTS
    mappings = [
        {
            "id": chunk.id,
            "tsv_text": tokenizer.to_tsvector_text(chunk.search_text or chunk.content),
        }
        for chunk in chunk_rows
    ]
    db.execute(
        sql_text(
            "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
        ),
        mappings,
    )
    db.flush()

    AuditService.log(
        db,
        action=AuditService.INGEST,
        resource_type="source",
        user_id=current_user.id,
        resource_id=str(source.id),
        detail={"title": title, "chunk_count": len(chunk_rows)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return IngestResponse(
        source_id=source.id,
        title=title,
        primary_bridge_names=sorted(primary_bridge_names),
        ambiguous_chunk_count=ambiguous_chunk_count,
        auto_created_bridges=sorted(auto_created_bridges),
        chunk_count=len(chunk_rows),
        chunks=chunk_summaries,
    )
