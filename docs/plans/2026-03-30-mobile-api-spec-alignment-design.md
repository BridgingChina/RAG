# Mobile API Spec Alignment Design

> 2026-03-30 | 修复 `docs/api-spec.md` 与实现之间的阻塞级差异，确保移动端开发可按 spec 编码。

## Background

API spec v1.1 定义了移动端 API 契约，但当前实现在响应结构、错误格式、字段命名等方面与 spec 存在 10 处阻塞级差异。移动端即将开发，需先对齐。

**决策：** 实现对齐 spec（spec 为准），仅 `X-Device-Id` 适用范围改 spec 对齐实现。

## Changes

### 1. Global Mobile Error Handler

新增 `app/api/mobile/v1/error_handlers.py`，在 `app/main.py` 中注册。

- 拦截 `HTTPException`，仅当 `request.url.path` 以 `/api/mobile/` 开头时转换格式
- 转换为 `{"error": {"code": "NOT_FOUND", "message": "..."}}`
- HTTP status → code 映射: `{400: "BAD_REQUEST", 404: "NOT_FOUND", 409: "CONFLICT", 422: "UNPROCESSABLE", 429: "RATE_LIMITED", 500: "INTERNAL_ERROR"}`
- 非 mobile 路由保持 FastAPI 默认行为

### 2. List Endpoint Response Wrapping

所有列表端点的 `data` 内使用命名 key 包裹数组：

| Endpoint | Current `data` | Target `data` |
|----------|---------------|---------------|
| `GET /bridges` | `[...]` | `{"bridges": [...]}` |
| `GET /search` | `[...]` | `{"results": [...], "suggestions": []}` |
| `GET /favorites` | `[...]` | `{"items": [...]}` |
| `GET /history` | `[...]` | `{"items": [...]}` |
| `GET /review/today` | `[...]` | `{"cards": [...], "total_due": N}` |
| `GET /review/cards` | `[...]` | `{"cards": [...]}` |

`total_due` = len(cards)（today 端点不分页，返回全量）。

### 3. Flashcard Field Name Alignment

三处返回闪卡数据的代码统一字段名：

| Location | Field | Current | Target |
|----------|-------|---------|--------|
| `review.py` `_format_card()` | 卡片 ID | `flashcard_id` | `id` |
| `review.py` `_format_card()` | 桥梁示例 | `example_bridge_id: str` | `example_bridge: {id, name}` |
| `knowledge.py` flashcards | 桥梁示例 | `example_bridge: {id, name: null}` | resolve name from Bridge |
| `review.py` progress | 时间字段 | `last_reviewed_at` | `reviewed_at` |

`example_bridge.name` 通过批量预查 Bridge 表获取。`_format_card()` 增加 `bridge_name_map` 参数。

### 4. Favorites Missing Fields

`GET /favorites` 每条记录补充 `target_summary` 和 `thumbnail`：

| target_type | target_summary | thumbnail |
|-------------|---------------|-----------|
| bridge | `"{region}，{era}{bridge_type}"` | `bridge_images` 表 order_index=0 |
| knowledge_point | `kp.summary` 截断 50 字 | `null` |
| flashcard | `fc.front_title` | `null` |

扩展现有 batch resolve 逻辑。

### 5. Clusters Representative Structure

`GET /bridges/clusters` 的 cluster 项：

- Current: `{"representative_ids": ["uuid1", ...]}`
- Target: `{"representative": {"id": "uuid1", "name": "桥名"}}`

取第一个 ID 作为代表，批量查 name。

### 6. Spec Correction

`docs/api-spec.md` §0.2: `X-Device-Id` 从"所有请求必选"改为"仅 favorites/review/history 端点必选"。

## Files Affected

- **New:** `app/api/mobile/v1/error_handlers.py`
- **Modified:** `app/main.py`, `bridges.py`, `search.py`, `favorites.py`, `history.py`, `review.py`, `knowledge.py`
- **Modified:** `docs/api-spec.md` (§0.2 only)

## Not In Scope

- Database schema changes
- Admin API (`/api/v1/*`)
- Frontend code
- `POST /recognition` (unimplemented, deferred)
- Non-blocking differences (ETag, SSE heartbeat, sort=distance, etc.)
