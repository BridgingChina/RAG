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

**Pages:** Dashboard, Chunks (list/detail/editor), Bridges (list/create/detail), Sources (list/detail), Taxonomy, Knowledge Points (list/detail), Ingest (list/detail), Ask, Settings (+ batch operations), Audit Logs, Login

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

Copy `.env.example` to `.env` and set `ZHIPU_API_KEY` and `SECRET_KEY`. The database URL defaults to `postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag` (matching docker-compose.yml). `SECRET_KEY` is used for JWT token signing — change it in production. `CORS_ORIGINS` accepts a JSON list of allowed origins (default: `["http://localhost:3000", "http://localhost:5173"]`); set to `["https://your-domain.com"]` in production.

## Database Schema Management

The system uses automatic schema versioning:
- Schema version is tracked in the `schema_version` table（列: `version, description, created_at`，无 `id` 列。查询用 `get_current_schema_version(engine)`）
- Current version: 5 — Adds bridge_images + knowledge_point_bridges tables + bridges.geocode_source column
- Database auto-initializes on first startup if no version exists
- For development, use `python scripts/reset_db.py --force` to recreate from scratch
- Schema migration: `python scripts/migrate_db.py`（支持增量迁移，`MIGRATIONS` dict 定义版本间迁移函数）

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
- `app/services/chunk_editor.py` — Chunk 手动校对服务：content 编辑（重算 search_text/tsv）、bridge_links 替换、split/merge、批量 reindex。编辑后设 `needs_reindex=True`
- `app/services/reindex_cron.py` — 每日 03:00 后台 cron，自动重建 stale chunks 的 search_text + tsv（不含 embedding）
- `app/core/rate_limit.py` — Shared slowapi `Limiter` singleton (60 req/min/IP default). Import `limiter` to add `@limiter.limit()` on endpoints. `/health` is exempt

**桥梁详情聚合：** 四章节（structure/geography/society/history）从 chunks 实时聚合（无独立表），通过 `LVL1_TO_SECTION` 映射 lvl1 → section key。L0 = section_title 或 content 截断，L1 = 完整 content + citations。

**索引链路（search_text pipeline）：** chunk 入库时经历 `content → contextual_text（ContextEnricher 生成的上下文描述）→ search_text（拼合后用于检索的文本）→ tsv（jieba 分词后的 tsvector）`。向量索引用 `embedding` 列，全文索引用 `tsv` 列。

**Configuration:**

- `config/taxonomy.yaml` — 三级知识分类体系，通过 `app/core/constants.py` 加载（`@lru_cache`）
- `app/core/taxonomy_loader.py` — DB-backed taxonomy loader（API/admin 使用）。`constants.py` 仅供 `tagger.py` 使用，两者独立
- `config/facets.yaml` — Facet 枚举值（桥型、材料、年代、区域、功能）
- `app/core/config.py` — `git_commit`/`git_date` 字段从环境变量读取，Docker build args 注入（`deploy.sh` 设置）

**Data Model:**（所有表使用 UUID v4 主键，通过 `UUIDMixin` 统一管理）

- `chunks` — 核心检索单元，1024 维向量（HNSW 索引，m=16, ef_construction=64, ef_search=40）、taxonomy 标签（lvl1/lvl2/lvl3）、GIN 索引用于 FTS
- `bridges` — 桥梁档案（bridge_type/material/era/region/function/latitude/longitude）
- `chunk_bridge_links` — chunks ↔ bridges 多对多关联表
- `taxonomy_nodes` — 三级目录结构
- `sources` — 来源元信息
- `users` — 用户账户（username/hashed_password/display_name/is_active）
- `audit_logs` — 审计日志（user_id/action/resource_type/resource_id/detail/ip_address）
- `ingest_tasks` — 异步入库任务（status/file_name/file_type/r2_raw_key/zhipu_task_id/source_id/parsed_content）
- `knowledge_points` — 知识点实体（name/aliases/difficulty/summary/l2_content JSONB），挂在 taxonomy_nodes lvl3 下
- `knowledge_point_key_points` — 知识点要点（summary/explanation/order_index/chunk_ids[]），ON DELETE CASCADE
- `flashcards` — 闪卡内容（card_type/front_title/back_answer/back_key_features），FK → knowledge_points + bridges(SET NULL)
- `device_favorites` — 设备收藏（device_id/target_type/target_id），UNIQUE 约束
- `device_review_progress` — 闪卡复习状态（mastery/last_reviewed_at），预留 SM-2 字段（interval/ease_factor），FK → flashcards(CASCADE)
- `device_view_history` — 设备浏览历史（target_type/target_id/viewed_at）
- `bridge_images` — 桥梁图片（bridge_id/r2_key/caption/type/order_index），FK → bridges(CASCADE)
- `knowledge_point_bridges` — 知识点-桥梁关联（knowledge_point_id/bridge_id/relevance_note/order_index），UNIQUE(kp, bridge)

