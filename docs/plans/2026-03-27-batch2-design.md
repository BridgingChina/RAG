# Batch 2 设计文档 — MVP 完整功能

> 日期: 2026-03-27 | 基于 rag-roadmap.md #12-#17 + api-spec.md v1.1
> 前置: Batch 0 (UUID改造) + Batch 1 (移动端骨架+知识模型+SSE QA) 已合并

---

## 0. 范围

| # | 功能 | 类型 |
|---|------|------|
| 12 | 收藏/复习/历史 | 数据表 + API |
| 13 | Flash Cards | 数据表 + API |
| 14 | 统一搜索 | 填充现有空壳 |
| 15 | 地图聚类 | 新端点 |
| 16 | 知识点 L0/L1 内容生成 | 管理后台端点 + LLM |
| 17 | 桥梁详情四章节聚合 | 填充现有骨架 |

## 1. 架构决策

### 1.1 桥梁四章节：实时聚合（非预计算）

从 chunks 表按 `bridge_id + lvl1` 实时查询分组。理由：
- chunks 表已有 `ix_chunks_bridge` 索引，单桥通常 10-50 条 chunks
- L0 取 section_title 或 content 截断，L1 取完整 content，不需 LLM
- 零额外表，数据始终一致

### 1.2 知识点内容生成：管理后台按钮触发

管理员通过 `POST /api/v1/knowledge-points/{id}/generate-key-points` 触发 LLM 生成。可控可审核，不做批量自动生成。

---

## 2. 新增数据模型

Schema v2 → v3，新增 4 张表。

### 2.1 `flashcards`

```
flashcards
├── id                     UUID PK (UUIDMixin)
├── knowledge_point_id     UUID FK → knowledge_points.id
├── card_type              VARCHAR(20) NOT NULL  — concept / identification
├── front_title            TEXT NOT NULL
├── front_hint             TEXT
├── back_answer            TEXT NOT NULL
├── back_key_features      TEXT[]
├── back_example_bridge_id UUID FK → bridges.id (SET NULL on delete)
├── created_at             TIMESTAMPTZ (TimestampMixin)
└── updated_at             TIMESTAMPTZ (TimestampMixin)
INDEX: ix_flashcards_kp ON knowledge_point_id
```

### 2.2 `device_favorites`

```
device_favorites
├── id           UUID PK (UUIDMixin)
├── device_id    UUID NOT NULL
├── target_type  VARCHAR(20) NOT NULL  — bridge / knowledge_point / flashcard
├── target_id    UUID NOT NULL
├── created_at   TIMESTAMPTZ (CreatedAtMixin)
└── UNIQUE(device_id, target_type, target_id)
INDEX: ix_device_favorites_device ON device_id
```

### 2.3 `device_review_progress`

```
device_review_progress
├── id               UUID PK (UUIDMixin)
├── device_id        UUID NOT NULL
├── flashcard_id     UUID FK → flashcards.id (CASCADE on delete)
├── mastery          VARCHAR(20) DEFAULT 'needs_review'
├── last_reviewed_at TIMESTAMPTZ
├── interval         INTEGER DEFAULT 1       — 预留 SM-2
├── ease_factor      REAL DEFAULT 2.5        — 预留 SM-2
└── UNIQUE(device_id, flashcard_id)
```

### 2.4 `device_view_history`

```
device_view_history
├── id           UUID PK (UUIDMixin)
├── device_id    UUID NOT NULL
├── target_type  VARCHAR(20) NOT NULL
├── target_id    UUID NOT NULL
├── viewed_at    TIMESTAMPTZ DEFAULT now()
└── INDEX(device_id, viewed_at DESC)
```

### 2.5 迁移

- `LATEST_SCHEMA_VERSION`: 2 → 3
- `migrate_db.py`: 新增 `MIGRATIONS[2]`，用 `CREATE TABLE IF NOT EXISTS` 创建 4 张表
- `verify_schema_compatibility`: 加入 4 张表列集合
- `init_database` 描述: "Schema v3: flashcards + device tables"
- FK 策略: `flashcards.back_example_bridge_id` → `SET NULL`; `device_review_progress.flashcard_id` → `CASCADE`

---

## 3. 桥梁四章节实时聚合 (#17)

### 3.1 lvl1 → section 映射

| lvl1 | section key |
|------|-------------|
| 形制与技术 | structure |
| 地域与环境 | geography |
| 功能与社会 | society |
| 历史与演变 | history |

### 3.2 L0/L1 内容

- L0: chunk 的 `section_title`（如有），否则 `content[:80]`
- L1: 完整 `content` + source 引用

### 3.3 实现位置

直接在 `app/api/mobile/v1/bridges.py` 的 `get_bridge()` 中实现。一次 DB 查询 chunks + 内存分组。同时补全 `sources` 列表（从 chunks 的 source_id 去重构建）。

---

## 4. 统一搜索 (#14)

### 4.1 搜索策略

ILIKE 模糊匹配（不用 FTS，bridges/kp 记录量级 < 1000）。

```
Bridge 路: name ILIKE %keyword% OR aliases ILIKE %keyword%
  可选过滤: bridge_type, era, region

KP 路: name ILIKE %keyword% OR aliases ILIKE %keyword%
  可选过滤: line (taxonomy_node.lvl1), category (taxonomy_node.lvl2)
```

### 4.2 结果合并

- `type=all`: 两路各查 page_size 条，按 type 交替排列
- `type=bridge` / `type=knowledge_point`: 只查对应路
- highlight: Python `re.sub` 在 name/aliases 中包裹 `<em>`

### 4.3 实现位置

填充 `app/api/mobile/v1/search.py`，新增依赖 `db: Session`。

---

## 5. 地图聚类 (#15)

