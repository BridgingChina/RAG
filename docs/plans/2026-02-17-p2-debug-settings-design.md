# P2 — Q&A Debug Mode & System Settings Design

**Date:** 2026-02-17
**Status:** Approved

---

## Context

Admin dashboard P0 (Chunks/Bridges/Dashboard) and P1 (Sources/Taxonomy/Bridge Merge/Recharts) are complete. P2 completes the final two modules: **Q&A Debug Mode** and **System Settings**.

**Goals:**
1. Let operators see retrieval internals (facets, per-channel recall, scores, timings) when testing questions
2. Provide a read-only system status / config overview page

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Debug trigger | Frontend switch (`debug=true` request param) | Single endpoint, zero overhead when off |
| Debug data source | Service layer returns `DebugInfo` (Approach A) | Only way to get vector/FTS per-channel scores |
| LLM prompt in debug | Not included | Keep scope lean; can add later |
| Debug UI layout | Collapsible sections below answer | Non-intrusive, progressive disclosure |
| Settings scope | Read-only status + config display | No runtime param adjustment (YAGNI) |
| Settings data source | New `GET /api/v1/system/status` endpoint | Single query, no side effects |

---

## §1 Backend — Debug Data Model

### New dataclasses in `hybrid_retriever.py`

```python
@dataclass
class ChannelDebug:
    """Debug info for a single retrieval channel."""
    channel: str                         # "anchor" | "concept" | "analogy"
    filter_desc: str                     # e.g. "bridge_id=42" or "bridge_id IS NULL"
    vec_ids: list[int]                   # vector search raw results
    fts_ids: list[int]                   # FTS raw results
    rrf_scores: list[tuple[int, float]]  # after RRF merge
    final_ids: list[int]                 # after diversity + limit

@dataclass
class RetrievalDebug:
    """Full debug info for a retrieval request."""
    facet: dict | None
    channels: list[ChannelDebug]
    timings: dict[str, float]  # stage -> seconds
```

### Changes to `HybridRetriever`

- `retrieve(... debug=False)` — when `True`, collects `ChannelDebug` per channel
- `_retrieve_channel()` returns `(list[RetrievedChunk], ChannelDebug | None)` tuple
- Timings recorded with `time.perf_counter()` around embed / each channel
- `HybridRetrievalResult` gets optional `debug: RetrievalDebug | None` field

### Changes to `ask.py`

- `AskRequest` gets optional `debug: bool = False`
- When `debug=True`, pass through to retriever, also time `facet_extract` and `generate` stages
- Merge retriever timings + ask-level timings into final `timings` dict
- `AskResponse` gets optional `debug: DebugResponse | None` field

### New schemas in `schemas/ask.py`

```python
class ChannelDebugResponse(BaseModel):
    channel: str
    filter_desc: str
    vec_ids: list[int]
    fts_ids: list[int]
    rrf_scores: list[list]  # [[chunk_id, score], ...]
    final_ids: list[int]

class DebugResponse(BaseModel):
    facet: dict | None
    channels: list[ChannelDebugResponse]
    timings: dict[str, float]
```

---

## §2 Backend — System Status Endpoint

### New file: `app/api/v1/system.py`

```
GET /api/v1/system/status → SystemStatus
```

### Schema: `schemas/system.py`

```python
class SystemStatus(BaseModel):
    version: str              # "1.0.0"
    python_version: str

    db_connected: bool
    db_version: str | None
    schema_version: int | None

    vector_dimension: int     # 1024
    index_type: str           # "ivfflat"

    llm_provider: str         # "zhipu"
    embedding_model: str      # "embedding-3"
    chat_model: str           # "glm-4"
    chunk_quota: dict         # {"anchor": 6, "concept": 2, "analogy": 2}
    rrf_k: int                # 60

    api_key_configured: bool
```

Implementation: reads `settings`, `SELECT version()`, `schema_version` table. Pure query, no side effects.

### Route registration

- `app/api/v1/system.py` with `router = APIRouter(prefix="/system")`
- Register in `app/api/v1/__init__.py`

---

## §3 Frontend — AskPage Debug Panel

### Trigger

- `AskPanel` adds a `Switch` component ("调试模式") in the filter area
- When on, request body includes `debug: true`
- `askQuestion()` API function gets optional `debug` param