**API Endpoints:**

- `GET /health` — Health check
- `POST /api/v1/ask` — 问答端点，三通道混合检索，返回 `confidence` 和 `evidence_groups`
- `POST /api/v1/ingest` — 入库端点，接受 Markdown 格式文档
- `GET /api/v1/system/status` — 系统状态（只读，DB/配置信息）
- CRUD: `/api/v1/chunks`, `/api/v1/bridges`, `/api/v1/stats`
- Chunk editing: `POST /chunks/{id}/split`, `POST /chunks/merge`, `PATCH /chunks/batch`
- Reindex: `POST /sources/{id}/reindex` — 重建 stale chunks 的 search_text/tsv/embedding
- Read-only: `/api/v1/sources`（仅 GET list + detail）
- Ingest tasks: `/api/v1/ingest-tasks`（presign, create, list, detail, confirm, delete, retry, batch-delete, download-url）— 异步入库流水线，软删除（status="deleted"）
- Tree CRUD: `/api/v1/taxonomy`（`GET tree`, `POST/PUT/DELETE nodes`, `POST batch-update`）
- `POST /api/v1/bridges/{target_id}/merge` — 桥梁合并（将源桥 chunks 迁移到目标桥）
- Auth: `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `PUT /api/v1/auth/password`
- Audit: `GET /api/v1/audit-logs`（分页+筛选：user_id/action/resource_type/start/end）
- Knowledge Points CRUD: `GET/POST /api/v1/knowledge-points`, `GET/PUT/DELETE /api/v1/knowledge-points/{id}`, `POST /api/v1/knowledge-points/{id}/generate-key-points`（LLM 生成 key_points），`POST /{id}/generate-flashcards`，`POST /{id}/sync-bridges`，`GET/PUT /{id}/bridges`
- Bridge Images: `POST /api/v1/bridges/{id}/images/presign`, `POST /images`, `GET /images`, `PUT /images/reorder`, `DELETE /images/{image_id}`
- Batch Operations: `POST /api/v1/bridges/batch-geocode`（高德 API），`POST /bridges/import-coordinates`（CSV），`POST /api/v1/flashcards/batch-generate`
- Mobile API (no auth): `GET /api/mobile/v1/config`, `GET /api/mobile/v1/bridges`, `GET /api/mobile/v1/bridges/clusters`, `GET /api/mobile/v1/bridges/{id}`, `GET /api/mobile/v1/bridges/{id}/knowledge-points`, `GET /api/mobile/v1/knowledge/tree`, `GET /api/mobile/v1/knowledge/points/{id}`, `GET /api/mobile/v1/knowledge/points/{id}/bridges`, `GET /api/mobile/v1/knowledge/points/{id}/flashcards`, `POST /api/mobile/v1/qa/ask` (SSE), `GET /api/mobile/v1/search`
- Mobile favorites (X-Device-Id): `GET/POST /api/mobile/v1/favorites`, `DELETE /api/mobile/v1/favorites/{id}`, `POST /api/mobile/v1/favorites/check`
- Mobile review (X-Device-Id): `GET /api/mobile/v1/review/today`, `GET /api/mobile/v1/review/cards`, `PUT /api/mobile/v1/review/progress/{id}`
- Mobile history (X-Device-Id): `GET/POST /api/mobile/v1/history`
- Mobile endpoints use `MobileResponse`/`MobilePaginatedResponse` wrappers (not `PaginatedResponse`)
- 除 `/health`、`/auth/login` 和 `/api/mobile/v1/*` 外，所有端点均需 JWT Bearer token 认证。Mobile 端点中 favorites/review/history 需要 `X-Device-Id` header（UUID v4），其余 mobile 端点完全公开
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
- SQLAlchemy `onupdate=func.now()` 仅对 ORM 级别 UPDATE 生效 — raw SQL / `.update()` 需手动 `SET updated_at = now()`
- `AuditService.log()` 的 detail dict 必须是 JSON 可序列化的 — 不能放 `func.now()` 等 SQLAlchemy 对象
- Pydantic response schema 加 required field 后，端点构造器必须同步传值，否则 500 ValidationError
- FastAPI 路由顺序：literal 路由（`/merge`、`/batch`）必须在 parametric 路由（`/{chunk_id}/split`）之前注册，否则 "merge" 被当作 chunk_id 解析导致 422
- 所有分页端点（chunks/bridges/sources/audit）强制 `page_size ≤ 100`（`Query(le=100)`）— 前端请求不可超出，否则 422
- Dockerfile COPY `app/`, `config/`, `data/`, `scripts/` — `tests/` 不在镜像中。`docker-entrypoint.sh` 启动时跑 `migrate_db.py`（当前仅做版本检查）
- `IngestTaskService` 的 BackgroundTask 使用独立 `SessionLocal()` — 不能复用请求级 db session，否则 session 已关闭
- R2 presigned URL 有效期 1 小时 — 前端需在获取后尽快完成上传
- R2 bucket 必须配置 CORS（AllowedOrigins = 前端域名，AllowedMethods = PUT/GET，AllowedHeaders = Content-Type）— 否则浏览器 presigned URL 上传会被 CORS 拦截
- FastAPI BackgroundTasks 中的 async 函数必须用 `async def` + `await` — 不能用 `asyncio.run()`（会在已有事件循环中崩溃）
- 智谱文件解析 API `download_link` 模式下 `content=None` — 解析结果在 zip 包（`result.md` + `images/`）里，不在 `content` 字段中。`text` 模式有 1MB 上限
- 类型迁移（如 int→UUID）时注意"边缘文件" — `schemas/stats.py` 等非主路径 schema、前端组件的 `useState<number>` 局部状态不在主依赖链上，IDE/tsc 未必能检出
- `migrate_db.py` 增量迁移脚本 — `MIGRATIONS` dict 按版本号索引迁移函数，`docker-entrypoint.sh` 启动时自动执行
- Ingest task 软删除：`status="deleted"` 保留任务记录和 R2 文件，`_cleanup_task_data` 清理 chunks/bridge_links/source 但不删 R2 — retry/delete/batch-delete 共用
- `useApi` hook 的 `loading` 每次 `refetch()` 都重置为 `true` — 轮询场景用 `loading && !data` 显示骨架屏，避免每 3 秒闪烁
- Worktree 开发修改共享类型（如 `IngestTaskStatus` 加枚举值）后，main 上未修改的旧组件可能引用该类型而报错 — worktree 中 `tsc` 不会检查 main 独有的文件，squash merge 后 Docker build 才暴露
- `ChunkEditor` 的 `handleConflictError` + conflict dialog 被 save/split/delete 共用 — 修改对话框文案时要保持通用（不能用 save-specific 语言）
- 进入新 UI 模式（如 split mode）时必须 `setActionError(null)` — 否则前一个操作的错误会泄漏到新模式
- Mobile API 响应格式与管理后台不同：`{"data": ..., "meta": ...}` 而非 `{"items": ..., "total": ...}`
- `generate_streaming()` 返回 `list[tuple]` 而非 async generator — 伪流式，单次 LLM 调用后拆分，后续 TODO 升级为真流式
- `GET /bridges/clusters` 必须在 `/{bridge_id}` 之前注册（bridges.py 文件中），否则 "clusters" 被当作 UUID 解析
- `device_favorites` 使用 UNIQUE(device_id, target_type, target_id) — 重复添加收藏会触发 IntegrityError，需捕获返回 409
- `review/today` 端点的复习规则：mastery IS NULL OR needs_review OR (mastered 且 last_reviewed_at 超 3 天)
- `generate-key-points` 端点的 chunk 检索策略：先 lvl3 匹配，不足 3 条时退化到 lvl2
- `_download_and_store_parsed_assets` 有 SSRF 防护 — `download_url` 必须是 `https` 且 hostname 在白名单内（`open.bigmodel.cn`, `cdn.bigmodel.cn`）。如果智谱新增 CDN 域名需更新 `ALLOWED_ZHIPU_HOSTS`
- `db.rollback()` inside a helper method rolls back the **entire** transaction — use `db.begin_nested()` (savepoint) when catching `IntegrityError` mid-transaction to avoid nuking the caller's work
- `Bridge.name` has a unique constraint — `create_bridge` API returns 409 on duplicate, `BridgeLinker` uses savepoint + query-on-conflict
- Login rate limiter (`app/api/v1/auth.py`) is in-memory + process-local — state resets on restart, not shared across `uvicorn --workers N`. Uses `time.monotonic()` + `threading.Lock`. Tests must clear `_failed_attempts` dict in setup/teardown to avoid cross-test pollution
- slowapi `Limiter` must be a single shared instance (`app/core/rate_limit.py`) — creating a second `Limiter` in endpoint modules won't share state with `app.state.limiter`
- `/health` is `@limiter.exempt` — do not remove, or load balancer probes will get 429'd

## Worktrees

项目使用 `.worktrees/` 存放 git worktrees，已在 .gitignore 中忽略。
