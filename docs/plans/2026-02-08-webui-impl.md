# WebUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a React-based WebUI to `web/` that calls the existing `/api/v1/ask` and `/api/v1/ingest` endpoints.

**Architecture:** Single-page app with two tab panels (Ask / Ingest). React + Vite + shadcn/ui + Tailwind. No router, no state library. API calls via `fetch` through Vite proxy. Backend only change: add CORS middleware.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS v4, shadcn/ui, react-markdown, lucide-react

**Design doc:** `docs/plans/2026-02-08-webui-design.md`

---

### Task 1: Backend — Add CORS Middleware

**Files:**
- Modify: `app/main.py`

**Step 1: Add CORSMiddleware to FastAPI app**

Add after the `app = FastAPI(...)` line:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Step 2: Verify server still starts**

Run: `cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui && python -c "from app.main import app; print(app.title)"`
Expected: `Bridge RAG`

**Step 3: Run existing tests to ensure nothing breaks**

Run: `pytest tests/ -v --ignore=tests/integration 2>&1 | tail -5`
Expected: All tests pass

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: add CORS middleware for WebUI dev server"
```

---

### Task 2: Scaffold Vite + React + TypeScript Project

**Files:**
- Create: `web/` directory with Vite scaffold

**Step 1: Create Vite project**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
npm create vite@latest web -- --template react-ts
```

**Step 2: Install dependencies**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npm install
npm install react-markdown
```

**Step 3: Configure Vite proxy**

Replace `web/vite.config.ts` with:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

**Step 4: Verify dev server starts**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx vite --host 2>&1 &
sleep 3
curl -s http://localhost:5173 | head -5
kill %1
```

Expected: HTML response containing `<div id="root">`

**Step 5: Clean up default files**

Delete default Vite boilerplate:
- Delete `web/src/App.css`
- Delete `web/src/assets/react.svg`
- Delete `web/public/vite.svg`

Replace `web/src/App.tsx` with minimal placeholder:

```tsx
function App() {
  return <div>Bridge RAG</div>
}

export default App
```

Replace `web/src/index.css` with empty file (will be configured in Task 3).

**Step 6: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/
git commit -m "feat: scaffold Vite + React + TypeScript project"
```

---

### Task 3: Set Up Tailwind CSS + shadcn/ui + Fonts

**Files:**
- Modify: `web/package.json` (via npm install)
- Modify: `web/vite.config.ts`
- Modify: `web/src/index.css`
- Create: `web/src/lib/utils.ts`
- Create: `web/components.json`

**Step 1: Install Tailwind CSS v4**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npm install tailwindcss @tailwindcss/vite
```

Add `@tailwindcss/vite` plugin to `vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

**Step 2: Configure index.css with Tailwind + Google Fonts + theme**

Replace `web/src/index.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Libre+Bodoni:wght@400;500;600;700&family=Public+Sans:wght@300;400;500;600;700&display=swap');
@import "tailwindcss";

@theme {
  --font-sans: 'Public Sans', sans-serif;
  --font-serif: 'Libre Bodoni', serif;
  --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace;
}
```

**Step 3: Install shadcn/ui dependencies**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npm install class-variance-authority clsx tailwind-merge lucide-react
```

Create `web/src/lib/utils.ts`:

```ts
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**Step 4: Initialize shadcn/ui and add components**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx shadcn@latest init -y -d
npx shadcn@latest add button input textarea badge tabs
```

Note: If `shadcn init` prompts, pick defaults (New York style, Slate base color, CSS variables yes).

**Step 5: Verify Tailwind works**

Update `web/src/App.tsx`:

```tsx
function App() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <h1 className="font-serif text-3xl text-slate-800">Bridge RAG</h1>
    </div>
  )
}

export default App
```

Run dev server and visually confirm Libre Bodoni font renders.

**Step 6: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/
git commit -m "feat: configure Tailwind CSS v4, shadcn/ui, and fonts"
```

---

### Task 4: API Layer + TypeScript Types

**Files:**
- Create: `web/src/lib/api.ts`
- Create: `web/src/lib/types.ts`

**Step 1: Define TypeScript types mirroring backend schemas**

Create `web/src/lib/types.ts`:

```ts
// --- Ask ---

