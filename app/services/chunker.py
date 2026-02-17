import re
from dataclasses import dataclass

from app.services.markdown_parser import Section
from app.providers import LLMProvider


@dataclass
class ChunkResult:
    content: str
    section_title: str | None


class SemanticChunker:
    def __init__(
        self,
        provider: LLMProvider,
        min_chunk_size: int = 200,
        max_chunk_size: int = 500,
        similarity_threshold: float = 0.5,
    ):
        self.provider = provider
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.similarity_threshold = similarity_threshold

    async def chunk(self, sections: list[Section]) -> list[ChunkResult]:
        """Chunk sections using heading-aware strategy.

        Short sections are merged with neighbours; long sections are
        sub-split using sentence-level embedding similarity.
        """
        if not sections:
            return []

        # Build heading paths and filter empty sections
        items = self._prepare_sections(sections)
        if not items:
            return []

        # Group into chunks: merge short, split long
        chunks: list[ChunkResult] = []
        buffer_sections: list[tuple[str, str, int]] = []  # (heading_path, content, level)
        buffer_length = 0

        for heading_path, content, level in items:
            content_len = len(content)

            # Flush buffer when the top-level topic changes
            if buffer_sections and heading_path and buffer_sections[0][0]:
                prev_root = buffer_sections[0][0].split(" > ")[0]
                curr_root = heading_path.split(" > ")[0]
                if prev_root != curr_root:
                    chunks.extend(self._flush_buffer(buffer_sections))
                    buffer_sections = []
                    buffer_length = 0

            # Check if adding this section would exceed max
            if buffer_length > 0 and buffer_length + content_len > self.max_chunk_size:
                # Flush buffer first
                chunks.extend(self._flush_buffer(buffer_sections))
                buffer_sections = []
                buffer_length = 0

            # Check if this section alone exceeds max → sub-split
            if content_len > self.max_chunk_size:
                # Flush any pending buffer
                if buffer_sections:
                    chunks.extend(self._flush_buffer(buffer_sections))
                    buffer_sections = []
                    buffer_length = 0
                # Sub-split this long section
                sub_chunks = await self._semantic_subsplit(heading_path, content)
                chunks.extend(sub_chunks)
                continue

            # Add to buffer
            buffer_sections.append((heading_path, content, level))
            buffer_length += content_len

            # If buffer >= min_chunk_size, it's eligible to flush
            if buffer_length >= self.min_chunk_size:
                chunks.extend(self._flush_buffer(buffer_sections))
                buffer_sections = []
                buffer_length = 0

        # Flush remaining
        if buffer_sections:
            chunks.extend(self._flush_buffer(buffer_sections))

        return chunks

    def _prepare_sections(
        self, sections: list[Section]
    ) -> list[tuple[str, str, int]]:
        """Build heading paths and filter empty sections.

        Returns list of (heading_path, content, level) tuples.
        """
        parent_stack: list[tuple[int, str]] = []  # (level, title)
        items: list[tuple[str, str, int]] = []

        for section in sections:
            # Update parent stack
            if section.title:
                # Pop parents at same or deeper level
                while parent_stack and parent_stack[-1][0] >= section.level:
                    parent_stack.pop()
                parent_stack.append((section.level, section.title))

            # Skip empty sections
            if not section.content.strip():
                continue

            # Build heading path
            if parent_stack:
                heading_path = " > ".join(t for _, t in parent_stack)
            else:
                heading_path = ""

            items.append((heading_path, section.content, section.level))

        return items

    def _flush_buffer(
        self, buffer: list[tuple[str, str, int]]
    ) -> list[ChunkResult]:
        """Convert buffered sections into a single ChunkResult."""
        if not buffer:
            return []

        first_path = buffer[0][0]

        # Build content preserving Markdown headings
        parts: list[str] = []
        for heading_path, content, level in buffer:
            if len(buffer) > 1 and heading_path:
                last_title = heading_path.split(" > ")[-1]
                hashes = "#" * max(level, 1)
                parts.append(f"{hashes} {last_title}\n\n{content}")
            else:
                parts.append(content)

        body = "\n\n".join(parts)

        if first_path:
            full_content = f"[章节: {first_path}]\n\n{body}"
        else:
            full_content = body

        return [ChunkResult(
            content=full_content,
            section_title=first_path or None,
        )]

    async def _semantic_subsplit(
        self, heading_path: str, content: str
    ) -> list[ChunkResult]:
        """Sub-split a long section using sentence-level similarity."""
        sentences = self._split_into_sentences(content)

        if not sentences:
            return []

        if len(sentences) == 1:
            return self._make_chunks(heading_path, [sentences])

        embeddings = await self.provider.embed(sentences)

        groups: list[list[str]] = []
        current_group: list[str] = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            current_group.append(sentence)
            current_length += len(sentence)

            should_break = False

            if current_length >= self.max_chunk_size:
                should_break = True
            elif current_length >= self.min_chunk_size and i < len(sentences) - 1:
                sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
                if sim < self.similarity_threshold:
                    should_break = True

            if should_break:
                groups.append(current_group)
                current_group = []
                current_length = 0

        if current_group:
            groups.append(current_group)

        return self._make_chunks(heading_path, groups)

    def _make_chunks(
        self, heading_path: str, groups: list[list[str]]
    ) -> list[ChunkResult]:
        """Format sentence groups into ChunkResults."""
        chunks = []
        for group in groups:
            body = "\n".join(group)
            if heading_path:
                content = f"[章节: {heading_path}]\n\n{body}"
            else:
                content = body
            chunks.append(ChunkResult(
                content=content,
                section_title=heading_path or None,
            ))
        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using punctuation and newlines."""
        pattern = r'(?<=[。！？.!?])\s*|\n'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
