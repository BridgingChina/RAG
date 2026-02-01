# Bridge RAG V0 Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a working RAG system that can ingest documents, store chunks with embeddings, and answer questions with citations.

**Architecture:** FastAPI backend with PostgreSQL+pgvector for storage. Semantic chunking with LLM-based metadata tagging. Retrieval via vector similarity with metadata filtering, generation via Zhipu GLM-4.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, pgvector, Zhipu API (embedding + GLM-4), Docker Compose

---

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `.env.example`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "bridge-rag"
version = "0.1.0"
description = "Bridge Knowledge RAG System"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "psycopg[binary]>=3.1.0",
    "pgvector>=0.2.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Create app/core/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://bridge:bridge@localhost:5432/bridge_rag"
    zhipu_api_key: str = ""

    # LLM settings
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4"

    # Retrieval settings
    top_k: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
```

**Step 3: Create app/main.py**

```python
from fastapi import FastAPI

app = FastAPI(title="Bridge RAG", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 4: Create app/__init__.py and app/core/__init__.py**

Empty files for package structure.

**Step 5: Create docker-compose.yml**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: bridge_rag
      POSTGRES_USER: bridge
      POSTGRES_PASSWORD: bridge
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bridge -d bridge_rag"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

**Step 6: Create .env.example**

```
DATABASE_URL=postgresql://bridge:bridge@localhost:5432/bridge_rag
ZHIPU_API_KEY=your_api_key_here
```

**Step 7: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install .

COPY app app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 8: Verify setup**

```bash
docker compose up -d db
pip install -e ".[dev]"
uvicorn app.main:app --reload &
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

**Step 9: Commit**

```bash
git add -A
git commit -m "feat: project skeleton with FastAPI and Docker Compose"
```

---

## Task 2: Database Models

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/base.py`
- Create: `app/models/bridge.py`
- Create: `app/models/taxonomy.py`
- Create: `app/models/source.py`
- Create: `app/models/chunk.py`
- Create: `app/core/database.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

**Step 1: Create app/core/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Step 2: Create app/models/base.py**

```python
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
```

**Step 3: Create app/models/bridge.py**

```python
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Bridge(Base, TimestampMixin):
    __tablename__ = "bridges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    era: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

**Step 4: Create app/models/taxonomy.py**

```python
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lvl1: Mapped[str] = mapped_column(String(100))
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

**Step 5: Create app/models/source.py**

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))  # 'pdf' | 'web' | 'note'
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

**Step 6: Create app/models/chunk.py**

```python
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    content: Mapped[str] = mapped_column(Text)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bridges.id"), nullable=True
    )
    page_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))

    __table_args__ = (
        Index("ix_chunks_taxonomy", "lvl1", "lvl2", "lvl3"),
        Index("ix_chunks_bridge", "bridge_id"),
    )
```

**Step 7: Create app/models/__init__.py**

```python
from app.models.base import Base
from app.models.bridge import Bridge
from app.models.chunk import Chunk
from app.models.source import Source
from app.models.taxonomy import TaxonomyNode

__all__ = ["Base", "Bridge", "Chunk", "Source", "TaxonomyNode"]
```

**Step 8: Write test for models**

Create `tests/__init__.py` (empty) and `tests/test_models.py`:

```python
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Bridge, Chunk, Source, TaxonomyNode


@pytest.fixture
def db_session():
    engine = create_engine("postgresql://bridge:bridge@localhost:5432/bridge_rag")

    # Enable pgvector extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session
        session.rollback()


def test_create_bridge(db_session):
    bridge = Bridge(name="赵州桥", location="河北赵县")
    db_session.add(bridge)
    db_session.flush()

    assert bridge.id is not None
    assert bridge.name == "赵州桥"