export interface AskRequest {
  question: string
  target_bridge_id?: number | null
}

export interface CitationResponse {
  chunk_id: number
  source_title: string
  page_range: string | null
}

export interface ConfidenceResponse {
  level: "high" | "medium" | "low"
  reason: string
}

export interface ChunkSummary {
  chunk_id: number
  bridge_id: number | null
  bridge_name: string | null
  preview: string
}

export interface EvidenceGroupsResponse {
  anchor: ChunkSummary[]
  concept: ChunkSummary[]
  analogy: ChunkSummary[]
}

export interface AskResponse {
  summary: string
  details: string
  analogy: string | null
  citations: CitationResponse[]
  sources: string[]
  confidence: ConfidenceResponse
  evidence_groups: EvidenceGroupsResponse | null
  degraded: string[] | null
}

// --- Ingest ---

export interface IngestRequest {
  content: string
  source_type: string
}

export interface IngestedChunkSummary {
  content_preview: string
  lvl1: string | null
  lvl2: string | null
  bridge_name: string | null
}

export interface IngestResponse {
  source_id: number
  bridge_name: string | null
  title: string | null
  chunk_count: number
  chunks: IngestedChunkSummary[]
}
```

**Step 2: Create API functions**

Create `web/src/lib/api.ts`:

```ts
import type { AskResponse, IngestResponse } from "./types"

const BASE = "/api/v1"

async function request<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export function askQuestion(
  question: string,
  targetBridgeId?: number | null,
): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    question,
    target_bridge_id: targetBridgeId ?? null,
  })
}

export function ingestDocument(
  content: string,
  sourceType: string = "document",
): Promise<IngestResponse> {
  return request<IngestResponse>("/ingest", {
    content,
    source_type: sourceType,
  })
}
```

**Step 3: Verify TypeScript compiles**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

Expected: No errors

**Step 4: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/src/lib/
git commit -m "feat: add API layer and TypeScript types"
```

---

### Task 5: App Shell — Tab Navigation

**Files:**
- Create: `web/src/components/layout/TabNav.tsx`
- Modify: `web/src/App.tsx`

**Step 1: Create TabNav component**

Create `web/src/components/layout/TabNav.tsx`:

```tsx
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Search, Upload } from "lucide-react"

interface TabNavProps {
  value: string
  onValueChange: (value: string) => void
}

export function TabNav({ value, onValueChange }: TabNavProps) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-3xl px-6 py-4 flex items-center justify-between">
        <h1 className="font-serif text-xl font-semibold text-slate-800">
          Bridge RAG
        </h1>
        <Tabs value={value} onValueChange={onValueChange}>
          <TabsList>
            <TabsTrigger value="ask" className="gap-1.5 cursor-pointer">
              <Search className="h-4 w-4" />
              问答
            </TabsTrigger>
            <TabsTrigger value="ingest" className="gap-1.5 cursor-pointer">
              <Upload className="h-4 w-4" />
              入库
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </header>
  )
}
```

**Step 2: Wire up App.tsx**

Replace `web/src/App.tsx`:

```tsx
import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <div className="text-slate-500">问答页（待实现）</div>}
        {tab === "ingest" && <div className="text-slate-500">入库页（待实现）</div>}
      </main>
    </div>
  )
}

export default App
```

**Step 3: Verify in browser**

Run dev server, confirm Tab switching works, fonts render correctly.

**Step 4: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/src/
git commit -m "feat: add app shell with tab navigation"
```

---

### Task 6: Ask Panel — Input + Loading + Error

**Files:**
- Create: `web/src/components/ask/AskPanel.tsx`
- Modify: `web/src/App.tsx`

**Step 1: Create AskPanel with input, submit, loading skeleton, and error state**

Create `web/src/components/ask/AskPanel.tsx`:

```tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Search, ChevronDown, Loader2 } from "lucide-react"
import { askQuestion } from "@/lib/api"
import type { AskResponse } from "@/lib/types"

