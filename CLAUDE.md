# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bridge RAG System v1.0.0 — 桥梁知识检索增强生成系统。云端 RAG 服务，支持带引用的问答。

基于上下文增强索引 + FTS 全文检索 + 三通道混合检索（Anchor 本桥 / Concept 通用 / Analogy 类比）。

## Commands

### Frontend (web/)

```bash
cd web && npm run dev    # Vite dev server
cd web && npm run build  # TypeScript check + production build
cd web && npm run lint   # ESLint
cd web && npx tsc --noEmit  # Type check only (no build)
```

**Pages:** Dashboard, Chunks (list/detail), Bridges (list/create/detail), Sources (list/detail), Taxonomy, Ingest, Ask, Settings, Audit Logs, Login

### Development Setup

**Recommended (Works on all platforms):**
```bash
# Start database (PostgreSQL + pgvector on port 5433)
docker compose up -d db

# Install dependencies
pip install -e ".[dev]"

# Run server with hot reload
uvicorn app.main:app --reload
```

**Alternative: Full Docker Compose (Linux/WSL2):**
```bash
# Start all services (database + API + web)
make dev
# or
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Note:** On macOS, Docker volume mounts may cause `OSError: [Errno 35]` errors with API hot reload. The recommended approach (local Python + Docker database) works reliably across all platforms.

**Database Auto-Initialization:**
The database schema is automatically initialized on first startup. No need to manually run `reset_db.py` for fresh installations.

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run single test file
pytest tests/test_chunker.py -v

# Run single test
pytest tests/test_chunker.py::test_chunk_simple_text -v

# Run integration tests only (require running DB)
pytest tests/integration/ -v

# Seed test data
python scripts/seed_test_data.py

# Reset database (drop all tables and recreate)
python scripts/reset_db.py

# Create a user account
python3 scripts/create_user.py --username admin --password <password>
```

## Environment Setup

Copy `.env.example` to `.env` and set `ZHIPU_API_KEY` and `SECRET_KEY`. The database URL defaults to `postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag` (matching docker-compose.yml). `SECRET_KEY` is used for JWT token signing — change it in production.

## Database Schema Management

The system uses automatic schema versioning:
- Schema version is tracked in the `schema_version` table（列: `version, description, created_at`，无 `id` 列。查询用 `get_current_schema_version(engine)`）
- Current version: 3 (adds users and audit_logs tables)
- Database auto-initializes on first startup if no version exists
- For development, use `python scripts/reset_db.py --force` to recreate from scratch
- Schema migration: `python scripts/migrate_db.py`

## Architecture

**Tech Stack:** Python 3.11+ + FastAPI, PostgreSQL + pgvector, 智谱 API (embedding-3 + GLM-4)

**Core Flow:**
```
入库: Markdown → 解析 → 切块 → ContextEnricher(上下文描述) → Tagger(标注) → 组装search_text → jieba分词 → embedding+tsv → PostgreSQL
问答: 问题 → 向量化 + Facet抽取 → 三通道召回(Anchor/Concept/Analogy) → RRF融合 → LLM生成(带confidence)
```

**Key Abstractions:**

- `app/providers/` — LLM Provider 抽象层 (`LLMProvider` ABC)，`embed()` 返回 1024 维向量（智谱 embedding-3，可配置 512/1024/2048），`chat()` 返回 `ChatResponse`
- `app/services/markdown_parser.py` — Markdown 解析，提取 front matter 和章节结构
- `app/services/chunker.py` — Heading-aware 语义切块，`chunk(sections: list[Section])` 接收解析后的章节列表。短节合并、长节按 embedding 相似度子分割，保留 `[章节: path]` 前缀
- `app/services/context_enricher.py` — 为 chunk 生成上下文描述（80-160字），包含来源、主题、指代消歧
- `app/services/tagger.py` — LLM 自动标注 lvl1/lvl2/lvl3/bridge_id
- `app/services/tokenizer.py` — jieba 中文分词，支持自定义词典。生成 `to_tsvector_text()` 和 `to_tsquery()`
- `app/services/facet_extractor.py` — 从问题抽取结构化维度（bridge_type/material/era/region/function），带枚举约束。**注意:** `Facet` 是 `@dataclass`（非 Pydantic），序列化用 `dataclasses.asdict()` 而非 `model_dump()`
- `app/services/hybrid_retriever.py` — 三通道检索 + RRF 融合，每通道内部 vector + FTS 双路召回再 RRF 合并
- `app/services/bridge_linker.py` — 将 chunks 关联到 bridges（通过 `chunk_bridge_links` 表）
- `app/services/ranker.py` — RRF 算法 + `apply_diversity()` 多样性约束（analogy 通道限每桥 1 条）
- `app/services/generator.py` — 基于证据生成回答，输出引用和置信度

