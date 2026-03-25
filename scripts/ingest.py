"""Ingest text data into the RAG system.

Usage:
    # Ingest from a text file
    python scripts/ingest.py --file path/to/text.txt

    # Ingest from direct text
    python scripts/ingest.py --text "赵州桥是一座石拱桥..."

    # Specify source metadata
    python scripts/ingest.py --file notes.txt --source-type note --title "桥梁笔记"
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional, TypedDict

import click
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.core.config import settings
from app.core.constants import load_taxonomy
from app.models import Base, Bridge, Chunk, Source
from app.providers import ZhipuProvider
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path


def get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


class IngestedChunk(TypedDict):
    content: str
    section_title: Optional[str]
    contextual_text: str
    search_text: str
    lvl1: Optional[str]
    lvl2: Optional[str]
    lvl3: Optional[str]
    bridge_id: Optional[str]
    embedding: list[float]


def get_or_create_bridge(session: Session, name: str) -> Bridge | None:
    """Get existing bridge by name or create a new one."""
    if not name:
        return None

    bridge = session.execute(
        session.query(Bridge).filter(Bridge.name == name)
    ).scalar_one_or_none()

    if bridge:
        return bridge

    # Create new bridge
    bridge = Bridge(name=name)
    session.add(bridge)
    session.flush()
    return bridge


async def ingest_text(
    text: str,
    source_type: str = "note",
    source_title: str = "导入资料",
    session: Session | None = None,
) -> list[IngestedChunk]:
    """Ingest text into the database."""
    # Initialize provider and services
    provider = ZhipuProvider()
    context_enricher = ContextEnricher(provider=provider)
    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    chunker = SemanticChunker(
        provider=provider,
        min_chunk_size=200,
        max_chunk_size=500,
        similarity_threshold=0.5,
    )
    tagger = MetadataTagger(provider=provider, taxonomy_lvl2=get_taxonomy_lvl2_map())

    # Step 1: Parse and chunk the text
    print(f"正在切块...")
    doc = parse_markdown(text)
    chunk_results = await chunker.chunk(doc.sections)
    print(f"  切块完成: {len(chunk_results)} 个块")

    if not chunk_results:
        print("  警告: 没有生成任何块")
        return []

    # Step 2: Tag each chunk and get embeddings
    print(f"正在生成上下文、标注和 embedding...")
    chunks_to_save: list[IngestedChunk] = []

    for i, chunk_result in enumerate(chunk_results):
        # Step 2.1: Context enrich (best-effort, fall back to raw content)
        contextual_text = ""
        try:
            surrounding_chunks = None
            if i > 0:
                surrounding_chunks = [chunk_results[i - 1].content]
            context_result = await context_enricher.enrich(
                content=chunk_result.content,
                source_title=source_title,
                section_title=chunk_result.section_title,
                page_range=None,
                surrounding_chunks=surrounding_chunks,
            )
            contextual_text = (context_result.contextual_text or "").strip()
        except Exception as e:
            print(f"  警告: 第 {i+1} 个块上下文生成失败，将回退为原文用于 embedding: {e}")

        search_text = chunk_result.content
        if contextual_text:
            search_text = f"{contextual_text}\n\n{chunk_result.content}"

        # Tag with metadata
        tag_result = await tagger.tag(chunk_result.content)

        # Find or create bridge
        bridge_id = None
        if tag_result.bridge_id and session:
            bridge = get_or_create_bridge(session, tag_result.bridge_id)
            bridge_id = bridge.id if bridge else None

        # Get embedding
        embedding = await provider.embed([search_text])
        chunk_embedding = embedding[0] if embedding else []

        chunks_to_save.append(
            {
                "content": chunk_result.content,
                "section_title": chunk_result.section_title,
                "contextual_text": contextual_text,
                "search_text": search_text,
                "lvl1": tag_result.lvl1,
                "lvl2": tag_result.lvl2,
                "lvl3": tag_result.lvl3,
                "bridge_id": bridge_id,
                "embedding": chunk_embedding,
            }
        )
        print(f"  [{i+1}/{len(chunk_results)}] {chunk_result.content[:40]}... -> {tag_result.lvl1}")

    # Step 3: Save to database
    if session:
        print(f"正在保存到数据库...")

        # Create source
        source = Source(type=source_type, title=source_title)
        session.add(source)
        session.flush()

        # Create chunks
        chunk_rows: list[Chunk] = []
        for chunk_data in chunks_to_save:
            chunk = Chunk(
                source_id=source.id,
                content=chunk_data["content"],
                section_title=chunk_data["section_title"],
                contextual_text=chunk_data["contextual_text"],
                search_text=chunk_data["search_text"],
                lvl1=chunk_data["lvl1"],
                lvl2=chunk_data["lvl2"],
                lvl3=chunk_data["lvl3"],
                bridge_id=chunk_data["bridge_id"],
                embedding=chunk_data["embedding"],
            )
            session.add(chunk)
            chunk_rows.append(chunk)

        session.flush()
        # Populate tsvector for FTS queries (uses GIN index on chunks.tsv).
        mappings = [
            {
                "id": chunk.id,
                "tsv_text": tokenizer.to_tsvector_text(chunk.search_text or chunk.content),
            }
            for chunk in chunk_rows
        ]
        session.execute(
            sql_text(
                "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
            ),
            mappings,
        )
        session.commit()
        print(f"  保存完成: {len(chunks_to_save)} 个块")

    return chunks_to_save


@click.command()
@click.option("--file", "-f", type=click.Path(exists=True), help="Text file to ingest")
@click.option("--text", "-t", type=str, help="Direct text to ingest")
@click.option("--source-type", default="note", type=str, help="Source type (note, pdf, web, etc.)")
@click.option("--title", default="导入资料", type=str, help="Source title")
def main(file: str | None, text: str | None, source_type: str, title: str):
    """Ingest text data into the RAG system."""
    if not file and not text:
        click.echo("Error: Please provide --file or --text", err=True)
        sys.exit(1)

    if file and text:
        click.echo("Error: Please provide only one of --file or --text", err=True)
        sys.exit(1)

    # Get text content
    if file:
        text_content = Path(file).read_text(encoding="utf-8")
        if not title:
            title = Path(file).stem
    else:
        text_content = text

    # Setup database
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Ingest
        chunks = asyncio.run(ingest_text(text_content, source_type, title, session))

        # Show summary
        print(f"\n=== 入库完成 ===")
        print(f"总块数: {len(chunks)}")

        # Show taxonomy distribution
        lvl1_counts = {}
        for c in chunks:
            lvl1 = c["lvl1"] or "未分类"
            lvl1_counts[lvl1] = lvl1_counts.get(lvl1, 0) + 1

        print(f"\n分类分布:")
        for lvl1, count in lvl1_counts.items():
            print(f"  {lvl1}: {count}")


if __name__ == "__main__":
    main()
