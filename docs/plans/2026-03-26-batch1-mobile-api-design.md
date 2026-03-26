# Batch 1 — 移动端 API 骨架 + 知识点模型 + SSE 问答

> 基于 `rag-roadmap.md` 第一批（#6~#11）+ `api-spec.md` v1.1
> 日期：2026-03-26

---

## 0. 决策总结

| 决策 | 选项 | 理由 |
|------|------|------|
| 范围 | Batch 1 全量（#6~#11） | 一次做完，客户端可立即联调 |
| SSE 方式 | 伪流式（单次 LLM 调用 + 拆分） | MVP 优先，真流式标 TODO |
| 知识点数据 | Seed 脚本造测试数据 | 联调用，内容生产在 Batch 2 |
| 桥梁详情 sections | 返回空骨架 | 覆盖率审计在 Batch 2 #17，先不做聚合 |
| 目录结构 | 方案 B（v1/ 嵌套 + schemas/ 子目录） | 严格版本化，为后续扩展预留 |

---

## 1. 数据模型

### 1.1 `knowledge_points` 表

```python
# app/models/knowledge_point.py
class KnowledgePoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_points"

    taxonomy_node_id  UUID FK → taxonomy_nodes.id   # 所属 lvl3 分类节点
    name              VARCHAR(200) NOT NULL
    aliases           TEXT nullable                   # 逗号分隔
    difficulty        VARCHAR(20) nullable            # beginner/intermediate/advanced
    summary           TEXT nullable                   # L0 一句话摘要
    l2_content        JSONB nullable                  # L2 深挖（Batch 2+ 填充）
```

### 1.2 `knowledge_point_key_points` 表

```python
# app/models/knowledge_point_key_point.py
class KnowledgePointKeyPoint(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "knowledge_point_key_points"

    knowledge_point_id  UUID FK → knowledge_points.id (ON DELETE CASCADE)
    summary             TEXT NOT NULL                  # 要点摘要（L0）
    explanation         TEXT nullable                  # L1 展开
    order_index         INTEGER NOT NULL
    chunk_ids           UUID[] nullable                # 关联 chunk IDs（citations）
    illustration_urls   TEXT[] nullable
    related_term_ids    UUID[] nullable                # 关联知识点 IDs
```

**设计决策：**
- key_points 用 `CreatedAtMixin`（无 `updated_at`）— 批量生成/替换，不逐条更新
- `chunk_ids` 用数组列而非关联表 — 引用指针，查询模式单一
- `l2_content` 用 JSONB — 结构灵活，Batch 1 不填充
- Schema version: 1 → 2

---

## 2. 移动端 API 路由骨架

### 2.1 目录结构

```
app/api/mobile/
├── __init__.py              # mobile_router
├── v1/
│   ├── __init__.py          # v1_router, 聚合所有端点
│   ├── dependencies.py      # require_device_id
│   ├── config.py            # GET /config
│   ├── knowledge.py         # GET /knowledge/tree, /knowledge/points/{id}
│   ├── bridges.py           # GET /bridges, /bridges/{id}, /bridges/{id}/knowledge-points
│   ├── qa.py                # POST /qa/ask (SSE)
│   ├── search.py            # GET /search (占位)
│   └── schemas/
│       ├── __init__.py
│       ├── common.py        # MobileResponse, MobilePaginatedResponse
│       ├── config.py        # ConfigResponse
│       ├── knowledge.py     # KnowledgeTreeNode, KnowledgePointDetail, KeyPointSchema
│       ├── bridge.py        # MobileBridgeListItem, MobileBridgeDetail
│       ├── qa.py            # QARequest, QAContext
│       └── search.py        # SearchResult (占位)
```

### 2.2 路由注册

```python
# app/main.py 新增
from app.api.mobile import router as mobile_router
app.include_router(mobile_router, prefix="/api/mobile/v1")
```

URL 形如：`GET /api/mobile/v1/bridges`、`POST /api/mobile/v1/qa/ask`

### 2.3 依赖注入

```python
# dependencies.py
def require_device_id(x_device_id: str = Header(...)) -> str:
    uuid.UUID(x_device_id, version=4)  # 校验格式
    return x_device_id
```

Batch 1 中 QA 端点可选使用，收藏/复习在 Batch 2 才强制。

### 2.4 响应格式

```python
# schemas/common.py
class MobileResponse(BaseModel, Generic[T]):
    data: T

class MobileMeta(BaseModel):
    total: int
    page: int
    page_size: int
    has_more: bool

class MobilePaginatedResponse(BaseModel, Generic[T]):
    data: T
    meta: MobileMeta
```

