# Chunk Split UX Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the character-index split dialog with paragraph divider click (A) + precise cursor mode (C) + dual-panel preview.

**Architecture:** All changes in one file (`web/src/pages/ChunkEditorPage.tsx`). Add 4 internal components (`SplitModeHeader`, `SplitParagraphView`, `SplitPreciseView`, `SplitPreview`), a paragraph-parsing helper, and new state variables. Remove old split dialog state/JSX. Backend untouched.

**Tech Stack:** React, TypeScript, Tailwind CSS, shadcn/ui (Button, Textarea), lucide-react icons

---

### Task 1: Add paragraph parsing helper + split state types

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx:56-60` (Helpers section)

**Step 1: Add the helper function after the existing `staleCount` helper (line 60)**

```typescript
// --- Split helpers ---

interface ParagraphSegment {
  text: string
  startOffset: number  // character offset where this segment starts in original content
  endOffset: number    // character offset where this segment ends (exclusive)
}

/** Split content into paragraph segments with their character offsets.
 *  Tries \n\n first; falls back to \n if content is a single block. */
function parseContentSegments(content: string): ParagraphSegment[] {
  let parts = content.split("\n\n")
  let separator = "\n\n"

  // Fallback: if no \n\n found, split by \n
  if (parts.length <= 1) {
    parts = content.split("\n")
    separator = "\n"
  }

  // Filter out empty segments from consecutive separators
  const segments: ParagraphSegment[] = []
  let offset = 0
  for (let i = 0; i < parts.length; i++) {
    const text = parts[i]
    if (text.length > 0) {
      segments.push({
        text,
        startOffset: offset,
        endOffset: offset + text.length,
      })
    }
    offset += text.length
    if (i < parts.length - 1) {
      offset += separator.length
    }
  }
  return segments
}
```

**Step 2: Verify the build compiles**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (no errors — helper is defined but not yet used, tree-shaking is fine for tsc)

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): add paragraph parsing helper for split UX"
```

---

### Task 2: Replace split state variables in ChunkEditor

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — `ChunkEditor` component (lines 184-700)

**Step 1: Replace old split state (lines 200-202) with new state machine**

Remove these lines:
```typescript
  // Dialog state
  const [splitDialogOpen, setSplitDialogOpen] = useState(false)
  const [splitPos, setSplitPos] = useState("")
```

Replace with:
```typescript
  // Split mode state
  const [splitPhase, setSplitPhase] = useState<null | "selecting" | "previewing">(null)
  const [splitSubMode, setSplitSubMode] = useState<"paragraph" | "precise">("paragraph")
  const [splitPosition, setSplitPosition] = useState<number | null>(null)
```

**Step 2: Update `handleSplit` (lines 303-327) to use `splitPosition` instead of `splitPos`**

Replace the entire `handleSplit` callback with:
```typescript
  const handleSplit = useCallback(async (position: number) => {
    if (!chunk) return
    setSplitting(true)
    setActionError(null)
    try {
      await splitChunk(chunk.id, { position, expected_updated_at: chunk.updated_at })
      setSplitPhase(null)
      onMutated()
    } catch (e) {
      if (handleConflictError(e, () => {
        setSplitting(true)
        splitChunk(chunk.id, { position })
          .then(() => { setSplitPhase(null); onMutated() })
          .catch((err2) => setActionError(err2 instanceof Error ? err2.message : String(err2)))
          .finally(() => setSplitting(false))
      })) return
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSplitting(false)
    }
  }, [chunk, onMutated])
```

**Step 3: Remove `openSplitDialog` function (lines 353-364)**

Delete the entire `openSplitDialog` function.

**Step 4: Remove `textareaRef` (line 216)**

Delete: `const textareaRef = useRef<HTMLTextAreaElement>(null)`

