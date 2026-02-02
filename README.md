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
    ├── retriever.py # Vector search with metadata filtering
    └── tagger.py   # LLM-based taxonomy classification
```
