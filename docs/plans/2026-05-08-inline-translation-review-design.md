# Inline Translation Review — Design

- Date: 2026-05-08
- Status: Approved (brainstormed with user; pending implementation plan)
- Scope: `RAG/` (FastAPI) + `RAG/web/` (admin console)
- Phase: i18n Phase 3 follow-up — UX redistribution

## 1. Background

i18n Phase 3 (PR #169 + follow-ups) introduced a single `/translations`
admin page: a cross-table queue of `translation_reviews` rows surfaced in a
filter-and-dialog flow.

After dogfooding, the centralized form factor was rejected:

- The dialog hides which business object the row belongs to (a translator
  approving "拱圈 → Arch ring" cannot see whether the same KP's `summary_en`
  is also pending).
- Reviewing a single bridge end-to-end requires bouncing back and forth
  between Bridge detail and the central queue.
- "Coverage" is global (per-table %) but never per-object, so an editor
  cannot answer "is this bridge fully bilingual yet?" without writing SQL.

The user-stated rule for the redesign: **wherever a Chinese field is
displayed, its English counterpart should be displayed beside it, in the
same panel, with inline review controls.**

## 2. Decisions

The following were agreed during brainstorming and freeze the shape of the
design:

| ID | Decision | Implication |
|----|----------|-------------|
| X | **Side-by-side layout** — `zh` left / `en` right on the same row, not collapsible, not in a drawer | Each translatable field becomes one `TranslationCell` paired with the existing zh display |
| Y | **Expand `TRANSLATABLE_FIELDS` to include `knowledge_point_key_points.summary` + `.explanation`** | Schema v14 migration adds two `*_en` columns; backend `_model_registry` extended |
| Z | **"Related KP / related bridge" sections show status badges only, link out for editing** | Avoids two-mouth editing on the same review row; KP edits live on KP page, bridge edits on bridge page |
| — | **Central `/translations` page is kept** as queue/inbox + coverage dashboard, but its dialog is removed; row click deep-links to the business page anchored at the field | Single source of "what's pending across the corpus" without duplicating the editing surface |

## 3. Target UX

### 3.1 Bridge detail page

```
┌────────────────────────────────────────────────────────────────┐
│  [桥梁]  赵州桥                                  [删除] [合并] │
├────────────────────────────────────────────────────────────────┤
│  ┌─ 名称 (zh) ──────────┐  ┌─ Name (en)    🟢 已审校 ──────┐ │
│  │ 赵州桥               │  │ Zhaozhou Bridge                 │ │
│  └──────────────────────┘  │ [✏ 编辑] [♻ AI 重译]            │ │
│                            └─────────────────────────────────┘ │
│                                                                │
│  ┌─ 简介 (zh) ──────────┐  ┌─ Description (en)  🟡 待审 ───┐ │
│  │ 赵州桥位于...        │  │ Zhaozhou Bridge is located...  │ │
│  └──────────────────────┘  │ [✓ 通过] [✏ 编辑后通过] [✗]   │ │
│                            │ [♻ AI 重译]                     │ │
│                            └─────────────────────────────────┘ │
│                                                                │
│  ┌─ 相关知识点 ─ 3 个 (只读跳转)─────────────────────────────┐│
│  │  • 拱圈     Arch ring        🟢🟢   [→ KP 页]            ││
│  │  • 石材     Stonework        🟢🔴   [→ KP 页]            ││
│  └────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Knowledge point detail page

```
┌────────────────────────────────────────────────────────────────┐
│  [知识点]  拱圈                                                │
├────────────────────────────────────────────────────────────────┤
│  ┌─ 名称 (zh)  ─────────┐  ┌─ Name (en)  🟢 ──────────┐      │
│  │ 拱圈                 │  │ Arch ring                 │      │
│  └──────────────────────┘  └──────────────────────────┘      │
│                                                                │
│  ┌─ 摘要 (zh) ──────────┐  ┌─ Summary (en) 🟡 ─────────┐     │
│  │ 拱圈是石拱桥承担...  │  │ The arch ring is...        │     │
│  └──────────────────────┘  │ [✓] [✏] [✗] [♻]            │     │
│                            └────────────────────────────┘     │
│                                                                │
│  ┌─ 要点 ─ 5 条 ─────────────────────────────────────────────┐│
│  │  ▸ #1                                                     ││
│  │    summary    zh ◀──┐  ┌─ summary en  🟡 [✓][✏][✗][♻]   ││
│  │    explanation zh ◀─┤  ┌─ explanation en 🔴 [♻]          ││
│  │  ▸ #2 ...                                                 ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                │
│  ┌─ 关联闪卡 ─ 4 张 ────────────────────────────────────────┐ │
│  │  ▸ 卡 #1                                                 │ │
│  │    front_title  zh / en  🟡 [✓][✏][✗][♻]                │ │
│  │    back_answer  zh / en  🟡 [✓][✏][✗][♻]                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─ 关联桥梁 ─ 12 座 (只读跳转)─────────────────────────────┐ │
│  │  • 赵州桥  Zhaozhou Bridge  🟢   [→ 桥页]               │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### 3.3 Status badge legend

| Color | Status | Meaning | Inline buttons |
|-------|--------|---------|----------------|
| 🔴 | `pending_ai` | No English yet | `[♻ AI 翻译]` |
| 🟡 | `ai_generated` | AI produced, awaits human | `[✓ 通过]` `[✏ 编辑后通过]` `[✗ 驳回]` `[♻ AI 重译]` |
| 🟢 | `human_reviewed` | Approved | `[✏ 编辑]` `[♻ AI 重译]` (re-edit re-enters review state) |
| ⚫ | `rejected` | Reviewer rejected | `[♻ AI 重译]` |

## 4. Architecture

```
┌─ RAG/web/  (admin console) ───────────────────────────────────┐
│  pages/                                                        │
│    BridgeDetailPage.tsx               ┐                        │
│    KnowledgePointDetailPage.tsx       ├─ embed <TranslationCell>│
│    translations/TranslationsList.tsx  ┘                        │
│       ↳ remove dialog; row click → deep-link                   │
│                                                                │
│  components/translations/         ◀── new directory            │
│    TranslationCell.tsx                                         │
│    TranslationStatusBadge.tsx                                  │
│    KeyPointTranslationRow.tsx                                  │
└──────────────────┬─────────────────────────────────────────────┘
                   │ /api/v1/translations/*  (existing + 1 new endpoint)
                   ▼
┌─ RAG/  (FastAPI) ──────────────────────────────────────────────┐
│  app/services/translation_service.py                           │
│    TRANSLATABLE_FIELDS  ←  add knowledge_point_key_points       │
│    _model_registry      ←  add KnowledgePointKeyPoint           │
│  app/api/v1/translations.py                                    │
│    GET /translations/by-row?table=&row_id=   ←  new            │
│  app/models/knowledge_point.py                                 │
│    KnowledgePointKeyPoint.summary_en, .explanation_en  ← new   │
│  scripts/migrate_db.py                                         │
│    MIGRATIONS[14] = add_summary_en_explanation_en  ← new       │
└────────────────────────────────────────────────────────────────┘
```

Deep-link contract:
- `/bridges/{id}?tr=description_en` — page scrolls to + ring-highlights
  the matching `<TranslationCell>` for 2 s.
- `/knowledge-points/{id}?tr=key_points.{kp_id}.explanation_en` — same,
  for nested KP rows.
- The query-param style is chosen over fragment hash because `useSearchParams`
  re-renders cleanly when the user changes selection within the page.

## 5. Components

### 5.1 New React components — `RAG/web/src/components/translations/`

**`TranslationCell.tsx`** — minimal closed loop for one translatable field.

```ts
interface TranslationCellProps {
  table: TranslatableTable;     // 'bridges' | 'knowledge_points' | ...
  rowId: string;                // UUID of the business row
  fieldName: string;            // *_en column name
  sourceText: string;           // current zh value (for fallback if no review row)
  reviewItem: TranslationReviewItem | null;  // null means no review row yet
  onChange?: (next: TranslationReviewItem) => void;
}
```

Internal state machine maps `reviewItem.status` → button group. All
mutations call existing endpoints:

| Button | Endpoint | Body |
|--------|----------|------|
| `♻ AI 翻译` / `♻ AI 重译` | `POST /translations/generate` | `{table, row_id, field_name}` |
| `✓ 通过` | `PUT /translations/{id}/review` | `{action:'approve'}` |
| `✏ 编辑后通过` | (open inline `<Textarea>`, save →) | `PUT .../review {action:'edit', text}` |
| `✗ 驳回` | `PUT /translations/{id}/review` | `{action:'reject'}` |

**`TranslationStatusBadge.tsx`** — colored dot + label. 4 states.

**`KeyPointTranslationRow.tsx`** — composite row for one
`knowledge_point_key_points` record: `(zh summary | en summary cell) /
(zh explanation | en explanation cell)`. Internally renders 2
`TranslationCell` instances.

### 5.2 Modified pages

**`BridgeDetailPage.tsx`**: replace the current "name" + "description"
display rows with paired `(zh) <TranslationCell />` panels. Add a "相关知识点"
read-only section that shows each linked KP with its 2-status double-dot
(`name_en` + `summary_en`) and a "→ KP 页" button. **Do not** embed editable
KP cells inside the bridge page.

**`KnowledgePointDetailPage.tsx`**: same pairing for `name` + `summary`.
The existing "key points" management region gets a 2-column expansion to
hold `KeyPointTranslationRow`. The flashcards region pairs each
`front_title` and `back_answer` with their `*_en` cells. The "关联桥梁"
region becomes read-only with status badges.

**`pages/translations/TranslationsList.tsx`**: delete `TranslationReviewDialog`
import; replace the row's `[审校]` button with a router link to:

```ts
const target = (row.table_name === 'bridges')
  ? `/bridges/${row.row_id}?tr=${row.field_name}`
  : (row.table_name === 'knowledge_points')
  ? `/knowledge-points/${row.row_id}?tr=${row.field_name}`
  : (row.table_name === 'knowledge_point_key_points')
  ? `/knowledge-points/${row.parent_kp_id}?tr=key_points.${row.row_id}.${row.field_name}`
  : (row.table_name === 'flashcards')
  ? `/knowledge-points/${row.parent_kp_id}?tr=flashcards.${row.row_id}.${row.field_name}`
  : '/translations';
```

**Note**: the `parent_kp_id` for key_points / flashcards is not currently
exposed by `TranslationReviewItem`. The list endpoint must include parent
context for nested types — see §6.2.

### 5.3 Backend changes

**`app/services/translation_service.py`** — extend the registry:

```python
TRANSLATABLE_FIELDS["knowledge_point_key_points"] = [
    ("summary", "summary_en"),
    ("explanation", "explanation_en"),
]
```

```python
def _model_registry() -> dict[str, Any]:
    return {
        "bridges": Bridge,
        "knowledge_points": KnowledgePoint,
        "flashcards": Flashcard,
        "taxonomy_nodes": TaxonomyNode,
        "knowledge_point_key_points": KnowledgePointKeyPoint,  # new
    }
```

**`app/api/v1/translations.py`** — new endpoint:

```python
@router.get("/by-row", response_model=list[TranslationReviewItem])
def list_by_row(
    table: str = Query(...),
    row_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> list[TranslationReviewItem]:
    """Return all translation_reviews rows for a single business row.

    Auto-upserts virtual `human_reviewed` records for legacy rows where
    the business *_en column is populated but no review row exists.
    See §7 'Legacy data without review rows'.
    """
```

**`app/models/knowledge_point.py`** — add nullable `*_en` columns to
`KnowledgePointKeyPoint`. Plain `Mapped[str | None]` — no FK changes.

**`scripts/migrate_db.py`** — register `MIGRATIONS[14]`:

```sql
ALTER TABLE knowledge_point_key_points
  ADD COLUMN IF NOT EXISTS summary_en TEXT,
  ADD COLUMN IF NOT EXISTS explanation_en TEXT;
```

Update `schema_version` to 14.

## 6. Data Flow

### 6.1 Page load (Bridge detail)

```
BridgeDetailPage mount
  ├─ GET /bridges/{id}                      → bridge core
  └─ GET /translations/by-row?              → reviews keyed by field_name:
       table=bridges&row_id={id}                {name_en: review, description_en: review}
  
  for each translatable field:
      <TranslationCell
         table="bridges" rowId={id} fieldName="description_en"
         sourceText={bridge.description}
         reviewItem={reviewsByField['description_en'] ?? null} />
```

For KP detail page, two more by-row calls fan out (one per nested KP /
flashcard parent):

```
KnowledgePointDetailPage mount
  ├─ GET /knowledge-points/{id}             → KP core + key_points + flashcards
  ├─ GET /translations/by-row?
  │     table=knowledge_points&row_id={id}
  ├─ GET /translations/by-row?
  │     table=knowledge_point_key_points&row_id={kp.id}    (×N key_points)
  └─ GET /translations/by-row?
        table=flashcards&row_id={fc.id}                     (×M flashcards)
```

To avoid N+1, **`by-row` MUST accept a list of `row_id`s** as a comma-separated
query param: `row_id=uuid1,uuid2,uuid3`. Implementation uses `IN (...)` filter
and groups response by row_id. This collapses N+M roundtrips to 2.

### 6.2 Row click on central inbox

```
TranslationsList row click
  → resolve target URL by row.table_name (see §5.2)
  → navigate(target)
  → BridgeDetailPage / KnowledgePointDetailPage:
        useSearchParams() → tr param
        useEffect(() => {
          const cell = ref.current?.querySelector(`[data-tr="${tr}"]`)
          cell?.scrollIntoView({behavior:'smooth'})
          cell?.classList.add('ring-highlight')
          setTimeout(() => cell?.classList.remove('ring-highlight'), 2000)
        }, [tr])
```

### 6.3 Action: AI generate

```
TranslationCell user clicks [♻ AI 翻译]
  ├─ optimistic: setLocalStatus('pending_ai → loading')
  ├─ POST /translations/generate
  │   body {table, row_id, field_name}
  ├─ on success → setReviewItem(resp), status flips to ai_generated
  └─ on failure → setLocalStatus(prev), toast(error.detail)
```

### 6.4 Action: approve / edit / reject

```
[✓ 通过]:                PUT /translations/{id}/review {action:'approve'}
[✏ 编辑后通过]:          inline <Textarea> opens, prefilled with ai_translation
                         user edits → [保存]
                         PUT .../review {action:'edit', text}
[✗ 驳回]:                PUT /translations/{id}/review {action:'reject'}

  on success (approve/edit only):
    parent page must refetch business row (bridges.description_en is
    now populated). Use a per-cell onChange callback that bubbles up
    to the page-level useApi refetch.
```

## 7. Error Handling

| Scenario | Handling |
|----------|----------|
| LLM call failure during `POST /generate` | Service leaves status `pending_ai`; cell shows red error band + `[♻ 重试]`. No partial write. |
| Concurrent approval (another admin already approved) | PUT returns 404 "review state mismatch" (or 409). Cell shows toast "已被其他管理员处理"; trigger by-row refetch. |
| **Legacy data**: business row has `*_en` populated but no `translation_reviews` row | `GET /by-row` auto-upserts a `status=human_reviewed`, `reviewed_translation=<the *_en value>`, `source_text=<current zh>`, `reviewed_by='legacy'` virtual record so the cell renders 🟢 immediately. The DB write is idempotent under the unique constraint `(table_name, row_id, field_name)`. |
| Front-end deployed before schema v14 migration ran | Backend returns 400 "Unknown translatable table" for `knowledge_point_key_points` rows. `TranslationCell` catches and renders disabled "翻译功能未启用" placeholder; rest of page is unaffected. |
| zh source text mutated since review created | Existing `_get_or_create_review_row` already auto-syncs `source_text` if it differs (`translation_service.py:260`). Surfacing this in UI: when zh changes, cell silently re-renders with the new `sourceText` prop; the cached AI translation is not invalidated unless the admin clicks `♻ AI 重译`. |
| User clicks `♻ AI 重译` on a `rejected` cell | Backend currently short-circuits when status is `rejected`. **Fix**: change `generate_for_row` short-circuit guard from `{HUMAN_REVIEWED, REJECTED}` to `{HUMAN_REVIEWED}`. Rejected → re-translation must work (otherwise rejected rows are dead-end). |

## 8. Schema Migration v14

```python
# scripts/migrate_db.py
def migrate_v13_to_v14(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE knowledge_point_key_points
              ADD COLUMN IF NOT EXISTS summary_en     TEXT,
              ADD COLUMN IF NOT EXISTS explanation_en TEXT
        """))
        conn.execute(text("""
            INSERT INTO schema_version (version, description)
            VALUES (14, 'Add *_en columns to knowledge_point_key_points')
        """))

MIGRATIONS[14] = migrate_v13_to_v14
```

No backfill needed — empty `*_en` columns naturally fall into the
`pending_ai` state via `by-row`'s lazy upsert path.

Forward compatibility: v13 servers will continue to ignore the new
columns (SQLAlchemy unmapped). Reverse compatibility: `DROP COLUMN`
rollback would lose any reviewed translations — flagged in
`docs/plans/.../rollout.md` as a non-trivial rollback.

## 9. Testing

### 9.1 Backend (pytest)

| File | Purpose |
|------|---------|
| `tests/test_translation_service.py` | `TRANSLATABLE_FIELDS` includes `knowledge_point_key_points`; `generate_for_row` works on it; `rejected` → re-translation path passes |
| `tests/test_models_batch_X.py` | `schema_version == 14`; `KnowledgePointKeyPoint.summary_en` + `.explanation_en` are mapped |
| `tests/integration/test_translations_api.py` | `GET /by-row` returns all reviews for one row; multi-`row_id` request batches correctly; legacy-data auto-upsert produces `human_reviewed` virtual rows |
| `tests/test_migrations.py` | v13 → v14 migration is idempotent; columns nullable TEXT |

### 9.2 Frontend (vitest)

| File | Purpose |
|------|---------|
| `TranslationCell.test.tsx` | Each of the 4 statuses renders the correct button group; mutations call the right endpoint; optimistic rollback on failure |
| `KeyPointTranslationRow.test.tsx` | 4 cells (zh/en × summary/explanation) render independently; updates don't cross-contaminate |
| `BridgeDetailPage.test.tsx` | `?tr=description_en` triggers `scrollIntoView` + ring class on the matching cell |
| `KnowledgePointDetailPage.test.tsx` | `?tr=key_points.{kp_id}.explanation_en` resolves to the nested cell |

### 9.3 Manual smoke

1. Bridge page: trigger AI for `description_en` → approve → reload page → confirm `bridges.description_en` is populated.
2. KP page: edit a key point's `explanation_en`, save → confirm `knowledge_point_key_points.explanation_en` is populated.
3. From central `/translations`, click any row → confirm landing on the right page with the right cell highlighted.
4. Reject a row, then click `♻ AI 重译` → confirm new AI run produces fresh content.

## 10. Rollout

Phase order — each must ship green tests before next:

1. **Schema v14** (RAG): migration + model field + tests. Deploy to prod
   first; columns are additive, zero downtime.
2. **Backend `TRANSLATABLE_FIELDS` + `by-row` endpoint** (RAG): make new
   fields translatable; expose batch-row read.
3. **Frontend `TranslationCell` + business-page integration**
   (RAG/web): land all UI changes; ship dialog removal in same PR so
   `/translations` doesn't break mid-deploy.
4. **Audit** (post-deploy): seed a few `legacy data` rows in staging and
   confirm `by-row` upsert promotes them to `human_reviewed` correctly.

## 11. Out of Scope

- **Image caption translation** (`bridge_images.caption`): not in
  `TRANSLATABLE_FIELDS` today, not added by this design. Captions are
  short and frequently edited; revisit when there's user demand.
- **Static UI message i18n** (`app/locales/{zh,en}_us.py`): unrelated to
  this work; covered by the Phase 1 implementation already shipped.
- **Taxonomy lvl3 in-place review on the taxonomy tree page**: bridge /
  KP pages already cover the high-traffic types. Taxonomy editing
  remains in the central queue for now.
- **JWT `preferred_locale` wiring**: still a Phase 2 hook; orthogonal
  to this redesign.
- **C-end (`web/`) impact**: zero. The C-end consumes `*_en` columns
  read-only via `/v1/*`; this redesign only changes how those columns
  get populated.

## 12. References

- `RAG/CLAUDE.md` — i18n + glossary + LLM routing gotchas
- `RAG/app/services/translation_service.py` —审校 service that this
  design extends
- `RAG/app/api/v1/translations.py` — existing admin API surface
- `docs/plans/2026-04-19-unified-auth-design.md` — auth context for
  `reviewed_by` (Better Auth string IDs)
- `docs/plans/2026-04-20-i18n-phase3-db-review.md` — Phase 3 ledger
  (translation_reviews table origin)