### 2.5 CORS

Batch 1 不改动 CORS 配置 — 移动端原生 app 不受 CORS 限制。

> **TODO:** 生产部署时如有 H5/WebView 场景，需在 `main.py` CORS 中间件添加移动端域名。

---

## 3. 桥梁移动端端点（#8）

### 3.1 `GET /bridges` — 桥梁列表

参数：`bridge_type`, `era`, `region`, `keyword`, `near_lat`, `near_lng`, `near_radius`, `sort`, `page`, `page_size`

**Batch 1 实现：**
- `bridge_type` / `era`：逗号拆分 → `IN` 查询
- `region`：`ILIKE`
- `keyword`：`name ILIKE OR aliases ILIKE`
- `near_lat/lng`：矩形范围过滤（`WHERE lat BETWEEN ... AND ...`）
- `sort`：仅支持 `"name"`

> **TODO (Batch 2):** `sort=distance` 距离排序

### 3.2 `GET /bridges/{id}` — 桥梁详情

返回基础字段 + 空骨架：
- `sections`: 四章节空结构 `{ "structure": {"l0":[],"l1":[]}, ... }`
- `images`: 空数组
- `related_knowledge_points`: 空数组
- `sources_count`: 从 chunks 聚合 `COUNT(DISTINCT source_id)`

