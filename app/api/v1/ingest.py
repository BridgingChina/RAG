"""V1 Ingest API endpoint."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.api.v1.schemas import (
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)
from app.core.database import get_db
from app.models import Bridge, Chunk, Source
from app.providers import ZhipuProvider
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer
from app.core.constants import load_taxonomy

router = APIRouter()

_provider_cache: dict[object, object] = {}
_tokenizer_cache: dict[str | None, Tokenizer] = {}


def _get_provider():
    key = ZhipuProvider
    provider = _provider_cache.get(key)
    if provider is None:
        provider = key()
        _provider_cache[key] = provider
    return provider


def _get_tokenizer() -> Tokenizer:
    key = "data/bridge_terms.txt"
    tokenizer = _tokenizer_cache.get(key)
    if tokenizer is None:
        tokenizer = Tokenizer(user_dict_path=key)
        _tokenizer_cache[key] = tokenizer
    return tokenizer


def _get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


def _get_or_create_bridge(session: Session, name: str) -> Bridge | None:
    """Get existing bridge by name or create a new one."""
    if not name:
        return None

    bridge = session.query(Bridge).filter(Bridge.name == name).first()

    if bridge:
        return bridge

    # Create new bridge
    bridge = Bridge(name=name)
    session.add(bridge)
    session.flush()
    return bridge


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    request: IngestRequest,
    db: Session = Depends(get_db),
    provider=Depends(_get_provider),
    tokenizer: Tokenizer = Depends(_get_tokenizer),
):
    """Ingest a Markdown document.

    Parses Markdown with YAML front matter, chunks the content,
    enriches with context, tags with taxonomy, and stores in database.

    Front matter fields:
    - bridge: Name of the bridge this document is about
    - title: Document title
    - source_type: Override for source type (default from request)
    """
    async def _run():
        # Parse markdown
        doc = parse_markdown(request.content)

        # Extract metadata from front matter
        bridge_name = doc.frontmatter.get("bridge")
        title = doc.frontmatter.get("title", "导入资料")
        source_type = doc.frontmatter.get("source_type", request.source_type)

        # Get or create bridge
        bridge = _get_or_create_bridge(db, bridge_name) if bridge_name else None
        bridge_id = bridge.id if bridge else None

        # Combine sections into text with headings
        text_parts = []
        for section in doc.sections:
            heading = "#" * section.level + " " + section.title
            text_parts.append(f"{heading}\n\n{section.content}")
        text_content = "\n\n".join(text_parts)

        if not text_content.strip():
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
        tagger = MetadataTagger(provider=provider, taxonomy_lvl2=_get_taxonomy_lvl2_map())

        # Chunk the text
        chunk_results = await chunker.chunk(text_content)

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

            # Use bridge from front matter, or from tagger
            chunk_bridge_id = bridge_id
            chunk_bridge_name = bridge_name
            if not chunk_bridge_id and tag_result.bridge_id:
                tag_bridge = _get_or_create_bridge(db, tag_result.bridge_id)
                if tag_bridge:
                    chunk_bridge_id = tag_bridge.id
                    chunk_bridge_name = tag_bridge.name

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
            if len(chunk_embedding) != 2048:
                raise HTTPException(
                    status_code=502,
                    detail=f"Invalid embedding dimension: expected 2048, got {len(chunk_embedding)}",
                )

            # Create chunk
            chunk = Chunk(
                source_id=source.id,
                content=chunk_result.content,
                section_title=chunk_result.section_title,
                contextual_text=contextual_text,
                search_text=search_text,
                lvl1=tag_result.lvl1,
                lvl2=tag_result.lvl2,
                lvl3=tag_result.lvl3,
                bridge_id=chunk_bridge_id,
                embedding=chunk_embedding,
            )
            db.add(chunk)
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
                    bridge_name=chunk_bridge_name,
                )
            )

        db.flush()

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
        db.commit()

        return IngestResponse(
            source_id=source.id,
            bridge_name=bridge_name,
            title=title,
            chunk_count=len(chunk_rows),
            chunks=chunk_summaries,
        )

    return asyncio.run(_run())
