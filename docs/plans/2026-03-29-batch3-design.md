# Batch 3 Design — Content Enrichment + API Completion

> 基于 rag-roadmap.md §5.1 第三批 + api-spec.md gap analysis
> 日期：2026-03-29

## 决策汇总

| # | 决策 | 选择 |
|---|------|------|
| 1 | knowledge_point_bridges 数据来源 | 自动推导（chunk 标签）+ 人工校对 |
| 2 | Bridge Images 存储 | R2 presigned upload（复用 ingest 模式） |
| 3 | Flash Cards 生成 | 批量 LLM 生成 + 单点编辑补充 |
| 4 | 坐标补全 | 高德 API 批量为主 + 管理后台地图选点为辅 + CSV 导入兜底 |

---

## §1 数据模型

### 1.1 `bridge_images` 表

```sql
CREATE TABLE bridge_images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bridge_id       UUID NOT NULL REFERENCES bridges(id) ON DELETE CASCADE,
    r2_key          VARCHAR(500) NOT NULL,
    caption         TEXT,
    type            VARCHAR(20),          -- photo / illustration / map
    order_index     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_bridge_images_bridge_id ON bridge_images(bridge_id);
```

- 不存完整 URL，存 R2 object key（如 `bridges/images/{bridge_id}/{uuid}.jpg`）
- 读取时由 API 拼接完整 URL（presigned GET 或公开 bucket URL）
- CASCADE：桥梁删除时图片记录一起删

### 1.2 `knowledge_point_bridges` 关联表

```sql
CREATE TABLE knowledge_point_bridges (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_point_id  UUID NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
    bridge_id           UUID NOT NULL REFERENCES bridges(id) ON DELETE CASCADE,
    relevance_note      TEXT,
    order_index         INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(knowledge_point_id, bridge_id)
);
```

### 1.3 `bridges` 表新增字段

```sql
ALTER TABLE bridges ADD COLUMN IF NOT EXISTS geocode_source VARCHAR(20);
-- 值: amap / manual / csv / null
```

### 1.4 Schema 迁移 v3 → v4

`migrate_db.py` 新增 `MIGRATIONS[4] = migrate_v3_to_v4`，创建上述表和字段。

---

## §2 API 端点

### 2.1 管理后台新增

**Bridge Images：**
```
POST   /api/v1/bridges/{id}/images/presign    -- presigned upload URL
POST   /api/v1/bridges/{id}/images             -- confirm 写 DB
PUT    /api/v1/bridges/{id}/images/reorder      -- 批量 order_index
DELETE /api/v1/bridges/{id}/images/{image_id}   -- 删除 DB + R2
```

**Knowledge Point Bridges：**
```
POST   /api/v1/knowledge-points/{id}/sync-bridges   -- 从 chunk 标签自动推导
GET    /api/v1/knowledge-points/{id}/bridges         -- 列出关联
PUT    /api/v1/knowledge-points/{id}/bridges         -- 全量替换
```

**Flash Cards 批量生成：**
```
POST   /api/v1/flashcards/batch-generate              -- 异步批量生成
GET    /api/v1/flashcards/batch-generate/{task_id}     -- 查询进度
```

**坐标批量补全：**
```
POST   /api/v1/bridges/batch-geocode                   -- 异步批量地理编码
GET    /api/v1/bridges/batch-geocode/{task_id}          -- 查询进度
POST   /api/v1/bridges/import-coordinates               -- CSV 导入
```

### 2.2 移动端端点补全（增强现有端点）

| 端点 | 补全内容 |
|------|---------|
| `GET /bridges/{id}` | 填充 tags、images、related_knowledge_points |
| `GET /bridges/{id}/knowledge-points` | 从 knowledge_point_bridges 查询 |
| `GET /bridges` | 新增 sort=distance，填充 distance 字段 |
| `GET /knowledge/points/{id}` | 填充 typical_bridges_count、tags |
| `POST /qa/ask` | 15s ping heartbeat + 60s timeout |

### 2.3 tags 填充逻辑

- **Bridge tags**：`[bridge_type, material, era]` 去 NULL 组合
- **Knowledge point tags**：`[lvl1_name, difficulty]`

---

## §3 服务层

### 3.1 BridgeImageService

```python
class BridgeImageService:
    def presign_upload(bridge_id, filename, content_type) -> str
    def confirm_upload(db, bridge_id, r2_key, caption, type, order_index) -> BridgeImage
    def reorder(db, bridge_id, image_ids: list[UUID]) -> None
    def delete(db, image_id) -> None       # DB + R2
    def get_public_url(r2_key) -> str      # 拼接访问 URL
```

