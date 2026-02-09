"""Seed test data for integration testing.

Loads bridge data from data/seed/bridges.yaml and documents from data/seed/documents/*.md
"""
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import EMBEDDING_DIM, load_taxonomy
from app.models import Base, Bridge, Chunk, Source, TaxonomyNode
from app.providers import ZhipuProvider
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path

SEED_DIR = Path(__file__).parent.parent / "data" / "seed"


def get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


def seed_taxonomy(session: Session) -> None:
    """Seed taxonomy nodes from config/taxonomy.yaml."""
    taxonomy = load_taxonomy()
    nodes = []
    for lvl1, lvl2_dict in taxonomy.items():
        for lvl2, lvl3_list in lvl2_dict.items():
            for lvl3 in lvl3_list:
                nodes.append(TaxonomyNode(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3))
    session.add_all(nodes)
    print(f"  - {len(nodes)} taxonomy nodes")


def seed_bridges(session: Session) -> dict[str, Bridge]:
    """Seed bridges from data/seed/bridges.yaml."""
    bridges_file = SEED_DIR / "bridges.yaml"
    if not bridges_file.exists():
        print("  - bridges.yaml not found, skipping")
        return {}

    with open(bridges_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    bridge_map = {}
    for b in data.get("bridges", []):
        bridge = Bridge(
            name=b["name"],
            aliases=b.get("aliases"),
            location=b.get("location"),
            era=b.get("era"),
            bridge_type=b.get("bridge_type"),
            material=b.get("material"),
            function=b.get("function"),
            summary=b.get("summary"),
        )
        session.add(bridge)
        session.flush()
        bridge_map[b["name"]] = bridge

    print(f"  - {len(bridge_map)} bridges")
    return bridge_map


async def seed_documents(
    session: Session,
    bridge_map: dict[str, Bridge],
    use_llm: bool = False,
) -> int:
    """Seed chunks from data/seed/documents/*.md.

    Args:
        session: Database session
        bridge_map: Map of bridge name to Bridge object
        use_llm: If True, use LLM for chunking/tagging/enrichment (slow but realistic)
                If False, use simple splitting (fast for testing)
    """
    docs_dir = SEED_DIR / "documents"
    if not docs_dir.exists():
        print("  - documents/ not found, skipping")
        return 0

    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    chunk_count = 0

    if use_llm:
        # Full LLM pipeline (slow but realistic)
        provider = ZhipuProvider()
        chunker = SemanticChunker(
            provider=provider,
            min_chunk_size=200,
            max_chunk_size=500,
            similarity_threshold=0.5,
        )
        tagger = MetadataTagger(provider=provider, taxonomy_lvl2=get_taxonomy_lvl2_map())
        enricher = ContextEnricher(provider=provider)
    else:
        # Simple splitting (fast for testing)
        provider = None
        chunker = None
        tagger = None
        enricher = None

    for md_file in sorted(docs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        doc = parse_markdown(content)

        bridge_name = doc.frontmatter.get("bridge")
        title = doc.frontmatter.get("title", md_file.stem)
        source_type = doc.frontmatter.get("source_type", "document")

        # Get bridge
        bridge = bridge_map.get(bridge_name)
        bridge_id = bridge.id if bridge else None

        # Create source
        source = Source(type=source_type, title=title)
        session.add(source)
        session.flush()

        # Process sections
        if use_llm and chunker:
            # Use full LLM pipeline
            text_parts = []
            for section in doc.sections:
                heading = "#" * section.level + " " + section.title
                text_parts.append(f"{heading}\n\n{section.content}")
            full_text = "\n\n".join(text_parts)

            chunk_results = await chunker.chunk(full_text)
            for i, cr in enumerate(chunk_results):
                # Enrich context
                contextual_text = ""
                try:
                    surrounding = [chunk_results[i-1].content] if i > 0 else None
                    ctx = await enricher.enrich(
                        content=cr.content,
                        source_title=title,
                        section_title=cr.section_title,
                        page_range=None,
                        surrounding_chunks=surrounding,
                    )
                    contextual_text = ctx.contextual_text or ""
                except Exception:
                    pass

                # Tag
                tag = await tagger.tag(cr.content)

                # Embed
                search_text = f"{contextual_text}\n\n{cr.content}" if contextual_text else cr.content
                embeddings = await provider.embed([search_text])
                embedding = embeddings[0] if embeddings else [0.0] * EMBEDDING_DIM

                chunk = Chunk(
                    source_id=source.id,
                    content=cr.content,
                    section_title=cr.section_title,
                    contextual_text=contextual_text,
                    search_text=search_text,
                    lvl1=tag.lvl1,
                    lvl2=tag.lvl2,
                    lvl3=tag.lvl3,
                    bridge_id=bridge_id,
                    embedding=embedding,
                )
                session.add(chunk)
                chunk_count += 1
        else:
            # Simple splitting by section (fast)
            for section in doc.sections:
                section_content = (section.content or "").strip()
                if not section_content:
                    continue
                search_text = f"[{section.title}] {section_content}"
                # Use deterministic fake embedding based on content hash
                fake_emb = [float(hash(search_text + str(i)) % 1000) / 1000 for i in range(EMBEDDING_DIM)]

                chunk = Chunk(
                    source_id=source.id,
                    content=section_content,
                    section_title=section.title,
                    contextual_text="",
                    search_text=search_text,
                    lvl1="形制与技术",  # Default
                    lvl2="结构体系",
                    bridge_id=bridge_id,
                    embedding=fake_emb,
                )
                session.add(chunk)
                chunk_count += 1

        print(f"    - {md_file.name}: processed")

    session.flush()

    # Populate tsvector
    chunks = session.query(Chunk).filter(Chunk.source_id >= 1).all()
    mappings = [
        {
            "id": c.id,
            "tsv_text": tokenizer.to_tsvector_text(c.search_text or c.content),
        }
        for c in chunks
    ]
    if mappings:
        session.execute(
            text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
            mappings,
        )

    print(f"  - {chunk_count} chunks total")
    return chunk_count


def seed(use_llm: bool = False):
    """Seed all test data.

    Args:
        use_llm: If True, use LLM for realistic chunking/tagging (slow)
    """
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        print("Seeding test data...")

        # Taxonomy
        seed_taxonomy(session)

        # Bridges
        bridge_map = seed_bridges(session)

        # Documents
        asyncio.run(seed_documents(session, bridge_map, use_llm=use_llm))

        session.commit()
        print("\nTest data seeded successfully!")


if __name__ == "__main__":
    import sys
    use_llm = "--llm" in sys.argv
    if use_llm:
        print("Using LLM for chunking/tagging (this may take a while)...")
    seed(use_llm=use_llm)
