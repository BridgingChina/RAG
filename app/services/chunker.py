import re
from dataclasses import dataclass

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

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Chinese and English sentence boundaries
        pattern = r'(?<=[。！？.!?])\s*'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_section_title(self, text: str) -> tuple[str | None, str]:
        """Extract section title if present at start."""
        # Match patterns like "## Title" or "第X章 Title" or "X、Title"
        patterns = [
            r'^(#{1,3}\s+.+?)\n',
            r'^(第[一二三四五六七八九十\d]+[章节]\s*.+?)\n',
            r'^([一二三四五六七八九十\d]+[、.]\s*.+?)\n',
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                title = match.group(1).strip()
                remaining = text[match.end():].strip()
                return title, remaining
        return None, text

    async def chunk(self, text: str) -> list[ChunkResult]:
        """Chunk text using semantic similarity."""
        section_title, text = self._extract_section_title(text)
        sentences = self._split_into_sentences(text)

        if not sentences:
            return []

        # Get embeddings for all sentences
        embeddings = await self.provider.embed(sentences)

        chunks = []
        current_chunk = []
        current_length = 0

        for i, sentence in enumerate(sentences):
            current_chunk.append(sentence)
            current_length += len(sentence)

            # Check if we should break here
            should_break = False

            if current_length >= self.max_chunk_size:
                should_break = True
            elif current_length >= self.min_chunk_size and i < len(sentences) - 1:
                # Calculate similarity with next sentence
                sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
                if sim < self.similarity_threshold:
                    should_break = True

            if should_break:
                chunk_text = "".join(current_chunk)
                if section_title:
                    chunk_text = f"[章节: {section_title}] {chunk_text}"
                chunks.append(ChunkResult(content=chunk_text, section_title=section_title))
                current_chunk = []
                current_length = 0

        # Handle remaining sentences
        if current_chunk:
            chunk_text = "".join(current_chunk)
            if section_title:
                chunk_text = f"[章节: {section_title}] {chunk_text}"
            chunks.append(ChunkResult(content=chunk_text, section_title=section_title))

        return chunks

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