export function AskPanel() {
  const [question, setQuestion] = useState("")
  const [bridgeId, setBridgeId] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResponse | null>(null)

  async function handleSubmit() {
    const q = question.trim()
    if (!q) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const bid = bridgeId ? parseInt(bridgeId, 10) : undefined
      const res = await askQuestion(q, isNaN(bid as number) ? undefined : bid)
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败")
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="space-y-6">
      {/* Input area */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex gap-3">
          <Input
            placeholder="输入关于桥梁的问题…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1"
          />
          <Button
            onClick={handleSubmit}
            disabled={loading || !question.trim()}
            className="bg-orange-500 hover:bg-orange-600 text-white cursor-pointer"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            {loading ? "检索中…" : "提问"}
          </Button>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
        >
          <ChevronDown className={`h-3 w-3 transition-transform ${showFilters ? "rotate-180" : ""}`} />
          筛选条件
        </button>
        {showFilters && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500">桥梁 ID</label>
            <Input
              type="number"
              placeholder="可选"
              value={bridgeId}
              onChange={(e) => setBridgeId(e.target.value)}
              className="w-32"
            />
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
          <div className="h-4 w-20 bg-slate-200 rounded animate-pulse" />
          <div className="h-7 w-3/4 bg-slate-200 rounded animate-pulse" />
          <div className="space-y-2">
            <div className="h-4 w-full bg-slate-100 rounded animate-pulse" />
            <div className="h-4 w-5/6 bg-slate-100 rounded animate-pulse" />
            <div className="h-4 w-4/6 bg-slate-100 rounded animate-pulse" />
          </div>
        </div>
      )}

      {/* Result placeholder — wired in Task 7 */}
      {result && !loading && (
        <div className="text-sm text-slate-500">
          收到回答（AnswerDisplay 待实现）: {result.summary.slice(0, 100)}…
        </div>
      )}
    </div>
  )
}
```

**Step 2: Wire into App.tsx**

Replace the ask placeholder in `App.tsx`:

```tsx
import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"
import { AskPanel } from "@/components/ask/AskPanel"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <AskPanel />}
        {tab === "ingest" && <div className="text-slate-500">入库页（待实现）</div>}
      </main>
    </div>
  )
}

export default App
```

**Step 3: Verify TypeScript compiles**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

**Step 4: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/src/
git commit -m "feat: add AskPanel with input, loading, and error states"
```

---

### Task 7: Answer Display — Summary, Details, Analogy, Confidence, Citations

**Files:**
- Create: `web/src/components/ask/ConfidenceBadge.tsx`
- Create: `web/src/components/ask/AnswerDisplay.tsx`
- Modify: `web/src/components/ask/AskPanel.tsx`

**Step 1: Create ConfidenceBadge**

Create `web/src/components/ask/ConfidenceBadge.tsx`:

```tsx
import type { ConfidenceResponse } from "@/lib/types"

const styles = {
  high: "bg-green-500 text-white",
  medium: "bg-yellow-400 text-yellow-900",
  low: "bg-red-500 text-white",
}

const labels = { high: "高置信", medium: "中置信", low: "低置信" }

export function ConfidenceBadge({ confidence }: { confidence: ConfidenceResponse }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[confidence.level]}`}>
        {labels[confidence.level]}
      </span>
      <span className="text-xs text-slate-400">{confidence.reason}</span>
    </div>
  )
}
```

**Step 2: Create AnswerDisplay**

Create `web/src/components/ask/AnswerDisplay.tsx`:

```tsx
import Markdown from "react-markdown"
import { AlertTriangle } from "lucide-react"
import type { AskResponse } from "@/lib/types"
import { ConfidenceBadge } from "./ConfidenceBadge"