R2 路径：`bridges/images/{bridge_id}/{uuid}.{ext}`

### 3.2 KnowledgePointBridgeService

```python
class KnowledgePointBridgeService:
    def sync_from_chunks(db, knowledge_point_id, provider) -> list[KPBridge]:
        # 1. chunks WHERE lvl3 匹配 → chunk_bridge_links JOIN bridges
        # 2. 去重，LLM 生成 relevance_note
        # 3. 写入 knowledge_point_bridges

    def list_bridges(db, knowledge_point_id) -> list[KPBridge]
    def replace_all(db, knowledge_point_id, items) -> None
```

### 3.3 FlashcardBatchGenerator

```python
class FlashcardBatchGenerator:
    async def batch_generate(db, knowledge_point_ids, provider):
        # 逐知识点：获取 key_points + chunks → LLM → 写 flashcards
        # concept 卡 2-3 张 + identification 卡 1-2 张
```

Prompt 策略：
- concept 卡：从 key_point.summary → "什么是 X？"
- identification 卡：从 bridge 关联 → "哪座桥体现了 X？"

### 3.4 GeocodeService

```python
class GeocodeService:
    async def batch_geocode(db, bridge_ids):
        # 逐个调高德 API：name + region → lat/lng
        # confidence > 0.7 才写入，记录 geocode_source="amap"

    async def _amap_geocode(address) -> GeocodeResult | None:
        # GET https://restapi.amap.com/v3/geocode/geo?key=KEY&address=...
```

### 3.5 异步任务模式

复用 FastAPI BackgroundTasks + 独立 SessionLocal()（与 ingest pipeline 一致）：
1. 请求创建任务记录（status=pending）→ 返回 task_id
2. BackgroundTask 逐条处理，更新 progress
3. 前端轮询 task_id 查看进度

不引入 Celery/Redis。

---

## §4 管理后台前端

### 4.1 Bridge 编辑页增强

- **图片管理区域**：网格展示 + 拖拽排序 + presign 上传 + caption/type 编辑
- **地图坐标选点**：lat/lng 输入框旁"地图选点"按钮 → modal 内嵌地图 → 点击填充坐标
- 显示 geocode_source 标签

### 4.2 Knowledge Point 编辑页增强

- **关联桥梁**："同步关联"按钮 + 手动增删 + relevance_note 编辑 + 拖拽排序
- **L2 内容编辑**：结构化表单（comparisons/evolution/controversies/further_reading），保存写 JSONB

### 4.3 批量操作

嵌入 Settings 页面新 tab：
- 批量地理编码（选范围 → 启动 → 进度条）
- 批量生成闪卡（选知识点 → 启动 → 进度条）
- 批量同步知识点关联（一键 → 进度条）
- CSV 导入坐标（上传 → 预览 → 确认）

共用 TaskProgress 组件（轮询 task status）。

### 4.4 不做的事

- 不新增独立页面
- 不做地图全屏编辑器
- L2 不做富文本，纯 textarea
- 图片不做裁剪/压缩

---

## §5 移动端端点增强

### 5.1 Bridge Detail 填充

```python
tags = [v for v in [bridge.bridge_type, bridge.era] if v]
images = [{url, caption, type} for img in bridge.images]
related_knowledge_points = [{id, name, relevance} from knowledge_point_bridges]
```

### 5.2 Distance 排序

```python
# 平面近似 Haversine（中国范围短距离足够）
distance_expr = func.sqrt(
    func.pow((Bridge.latitude - near_lat) * 111000, 2) +
    func.pow((Bridge.longitude - near_lng) * 111000 * func.cos(func.radians(near_lat)), 2)
)
# sort=distance 时 order_by(distance_expr.asc())
# 填充 response.distance 字段（米）
```

### 5.3 Knowledge Point 填充

```python
typical_bridges_count = count(knowledge_point_bridges WHERE kp_id=...)
tags = [taxonomy_lvl1_name, difficulty]
```

### 5.4 QA SSE Heartbeat + Timeout

```python
# 每 15s 发 ping 事件
# 总时间超 60s 发 error(TIMEOUT) 并关闭
```

---

## §6 环境变量

```
AMAP_API_KEY=xxx    # 高德地理编码 API key（加入 1Password）
```

---

## §7 范围排除

以下不在 Batch 3 范围内：
- 识景服务（POST /recognition）— 依赖图片数据积累，Batch 4
- search suggestions — 无搜索日志数据源
- QA fallback_actions — 客户端 hardcode
- related_terms — 需大量标注
- Rate limiting — 独立安全迭代
