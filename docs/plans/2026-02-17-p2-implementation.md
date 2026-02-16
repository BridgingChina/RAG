# P2 — Q&A Debug Mode & System Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Q&A debug mode (showing retrieval internals) and a system settings page to complete the admin dashboard.

**Architecture:** Extend the existing ask endpoint with an optional `debug` flag that causes `HybridRetriever` to collect per-channel intermediate results (vector/FTS IDs, RRF scores, filters) and timings. Add a new `/system/status` read-only endpoint. Frontend gets a debug toggle on AskPage and a new SettingsPage.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/shadcn (frontend), existing patterns from P0/P1.

---

### Task 1: Backend — Debug dataclasses in hybrid_retriever.py

**Files:**
- Modify: `app/services/hybrid_retriever.py`
- Test: `tests/test_hybrid_retriever.py`

**Step 1: Write the failing test**

Add to `tests/test_hybrid_retriever.py`:

```python
from app.services.hybrid_retriever import ChannelDebug, RetrievalDebug


def test_channel_debug_dataclass():
    """ChannelDebug holds per-channel retrieval debug info."""
    cd = ChannelDebug(
        channel="anchor",
        filter_desc="bridge_id=42",
        vec_ids=[1, 2, 3],
        fts_ids=[2, 4],
        rrf_scores=[(2, 0.03), (1, 0.02), (3, 0.01), (4, 0.005)],
        final_ids=[2, 1, 3],
    )
    assert cd.channel == "anchor"
    assert len(cd.vec_ids) == 3
    assert len(cd.rrf_scores) == 4


def test_retrieval_debug_dataclass():
    """RetrievalDebug aggregates channels and timings."""
    rd = RetrievalDebug(
        facet={"bridge_type": "拱桥"},
        channels=[],
        timings={"embed": 0.12, "anchor": 0.08},
    )
    assert rd.facet["bridge_type"] == "拱桥"
    assert rd.timings["embed"] == 0.12
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_retriever.py::test_channel_debug_dataclass tests/test_hybrid_retriever.py::test_retrieval_debug_dataclass -v`
Expected: FAIL with `ImportError: cannot import name 'ChannelDebug'`

**Step 3: Write minimal implementation**

Add to `app/services/hybrid_retriever.py` after the existing `RetrievedChunk` dataclass:

```python
@dataclass
class ChannelDebug:
    """Debug info for a single retrieval channel."""
    channel: str                         # "anchor" | "concept" | "analogy"
    filter_desc: str                     # e.g. "bridge_id=42"
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

Also add `debug: RetrievalDebug | None = None` field to `HybridRetrievalResult`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_retriever.py::test_channel_debug_dataclass tests/test_hybrid_retriever.py::test_retrieval_debug_dataclass -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/hybrid_retriever.py tests/test_hybrid_retriever.py
git commit -m "feat: add ChannelDebug and RetrievalDebug dataclasses"
```

---

### Task 2: Backend — Wire debug through _retrieve_channel and retrieve

**Files:**
- Modify: `app/services/hybrid_retriever.py`
- Test: `tests/test_hybrid_retriever.py`

**Step 1: Write the failing test**

Add to `tests/test_hybrid_retriever.py`:

```python
def test_retrieve_channel_returns_debug_tuple():
    """When debug=True, _retrieve_channel returns (chunks, ChannelDebug)."""
    from unittest.mock import MagicMock, patch
    from app.services.hybrid_retriever import HybridRetriever

    provider = MagicMock()
    retriever = HybridRetriever(provider=provider)

    # Mock internal methods to avoid DB
    retriever._vector_search = MagicMock(return_value=[10, 20])
    retriever._fts_search = MagicMock(return_value=[20, 30])
    retriever._fetch_chunk_details = MagicMock(return_value={
        10: {"content": "c10", "bridge_id": 1, "bridge_name": "B1"},
        20: {"content": "c20", "bridge_id": 1, "bridge_name": "B1"},
        30: {"content": "c30", "bridge_id": 1, "bridge_name": "B1"},
    })

    import asyncio
    chunks, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(),
        query="test",
        query_embedding=[0.1] * 1024,
        bridge_filter=1,
        limit=3,
        debug=True,
        channel_name="anchor",
    ))
    assert isinstance(debug, ChannelDebug)
    assert debug.channel == "anchor"
    assert debug.vec_ids == [10, 20]
    assert debug.fts_ids == [20, 30]
    assert len(debug.final_ids) <= 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_retriever.py::test_retrieve_channel_returns_debug_tuple -v`