def test_create_chunk_with_embedding(db_session):
    source = Source(type="note", title="Test Note")
    db_session.add(source)
    db_session.flush()

    embedding = [0.1] * 1024
    chunk = Chunk(
        source_id=source.id,
        content="赵州桥是一座石拱桥",
        lvl1="形制与技术",
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.flush()

    assert chunk.id is not None
    assert len(chunk.embedding) == 1024
```

**Step 9: Run tests**

```bash
docker compose up -d db
pytest tests/test_models.py -v
# Expected: 2 passed
```

**Step 10: Commit**

```bash
git add -A
git commit -m "feat: database models for bridges, taxonomy, sources, chunks"
```

---

## Task 3: LLM Provider Abstraction

**Files:**
- Create: `app/providers/__init__.py`
- Create: `app/providers/base.py`
- Create: `app/providers/zhipu.py`
- Create: `tests/test_providers.py`

**Step 1: Create app/providers/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResponse:
    content: str
    usage: dict


class LLMProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        pass

    @abstractmethod
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Generate chat completion."""
        pass
```

**Step 2: Create app/providers/zhipu.py**

```python
import httpx

from app.core.config import settings
from app.providers.base import ChatMessage, ChatResponse, LLMProvider


class ZhipuProvider(LLMProvider):
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.embedding_model = settings.embedding_model
        self.chat_model = settings.chat_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            embeddings = []
            for text in texts:
                resp = await client.post(
                    f"{self.BASE_URL}/embeddings",
                    headers=self._headers(),
                    json={"model": self.embedding_model, "input": text},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings.append(data["data"][0]["embedding"])
            return embeddings

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.chat_model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return ChatResponse(
                content=data["choices"][0]["message"]["content"],
                usage=data.get("usage", {}),
            )
```

**Step 3: Create app/providers/__init__.py**

```python
from app.providers.base import ChatMessage, ChatResponse, LLMProvider
from app.providers.zhipu import ZhipuProvider

__all__ = ["ChatMessage", "ChatResponse", "LLMProvider", "ZhipuProvider"]
```

**Step 4: Write provider test (mock-based)**

Create `tests/test_providers.py`:

```python
import pytest

from app.providers import ChatMessage, ZhipuProvider


@pytest.fixture
def provider():
    return ZhipuProvider()


def test_provider_has_required_methods(provider):
    assert hasattr(provider, "embed")
    assert hasattr(provider, "chat")
    assert callable(provider.embed)
    assert callable(provider.chat)


def test_chat_message_structure():
    msg = ChatMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
```

**Step 5: Run tests**

```bash
pytest tests/test_providers.py -v
# Expected: 2 passed
```

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: LLM provider abstraction with Zhipu implementation"
```

---

## Task 4: Semantic Chunker Service

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/chunker.py`
- Create: `tests/test_chunker.py`

**Step 1: Create app/services/chunker.py**

```python
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
```

**Step 2: Write chunker tests**

Create `tests/test_chunker.py`:

```python
import pytest

from app.services.chunker import SemanticChunker


class MockProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Return mock embeddings - similar sentences get similar vectors
        embeddings = []
        for i, text in enumerate(texts):
            # Simple mock: use text hash to create pseudo-embedding
            base = [0.1] * 1024
            base[i % 1024] = 0.9
            embeddings.append(base)
        return embeddings

    async def chat(self, messages):
        pass


@pytest.fixture
def chunker():
    return SemanticChunker(
        provider=MockProvider(),
        min_chunk_size=50,
        max_chunk_size=200,
    )


@pytest.mark.asyncio
async def test_chunk_simple_text(chunker):
    text = "这是第一句话。这是第二句话。这是第三句话。"
    chunks = await chunker.chunk(text)

    assert len(chunks) >= 1
    assert all(c.content for c in chunks)


@pytest.mark.asyncio
async def test_chunk_with_section_title(chunker):
    text = "## 结构特点\n这座桥采用了石拱结构。跨度达到37米。"
    chunks = await chunker.chunk(text)

    assert len(chunks) >= 1
    assert "[章节: 结构特点]" in chunks[0].content


@pytest.mark.asyncio
async def test_chunk_respects_max_size(chunker):
    # Create text longer than max_chunk_size
    text = "这是一个很长的句子。" * 50
    chunks = await chunker.chunk(text)

    assert len(chunks) > 1
    for chunk in chunks:
        # Allow some overflow due to sentence boundaries
        assert len(chunk.content) <= chunker.max_chunk_size * 2


def test_extract_section_title():
    chunker = SemanticChunker(provider=MockProvider())

    title, text = chunker._extract_section_title("## 结构特点\n内容")
    assert title == "## 结构特点"
    assert text == "内容"

    title, text = chunker._extract_section_title("普通文本")
    assert title is None
    assert text == "普通文本"
```

**Step 3: Create app/services/__init__.py**

```python
from app.services.chunker import ChunkResult, SemanticChunker

__all__ = ["ChunkResult", "SemanticChunker"]
```

**Step 4: Run tests**

```bash
pytest tests/test_chunker.py -v
# Expected: 4 passed
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: semantic chunker service with section title extraction"
```

---

## Task 5: Metadata Tagger Service

**Files:**
- Create: `app/services/tagger.py`
- Create: `tests/test_tagger.py`

**Step 1: Create app/services/tagger.py**

```python
import json
import re
from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider

# Fixed taxonomy for V0
TAXONOMY_LVL1 = ["形制与技术", "地域与环境", "功能与社会", "历史与演变"]


@dataclass
class TagResult:
    lvl1: str | None
    lvl2: str | None
    lvl3: str | None
    bridge_id: str | None


class MetadataTagger:
    def __init__(self, provider: LLMProvider, taxonomy_lvl2: dict[str, list[str]] | None = None):
        self.provider = provider
        self.taxonomy_lvl2 = taxonomy_lvl2 or {}

    async def tag(self, chunk_content: str) -> TagResult:
        """Tag a chunk with taxonomy metadata."""
        lvl2_info = ""
        if self.taxonomy_lvl2:
            lvl2_info = "\n二级分类：\n"
            for lvl1, lvl2s in self.taxonomy_lvl2.items():
                lvl2_info += f"  {lvl1}: {', '.join(lvl2s)}\n"

        prompt = f"""你是桥梁知识分类专家。请分析以下文本，判断它属于哪个知识分类。

一级分类（必选其一）：
1. 形制与技术 - 桥梁的结构、材料、建造技术
2. 地域与环境 - 桥梁所在地理位置、自然环境
3. 功能与社会 - 桥梁的用途、社会意义
4. 历史与演变 - 桥梁的历史、修缮、变迁
{lvl2_info}
如果文本明确提到某座具体桥梁的名称，请提取桥梁名称。

文本：
{chunk_content}

请以JSON格式回答，格式如下：
{{"lvl1": "一级分类", "lvl2": "二级分类或null", "bridge_name": "桥梁名称或null"}}

只输出JSON，不要其他内容。"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> TagResult:
        """Parse LLM response to TagResult."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group())
                lvl1 = data.get("lvl1")
                # Validate lvl1
                if lvl1 not in TAXONOMY_LVL1:
                    lvl1 = None
                return TagResult(
                    lvl1=lvl1,
                    lvl2=data.get("lvl2"),
                    lvl3=None,  # V0 leaves lvl3 empty
                    bridge_id=data.get("bridge_name"),
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        return TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
```

**Step 2: Write tagger tests**

Create `tests/test_tagger.py`:

```python
import pytest

from app.providers import ChatMessage, ChatResponse
from app.services.tagger import MetadataTagger, TagResult, TAXONOMY_LVL1


class MockProvider:
    def __init__(self, response_content: str):
        self.response_content = response_content

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content=self.response_content, usage={})


@pytest.mark.asyncio
async def test_tag_with_valid_response():
    provider = MockProvider('{"lvl1": "形制与技术", "lvl2": "结构体系", "bridge_name": "赵州桥"}')
    tagger = MetadataTagger(provider)

    result = await tagger.tag("赵州桥是一座石拱桥，采用敞肩式结构。")

    assert result.lvl1 == "形制与技术"
    assert result.lvl2 == "结构体系"
    assert result.bridge_id == "赵州桥"


@pytest.mark.asyncio
async def test_tag_with_invalid_lvl1():
    provider = MockProvider('{"lvl1": "无效分类", "lvl2": null, "bridge_name": null}')
    tagger = MetadataTagger(provider)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None


@pytest.mark.asyncio
async def test_tag_with_malformed_response():
    provider = MockProvider("这不是JSON格式")
    tagger = MetadataTagger(provider)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None
    assert result.lvl2 is None


def test_taxonomy_lvl1_values():
    assert "形制与技术" in TAXONOMY_LVL1
    assert "地域与环境" in TAXONOMY_LVL1
    assert "功能与社会" in TAXONOMY_LVL1
    assert "历史与演变" in TAXONOMY_LVL1
```

**Step 3: Update app/services/__init__.py**

```python
from app.services.chunker import ChunkResult, SemanticChunker
from app.services.tagger import MetadataTagger, TagResult

__all__ = ["ChunkResult", "SemanticChunker", "MetadataTagger", "TagResult"]
```

**Step 4: Run tests**

```bash
pytest tests/test_tagger.py -v
# Expected: 4 passed
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: metadata tagger service with LLM-based classification"
```

---

## Task 6: Retriever Service

**Files:**
- Create: `app/services/retriever.py`
- Create: `tests/test_retriever.py`

**Step 1: Create app/services/retriever.py**

```python
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Chunk
from app.providers import LLMProvider


@dataclass
class RetrievalContext:
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, provider: LLMProvider, top_k: int = 5):
        self.provider = provider
        self.top_k = top_k

    async def retrieve(
        self,
        db: Session,
        query: str,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks for a query."""
        # Get query embedding
        embeddings = await self.provider.embed([query])
        query_embedding = embeddings[0]

        # Build query with optional filters
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        where_clauses = []
        params = {"embedding": embedding_str, "limit": self.top_k}

        if context:
            if context.bridge_id:
                where_clauses.append("bridge_id = :bridge_id")
                params["bridge_id"] = context.bridge_id
            if context.lvl1:
                where_clauses.append("lvl1 = :lvl1")
                params["lvl1"] = context.lvl1
            if context.lvl2:
                where_clauses.append("lvl2 = :lvl2")
                params["lvl2"] = context.lvl2
            if context.lvl3:
                where_clauses.append("lvl3 = :lvl3")
                params["lvl3"] = context.lvl3

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = text(f"""
            SELECT id, content, section_title, lvl1, lvl2, lvl3, bridge_id,
                   page_range, source_id, created_at, embedding,
                   1 - (embedding <=> :embedding::vector) as score
            FROM chunks
            {where_sql}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = db.execute(sql, params)
        rows = result.fetchall()

        results = []
        for row in rows:
            chunk = Chunk(
                id=row.id,
                content=row.content,
                section_title=row.section_title,
                lvl1=row.lvl1,
                lvl2=row.lvl2,
                lvl3=row.lvl3,
                bridge_id=row.bridge_id,
                page_range=row.page_range,
                source_id=row.source_id,
                embedding=list(row.embedding) if row.embedding else [],
            )
            results.append(RetrievalResult(chunk=chunk, score=row.score))

        return results
```

**Step 2: Write retriever tests**

Create `tests/test_retriever.py`:

```python
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Chunk, Source
from app.services.retriever import Retriever, RetrievalContext


class MockProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    async def chat(self, messages):
        pass


@pytest.fixture
def db_session():
    engine = create_engine("postgresql://bridge:bridge@localhost:5432/bridge_rag")

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Clean up and seed test data
        session.execute(text("DELETE FROM chunks"))
        session.execute(text("DELETE FROM sources"))
        session.commit()

        source = Source(type="note", title="Test")
        session.add(source)
        session.flush()

        chunks = [
            Chunk(
                source_id=source.id,
                content="赵州桥是石拱桥",
                lvl1="形制与技术",
                bridge_id=1,
                embedding=[0.1] * 1024,
            ),
            Chunk(
                source_id=source.id,
                content="卢沟桥位于北京",
                lvl1="地域与环境",
                bridge_id=2,
                embedding=[0.2] * 1024,
            ),
        ]
        session.add_all(chunks)
        session.commit()

        yield session
        session.rollback()


@pytest.fixture
def retriever():
    return Retriever(provider=MockProvider(), top_k=5)


@pytest.mark.asyncio
async def test_retrieve_without_context(retriever, db_session):
    results = await retriever.retrieve(db_session, "桥梁结构")

    assert len(results) == 2
    assert all(r.chunk.content for r in results)


@pytest.mark.asyncio
async def test_retrieve_with_lvl1_filter(retriever, db_session):
    context = RetrievalContext(lvl1="形制与技术")
    results = await retriever.retrieve(db_session, "桥梁", context)

    assert len(results) == 1
    assert results[0].chunk.lvl1 == "形制与技术"


@pytest.mark.asyncio
async def test_retrieve_with_bridge_filter(retriever, db_session):
    context = RetrievalContext(bridge_id=2)
    results = await retriever.retrieve(db_session, "桥梁", context)

    assert len(results) == 1
    assert "卢沟桥" in results[0].chunk.content
```

**Step 3: Update app/services/__init__.py**

```python
from app.services.chunker import ChunkResult, SemanticChunker
from app.services.retriever import Retriever, RetrievalContext, RetrievalResult
from app.services.tagger import MetadataTagger, TagResult

__all__ = [
    "ChunkResult",
    "SemanticChunker",
    "MetadataTagger",
    "TagResult",
    "Retriever",
    "RetrievalContext",
    "RetrievalResult",
]
```

**Step 4: Run tests**

```bash
pytest tests/test_retriever.py -v
# Expected: 3 passed
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: retriever service with metadata filtering and vector search"
```

---

## Task 7: Generator Service

**Files:**
- Create: `app/services/generator.py`
- Create: `tests/test_generator.py`

**Step 1: Create app/services/generator.py**

```python
from dataclasses import dataclass

from app.providers import ChatMessage, LLMProvider
from app.services.retriever import RetrievalResult


@dataclass
class Citation:
    chunk_id: int
    source_title: str
    page_range: str | None


@dataclass
class GenerationResult:
    summary: str
    details: str
    citations: list[Citation]
    sources: list[str]


class Generator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(
        self,
        question: str,
        evidence: list[RetrievalResult],
    ) -> GenerationResult:
        """Generate answer based on retrieved evidence."""
        if not evidence:
            return GenerationResult(
                summary="未找到相关证据。",
                details="知识库中没有与您问题相关的内容。",
                citations=[],
                sources=[],
            )

        # Build evidence text with citation markers
        evidence_text = ""
        for i, result in enumerate(evidence, 1):
            evidence_text += f"[{i}] {result.chunk.content}\n\n"

        prompt = f"""你是桥梁知识助手。根据以下证据回答问题。

证据：
{evidence_text}

问题：{question}

要求：
1. 优先基于证据回答，在关键信息后标注引用编号如[1][2]
2. 若证据不足以完整回答，明确说明"未找到直接证据"
3. 可附加常识性解释，但要标注为"（非引用）"

请按以下格式回答：

## 要点
- 要点1 [引用编号]
- 要点2 [引用编号]
...

## 详细说明
详细展开解释...
"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        # Build citations and sources
        citations = []
        sources = []
        seen_sources = set()

        for i, result in enumerate(evidence):
            citations.append(Citation(
                chunk_id=result.chunk.id,
                source_title=f"来源{i+1}",  # Would need source lookup in real impl
                page_range=result.chunk.page_range,
            ))
            source_key = f"来源{i+1}"
            if source_key not in seen_sources:
                sources.append(source_key)
                seen_sources.add(source_key)

        # Parse response into summary and details
        content = response.content
        summary = ""
        details = content

        if "## 要点" in content and "## 详细说明" in content:
            parts = content.split("## 详细说明")
            summary_part = parts[0].replace("## 要点", "").strip()
            summary = summary_part
            details = parts[1].strip() if len(parts) > 1 else ""

        return GenerationResult(
            summary=summary,
            details=details,
            citations=citations,
            sources=sources,
        )
```

**Step 2: Write generator tests**

Create `tests/test_generator.py`:

```python
import pytest

from app.models import Chunk
from app.providers import ChatMessage, ChatResponse
from app.services.generator import Generator
from app.services.retriever import RetrievalResult


class MockProvider:
    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(
            content="""## 要点
- 赵州桥是石拱桥 [1]
- 采用敞肩式结构 [1]

## 详细说明
赵州桥是中国著名的石拱桥，位于河北省赵县。它采用了独特的敞肩式结构，这种设计减轻了桥身重量。[1]""",
            usage={},
        )


@pytest.fixture
def generator():
    return Generator(provider=MockProvider())


@pytest.fixture
def mock_evidence():
    chunk = Chunk(
        id=1,
        source_id=1,
        content="赵州桥是一座石拱桥，采用敞肩式结构。",
        lvl1="形制与技术",
        embedding=[0.1] * 1024,
    )
    return [RetrievalResult(chunk=chunk, score=0.9)]


@pytest.mark.asyncio
async def test_generate_with_evidence(generator, mock_evidence):
    result = await generator.generate("赵州桥是什么结构？", mock_evidence)

    assert result.summary
    assert result.details
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == 1


@pytest.mark.asyncio
async def test_generate_without_evidence(generator):
    result = await generator.generate("问题", [])

    assert "未找到" in result.summary
    assert len(result.citations) == 0


def test_citation_structure():
    from app.services.generator import Citation

    citation = Citation(chunk_id=1, source_title="来源", page_range="10-12")
    assert citation.chunk_id == 1
    assert citation.page_range == "10-12"
```

**Step 3: Update app/services/__init__.py**

```python
from app.services.chunker import ChunkResult, SemanticChunker
from app.services.generator import Citation, GenerationResult, Generator
from app.services.retriever import Retriever, RetrievalContext, RetrievalResult
from app.services.tagger import MetadataTagger, TagResult

__all__ = [
    "ChunkResult",
    "SemanticChunker",
    "MetadataTagger",
    "TagResult",
    "Retriever",
    "RetrievalContext",
    "RetrievalResult",
    "Generator",
    "GenerationResult",
    "Citation",
]
```

**Step 4: Run tests**

```bash
pytest tests/test_generator.py -v
# Expected: 3 passed
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: generator service with citation support"
```

---

## Task 8: Ask API Endpoint

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/ask.py`
- Create: `app/api/schemas.py`
- Modify: `app/main.py`
- Create: `tests/test_api_ask.py`

**Step 1: Create app/api/schemas.py**

```python
from pydantic import BaseModel


class AskContext(BaseModel):
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    question: str
    context: AskContext | None = None


class CitationResponse(BaseModel):
    chunk_id: int
    source_title: str
    page_range: str | None


class AskResponse(BaseModel):
    summary: str
    details: str
    citations: list[CitationResponse]
    sources: list[str]
```

**Step 2: Create app/api/ask.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import AskRequest, AskResponse, CitationResponse
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator, Retriever, RetrievalContext

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    provider = ZhipuProvider()
    retriever = Retriever(provider=provider)
    generator = Generator(provider=provider)

    # Build retrieval context
    context = None
    if request.context:
        context = RetrievalContext(
            bridge_id=request.context.bridge_id,
            lvl1=request.context.lvl1,
            lvl2=request.context.lvl2,
            lvl3=request.context.lvl3,
        )

    # Retrieve evidence
    evidence = await retriever.retrieve(db, request.question, context)

    # Generate answer
    result = await generator.generate(request.question, evidence)

    return AskResponse(
        summary=result.summary,
        details=result.details,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                source_title=c.source_title,
                page_range=c.page_range,
            )
            for c in result.citations
        ],
        sources=result.sources,
    )
```

**Step 3: Create app/api/__init__.py**

```python
from app.api.ask import router as ask_router

__all__ = ["ask_router"]
```

**Step 4: Update app/main.py**

```python
from fastapi import FastAPI

from app.api import ask_router

app = FastAPI(title="Bridge RAG", version="0.1.0")

app.include_router(ask_router, tags=["ask"])


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 5: Write API tests**

Create `tests/test_api_ask.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_endpoint_schema(client):
    # Test request validation
    response = client.post("/ask", json={})
    assert response.status_code == 422  # Missing required field


@patch("app.api.ask.Retriever")
@patch("app.api.ask.Generator")
@patch("app.api.ask.ZhipuProvider")
def test_ask_endpoint_success(mock_provider, mock_generator, mock_retriever, client):
    # Setup mocks
    mock_retriever_instance = AsyncMock()
    mock_retriever_instance.retrieve.return_value = []
    mock_retriever.return_value = mock_retriever_instance

    mock_generator_instance = AsyncMock()
    mock_generator_instance.generate.return_value = AsyncMock(
        summary="测试摘要",
        details="测试详情",
        citations=[],
        sources=[],
    )
    mock_generator.return_value = mock_generator_instance

    response = client.post("/ask", json={"question": "什么是赵州桥？"})

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "details" in data
    assert "citations" in data
```

**Step 6: Run tests**

```bash
pytest tests/test_api_ask.py -v
# Expected: 3 passed
```

**Step 7: Commit**

```bash
git add -A
git commit -m "feat: /ask API endpoint with retrieval and generation"
```

---

## Task 9: Integration Test & Verification

**Files:**
- Create: `tests/test_integration.py`
- Create: `scripts/seed_test_data.py`

**Step 1: Create scripts/seed_test_data.py**

```python
"""Seed test data for integration testing."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base, Bridge, Chunk, Source, TaxonomyNode


def seed():
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Create taxonomy nodes
        nodes = [
            TaxonomyNode(lvl1="形制与技术", lvl2="结构体系"),
            TaxonomyNode(lvl1="形制与技术", lvl2="构造细部"),
            TaxonomyNode(lvl1="地域与环境", lvl2="水文地形"),
            TaxonomyNode(lvl1="功能与社会", lvl2="交通功能"),
            TaxonomyNode(lvl1="历史与演变", lvl2="建造年代"),
        ]
        session.add_all(nodes)

        # Create bridges
        bridges = [
            Bridge(
                name="赵州桥",
                aliases="安济桥",
                location="河北省赵县",
                era="隋代",
                bridge_type="石拱桥",
                material="石材",
                summary="中国现存最古老的石拱桥",
            ),
            Bridge(
                name="卢沟桥",
                location="北京市丰台区",
                era="金代",
                bridge_type="石拱桥",
                material="石材",
                summary="著名的联拱石桥",
            ),
        ]
        session.add_all(bridges)
        session.flush()

        # Create sources
        source = Source(type="note", title="桥梁知识笔记")
        session.add(source)
        session.flush()

        # Create chunks with embeddings
        chunks = [
            Chunk(
                source_id=source.id,
                content="[章节: 结构特点] 赵州桥是一座敞肩式石拱桥，主拱由28道拱券并列砌成，跨度37.02米。",
                section_title="结构特点",
                lvl1="形制与技术",
                lvl2="结构体系",
                bridge_id=bridges[0].id,
                embedding=[0.1] * 1024,
            ),
            Chunk(
                source_id=source.id,
                content="[章节: 历史背景] 赵州桥建于隋代大业年间（公元605-616年），由工匠李春设计建造。",
                section_title="历史背景",
                lvl1="历史与演变",
                lvl2="建造年代",
                bridge_id=bridges[0].id,
                embedding=[0.2] * 1024,
            ),
            Chunk(
                source_id=source.id,
                content="[章节: 地理位置] 卢沟桥位于北京西南郊永定河上，是华北最长的古代石桥。",
                section_title="地理位置",
                lvl1="地域与环境",
                lvl2="水文地形",
                bridge_id=bridges[1].id,
                embedding=[0.3] * 1024,
            ),
        ]
        session.add_all(chunks)
        session.commit()

        print("Test data seeded successfully!")
        print(f"- {len(nodes)} taxonomy nodes")
        print(f"- {len(bridges)} bridges")
        print(f"- {len(chunks)} chunks")


if __name__ == "__main__":
    seed()
```

**Step 2: Create tests/test_integration.py**

```python
"""Integration tests for the full RAG pipeline."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base, Chunk, Source
from app.services import Generator, Retriever, RetrievalContext


class MockProvider:
    """Mock provider for integration tests without real API calls."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Return consistent embeddings based on text content
        embeddings = []
        for text in texts:
            if "赵州桥" in text or "石拱" in text:
                embeddings.append([0.1] * 1024)
            elif "卢沟桥" in text:
                embeddings.append([0.3] * 1024)
            else:
                embeddings.append([0.15] * 1024)
        return embeddings

    async def chat(self, messages):
        from app.providers import ChatResponse
        return ChatResponse(
            content="""## 要点
- 赵州桥是石拱桥 [1]

## 详细说明
赵州桥是中国著名的石拱桥。[1]""",
            usage={},
        )


@pytest.fixture
def db_session():
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Setup test data
        session.execute(text("DELETE FROM chunks"))
        session.execute(text("DELETE FROM sources"))
        session.commit()

        source = Source(type="note", title="Test")
        session.add(source)
        session.flush()

        chunks = [
            Chunk(
                source_id=source.id,
                content="赵州桥是一座石拱桥，跨度37米。",
                lvl1="形制与技术",
                bridge_id=1,
                embedding=[0.1] * 1024,
            ),
            Chunk(
                source_id=source.id,
                content="赵州桥建于隋代。",
                lvl1="历史与演变",
                bridge_id=1,
                embedding=[0.12] * 1024,
            ),
        ]
        session.add_all(chunks)
        session.commit()

        yield session


@pytest.mark.asyncio
async def test_full_rag_pipeline(db_session):
    """Test the complete RAG pipeline: retrieve -> generate."""
    provider = MockProvider()
    retriever = Retriever(provider=provider, top_k=5)
    generator = Generator(provider=provider)

    # Retrieve
    results = await retriever.retrieve(db_session, "赵州桥是什么结构？")
    assert len(results) >= 1

    # Generate
    answer = await generator.generate("赵州桥是什么结构？", results)
    assert answer.summary
    assert answer.details
    assert len(answer.citations) >= 1


@pytest.mark.asyncio
async def test_filtered_retrieval(db_session):
    """Test retrieval with context filters."""
    provider = MockProvider()
    retriever = Retriever(provider=provider, top_k=5)

    # Filter by lvl1
    context = RetrievalContext(lvl1="形制与技术")
    results = await retriever.retrieve(db_session, "桥梁结构", context)

    assert len(results) >= 1
    assert all(r.chunk.lvl1 == "形制与技术" for r in results)
```

**Step 3: Run all tests**

```bash
docker compose up -d db
pytest tests/ -v --tb=short
# Expected: All tests passing
```

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: integration tests and test data seeding script"
```

---

## Task 10: Final Cleanup & Documentation

**Files:**
- Create: `README.md`
- Update: `pyproject.toml` (add scripts)

**Step 1: Create README.md**

```markdown
# Bridge RAG System

桥梁知识检索增强生成系统 V0

## Quick Start

```bash
# Start database
docker compose up -d db

# Install dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your ZHIPU_API_KEY

# Seed test data (optional)
python scripts/seed_test_data.py

# Run server
uvicorn app.main:app --reload

# Test the API
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "赵州桥是什么结构？"}'
```

## API Endpoints

- `GET /health` - Health check
- `POST /ask` - Ask a question with optional context filtering

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
app/
├── api/          # FastAPI routes
├── core/         # Config, database
├── models/       # SQLAlchemy models
├── providers/    # LLM provider abstraction
└── services/     # Business logic (chunker, retriever, generator)
```
```

**Step 2: Run final test suite**

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

**Step 3: Commit**

```bash
git add -A
git commit -m "docs: add README with quick start guide"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Project skeleton | Manual verification |
| 2 | Database models | test_models.py |
| 3 | LLM Provider | test_providers.py |
| 4 | Semantic Chunker | test_chunker.py |
| 5 | Metadata Tagger | test_tagger.py |
| 6 | Retriever | test_retriever.py |
| 7 | Generator | test_generator.py |
| 8 | Ask API | test_api_ask.py |
| 9 | Integration | test_integration.py |
| 10 | Documentation | - |

**Total estimated commits:** 10