(It was only used by `openSplitDialog` and the content textarea. The content textarea doesn't need a ref anymore; the precise mode will create its own.)

**Step 5: Update the "拆分" button onClick (line 591)**

Change from:
```typescript
          onClick={openSplitDialog}
```
To:
```typescript
          onClick={() => {
            setSplitPhase("selecting")
            setSplitSubMode("paragraph")
            setSplitPosition(null)
          }}
```

**Step 6: Remove the split dialog JSX (lines 608-639)**

Delete the entire `{/* Split dialog */}` block including the `<Dialog>` and all children.

**Step 7: Remove the `ref={textareaRef}` from the content Textarea (line 396)**

Change from:
```typescript
        <Textarea
          ref={textareaRef}
          value={content}
```
To:
```typescript
        <Textarea
          value={content}
```

**Step 8: Verify build**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (handleSplit signature changed, dialog removed, no dead refs)

**Step 9: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "refactor(web): replace split dialog state with split mode state machine"
```

---

### Task 3: Build SplitParagraphView component

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — add component before `ChunkEditor`

**Step 1: Add the component after the `parseContentSegments` helper**

```typescript
// --- Split paragraph view (Mode A) ---

interface SplitParagraphViewProps {
  content: string
  onSelectPosition: (position: number) => void
}

function SplitParagraphView({ content, onSelectPosition }: SplitParagraphViewProps) {
  const segments = parseContentSegments(content)
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)
  const totalLen = content.length

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-4 py-2 space-y-0">
      {segments.map((seg, i) => (
        <div key={seg.startOffset}>
          {/* Paragraph text */}
          <div
            className={`rounded px-3 py-2 font-mono text-sm whitespace-pre-wrap transition-colors ${
              hoveredIdx !== null && i < hoveredIdx
                ? "bg-blue-50"
                : hoveredIdx !== null && i >= hoveredIdx
                  ? "bg-emerald-50"
                  : ""
            }`}
          >
            {seg.text}
          </div>

          {/* Divider between paragraphs (not after last) */}
          {i < segments.length - 1 && (
            <div
              className="group flex cursor-pointer items-center gap-2 py-1 px-3 my-1 select-none"
              onMouseEnter={() => setHoveredIdx(i + 1)}
              onMouseLeave={() => setHoveredIdx(null)}
              onClick={() => onSelectPosition(segments[i + 1].startOffset)}
            >
              <div className="flex-1 border-t border-dashed border-slate-300 group-hover:border-blue-400 transition-colors" />
              <span className="shrink-0 text-xs text-slate-400 group-hover:text-blue-600 transition-colors">
                ✂ {seg.endOffset} 字 | {totalLen - segments[i + 1].startOffset} 字
              </span>
              <div className="flex-1 border-t border-dashed border-slate-300 group-hover:border-blue-400 transition-colors" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
```

**Step 2: Verify build**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): add SplitParagraphView component for divider-click splitting"
```

---

### Task 4: Build SplitPreciseView component

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — add component after `SplitParagraphView`

**Step 1: Add the component**

```typescript
// --- Split precise view (Mode C) ---

interface SplitPreciseViewProps {
  content: string
  onSelectPosition: (position: number) => void
}

function SplitPreciseView({ content, onSelectPosition }: SplitPreciseViewProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorPos, setCursorPos] = useState<number>(0)

  function handleSelect() {
    const pos = textareaRef.current?.selectionStart ?? 0
    setCursorPos(pos)
  }

  const canSplit = cursorPos > 0 && cursorPos < content.length

  return (
    <div className="flex flex-1 min-h-0 flex-col px-4 py-2 gap-2">
      <Textarea
        ref={textareaRef}
        value={content}
        readOnly
        onSelect={handleSelect}
        onClick={handleSelect}
        className="flex-1 min-h-0 resize-none font-mono text-sm"
      />
      <div className="flex items-center justify-between rounded-md border bg-white px-3 py-2">
        <span className="text-xs text-slate-500">
          {canSplit
            ? `光标: 第 ${cursorPos} 字符 · 上半 ${cursorPos} 字 | 下半 ${content.length - cursorPos} 字`
            : "点击文本中的位置来设定拆分点"}
        </span>
        <Button
          size="sm"
          disabled={!canSplit}
          onClick={() => onSelectPosition(cursorPos)}
          className="gap-1"
        >
          <Scissors className="h-3 w-3" />
          在此拆分
        </Button>
      </div>
    </div>
  )
}
```

**Step 2: Verify build**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): add SplitPreciseView component for cursor-based splitting"
```

---

### Task 5: Build SplitPreview component

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — add component after `SplitPreciseView`

**Step 1: Add the component**

```typescript
// --- Split preview ---

interface SplitPreviewProps {
  content: string
  position: number
  splitting: boolean
  onConfirm: () => void
  onReselect: () => void
  onCancel: () => void
}

function SplitPreview({ content, position, splitting, onConfirm, onReselect, onCancel }: SplitPreviewProps) {
  const chunkA = content.slice(0, position)
  const chunkB = content.slice(position)

  return (
    <div className="flex flex-1 min-h-0 flex-col p-4 gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">拆分预览</h3>
        <Button size="sm" variant="ghost" onClick={onReselect} className="gap-1 text-xs">
          <ArrowLeft className="h-3 w-3" />
          重选位置
        </Button>
      </div>

      {/* Chunk A */}
      <div className="flex flex-1 min-h-0 flex-col rounded-md border border-blue-200 bg-blue-50">
        <div className="flex items-center justify-between border-b border-blue-200 px-3 py-1.5">
          <span className="text-xs font-medium text-blue-700">Chunk A</span>
          <span className="text-xs text-blue-500">{chunkA.length} 字</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-sm whitespace-pre-wrap">
          {chunkA}
        </div>
      </div>

      {/* Chunk B */}
      <div className="flex flex-1 min-h-0 flex-col rounded-md border border-emerald-200 bg-emerald-50">
        <div className="flex items-center justify-between border-b border-emerald-200 px-3 py-1.5">
          <span className="text-xs font-medium text-emerald-700">Chunk B</span>
          <span className="text-xs text-emerald-500">{chunkB.length} 字</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-sm whitespace-pre-wrap">
          {chunkB}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-end gap-2 border-t pt-3">
        <Button size="sm" variant="outline" onClick={onCancel}>
          取消
        </Button>
        <Button size="sm" onClick={onConfirm} disabled={splitting} className="gap-1">
          {splitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Scissors className="h-3 w-3" />}
          确认拆分
        </Button>
      </div>
    </div>
  )
}
```

**Step 2: Verify build**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): add SplitPreview component with dual-panel layout"
```

---

### Task 6: Wire split mode into ChunkEditor render

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — `ChunkEditor` component return JSX (lines 382-700)

This is the final wiring task. The `ChunkEditor` return statement needs to branch on `splitPhase`.

**Step 1: Compute whether paragraph mode is available (add before the `return`)**

Add this just before the `if (loading)` check (around line 365):

```typescript
  // Check if paragraph mode is available (needs at least one \n)
  const paragraphModeAvailable = chunk ? /\n/.test(chunk.content) : false
```

**Step 2: Replace the entire `return` block of ChunkEditor (lines 382-699)**

The new return wraps everything in a `splitPhase` conditional:

```tsx
  return (
    <div className="flex h-full flex-col">
      {splitPhase !== null ? (
        // --- Split mode ---
        <>
          {/* Split mode header */}
          <div className="flex items-center gap-3 border-b bg-white px-4 py-2">
            <Scissors className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-700">
              {splitPhase === "selecting" ? "选择拆分位置" : "拆分预览"}
            </span>

            {splitPhase === "selecting" && (
              <div className="ml-auto flex items-center gap-1">
                <Button
                  size="sm"
                  variant={splitSubMode === "paragraph" ? "default" : "outline"}
                  disabled={!paragraphModeAvailable}
                  onClick={() => setSplitSubMode("paragraph")}
                  className="h-7 px-2 text-xs"
                >
                  段落模式
                </Button>
                <Button
                  size="sm"
                  variant={splitSubMode === "precise" ? "default" : "outline"}
                  onClick={() => setSplitSubMode("precise")}
                  className="h-7 px-2 text-xs"
                >
                  精确模式
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSplitPhase(null)}
                  className="ml-2 h-7 px-2 text-xs"
                >
                  取消
                </Button>
              </div>
            )}
          </div>

          {/* Error display */}
          {actionError && (
            <p className="px-4 pt-2 text-xs text-destructive">{actionError}</p>
          )}

          {/* Split content area */}
          {splitPhase === "selecting" && splitSubMode === "paragraph" && (
            <SplitParagraphView
              content={chunk.content}
              onSelectPosition={(pos) => {
                setSplitPosition(pos)
                setSplitPhase("previewing")
              }}
            />
          )}
          {splitPhase === "selecting" && splitSubMode === "precise" && (
            <SplitPreciseView
              content={chunk.content}
              onSelectPosition={(pos) => {
                setSplitPosition(pos)
                setSplitPhase("previewing")
              }}
            />
          )}
          {splitPhase === "previewing" && splitPosition !== null && (
            <SplitPreview
              content={chunk.content}
              position={splitPosition}
              splitting={splitting}
              onConfirm={() => handleSplit(splitPosition)}
              onReselect={() => setSplitPhase("selecting")}
              onCancel={() => setSplitPhase(null)}
            />
          )}
        </>
      ) : (
        // --- Normal edit mode (existing UI) ---
        <div className="flex flex-col gap-4 overflow-y-auto p-4">
          {/* Reindex warning */}
          {chunk.needs_reindex && (
            <div className="flex items-center gap-2 rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-sm text-orange-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              内容已修改，embedding 待更新
            </div>
          )}

          {/* Content textarea */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-slate-600">内容</Label>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="min-h-[200px] resize-y font-mono text-sm"
            />
          </div>

          {/* Section title */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-slate-600">章节标题</Label>
            <Input
              value={sectionTitle}
              onChange={(e) => setSectionTitle(e.target.value)}
              placeholder="章节标题（可选）"
              className="text-sm"
            />
          </div>

          {/* Taxonomy cascading selects — unchanged */}
          <div className="space-y-2">
            <Label className="text-xs font-medium text-slate-600">分类标签</Label>
            <div className="grid grid-cols-3 gap-2">
              <Select
                value={lvl1 ?? "__none__"}
                onValueChange={(v) => {
                  const next = v === "__none__" ? null : v
                  setLvl1(next)
                  setLvl2(null)
                  setLvl3(null)
                }}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl1" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl1Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={lvl2 ?? "__none__"}
                onValueChange={(v) => {
                  const next = v === "__none__" ? null : v
                  setLvl2(next)
                  setLvl3(null)
                }}
                disabled={!lvl1}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl2" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl2Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={lvl3 ?? "__none__"}
                onValueChange={(v) => {
                  setLvl3(v === "__none__" ? null : v)
                }}
                disabled={!lvl2}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl3" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl3Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Bridge links — unchanged */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-slate-600">桥梁关联</Label>
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-xs"
                onClick={() =>
                  setBridgeLinks([
                    ...bridgeLinks,
                    { bridge_id: "", role: "secondary", confidence: "1.0" },
                  ])
                }
              >
                <Plus className="h-3 w-3 mr-1" />
                添加
              </Button>
            </div>
            {bridgeLinks.length === 0 ? (
              <p className="text-xs text-slate-400">暂无桥梁关联</p>
            ) : (
              <div className="space-y-1">
                {bridgeLinks.map((row, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <Input
                      value={row.bridge_id}
                      onChange={(e) => {
                        const next = [...bridgeLinks]
                        next[i] = { ...next[i], bridge_id: e.target.value }
                        setBridgeLinks(next)
                      }}
                      placeholder="Bridge ID"
                      className="h-7 w-20 text-xs font-mono"
                    />
                    <Select
                      value={row.role}
                      onValueChange={(v) => {
                        const next = [...bridgeLinks]
                        next[i] = {
                          ...next[i],
                          role: v as "primary" | "secondary" | "candidate",
                        }
                        setBridgeLinks(next)
                      }}
                    >
                      <SelectTrigger className="h-7 w-24 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="primary">主桥</SelectItem>
                        <SelectItem value="secondary">次桥</SelectItem>
                        <SelectItem value="candidate">候选</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      value={row.confidence}
                      onChange={(e) => {
                        const next = [...bridgeLinks]
                        next[i] = { ...next[i], confidence: e.target.value }
                        setBridgeLinks(next)
                      }}
                      placeholder="置信度"
                      className="h-7 w-16 text-xs"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 text-slate-400 hover:text-destructive"
                      onClick={() =>
                        setBridgeLinks(bridgeLinks.filter((_, idx) => idx !== i))
                      }
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Action error */}
          {actionError && (
            <p className="text-xs text-destructive">{actionError}</p>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 border-t pt-3">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="gap-1"
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Save className="h-3 w-3" />
              )}
              保存
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSplitPhase("selecting")
                setSplitSubMode(paragraphModeAvailable ? "paragraph" : "precise")
                setSplitPosition(null)
              }}
              className="gap-1"
            >
              <Scissors className="h-3 w-3" />
              拆分
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setDeleteDialogOpen(true)}
              className="gap-1 ml-auto"
            >
              <Trash2 className="h-3 w-3" />
              删除
            </Button>
          </div>
        </div>
      )}

      {/* Delete dialog — unchanged */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除知识块 #{chunk.id} 吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Conflict dialog — unchanged */}
      <Dialog open={conflictOpen} onOpenChange={setConflictOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>编辑冲突</DialogTitle>
            <DialogDescription>
              该 Chunk 已被其他用户修改。您可以强制覆盖或放弃本次更改。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConflictOpen(false)
                refetch()
              }}
            >
              放弃修改
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConflictOpen(false)
                conflictRetryFn?.()
              }}
            >
              强制覆盖
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
```

**Key wiring points:**
- Outer div changed from `className="flex flex-col gap-4 overflow-y-auto p-4"` to `className="flex h-full flex-col"` so split mode panels can use flex-1
- Normal edit mode wrapped in its own scrollable div preserving original classes
- `paragraphModeAvailable` gates the default sub-mode and the paragraph button's disabled state
- `handleSplit(splitPosition)` called from SplitPreview's `onConfirm`

**Step 2: Verify build**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): wire split mode into ChunkEditor with paragraph + precise views"
```

---

### Task 7: Clean up unused imports and verify

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx` — imports (lines 1-54)

**Step 1: Check if `Input` import is still needed**

`Input` is used by: section title, bridge links, batch toolbar. Still needed. Keep it.

**Step 2: Check if `Dialog`-related imports are still needed**

Delete dialog and conflict dialog still exist. Batch toolbar still uses Dialog. Keep all Dialog imports.

**Step 3: Verify no unused imports**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

If there are unused import warnings from ESLint:
Run: `cd web && npm run lint`
Fix any warnings.

**Step 4: Commit (only if changes were needed)**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "chore(web): clean up imports after split UX refactor"
```

---

### Task 8: Manual testing checklist

**Step 1: Start dev server**

Run: `cd web && npm run dev`

**Step 2: Test paragraph mode (A)**

1. Navigate to any source's chunk editor page
2. Select a chunk that has multiple paragraphs (contains `\n\n`)
3. Click "拆分" button
4. Verify: textarea/form disappears, replaced by paragraph view with dividers
5. Hover over a divider → verify blue highlight on line, paragraphs above go blue, below go green
6. Verify character counts on dividers are correct
7. Click a divider → verify preview appears with Chunk A (blue) and Chunk B (green)
8. Click "重选位置" → verify returns to selecting phase
9. Click "确认拆分" → verify API call succeeds and chunk list refreshes
10. Click "取消" at any point → verify returns to normal edit mode

**Step 3: Test precise mode (C)**

1. Select a chunk with a single paragraph (no `\n\n`)
2. Click "拆分" → verify it enters precise mode (paragraph button disabled)
3. Click inside textarea → verify status bar updates with cursor position
4. Click "在此拆分" → verify preview appears
5. Verify "在此拆分" is disabled when cursor is at position 0

**Step 4: Test mode switching**

1. Select a multi-paragraph chunk, click "拆分"
2. Toggle between "段落模式" and "精确模式" buttons
3. Verify content displays correctly in each mode

**Step 5: Test conflict handling**

1. Open same chunk in two browser tabs
2. Modify and save in tab 2
3. Try to split in tab 1 → verify conflict dialog appears
4. Test both "放弃修改" and "强制覆盖"

**Step 6: Final commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat(web): complete chunk split UX redesign — paragraph dividers + precise cursor"
```