Expected: FAIL — `_retrieve_channel` doesn't accept `debug`/`channel_name` params yet.

**Step 3: Implement the changes**

Modify `_retrieve_channel` signature to add `debug: bool = False, channel_name: str = ""`. When `debug=True`:
1. Capture `vec_results` and `fts_results` lists before they are consumed
2. Capture `merged` (RRF scores) list
3. Build `filter_desc` string from `bridge_filter` / `require_no_bridge_id`
4. Return `(chunks, ChannelDebug(...))` if debug else `(chunks, None)`

Modify `retrieve()` to:
1. Add `debug: bool = False` parameter
2. Pass debug + channel_name to each `_retrieve_channel` call
3. When debug, wrap `time.perf_counter()` around embed + each channel
4. Collect `ChannelDebug` objects and timings into `RetrievalDebug`
5. Set `result.debug = RetrievalDebug(...)` when debug

**Important:** When `debug=False` (default), behavior is exactly the same as before — `_retrieve_channel` returns `(chunks, None)`, no timing overhead.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_retriever.py -v`
Expected: ALL PASS (new test + existing tests unbroken)

**Step 5: Commit**

```bash
git add app/services/hybrid_retriever.py tests/test_hybrid_retriever.py
git commit -m "feat: wire debug info through retrieve channels"
```

---

### Task 3: Backend — Debug schemas for ask endpoint

**Files:**
- Modify: `app/api/v1/schemas/ask.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Test: `tests/test_schemas_v2.py`

**Step 1: Write the failing test**

Add to `tests/test_schemas_v2.py`:

```python
def test_debug_response_schema():
    """DebugResponse serializes correctly."""
    from app.api.v1.schemas.ask import ChannelDebugResponse, DebugResponse

    channel = ChannelDebugResponse(
        channel="anchor",
        filter_desc="bridge_id=1",
        vec_ids=[10, 20],
        fts_ids=[20, 30],
        rrf_scores=[[20, 0.033], [10, 0.016], [30, 0.016]],
        final_ids=[20, 10],
    )
    debug = DebugResponse(
        facet={"bridge_type": "拱桥"},
        channels=[channel],
        timings={"embed": 0.12, "anchor": 0.08},
    )
    data = debug.model_dump()
    assert data["channels"][0]["channel"] == "anchor"
    assert data["timings"]["embed"] == 0.12


def test_ask_request_accepts_debug_flag():
    """AskRequest accepts optional debug field."""
    from app.api.v1.schemas.ask import AskRequest

    req = AskRequest(question="test", debug=True)
    assert req.debug is True

    req_default = AskRequest(question="test")
    assert req_default.debug is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas_v2.py::test_debug_response_schema tests/test_schemas_v2.py::test_ask_request_accepts_debug_flag -v`
Expected: FAIL with `ImportError`

**Step 3: Write the schemas**

Add to `app/api/v1/schemas/ask.py`:

```python
class ChannelDebugResponse(BaseModel):
    """Debug info for a single retrieval channel."""
    channel: str
    filter_desc: str
    vec_ids: list[int]
    fts_ids: list[int]
    rrf_scores: list[list]  # [[chunk_id, score], ...]
    final_ids: list[int]


class DebugResponse(BaseModel):
    """Full debug info for a retrieval request."""
    facet: dict | None = None
    channels: list[ChannelDebugResponse] = []
    timings: dict[str, float] = {}
```

