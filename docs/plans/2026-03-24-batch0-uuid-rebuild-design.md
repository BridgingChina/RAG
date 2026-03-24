# 第零批：UUID 全面迁移 + 清库重建设计

> 日期：2026-03-24
> 状态：已批准
> 范围：第零批基础改造（阻塞一切后续工作）
> 策略：单 PR，worktree 开发，一次性完成后端 + 前端

---

## 1. 决策记录

| 决策项 | 结论 |
|--------|------|
| 起始批次 | 第零批（基础改造） |
| 清库策略 | 彻底清库，删除旧 migration，版本重置为 1 |
| TimestampMixin | 拆分为 `CreatedAtMixin` + `TimestampMixin`（继承前者） |
| UUID 范围 | 8 张表全部改 UUID，`schema_version` 保持 int |
| 前端同步 | 本次一并改完，保证整体一致性 |
| 分支策略 | 单 PR 一次性完成 |
| `location→region` | 按 roadmap，无特殊格式要求 |

---

## 2. Model 层改造

### 2.1 `base.py` — Mixin 拆分 + UUID 主键

```python
import uuid
from sqlalchemy.dialects.postgresql import UUID

class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### 2.2 各表 Mixin 分配

| 表 | Mixin 组合 | 理由 |
|---|---|---|
| `bridges` | UUIDMixin + TimestampMixin | 新增 `updated_at`（坐标编辑等场景） |
| `chunks` | UUIDMixin + CreatedAtMixin | `updated_at` 已手动定义（optimistic lock） |
| `sources` | UUIDMixin + CreatedAtMixin | 只读不改 |
| `taxonomy_nodes` | UUIDMixin（无时间戳） | 现有就没有时间戳 |
| `chunk_bridge_links` | UUIDMixin + CreatedAtMixin | 只写不改 |
| `users` | UUIDMixin + TimestampMixin | 密码修改需 `updated_at` |
| `audit_logs` | UUIDMixin + CreatedAtMixin | 只写不改 |
| `ingest_tasks` | UUIDMixin + TimestampMixin | 状态流转需 `updated_at` |

### 2.3 `bridges` 模型变更

- `location` → `region`（String(255)，nullable）
- 新增 `latitude`（Double，nullable）
- 新增 `longitude`（Double，nullable）
- 新增部分索引：`ix_bridges_geo ON (latitude, longitude) WHERE latitude IS NOT NULL`
- 新增 `updated_at`（通过 TimestampMixin）

### 2.4 `chunks` 特殊处理

`chunks.updated_at` 保留手动定义（`onupdate` + optimistic lock 依赖），不从 TimestampMixin 继承。Chunk 使用 `CreatedAtMixin` + 手动 `updated_at`。

外键 `bridge_id`、`source_id` 类型从 `int` 改为 `UUID`。

### 2.5 外键依赖关系

```
bridges.id ← chunks.bridge_id, chunk_bridge_links.bridge_id
sources.id ← chunks.source_id, ingest_tasks.source_id
users.id   ← audit_logs.user_id, ingest_tasks.created_by
chunks.id  ← chunk_bridge_links.chunk_id
```

---

## 3. `database.py` 清库重建

### 3.1 版本重置

- `LATEST_SCHEMA_VERSION = 1`
- 描述：`"Schema v1: UUID primary keys, clean rebuild"`

### 3.2 删除旧 migration

`_migrate_schema()` 函数整个删除（v2→v3→v4→v5→v6 增量 migration 全部废弃）。

### 3.3 `init_database()` 简化逻辑

```
schema_version 不存在 → create_all() + seed_taxonomy + stamp v1
version == 1          → verify_schema_compatibility()，正常启动
version > 1           → RuntimeError（未来 migration 预留）
version < 1           → RuntimeError
```

### 3.4 `verify_schema_compatibility()` 更新

- `bridges`: `location` → `region`，新增 `latitude`、`longitude`、`updated_at`
- 新增 `users` 和 `audit_logs` 表的列校验
- 其余表更新列名以匹配新 schema

---

## 4. API 层 + Schema 改造

### 4.1 Backend Schemas（`app/api/v1/schemas/`）

所有 response/request schema 中 ID 字段从 `int` 改为 `uuid.UUID`。

涉及文件：
- `schemas/bridge.py` — `location→region`，新增 `latitude`/`longitude`，ID 改 UUID
- `schemas/chunk.py` — `id`、`source_id`、`bridge_id` 改 UUID
- `schemas/source.py` — `id` 改 UUID
- `schemas/taxonomy.py` — `id`/`node_id` 改 UUID
- `schemas/ingest_task.py` — `id`、`source_id`、`created_by` 改 UUID
- `schemas/audit.py` — `id`、`user_id` 改 UUID
- `schemas/auth.py` — `id` 改 UUID
- `schemas/ask.py` — bridge_id 引用改 UUID

### 4.2 Backend Endpoints

所有 path parameter 从 `int` 改为 `UUID`。

涉及文件：`chunks.py`、`bridges.py`、`sources.py`、`taxonomy.py`、`ingest_tasks.py`、`audit.py`

### 4.3 `hybrid_retriever.py`

`Bridge.location.like(...)` → `Bridge.region.like(...)`

---

## 5. 前端改造

| 文件 | 改动 |
|---|---|
| `lib/types.ts` | 所有 `id: number` → `id: string`，所有 FK 同理，`location` → `region` |
| `lib/api.ts` | 函数签名 `id: number` → `id: string` |
| `ChunkDetailPage.tsx` | 删除 `Number(id)` 转换 |
| `BridgeDetailPage.tsx` | 删除 `Number(id)` 转换 |
| `SourceDetailPage.tsx` | 删除 `Number(id)` 转换 |
| `IngestTaskDetailPage.tsx` | 删除 `Number(id)` 转换 |
| `BridgeForm.tsx` | `location` → `region` |
| `BridgeListPage.tsx` | `location` → `region` |

---

## 6. 测试 + 部署

### 6.1 测试更新

- `conftest.py` 中 fixture 的 ID 生成改为 UUID
- 硬编码 `id=1` 改为 UUID 字面量或动态生成

### 6.2 验证清单

- `npx tsc --noEmit` 通过
- `pytest tests/ -v` 通过（不含 integration）
- `reset_db.py --force` + `uvicorn` 能正常启动

### 6.3 生产部署

1. 合入 main → GitHub Actions 触发
2. 服务器手动执行 `reset_db.py --force`（清库重建，现有数据丢失——预期行为）
3. `docker compose up` 正常启动

---

## 7. 不在本次范围内

- 新增 `knowledge_points` 等表（第一批）
- 移动端 API 路由（第一批）
- SSE 流式问答（第一批）
- 任何 P1/P2 功能
