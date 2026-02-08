# Bridge RAG System

桥梁知识检索增强生成系统 V1

## Quick Start

### Option 1: Docker Deployment (推荐)

使用 Docker Compose 一键部署数据库、API、Web 三个服务：

```bash
# 设置环境变量
export ZHIPU_API_KEY="your_api_key_here"

# 启动开发环境（支持热重载）
make dev

# 或启动生产环境
make prod
```

访问：
- Web UI: http://localhost:3000 (开发) / http://localhost:80 (生产)
- API Docs: http://localhost:8000/docs (开发)

详见 [Docker 部署指南](./docs/docker-deployment.md)

### Option 2: Local Development

传统方式，本地运行 API 服务：

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
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "赵州桥是什么结构？"}'
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/v1/ask` - Ask with hybrid retrieval (vector + FTS + facets) and citations
- `POST /api/v1/ingest` - Ingest markdown content into chunks

## Running Tests

```bash
pytest -q
```

## DB Notes (V1)

V1 adds fields/indexes for full-text search:
- `chunks.contextual_text` / `chunks.search_text`
- `chunks.tsv` (TSVECTOR) + GIN index
- `chunks.embedding` IVFFLAT index (pgvector; best-effort)

`Base.metadata.create_all()` will not alter an existing schema; use `python scripts/migrate_db.py` to upgrade old DBs and backfill `tsv`.

## Project Structure

```
app/
├── api/          # FastAPI routes
│   └── v1/
│       ├── ask.py     # /api/v1/ask endpoint
│       ├── ingest.py  # /api/v1/ingest endpoint
│       └── schemas.py # Request/response models
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
    ├── hybrid_retriever.py # V1 hybrid retrieval with RRF fusion
    └── tagger.py   # LLM-based taxonomy classification
```