Add `debug: bool = False` to `AskRequest`.
Add `debug: DebugResponse | None = None` to `AskResponse`.

Update `app/api/v1/schemas/__init__.py` to re-export `ChannelDebugResponse` and `DebugResponse`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas_v2.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/v1/schemas/ask.py app/api/v1/schemas/__init__.py tests/test_schemas_v2.py
git commit -m "feat: add debug request/response schemas for ask endpoint"
```

---

### Task 4: Backend — Wire debug through ask.py endpoint

**Files:**
- Modify: `app/api/v1/ask.py`
- Test: `tests/test_api_v1_ask.py`

**Step 1: Write the failing test**

Add to `tests/test_api_v1_ask.py`:

```python
def test_ask_v1_accepts_debug_param(client):
    """Ask endpoint accepts debug field without error (422)."""
    response = client.post("/api/v1/ask", json={
        "question": "测试问题",
        "debug": True,
    })
    # Will fail with DB error (no DB in unit test), but NOT 422
    assert response.status_code != 422
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_ask.py::test_ask_v1_accepts_debug_param -v`
Expected: FAIL — likely 422 because `debug` is not in `AskRequest` yet (but we added it in Task 3, so this may already pass for the schema part. The real change is in the endpoint logic.)

**Step 3: Implement ask.py changes**

Modify `ask()` in `app/api/v1/ask.py`:

1. Import `DebugResponse`, `ChannelDebugResponse`, and `time`
2. In `_run()`, add `import time` and wrap each stage with `time.perf_counter()`:
   - `t0` before facet extraction, `t1` after → `timings["facet"]`
   - Pass `debug=request.debug` to `retriever.retrieve()`
   - `t2` after retrieval → `timings["retrieve"]` (total retrieval time)
   - `t3` after `generator.generate_v2()` → `timings["generate"]`
3. When `request.debug` and `evidence.debug` is not None:
   - Convert `evidence.debug.channels` to `ChannelDebugResponse` list
   - Merge `evidence.debug.timings` into the timings dict
   - Build `DebugResponse` and attach to `AskResponse`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_v1_ask.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/v1/ask.py tests/test_api_v1_ask.py
git commit -m "feat: wire debug flag through ask endpoint with timings"
```

---

### Task 5: Backend — System status schema + endpoint

**Files:**
- Create: `app/api/v1/schemas/system.py`
- Create: `app/api/v1/system.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_api_v1_system.py`

**Step 1: Write the failing test**

Create `tests/test_api_v1_system.py`:

```python
"""Tests for V1 System API endpoint."""
from app.main import app


def test_system_status_endpoint_exists():
    """Test that /api/v1/system/status is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/system/status" in route_paths


def test_system_status_response_not_404():
    """Test system status returns a response (may fail on DB, but not 404)."""
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/system/status")
    assert response.status_code != 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_system.py -v`
Expected: FAIL — route doesn't exist yet

**Step 3: Implement**

Create `app/api/v1/schemas/system.py`:

```python
"""System status schemas."""
from pydantic import BaseModel


class SystemStatus(BaseModel):
    """Read-only system status and configuration."""
    version: str
    python_version: str

    db_connected: bool
    db_version: str | None = None
    schema_version: int | None = None

    vector_dimension: int
    index_type: str

    llm_provider: str
    embedding_model: str
    chat_model: str
    chunk_quota: dict
    rrf_k: int

    api_key_configured: bool
```

Create `app/api/v1/system.py`:

```python
"""V1 System API endpoint."""
import platform
import sys

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.schemas.system import SystemStatus
from app.core.config import settings
from app.core.database import get_db
from app.services.hybrid_retriever import DEFAULT_QUOTA, RRF_K

router = APIRouter(prefix="/system")


@router.get("/status", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db)):
    """Return read-only system status and configuration."""
    # Database info
    db_connected = False
    db_version = None
    schema_version = None
    try:
        row = db.execute(text("SELECT version()")).scalar()
        db_version = row
        db_connected = True
        sv = db.execute(
            text("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")
        ).scalar()
        schema_version = sv
    except Exception:
        pass

    return SystemStatus(
        version="1.0.0",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        db_connected=db_connected,
        db_version=db_version,
        schema_version=schema_version,
        vector_dimension=1024,
        index_type="ivfflat",
        llm_provider="zhipu",
        embedding_model=settings.embedding_model,
        chat_model=settings.chat_model,
        chunk_quota={
            "anchor": DEFAULT_QUOTA[0],
            "concept": DEFAULT_QUOTA[1],
            "analogy": DEFAULT_QUOTA[2],
        },
        rrf_k=RRF_K,
        api_key_configured=bool(settings.zhipu_api_key),
    )
```

Register in `app/api/v1/__init__.py`:
```python
from app.api.v1.system import router as system_router
router.include_router(system_router)
```

Re-export `SystemStatus` in `app/api/v1/schemas/__init__.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_v1_system.py -v`
Expected: ALL PASS

**Step 5: Run all existing tests to verify no regressions**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add app/api/v1/schemas/system.py app/api/v1/system.py app/api/v1/schemas/__init__.py app/api/v1/__init__.py tests/test_api_v1_system.py
git commit -m "feat: add system status endpoint"
```

---

### Task 6: Frontend — Install shadcn Switch and Collapsible

**Files:**
- Create: `web/src/components/ui/switch.tsx` (generated by shadcn CLI)
- Create: `web/src/components/ui/collapsible.tsx` (generated by shadcn CLI)

**Step 1: Install components**

Run from `web/` directory:

```bash
cd web && npx shadcn@latest add switch collapsible -y
```

**Step 2: Verify files created**

Run: `ls web/src/components/ui/switch.tsx web/src/components/ui/collapsible.tsx`
Expected: Both files exist

**Step 3: Commit**

```bash
git add web/src/components/ui/switch.tsx web/src/components/ui/collapsible.tsx web/package.json web/package-lock.json
git commit -m "chore: install shadcn Switch and Collapsible components"
```

---

### Task 7: Frontend — Types for debug and system status

**Files:**
- Modify: `web/src/lib/types.ts`

**Step 1: Add new types**

Append to `web/src/lib/types.ts`:

```typescript
// --- Debug ---

export interface ChannelDebug {
  channel: string
  filter_desc: string
  vec_ids: number[]
  fts_ids: number[]
  rrf_scores: [number, number][]
  final_ids: number[]
}

export interface DebugInfo {
  facet: Record<string, unknown> | null
  channels: ChannelDebug[]
  timings: Record<string, number>
}

// --- System ---

export interface SystemStatus {
  version: string
  python_version: string
  db_connected: boolean
  db_version: string | null
  schema_version: number | null
  vector_dimension: number
  index_type: string
  llm_provider: string
  embedding_model: string
  chat_model: string
  chunk_quota: Record<string, number>
  rrf_k: number
  api_key_configured: boolean
}
```

Also add `debug?: DebugInfo | null` to the existing `AskResponse` interface.

**Step 2: Verify types compile**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 3: Commit**

```bash
git add web/src/lib/types.ts
git commit -m "feat: add DebugInfo and SystemStatus frontend types"
```

---

### Task 8: Frontend — API functions

**Files:**
- Modify: `web/src/lib/api.ts`

**Step 1: Update askQuestion to accept debug param**

Change `askQuestion` in `web/src/lib/api.ts`:

```typescript
export function askQuestion(
  question: string,
  targetBridgeId?: number | null,
  debug?: boolean,
): Promise<AskResponse> {
  return post<AskResponse>("/ask", {
    question,
    target_bridge_id: targetBridgeId ?? null,
    debug: debug ?? false,
  })
}
```

Add import for `SystemStatus` type and add:

```typescript
// --- System ---

export function fetchSystemStatus(): Promise<SystemStatus> {
  return get<SystemStatus>("/system/status")
}
```

**Step 2: Verify types compile**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 3: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: update askQuestion with debug param, add fetchSystemStatus"
```