> **TODO (Batch 2 #17):** sections 四章节聚合（需先做覆盖率审计）
> **TODO (Batch 2):** images、related_knowledge_points 填充

### 3.3 `GET /bridges/{id}/knowledge-points`

Batch 1 返回空列表。

> **TODO (P2):** `knowledge_point_bridges` 关联表建好后实现

---

## 4. 知识架构树端点（#9）

### 4.1 `GET /knowledge/tree`

参数：`depth`（1=仅lvl1, 2=含lvl2, None=全部）

**查询策略：**
1. 一次查所有 `taxonomy_nodes`（ORDER BY level, name）
2. 一次查所有 `knowledge_points`（id, taxonomy_node_id, name, aliases, difficulty, summary）
3. Python 内存组装树，`depth` 截断

**节点格式：**
- taxonomy_node：有 `children`，无 `type`
- knowledge_point 叶子：有 `type: "knowledge_point"`、`summary`、`tags`（Batch 1 空数组），无 `children`

### 4.2 `GET /knowledge/points/{id}`

参数：`level`（"L0" / "L1" / "L2" / "all"，默认 "all"）

**查询：**
1. `knowledge_points` 主记录
2. `knowledge_point_key_points` 子记录（ORDER BY order_index）
3. 反查 taxonomy_node 得 line（lvl1）和 category（lvl2）
4. 按 `level` 裁剪：L0=summary列表, L1=+explanation+citations, L2=l2_content, all=全部

**citations → sources 聚合：**
key_point.chunk_ids → chunks.source_id → sources.title/author → 去重返回

### 4.3 `GET /knowledge/points/{id}/bridges`

Batch 1 返回空列表，同 3.3。

---

## 5. SSE 流式问答（#10）+ TaxonomyFilter（#11）

### 5.1 TaxonomyFilter

```python
# app/services/hybrid_retriever.py 新增
@dataclass
class TaxonomyFilter:
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
```

### 5.2 HybridRetriever 改造

`retrieve()` 新增 `taxonomy_filter: Optional[TaxonomyFilter] = None` 参数。

注入点：`_retrieve_channel()` → `_vector_search()` / `_fts_search()` 的 WHERE 子句：
```sql
AND chunks.lvl1 = :filter_lvl1   -- 仅非 None 的字段
AND chunks.lvl2 = :filter_lvl2
```

**通道行为：**
- 有 `taxonomy_filter` 时 → Anchor 通道按 taxonomy 过滤（替代 bridge_id）
- Concept / Analogy 通道不变
- 与 `bridge_filter` 正交

### 5.3 Generator.generate_streaming()

```python
async def generate_streaming(
    self, question: str, evidence: HybridRetrievalResult,
) -> list[tuple[str, dict]]:
```

1. 构造 prompt → 要求输出 `{"key_points": [...], "deep_dive": null}`
2. 单次 `self.provider.chat()` 调用
3. 解析 JSON → 拆分为事件列表：
   - `("outline", {"key_points": [{"id": uuid, "summary": ..., "order": i}]})`
   - 每个 key_point → `("detail", {"key_point_id": ..., "explanation": ..., "citations": [...]})`
   - `("sources", {"sources": [...]})`

返回 `list` 而非 async generator — 伪流式下数据已在内存，list 更简单可测试。

> **TODO:** 升级真流式时改为 async generator + LLM streaming

### 5.4 SSE 端点 `POST /qa/ask`

```python
@router.post("/ask")
async def ask_sse(request: QARequest, db: Session = Depends(get_db)):
    async def event_stream():
        qa_id = str(uuid.uuid4())
        yield sse_event("started", {"qa_id": qa_id})
        # 1. context → target_bridge_id 或 taxonomy_filter
        # 2. _resolve_bridge_from_question（复用）
        # 3. HybridRetriever.retrieve()
        # 4. Generator.generate_streaming()
        # 5. 遍历事件 list 逐个 yield
        yield sse_event("done", {"qa_id": qa_id})
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**辅助：**
```python
def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

**错误处理：**
- LLM 失败 / JSON 解析失败 → `event: error`
- 证据不足 → `event: error` + `INSUFFICIENT_EVIDENCE`

> **TODO:** SSE 心跳 15s ping + 60s 总超时（真流式时实现）

---

## 6. Schema 迁移 + Seed

### 6.1 Schema v1 → v2

`scripts/migrate_db.py` 新增 `migrate_v1_to_v2()`：
- CREATE TABLE `knowledge_points`（含索引 `ix_kp_taxonomy`）
- CREATE TABLE `knowledge_point_key_points`（含索引 `ix_kpkp_kp`，ON DELETE CASCADE）
- `LATEST_SCHEMA_VERSION = 2`

线上通过 `docker-entrypoint.sh` → `migrate_db.py` 自动执行。

### 6.2 Seed 脚本

`scripts/seed_knowledge_points.py`：
- 从 taxonomy_nodes lvl3 选 3~5 个节点
- 每个创建 1 条 knowledge_point + 2~3 条 key_points
- chunk_ids 从现有 chunks 按 lvl3 匹配取样
- 目的：联调用，结构完整即可

### 6.3 models/__init__.py

新增注册：
```python
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint
```

---

## 7. TODO 清单

| TODO | 目标批次 | 位置 |
|------|----------|------|
| 桥梁详情 sections 四章节聚合 | Batch 2 #17 | `bridges.py` |
| 桥梁详情 images | Batch 2 | `bridges.py` |
| 桥梁详情 related_knowledge_points | Batch 2 | `bridges.py` |
| 知识点典型桥梁 | Batch 2 | `knowledge.py` |
| SSE 真流式（LLM streaming） | 后续 | `generator.py` |
| SSE 心跳 15s ping + 60s 超时 | 后续 | `qa.py` |
| 桥梁列表距离排序 sort=distance | Batch 2 | `bridges.py` |
| CORS 移动端配置 | 生产部署时 | `main.py` |
| 统一搜索实现 | Batch 2 #14 | `search.py` |

---

## 8. 涉及文件总览

**新增：**
- `app/models/knowledge_point.py`
- `app/models/knowledge_point_key_point.py`
- `app/api/mobile/__init__.py`
- `app/api/mobile/v1/__init__.py`
- `app/api/mobile/v1/dependencies.py`
- `app/api/mobile/v1/config.py`
- `app/api/mobile/v1/knowledge.py`
- `app/api/mobile/v1/bridges.py`
- `app/api/mobile/v1/qa.py`
- `app/api/mobile/v1/search.py`
- `app/api/mobile/v1/schemas/__init__.py`
- `app/api/mobile/v1/schemas/common.py`
- `app/api/mobile/v1/schemas/config.py`
- `app/api/mobile/v1/schemas/knowledge.py`
- `app/api/mobile/v1/schemas/bridge.py`
- `app/api/mobile/v1/schemas/qa.py`
- `app/api/mobile/v1/schemas/search.py`
- `scripts/seed_knowledge_points.py`

**修改：**
- `app/models/__init__.py` — 注册新 model
- `app/main.py` — 注册 mobile router
- `app/core/database.py` — `LATEST_SCHEMA_VERSION = 2`
- `scripts/migrate_db.py` — 新增 v1→v2 迁移
- `app/services/hybrid_retriever.py` — 新增 `TaxonomyFilter` + `taxonomy_filter` 参数
- `app/services/generator.py` — 新增 `generate_streaming()` 方法

**不改动：**
- `app/providers/zhipu.py`
- `app/services/tokenizer.py`
- `app/services/facet_extractor.py`
- `app/services/ranker.py`
- `app/api/v1/` 全部现有端点
