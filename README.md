# Bridge RAG System

桥梁知识检索增强生成系统 V1

## Quick Start

```bash
# Start database
docker compose up -d db

# Install dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your ZHIPU_API_KEY

# Migrate / backfill DB (required for existing databases; safe to run repeatedly)
python scripts/migrate_db.py

# Seed test data (optional)
python scripts/seed_test_data.py

# Run server
uvicorn app.main:app --reload

# Test the API
curl -X POST http://localhost:8000/ask/v2 \
  -H "Content-Type: application/json" \
  -d '{"question": "赵州桥是什么结构？"}'
```

## API Endpoints

- `GET /health` - Health check
- `POST /ask` - Legacy (V0): vector retrieval with optional context filtering
- `POST /ask/v2` - V1: hybrid retrieval (vector + FTS + facet-guided analogy) with confidence + evidence groups

## Running Tests

```bash
pytest tests/ -v
```

## DB Notes (V1)

V1 adds fields/indexes for full-text search:
- `chunks.contextual_text` / `chunks.search_text`
- `chunks.tsv` (TSVECTOR) + GIN index
- `chunks.embedding` HNSW index (pgvector; best-effort)

`Base.metadata.create_all()` will not alter an existing schema; use `python scripts/migrate_db.py` to upgrade old DBs and backfill `tsv`.

## Project Structure

```
app/
├── api/          # FastAPI routes
│   ├── ask.py       # /ask endpoint
│   └── schemas.py  # Request/response models
├── core/         # Config, database
│   ├── config.py   # Pydantic settings
│   └── database.py # SQLAlchemy session
├── models/       # SQLAlchemy models
│   ├── base.py     # Base class, TimestampMixin
│   ├── bridge.py   # Bridge model
│   ├── chunk.py    # Chunk model with pgvector embedding
│   ├── source.py   # Source model
│   └── taxonomy.py # TaxonomyNode model
├── providers/    # LLM provider abstraction
│   ├── base.py     # LLMProvider ABC
│   └── zhipu.py    # Zhipu API implementation
└── services/     # Business logic
    ├── chunker.py  # Semantic chunking
    ├── generator.py # Answer generation with citations
    ├── retriever.py # (Legacy) vector search with metadata filtering
    ├── hybrid_retriever.py # V1 hybrid retrieval with RRF fusion
    └── tagger.py   # LLM-based taxonomy classification
```