export function AnswerDisplay({ data }: { data: AskResponse }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-5">
      {/* Degraded warning */}
      {data.degraded && data.degraded.length > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-50 border border-yellow-200 px-3 py-2 text-sm text-yellow-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          部分功能降级：{data.degraded.join("、")}
        </div>
      )}

      {/* Confidence */}
      <ConfidenceBadge confidence={data.confidence} />

      {/* Summary */}
      <h2 className="font-serif text-2xl font-semibold text-slate-800 leading-snug">
        {data.summary}
      </h2>

      {/* Details */}
      <div className="prose prose-slate prose-sm max-w-none">
        <Markdown>{data.details}</Markdown>
      </div>

      {/* Analogy */}
      {data.analogy && (
        <blockquote className="border-l-4 border-blue-400 pl-4 text-sm text-slate-600 italic">
          {data.analogy}
        </blockquote>
      )}

      {/* Citations */}
      {data.citations.length > 0 && (
        <div className="border-t border-slate-100 pt-4">
          <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-2">引用来源</h3>
          <ul className="space-y-1">
            {data.citations.map((c) => (
              <li key={c.chunk_id} className="text-xs text-slate-500">
                {c.source_title}
                {c.page_range && <span className="text-slate-400">（{c.page_range}）</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
```

**Step 3: Wire AnswerDisplay into AskPanel**

In `web/src/components/ask/AskPanel.tsx`, replace the result placeholder:

```tsx
// Add import at top
import { AnswerDisplay } from "./AnswerDisplay"

// Replace the result placeholder block with:
{result && !loading && <AnswerDisplay data={result} />}
```

**Step 4: Install @tailwindcss/typography for prose class**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npm install @tailwindcss/typography
```

Add to `web/src/index.css` after `@import "tailwindcss";`:

```css
@plugin "@tailwindcss/typography";
```

**Step 5: Verify TypeScript compiles**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

**Step 6: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/
git commit -m "feat: add AnswerDisplay with confidence, markdown, and citations"
```

---

### Task 8: Evidence Grid — Three-Channel Display

**Files:**
- Create: `web/src/components/ask/EvidenceGrid.tsx`
- Modify: `web/src/components/ask/AnswerDisplay.tsx`

**Step 1: Create EvidenceGrid**

Create `web/src/components/ask/EvidenceGrid.tsx`:

```tsx
import type { EvidenceGroupsResponse } from "@/lib/types"

interface ChannelConfig {
  key: keyof EvidenceGroupsResponse
  label: string
  color: string
}

const channels: ChannelConfig[] = [
  { key: "anchor", label: "本桥资料", color: "bg-blue-500" },
  { key: "concept", label: "通用知识", color: "bg-slate-400" },
  { key: "analogy", label: "类比案例", color: "bg-amber-500" },
]

export function EvidenceGrid({ evidence }: { evidence: EvidenceGroupsResponse }) {
  const hasAny = evidence.anchor.length + evidence.concept.length + evidence.analogy.length > 0
  if (!hasAny) return null

  return (
    <div className="border-t border-slate-100 pt-5">
      <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-3">检索证据</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {channels.map(({ key, label, color }) => (
          <div key={key} className="space-y-2">
            <div className={`h-1 w-full rounded-full ${color}`} />
            <h4 className="text-xs uppercase tracking-wider text-slate-500 font-medium">
              {label}
            </h4>
            {evidence[key].length === 0 ? (
              <p className="text-xs text-slate-300">无</p>
            ) : (
              <ul className="space-y-2">
                {evidence[key].map((chunk) => (
                  <li
                    key={chunk.chunk_id}
                    className="rounded border border-slate-100 bg-slate-50/50 p-2.5"
                  >
                    <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">
                      {chunk.preview}
                    </p>
                    {chunk.bridge_name && (
                      <p className="mt-1 text-[11px] text-slate-400">{chunk.bridge_name}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Step 2: Wire into AnswerDisplay**

In `web/src/components/ask/AnswerDisplay.tsx`, add between the analogy blockquote and the citations section:

```tsx
// Add import
import { EvidenceGrid } from "./EvidenceGrid"

// Add after analogy block, before citations:
{data.evidence_groups && <EvidenceGrid evidence={data.evidence_groups} />}
```

**Step 3: Verify TypeScript compiles**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

**Step 4: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/src/
git commit -m "feat: add three-channel evidence grid"
```

---

### Task 9: Ingest Panel

**Files:**
- Create: `web/src/components/ingest/ChunkList.tsx`
- Create: `web/src/components/ingest/IngestPanel.tsx`
- Modify: `web/src/App.tsx`

**Step 1: Create ChunkList**

Create `web/src/components/ingest/ChunkList.tsx`:

```tsx
import { Badge } from "@/components/ui/badge"
import type { IngestedChunkSummary } from "@/lib/types"

export function ChunkList({ chunks }: { chunks: IngestedChunkSummary[] }) {
  if (chunks.length === 0) return null

  return (
    <ul className="divide-y divide-slate-100">
      {chunks.map((chunk, i) => (
        <li key={i} className="py-2.5 flex items-start justify-between gap-3">
          <p className="text-sm text-slate-600 truncate flex-1">
            {chunk.content_preview}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            {chunk.lvl1 && (
              <Badge variant="secondary" className="text-[11px]">
                {chunk.lvl1}
              </Badge>
            )}
            {chunk.lvl2 && (
              <Badge variant="secondary" className="text-[11px]">
                {chunk.lvl2}
              </Badge>
            )}
            {chunk.bridge_name && (
              <span className="text-[11px] text-slate-400">{chunk.bridge_name}</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
```

**Step 2: Create IngestPanel**

Create `web/src/components/ingest/IngestPanel.tsx`:

```tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Upload, Loader2 } from "lucide-react"
import { ingestDocument } from "@/lib/api"
import type { IngestResponse } from "@/lib/types"
import { ChunkList } from "./ChunkList"

const SOURCE_TYPES = ["document", "note"]

export function IngestPanel() {
  const [content, setContent] = useState("")
  const [sourceType, setSourceType] = useState("document")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<IngestResponse | null>(null)

  async function handleSubmit() {
    const c = content.trim()
    if (!c) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await ingestDocument(c, sourceType)
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : "入库失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Input area */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-slate-700">Markdown 内容</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            className="text-sm border border-slate-200 rounded-md px-2 py-1 text-slate-600 bg-white cursor-pointer"
          >
            {SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <Textarea
          placeholder={"---\nbridge: 桥梁名称\nsource_type: document\ntitle: 资料标题\n---\n\n# 章节标题\n\n正文内容..."}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="font-mono min-h-[300px] resize-y"
        />
        <div className="flex justify-end">
          <Button
            onClick={handleSubmit}
            disabled={loading || !content.trim()}
            className="bg-orange-500 hover:bg-orange-600 text-white cursor-pointer"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {loading ? "入库中…" : "提交入库"}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
          <div className="flex items-baseline justify-between">
            <div>
              {result.bridge_name && (
                <h2 className="font-serif text-xl font-semibold text-slate-800">
                  {result.bridge_name}
                </h2>
              )}
              {result.title && (
                <p className="text-sm text-slate-400">{result.title}</p>
              )}
            </div>
            <span className="text-sm text-slate-500">
              共 <span className="font-semibold text-blue-500">{result.chunk_count}</span> 个知识块
            </span>
          </div>
          <ChunkList chunks={result.chunks} />
        </div>
      )}
    </div>
  )
}
```

**Step 3: Wire into App.tsx**

```tsx
import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"
import { AskPanel } from "@/components/ask/AskPanel"
import { IngestPanel } from "@/components/ingest/IngestPanel"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <AskPanel />}
        {tab === "ingest" && <IngestPanel />}
      </main>
    </div>
  )
}

export default App
```

**Step 4: Verify TypeScript compiles**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

**Step 5: Commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add web/src/
git commit -m "feat: add IngestPanel with markdown input and chunk list"
```

---

### Task 10: Final Polish + Verify End-to-End

**Files:**
- Possibly modify: various component files for visual tweaks

**Step 1: Verify TypeScript compiles cleanly**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx tsc --noEmit
```

**Step 2: Verify production build succeeds**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui/web
npx vite build
```

Expected: Build completes with no errors, output in `web/dist/`.

**Step 3: Add web/dist/ to .gitignore**

Append to `.gitignore`:

```
web/dist/
web/node_modules/
```

**Step 4: Verify backend tests still pass**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
pytest tests/ -v --ignore=tests/integration 2>&1 | tail -5
```

Expected: All 75 tests pass

**Step 5: End-to-end smoke test (manual)**

1. Start DB: `docker compose up -d db`
2. Start backend: `uvicorn app.main:app --reload`
3. Start frontend: `cd web && npm run dev`
4. Open `http://localhost:5173`
5. Verify: Tab switching works, Ask input submits to backend, Ingest form submits

**Step 6: Final commit**

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG/.worktrees/webui
git add .gitignore
git commit -m "chore: add web build artifacts to gitignore"
```