**索引链路（search_text pipeline）：** chunk 入库时经历 `content → contextual_text（ContextEnricher 生成的上下文描述）→ search_text（拼合后用于检索的文本）→ tsv（jieba 分词后的 tsvector）`。向量索引用 `embedding` 列，全文索引用 `tsv` 列。

**Configuration:**

- `config/taxonomy.yaml` — 三级知识分类体系，通过 `app/core/constants.py` 加载（`@lru_cache`）
- `app/core/taxonomy_loader.py` — DB-backed taxonomy loader（API/admin 使用）。`constants.py` 仅供 `tagger.py` 使用，两者独立
- `config/facets.yaml` — Facet 枚举值（桥型、材料、年代、区域、功能）

**Data Model:**

- `chunks` — 核心检索单元，1024 维向量（IVFFLAT 索引，IVFFLAT 和 HNSW 均有 2000 维上限）、taxonomy 标签（lvl1/lvl2/lvl3）、GIN 索引用于 FTS
- `bridges` — 桥梁档案（bridge_type/material/era/location/function）
- `chunk_bridge_links` — chunks ↔ bridges 多对多关联表
- `taxonomy_nodes` — 三级目录结构
- `sources` — 来源元信息
- `users` — 用户账户（username/hashed_password/display_name/is_active）
- `audit_logs` — 审计日志（user_id/action/resource_type/resource_id/detail/ip_address）

**API Endpoints:**

- `GET /health` — Health check
- `POST /api/v1/ask` — 问答端点，三通道混合检索，返回 `confidence` 和 `evidence_groups`
- `POST /api/v1/ingest` — 入库端点，接受 Markdown 格式文档
- `GET /api/v1/system/status` — 系统状态（只读，DB/配置信息）
- CRUD: `/api/v1/chunks`, `/api/v1/bridges`, `/api/v1/stats`
- Read-only: `/api/v1/sources`（仅 GET list + detail）
- Tree CRUD: `/api/v1/taxonomy`（`GET tree`, `POST/PUT/DELETE nodes`, `POST batch-update`）
- `POST /api/v1/bridges/{target_id}/merge` — 桥梁合并（将源桥 chunks 迁移到目标桥）
- Auth: `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `PUT /api/v1/auth/password`
- Audit: `GET /api/v1/audit-logs`（分页+筛选：user_id/action/resource_type/start/end）
- 除 `/health` 和 `/auth/login` 外，所有端点均需 JWT Bearer token 认证
- 所有写操作自动记录审计日志（含登录成功/失败）

## Testing

- **Unit tests** (`tests/test_*.py`): 不需要数据库，可直接运行
- **Integration tests** (`tests/integration/`): 需要 PostgreSQL+pgvector 运行中，缺失时自动 `pytest.skip`
- **conftest.py**: `db_session` fixture 在事务内运行并回滚；`chunk_factory` 自动处理 tsvector 填充

## Domain Context

知识体系采用三级目录：
- lvl1（四大主线）：形制与技术 / 地域与环境 / 功能与社会 / 历史与演变
- lvl2（主题桶）：结构体系、构造细部、水文地形等
- lvl3（具体知识点）：拱桥结构、桥墩设计、河流特征等

Chunk 可同时挂目录标签和 bridge_id，支持按知识点或按具体桥梁检索。

**三通道检索配额：** Anchor 6 条（本桥） + Concept 2 条（通用） + Analogy 2 条（类比） = 10 条

## Ingest Format

入库资料采用 Markdown 格式，支持 YAML front matter：

```markdown
---
bridge: 桥梁名称
source_type: document
title: 资料标题
---

# 章节标题

正文内容...
```

## Gotchas

- `AuditService.log()` 只做 `db.flush()` 不 commit — 调用者必须自行 `db.commit()`，否则审计记录静默丢失。delete 端点除外（audit+delete 在同一事务内原子提交）
- `passlib[bcrypt]` 在 pyproject.toml 中声明但未使用 — `auth_service.py` 直接用 `bcrypt` 库（passlib 1.7.4 与 bcrypt 5.0.0 不兼容）
- `get_db()` 的 session 是 `autocommit=False` — 不显式 commit 则所有写入在 session close 时丢失
- `SemanticChunker.chunk()` 接收 `list[Section]`（非 `str`）— 调用方必须先 `parse_markdown()` 再传 `doc.sections`
- `ask` 端点自动从问题文本匹配桥梁名（`_resolve_bridge_from_question`），无需调用方传 `target_bridge_id`
- Radix UI `<SelectItem value="">` 不工作 — 必须用哨兵值（如 `"__all__"`、`"__none__"`）

## Worktrees

项目使用 `.worktrees/` 存放 git worktrees，已在 .gitignore 中忽略。
