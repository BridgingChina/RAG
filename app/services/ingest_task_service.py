"""Ingest task orchestration service.

Coordinates R2 storage, Zhipu file parsing, chunking, and indexing
across the async multi-stage ingest pipeline.
"""
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.core.constants import EMBEDDING_DIM
from app.core.logging import logger
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.ingest_task import IngestTask
from app.providers.base import LLMProvider
from app.providers.file_parser import FileParserProvider
from app.services.bridge_linker import BridgeLinker
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.r2_storage import R2StorageService
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer, default_user_dict_path


def _get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


class IngestTaskService:
    """Orchestrates the multi-stage ingest pipeline."""

    def __init__(
        self,
        db: Session,
        r2: R2StorageService,
        provider: LLMProvider,
        file_parser: FileParserProvider | None = None,
    ):
        self.db = db
        self.r2 = r2
        self.provider = provider
        self.file_parser = file_parser or FileParserProvider()

    def _get_task(self, task_id: int) -> IngestTask:
        task = self.db.get(IngestTask, task_id)
        if task is None:
            raise ValueError(f"IngestTask {task_id} not found")
        return task

    def _fail(self, task: IngestTask, error: str) -> None:
        try:
            task.status = "failed"
            task.error_message = error
            self.db.commit()
        except Exception:
            self.db.rollback()
        logger.error(f"IngestTask {task.id} failed: {error}")

    async def sync_and_parse(self, task_id: int) -> None:
        """Stage: syncing -> parsing -> chunked.

        For PDF: download from R2 -> submit to Zhipu -> poll -> chunk.
        For MD: download from R2 -> chunk directly.
        """
        task = self._get_task(task_id)

        try:
            task.status = "syncing"
            self.db.commit()

            file_bytes = self.r2.download(task.r2_raw_key)

            if task.file_type == "pdf":
                await self._parse_pdf(task, file_bytes)
            else:
                task.parsed_content = file_bytes.decode("utf-8")
                task.r2_parsed_prefix = f"parsed/{task.id}/"
                self.r2.upload(
                    f"parsed/{task.id}/result.md",
                    task.parsed_content.encode("utf-8"),
                    "text/markdown",
                )

            await self._chunk(task)

            task.status = "chunked"
            self.db.commit()

        except Exception as e:
            self._fail(task, str(e))

    async def _parse_pdf(self, task: IngestTask, file_bytes: bytes) -> None:
        """Submit PDF to Zhipu and poll for result."""
        task.status = "parsing"
        self.db.commit()

        zhipu_task_id = await self.file_parser.create_task(
            file_bytes=file_bytes,
            file_name=task.file_name,
            file_type="pdf",
        )
        task.zhipu_task_id = zhipu_task_id
        self.db.commit()

        result = await self.file_parser.poll_until_done(zhipu_task_id)

        parsed_md = result.content or ""

        if result.download_url:
            await self._download_and_store_parsed_assets(task, result.download_url)

        task.parsed_content = parsed_md
        task.r2_parsed_prefix = f"parsed/{task.id}/"
        self.r2.upload(
            f"parsed/{task.id}/result.md",
            parsed_md.encode("utf-8"),
            "text/markdown",
        )

    async def _download_and_store_parsed_assets(
        self, task: IngestTask, download_url: str
    ) -> None:
        """Download parsed assets (images, markdown) from Zhipu and store in R2.

        TODO: Implement archive download, image extraction, and URL rewriting.
        """
        pass

    async def _chunk(self, task: IngestTask) -> None:
        """Parse markdown and create chunks (without embedding)."""
        doc = parse_markdown(task.parsed_content)
        title = doc.frontmatter.get("title", task.file_name)

        chunker = SemanticChunker(
            provider=self.provider,
            min_chunk_size=200,
            max_chunk_size=500,
            similarity_threshold=0.5,
        )

        chunk_results = await chunker.chunk(doc.sections)
        if not chunk_results:
            raise ValueError("No chunks generated from parsed content")

        source = Source(type="document", title=title)
        self.db.add(source)
        self.db.flush()
        task.source_id = source.id

        # Use a zero vector as placeholder; real embedding is set during indexing.
        placeholder_embedding = [0.0] * EMBEDDING_DIM

        for chunk_result in chunk_results:
            chunk = Chunk(
                source_id=source.id,
                content=chunk_result.content,
                section_title=chunk_result.section_title,
                embedding=placeholder_embedding,
                needs_reindex=True,
            )
            self.db.add(chunk)

        self.db.flush()
        task.chunk_count = len(chunk_results)

    async def start_indexing(self, task_id: int) -> None:
        """Stage: indexing -> completed.

        After user confirms chunks via ChunkEditor, run embedding + tagging
        + tsv + bridge linking.
        """
        task = self._get_task(task_id)

        try:
            task.status = "indexing"
            self.db.commit()

            chunks = (
                self.db.query(Chunk)
                .filter(Chunk.source_id == task.source_id)
                .all()
            )

            if not chunks:
                raise ValueError(f"No chunks found for source {task.source_id}")

            context_enricher = ContextEnricher(provider=self.provider)
            tagger = MetadataTagger(
                provider=self.provider, taxonomy_lvl2=_get_taxonomy_lvl2_map()
            )
            bridge_linker = BridgeLinker(provider=self.provider)
            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())

            doc = parse_markdown(task.parsed_content or "")
            bridge_hints = []
            bridge_val = doc.frontmatter.get("bridge")
            if isinstance(bridge_val, str) and bridge_val.strip():
                bridge_hints.append(bridge_val.strip())
            bridges_val = doc.frontmatter.get("bridges")
            if isinstance(bridges_val, list):
                bridge_hints.extend(
                    [b.strip() for b in bridges_val if isinstance(b, str) and b.strip()]
                )

            for i, chunk in enumerate(chunks):
                contextual_text = ""
                try:
                    surrounding = [chunks[i - 1].content] if i > 0 else None
                    ctx = await context_enricher.enrich(
                        content=chunk.content,
                        source_title=doc.frontmatter.get("title", task.file_name),
                        section_title=chunk.section_title,
                        page_range=None,
                        surrounding_chunks=surrounding,
                    )
                    contextual_text = (ctx.contextual_text or "").strip()
                except Exception:
                    pass

                search_text = chunk.content
                if contextual_text:
                    search_text = f"{contextual_text}\n\n{chunk.content}"

                tag_result = await tagger.tag(chunk.content)

                link_result = await bridge_linker.link_chunk(
                    db=self.db,
                    content=chunk.content,
                    hint_bridge_names=bridge_hints,
                )
                primary_link = next(
                    (l for l in link_result.links if l.role == "primary"), None
                )

                embeddings = await self.provider.embed([search_text])
                if not embeddings or len(embeddings[0]) != EMBEDDING_DIM:
                    raise ValueError(
                        f"Invalid embedding for chunk {chunk.id}: "
                        f"expected dim {EMBEDDING_DIM}"
                    )

                chunk.contextual_text = contextual_text
                chunk.search_text = search_text
                chunk.lvl1 = tag_result.lvl1
                chunk.lvl2 = tag_result.lvl2
                chunk.lvl3 = tag_result.lvl3
                chunk.bridge_id = primary_link.bridge_id if primary_link else None
                chunk.bridge_binding_status = link_result.binding_status
                chunk.embedding = embeddings[0]

                for link in link_result.links:
                    self.db.add(
                        ChunkBridgeLink(
                            chunk_id=chunk.id,
                            bridge_id=link.bridge_id,
                            role=link.role,
                            confidence=link.confidence,
                            method=link.method,
                        )
                    )

            self.db.flush()

            mappings = [
                {
                    "id": c.id,
                    "tsv_text": tokenizer.to_tsvector_text(c.search_text or c.content),
                }
                for c in chunks
            ]
            self.db.execute(
                sql_text(
                    "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) "
                    "WHERE id = :id"
                ),
                mappings,
            )

            task.status = "completed"
            self.db.commit()

        except Exception as e:
            self._fail(task, str(e))