---

### Task 9: Frontend — Debug components

**Files:**
- Create: `web/src/components/ask/DebugTimings.tsx`
- Create: `web/src/components/ask/DebugFacet.tsx`
- Create: `web/src/components/ask/DebugChannel.tsx`
- Create: `web/src/components/ask/DebugPanel.tsx`

**Step 1: Create DebugTimings**

`web/src/components/ask/DebugTimings.tsx` — displays timing badges:

```tsx
import { Badge } from "@/components/ui/badge"

export function DebugTimings({ timings }: { timings: Record<string, number> }) {
  const total = Object.values(timings).reduce((a, b) => a + b, 0)
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(timings).map(([key, val]) => (
        <Badge key={key} variant="secondary" className="font-mono text-xs">
          {key}: {val.toFixed(3)}s
        </Badge>
      ))}
      <Badge variant="outline" className="font-mono text-xs">
        total: {total.toFixed(3)}s
      </Badge>
    </div>
  )
}
```

**Step 2: Create DebugFacet**

`web/src/components/ask/DebugFacet.tsx` — displays facet key-value pairs:

```tsx
const FACET_LABELS: Record<string, string> = {
  bridge_type: "桥型",
  material: "材料",
  era: "年代",
  region: "区域",
  function: "功能",
}

export function DebugFacet({ facet }: { facet: Record<string, unknown> | null }) {
  if (!facet) return <p className="text-sm text-muted-foreground">未提取到 facet</p>

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
      {Object.entries(FACET_LABELS).map(([key, label]) => {
        const val = facet[key]
        const display = val == null ? "—" : Array.isArray(val) ? val.join(", ") : String(val)
        return (
          <div key={key}>
            <span className="text-muted-foreground">{label}:</span>{" "}
            <span className="font-medium">{display}</span>
          </div>
        )
      })}
    </div>
  )
}
```

**Step 3: Create DebugChannel**

`web/src/components/ask/DebugChannel.tsx` — reusable per-channel detail:

```tsx
import type { ChannelDebug } from "@/lib/types"

const CHANNEL_LABELS: Record<string, string> = {
  anchor: "Anchor 通道",
  concept: "Concept 通道",
  analogy: "Analogy 通道",
}

export function DebugChannel({ data }: { data: ChannelDebug }) {
  const maxRows = Math.max(data.vec_ids.length, data.fts_ids.length, data.rrf_scores.length, data.final_ids.length)
  const finalSet = new Set(data.final_ids)

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        筛选: <code className="text-xs bg-muted px-1 py-0.5 rounded">{data.filter_desc}</code>
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="text-left py-1 pr-4">Vector</th>
              <th className="text-left py-1 pr-4">FTS</th>
              <th className="text-left py-1 pr-4">RRF 融合</th>
              <th className="text-left py-1">最终选取</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {Array.from({ length: maxRows }, (_, i) => (
              <tr key={i} className="border-b border-dashed last:border-0">
                <td className="py-0.5 pr-4">{data.vec_ids[i] != null ? `#${data.vec_ids[i]}` : ""}</td>
                <td className="py-0.5 pr-4">{data.fts_ids[i] != null ? `#${data.fts_ids[i]}` : ""}</td>
                <td className="py-0.5 pr-4">
                  {data.rrf_scores[i] != null
                    ? `#${data.rrf_scores[i][0]} ${data.rrf_scores[i][1].toFixed(4)}`
                    : ""}
                </td>
                <td className="py-0.5">
                  {data.final_ids[i] != null ? (
                    <span className="text-green-600">#{data.final_ids[i]}</span>
                  ) : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

**Step 4: Create DebugPanel**

`web/src/components/ask/DebugPanel.tsx` — container with collapsible sections:

```tsx
import { useState } from "react"
import { ChevronRight } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Button } from "@/components/ui/button"
import type { DebugInfo } from "@/lib/types"
import { DebugTimings } from "./DebugTimings"
import { DebugFacet } from "./DebugFacet"
import { DebugChannel } from "./DebugChannel"

const CHANNEL_LABELS: Record<string, string> = {
  anchor: "Anchor 通道",
  concept: "Concept 通道",
  analogy: "Analogy 通道",
}

export function DebugPanel({ debug }: { debug: DebugInfo }) {
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())

  function toggle(key: string) {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function toggleAll() {
    const allKeys = ["timings", "facet", ...debug.channels.map((c) => c.channel)]
    if (openSections.size === allKeys.length) {
      setOpenSections(new Set())
    } else {
      setOpenSections(new Set(allKeys))
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/50 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-600">调试信息</h3>
        <Button variant="ghost" size="sm" onClick={toggleAll} className="text-xs h-7">
          {openSections.size > 0 ? "全部折叠" : "全部展开"}
        </Button>
      </div>

      <Section title="耗时统计" id="timings" open={openSections.has("timings")} onToggle={toggle}>
        <DebugTimings timings={debug.timings} />
      </Section>

      <Section title="Facet 抽取" id="facet" open={openSections.has("facet")} onToggle={toggle}>
        <DebugFacet facet={debug.facet} />
      </Section>

      {debug.channels.map((ch) => (
        <Section
          key={ch.channel}
          title={`${CHANNEL_LABELS[ch.channel] ?? ch.channel} (${ch.final_ids.length} 条)`}
          id={ch.channel}
          open={openSections.has(ch.channel)}
          onToggle={toggle}
        >
          <DebugChannel data={ch} />
        </Section>
      ))}
    </div>
  )
}

function Section({
  title,
  id,
  open,
  onToggle,
  children,
}: {
  title: string
  id: string
  open: boolean
  onToggle: (id: string) => void
  children: React.ReactNode
}) {
  return (
    <Collapsible open={open} onOpenChange={() => onToggle(id)}>
      <CollapsibleTrigger className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 cursor-pointer w-full py-1">
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-5 pt-1 pb-2">
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
```

**Step 5: Verify types compile**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 6: Commit**

```bash
git add web/src/components/ask/DebugTimings.tsx web/src/components/ask/DebugFacet.tsx web/src/components/ask/DebugChannel.tsx web/src/components/ask/DebugPanel.tsx
git commit -m "feat: add debug panel components for AskPage"
```

---

### Task 10: Frontend — Wire debug toggle into AskPanel

**Files:**
- Modify: `web/src/components/ask/AskPanel.tsx`
- Modify: `web/src/components/ask/AnswerDisplay.tsx`

**Step 1: Update AskPanel**

In `web/src/components/ask/AskPanel.tsx`:

1. Add `import { Switch } from "@/components/ui/switch"` and `import { Label } from "@/components/ui/label"`
2. Add state: `const [debug, setDebug] = useState(false)`
3. Add Switch in the filter area (next to the bridge ID filter toggle):
   ```tsx
   <div className="flex items-center gap-2">
     <Switch id="debug-mode" checked={debug} onCheckedChange={setDebug} />
     <Label htmlFor="debug-mode" className="text-xs text-slate-500 cursor-pointer">调试模式</Label>
   </div>
   ```
4. Pass `debug` to `askQuestion`: `await askQuestion(q, isNaN(bid as number) ? undefined : bid, debug)`

**Step 2: Update AnswerDisplay**

In `web/src/components/ask/AnswerDisplay.tsx`:

1. Add `import { DebugPanel } from "./DebugPanel"`
2. After the citations section, add:
   ```tsx
   {data.debug && <DebugPanel debug={data.debug} />}
   ```

**Step 3: Verify types compile and dev server starts**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 4: Commit**

```bash
git add web/src/components/ask/AskPanel.tsx web/src/components/ask/AnswerDisplay.tsx
git commit -m "feat: add debug toggle to AskPanel, show DebugPanel in answer"
```

---

### Task 11: Frontend — SettingsPage

**Files:**
- Create: `web/src/pages/SettingsPage.tsx`

**Step 1: Create the page**

`web/src/pages/SettingsPage.tsx`:

```tsx
import { PageHeader } from "@/components/layout/PageHeader"
import { useApi } from "@/hooks/useApi"
import { fetchSystemStatus } from "@/lib/api"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

export function Component() {
  const { data, loading, error, refetch } = useApi(fetchSystemStatus)

  return (
    <>
      <PageHeader title="设置" description="系统状态与配置" />
      <main className="p-6">
        {loading && <LoadingState />}

        {error && (
          <div className="space-y-4">
            <p className="text-sm text-red-600">加载失败: {error}</p>
            <Button onClick={refetch} variant="outline" size="sm">重试</Button>
          </div>
        )}

        {data && (
          <div className="grid gap-6 lg:grid-cols-2">
            {/* System Status */}
            <Card>
              <CardHeader>
                <CardTitle>系统状态</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <StatusRow label="数据库" connected={data.db_connected} detail={data.db_version} />
                <InfoRow label="Schema 版本" value={data.schema_version != null ? `v${data.schema_version}` : "未知"} />
                <StatusRow label="API 密钥" connected={data.api_key_configured} detail={data.api_key_configured ? "已配置" : "未配置"} />
                <InfoRow label="版本" value={`${data.version} · Python ${data.python_version}`} />
              </CardContent>
            </Card>

            {/* Config */}
            <Card>
              <CardHeader>
                <CardTitle>检索配置</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <InfoRow label="LLM 供应商" value={data.llm_provider} />
                <InfoRow label="嵌入模型" value={data.embedding_model} />
                <InfoRow label="对话模型" value={data.chat_model} />
                <InfoRow label="向量维度" value={String(data.vector_dimension)} />
                <InfoRow label="索引类型" value={data.index_type.toUpperCase()} />
                <InfoRow label="RRF k 值" value={String(data.rrf_k)} />
                <InfoRow
                  label="通道配额"
                  value={`Anchor ${data.chunk_quota.anchor} / Concept ${data.chunk_quota.concept} / Analogy ${data.chunk_quota.analogy}`}
                />
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </>
  )
}

function StatusRow({ label, connected, detail }: { label: string; connected: boolean; detail?: string | null }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} />
        <span className="font-medium">{detail ?? (connected ? "正常" : "异常")}</span>
      </span>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {[0, 1].map((i) => (
        <Card key={i}>
          <CardHeader><Skeleton className="h-6 w-24" /></CardHeader>
          <CardContent className="space-y-3">
            {[...Array(4)].map((_, j) => (
              <div key={j} className="flex justify-between">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-32" />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
```

**Step 2: Verify types compile**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 3: Commit**

```bash
git add web/src/pages/SettingsPage.tsx
git commit -m "feat: add SettingsPage with system status and config display"
```

---

### Task 12: Frontend — Router + Sidebar

**Files:**
- Modify: `web/src/router.tsx`
- Modify: `web/src/components/layout/AppSidebar.tsx`

**Step 1: Add route**

In `web/src/router.tsx`, add inside the children array:

```tsx
{ path: "settings", lazy: () => import("@/pages/SettingsPage") },
```

**Step 2: Add sidebar entry**

In `web/src/components/layout/AppSidebar.tsx`:

1. Add `Settings` to the lucide-react import
2. Add a new nav group after "工具":
   ```typescript
   {
     label: "系统",
     items: [
       { path: "/settings", icon: Settings, label: "设置" },
     ],
   },
   ```

**Step 3: Verify types compile**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

**Step 4: Commit**

```bash
git add web/src/router.tsx web/src/components/layout/AppSidebar.tsx
git commit -m "feat: add settings route and sidebar navigation entry"
```

---

### Task 13: Smoke test full backend

**Files:** (none new — verification only)

**Step 1: Run all unit tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: ALL PASS — no regressions

**Step 2: Run frontend type check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Final commit (if any fixups needed)**

Fix any issues found, commit with descriptive message.