### 5.1 算法

Grid-based 聚类，按 zoom 级别计算网格大小：

```python
grid_size = 180.0 / (2 ** zoom)
```

SQL 按 `FLOOR(lat/grid_size), FLOOR(lng/grid_size)` 分桶，COUNT + AVG 坐标。

### 5.2 聚类 vs 散点

- count = 1 → `points` 数组
- count > 1 → `clusters` 数组，representative 通过二次查询取 name

### 5.3 路由注册

`GET /bridges/clusters` 必须在 `/{bridge_id}` 之前注册。

参数校验: zoom 1-20, sw_lat < ne_lat。

---

## 6. 收藏/复习/历史 (#12)

### 6.1 新增路由文件

```
app/api/mobile/v1/
├── favorites.py     # 收藏
├── review.py        # 复习
└── history.py       # 浏览历史
```

所有端点通过 `require_device_id` 注入 device_id。

### 6.2 收藏端点

| 端点 | 要点 |
|------|------|
| `GET /favorites` | 按 device_id 查，type 过滤 + 分页。两步查询取 target_name |
| `POST /favorites` | INSERT，重复 → 409 (IntegrityError) |
| `DELETE /favorites/{id}` | 校验 device_id 归属，204 |
| `POST /favorites/check` | 批量查询 `{target_id: {favorited, favorite_id}}` |

target_name 解析策略: 先查 favorites 分页，再按 target_type 分组批量查各目标表。

### 6.3 复习端点

| 端点 | 要点 |
|------|------|
| `GET /review/today` | favorites(flashcard) LEFT JOIN review_progress → 筛选 needs_review 或 mastered 超 3 天 |
| `GET /review/cards` | 该设备收藏的全部 flashcard，分页 |
| `PUT /review/progress/{flashcard_id}` | UPSERT review_progress，更新 mastery + last_reviewed_at |

### 6.4 浏览历史

| 端点 | 要点 |
|------|------|
| `GET /history` | device_id + viewed_at DESC 分页，两步查询取 target_name |
| `POST /history` | INSERT（不去重） |

### 6.5 不建 Service 层

CRUD 逻辑直接在路由函数中实现。

---

## 7. Flash Cards (#13)

### 7.1 读取端点

`GET /knowledge/points/{id}/flashcards` 在现有 `knowledge.py` 中新增，支持 card_type 过滤。

### 7.2 管理后台 CRUD

放在 #16 的知识点管理路由中（如需要），本批暂不实现 flashcard 管理后台 CRUD。

---

## 8. 知识点 L0/L1 内容生成 (#16)

### 8.1 管理后台路由

新建 `app/api/v1/knowledge_points.py`，需 JWT + 审计日志：

| 端点 | 说明 |
|------|------|
| `GET /api/v1/knowledge-points` | 列表，taxonomy_node_id 过滤 + 分页 |
| `POST /api/v1/knowledge-points` | 创建 |
| `GET /api/v1/knowledge-points/{id}` | 详情 |
| `PUT /api/v1/knowledge-points/{id}` | 更新 |
| `DELETE /api/v1/knowledge-points/{id}` | 删除 (CASCADE key_points) |
| `POST /api/v1/knowledge-points/{id}/generate-key-points` | LLM 生成 |

### 8.2 生成流程

1. 查 KP 的 taxonomy_node → 用 lvl1/lvl2/lvl3 从 chunks 检索（limit 20）
2. lvl3 不足 3 条时退化到 lvl2 匹配
3. 拼合 context → 单次 LLM 调用（JSON 结构化输出）
4. 事务内: 删旧 key_points → 插入新 key_points
5. chunk citation index 映射为 chunk UUID 存入 `chunk_ids[]`

### 8.3 LLM Prompt

要求输出 3-7 条 key_points，每条含 summary (20-40字) + explanation (80-200字) + citations[]。复用 ZhipuProvider.chat()。

### 8.4 前端

本批不做管理后台 UI，通过 Swagger/curl 调用。

---

## 9. 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/models/flashcard.py` | 新增 | Flashcard model |
| `app/models/device_favorite.py` | 新增 | DeviceFavorite model |
| `app/models/device_review_progress.py` | 新增 | DeviceReviewProgress model |
| `app/models/device_view_history.py` | 新增 | DeviceViewHistory model |
| `app/models/__init__.py` | 修改 | 注册 4 个新 model |
| `app/core/database.py` | 修改 | LATEST_SCHEMA_VERSION=3, verify_schema 加 4 表 |
| `scripts/migrate_db.py` | 修改 | MIGRATIONS[2] 创建 4 张表 |
| `app/api/mobile/v1/bridges.py` | 修改 | 填充 sections 聚合 + sources |
| `app/api/mobile/v1/search.py` | 重写 | ILIKE 双路搜索 |
| `app/api/mobile/v1/knowledge.py` | 修改 | 新增 flashcards 端点 |
| `app/api/mobile/v1/favorites.py` | 新增 | 收藏 CRUD |
| `app/api/mobile/v1/review.py` | 新增 | 复习队列 + 进度 |
| `app/api/mobile/v1/history.py` | 新增 | 浏览历史 |
| `app/api/mobile/v1/__init__.py` | 修改 | 注册 favorites/review/history 路由 |
| `app/api/mobile/v1/schemas/` | 修改 | 新增 flashcard/favorite/review/history schemas |
| `app/api/v1/knowledge_points.py` | 新增 | 管理后台 KP CRUD + generate |
| `app/api/v1/schemas/knowledge_point.py` | 新增 | 管理后台 KP schemas |
| `app/api/v1/__init__.py` | 修改 | 注册 knowledge_points 路由 |
| `tests/test_batch2_smoke.py` | 新增 | 路由注册 smoke tests |