### Layout (below AnswerDisplay)

```
┌─ 调试信息 ────────────── [全部展开/全部折叠] ──┐
│  ▸ 耗时统计     (horizontal bar/badges)        │
│  ▸ Facet 抽取   (key-value pairs)              │
│  ▸ Anchor 通道  (filter + 4-col table)         │
│  ▸ Concept 通道 (filter + 4-col table)         │
│  ▸ Analogy 通道 (filter + candidates + table)  │
└────────────────────────────────────────────────┘
```

Each channel section shows:
- Filter description (e.g. `bridge_id = 42`)
- 4-column table: vector results | FTS results | RRF merged | final selection

### New components

| Component | Purpose |
|-----------|---------|
| `DebugPanel.tsx` | Container, expand/collapse all |
| `DebugTimings.tsx` | Timing badges |
| `DebugFacet.tsx` | Facet key-value display |
| `DebugChannel.tsx` | Reusable per-channel detail (used 3x) |

### New shadcn components needed

- `Collapsible` (if not already installed)
- `Switch` (if not already installed)

### Types (`types.ts`)

```typescript
interface ChannelDebug {
  channel: string
  filter_desc: string
  vec_ids: number[]
  fts_ids: number[]
  rrf_scores: [number, number][]
  final_ids: number[]
}

interface DebugInfo {
  facet: Record<string, unknown> | null
  channels: ChannelDebug[]
  timings: Record<string, number>
}

// Extend AskResponse
interface AskResponse {
  // ... existing fields
  debug?: DebugInfo | null
}
```

---

## §4 Frontend — Settings Page

### Route

`/settings` → `SettingsPage.tsx` (lazy loaded with `export function Component()`)

### Layout

Two Card sections:

**Card 1 — 系统状态:**
- 数据库连接 (green/red dot + PostgreSQL version)
- Schema 版本
- API 密钥状态 (green/red dot)
- 应用版本 + Python 版本

**Card 2 — 检索配置:**
- LLM 供应商 / 嵌入模型 / 对话模型
- 向量维度 / 索引类型
- RRF k 值 / 通道配额

### Sidebar

Add "系统" group to `navGroups` in `AppSidebar.tsx`:

```typescript
{
  label: "系统",
  items: [
    { path: "/settings", icon: Settings, label: "设置" },
  ],
}
```

### API

```typescript
export function fetchSystemStatus(): Promise<SystemStatus> {
  return get<SystemStatus>("/system/status")
}
```

---

## File Inventory

### New files (~10)

| Category | Files |
|----------|-------|
| Backend endpoint | `app/api/v1/system.py` |
| Backend schema | `app/api/v1/schemas/system.py` |
| Frontend page | `web/src/pages/SettingsPage.tsx` |
| Frontend components | `web/src/components/ask/DebugPanel.tsx` |
| | `web/src/components/ask/DebugTimings.tsx` |
| | `web/src/components/ask/DebugFacet.tsx` |
| | `web/src/components/ask/DebugChannel.tsx` |
| shadcn (maybe) | `Collapsible`, `Switch` |

### Modified files (~10)

| File | Change |
|------|--------|
| `app/services/hybrid_retriever.py` | Add debug dataclasses, `_retrieve_channel` returns debug tuple |
| `app/api/v1/ask.py` | Pass debug flag, collect timings, serialize debug |
| `app/api/v1/schemas/ask.py` | Add `DebugResponse`, extend `AskRequest`/`AskResponse` |
| `app/api/v1/schemas/__init__.py` | Re-export new schemas |
| `app/api/v1/__init__.py` | Register system router |
| `web/src/lib/api.ts` | Add `fetchSystemStatus`, update `askQuestion` |
| `web/src/lib/types.ts` | Add `SystemStatus`, `DebugInfo`, `ChannelDebug` types |
| `web/src/components/ask/AskPanel.tsx` | Add debug switch + DebugPanel |
| `web/src/components/layout/AppSidebar.tsx` | Add "系统" nav group |
| `web/src/app-routes.tsx` (or router config) | Add `/settings` route |

### Tests

- `tests/test_system_status.py` — smoke test for system status route
- `tests/test_ask_debug.py` — smoke test for ask with debug=true
