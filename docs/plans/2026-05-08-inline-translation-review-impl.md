# Inline Translation Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Distribute translation审校 from the centralized `/translations` dialog
to inline `TranslationCell` components on Bridge / Knowledge Point detail
pages; central page kept as queue + coverage dashboard. Schema v14 adds
`*_en` columns to `knowledge_point_key_points` so 要点 fields become
translatable.

**Architecture:** Frontend builds a reusable `<TranslationCell>` that renders
one en field with status-driven action buttons; pages slot it next to each
zh display. Backend adds a `GET /translations/by-row` batched read so a page
loads all its review rows in one shot, plus a small set of changes
(TRANSLATABLE_FIELDS extension, rejected→re-translation fix, schema v14).

**Tech Stack:** FastAPI · SQLAlchemy · pgvector PostgreSQL · React 19 · Vite ·
shadcn/ui · TanStack Query (existing `useApi` hook)

**Design doc:** `@RAG/docs/plans/2026-05-08-inline-translation-review-design.md`

**Worktree:** Run in a dedicated git worktree off `RAG/` `main`, e.g.
`git worktree add .worktrees/inline-translation-review main` —
schema migration is additive so no DB conflict with main, but UI work
benefits from isolation against unrelated dev.

**Repo:** All paths below are relative to `RAG/` unless otherwise noted.

---

## Phase 1 — Schema v14 (additive migration)

### Task 1: Add `summary_en` + `explanation_en` to `KnowledgePointKeyPoint`

**Files:**
- Modify: `app/models/knowledge_point.py` (the `KnowledgePointKeyPoint` class)
- Test: `tests/test_models_knowledge_point.py`

**Step 1: Write failing test**

```python
# tests/test_models_knowledge_point.py — append
def test_key_point_has_en_translation_columns():
    """Phase v14: knowledge_point_key_points carries summary_en + explanation_en."""
    from app.models.knowledge_point import KnowledgePointKeyPoint
    assert "summary_en" in KnowledgePointKeyPoint.__table__.columns
    assert "explanation_en" in KnowledgePointKeyPoint.__table__.columns
    # Both nullable — migration is additive, populated lazily via translation flow
    assert KnowledgePointKeyPoint.__table__.columns["summary_en"].nullable
    assert KnowledgePointKeyPoint.__table__.columns["explanation_en"].nullable
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_models_knowledge_point.py::test_key_point_has_en_translation_columns -v
# Expected: FAIL — KeyError: 'summary_en'
```

**Step 3: Add the columns**

In `app/models/knowledge_point.py`, on the `KnowledgePointKeyPoint` class:

```python
summary_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
explanation_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

**Step 4: Run test, expect PASS**

```
pytest tests/test_models_knowledge_point.py::test_key_point_has_en_translation_columns -v
```

**Step 5: Commit**

```bash
git add app/models/knowledge_point.py tests/test_models_knowledge_point.py
git commit -m "feat(models): add summary_en + explanation_en to knowledge_point_key_points"
```

---

### Task 2: Add migration v14 to `migrate_db.py`

**Files:**
- Modify: `scripts/migrate_db.py` (`MIGRATIONS` dict)
- Test: `tests/test_migrations.py`

**Step 1: Write failing test**

```python
# tests/test_migrations.py — append
def test_migration_v14_adds_kp_en_columns(real_db):
    """v13 → v14 adds nullable summary_en + explanation_en, idempotent."""
    from sqlalchemy import text
    from scripts.migrate_db import MIGRATIONS

    engine = real_db.get_bind()
    # Drop columns if present (test isolation against earlier runs)
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE knowledge_point_key_points
              DROP COLUMN IF EXISTS summary_en,
              DROP COLUMN IF EXISTS explanation_en
        """))

    MIGRATIONS[14](engine)
    # Idempotency: re-running should not raise.
    MIGRATIONS[14](engine)

    with engine.connect() as conn:
        cols = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='knowledge_point_key_points'"
        ))}
        assert "summary_en" in cols
        assert "explanation_en" in cols

        ver = conn.execute(text(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )).scalar_one()
        assert ver == 14
```

**Step 2: Run test, expect FAIL**

```
pytest tests/test_migrations.py::test_migration_v14_adds_kp_en_columns -v
# Expected: FAIL — KeyError: 14
```

**Step 3: Add the migration**

In `scripts/migrate_db.py`:

```python
def migrate_v13_to_v14(engine):
    """v14: add summary_en + explanation_en to knowledge_point_key_points."""
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE knowledge_point_key_points
              ADD COLUMN IF NOT EXISTS summary_en     TEXT,
              ADD COLUMN IF NOT EXISTS explanation_en TEXT
        """))
        # Use ON CONFLICT DO NOTHING so re-runs don't violate PK
        conn.execute(text("""
            INSERT INTO schema_version (version, description)
            VALUES (14, 'Add *_en columns to knowledge_point_key_points')
            ON CONFLICT (version) DO NOTHING
        """))


MIGRATIONS[14] = migrate_v13_to_v14
```

**Step 4: Run test, expect PASS**

```
pytest tests/test_migrations.py::test_migration_v14_adds_kp_en_columns -v
```

**Step 5: Commit**

```bash
git add scripts/migrate_db.py tests/test_migrations.py
git commit -m "feat(migrations): v14 adds *_en columns to knowledge_point_key_points"
```

---

### Task 3: Bump `schema_version` test + freshness guard

**Files:**
- Modify: `tests/test_models_batch2.py` (or wherever
  `test_schema_version_is_N` lives — `git grep -n test_schema_version_is_`)
- Modify: `app/core/database.py` if there's a `CURRENT_SCHEMA_VERSION` const
- Test: existing test, just bump the constant

**Step 1: Find the test pinning current version**

```
git grep -n "test_schema_version_is_" tests/
```

**Step 2: Update the assertion**

Replace `assert current == 13` with `assert current == 14`. Same for any
`CURRENT_SCHEMA_VERSION = 13` constant in `app/core/database.py` if one
exists.

**Step 3: Run test, expect PASS**

```
pytest tests/test_models_batch2.py -k schema_version -v
```

**Step 4: Commit**

```bash
git add tests/ app/core/database.py
git commit -m "chore(schema): bump current schema version to 14"
```

---

## Phase 2 — Backend Translation Service Changes

### Task 4: Extend `TRANSLATABLE_FIELDS` + `_model_registry`

**Files:**
- Modify: `app/services/translation_service.py:80-98`
- Test: `tests/test_translation_service.py`

**Step 1: Write failing test**

```python
def test_translatable_fields_includes_key_points():
    from app.services.translation_service import TRANSLATABLE_FIELDS, _model_registry
    from app.models import KnowledgePointKeyPoint

    assert "knowledge_point_key_points" in TRANSLATABLE_FIELDS
    pairs = TRANSLATABLE_FIELDS["knowledge_point_key_points"]
    assert ("summary", "summary_en") in pairs
    assert ("explanation", "explanation_en") in pairs

    assert _model_registry()["knowledge_point_key_points"] is KnowledgePointKeyPoint
```

**Step 2: Run, expect FAIL**

```
pytest tests/test_translation_service.py::test_translatable_fields_includes_key_points -v
```

**Step 3: Implement**

In `app/services/translation_service.py`:

```python
TRANSLATABLE_FIELDS: dict[str, list[tuple[str, str]]] = {
    "bridges": [("name", "name_en"), ("description", "description_en")],
    "knowledge_points": [("name", "name_en"), ("summary", "summary_en")],
    "flashcards": [
        ("front_title", "front_title_en"),
        ("back_answer", "back_answer_en"),
    ],
    "taxonomy_nodes": [("lvl3", "name_en")],
    "knowledge_point_key_points": [   # new in v14
        ("summary", "summary_en"),
        ("explanation", "explanation_en"),
    ],
}


def _model_registry() -> dict[str, Any]:
    from app.models import KnowledgePointKeyPoint  # local import to avoid cycles
    return {
        "bridges": Bridge,
        "knowledge_points": KnowledgePoint,
        "flashcards": Flashcard,
        "taxonomy_nodes": TaxonomyNode,
        "knowledge_point_key_points": KnowledgePointKeyPoint,
    }
```

If `KnowledgePointKeyPoint` is not exported from `app/models/__init__.py`,
also add it to `__all__` there.

**Step 4: Run all translation_service tests, expect PASS**

```
pytest tests/test_translation_service.py -v
```

**Step 5: Commit**

```bash
git add app/services/translation_service.py app/models/__init__.py tests/test_translation_service.py
git commit -m "feat(translation): register knowledge_point_key_points as translatable"
```

---

### Task 5: Allow re-translation of `rejected` rows

**Files:**
- Modify: `app/services/translation_service.py` `generate_for_row` short-circuit (around line 327)
- Test: `tests/test_translation_service.py`

**Step 1: Write failing test**

```python
async def test_rejected_can_be_retranslated(db_session):
    from app.services.translation_service import generate_for_row
    from app.models.translation_review import (
        TranslationReview, TRANSLATION_STATUS_REJECTED, TRANSLATION_STATUS_AI_GENERATED,
    )
    # Create a rejected review on bridges.description_en
    bridge = make_bridge(db_session, description="赵州桥位于河北省赵县。")
    review = TranslationReview(
        table_name="bridges", row_id=bridge.id, field_name="description_en",
        source_text=bridge.description, ai_translation="OLD AI OUTPUT",
        status=TRANSLATION_STATUS_REJECTED,
    )
    db_session.add(review); db_session.flush()

    # Retranslate — should overwrite ai_translation and flip to ai_generated
    result = await generate_for_row(
        db_session, table_name="bridges", row_id=bridge.id,
        field_name="description_en", source_text=bridge.description,
    )
    assert result.status == TRANSLATION_STATUS_AI_GENERATED
    assert result.ai_translation != "OLD AI OUTPUT"
```

(`make_bridge` is whatever the existing test helpers expose — see
`conftest.py` / `tests/factories.py`. Mock the LLM via the
`fast_retry_provider` / patched `chat_for_task` pattern in
`tests/test_providers.py`.)

**Step 2: Run, expect FAIL** (current code returns the row unchanged when
status is `rejected`).

**Step 3: Fix the guard**

In `app/services/translation_service.py` around the existing block:

```python
# OLD:
if review.status in {
    TRANSLATION_STATUS_HUMAN_REVIEWED,
    TRANSLATION_STATUS_REJECTED,
}:
    return review

# NEW: only `human_reviewed` short-circuits. `rejected` should be re-translatable.
if review.status == TRANSLATION_STATUS_HUMAN_REVIEWED:
    return review
```

**Step 4: Run, expect PASS**

```
pytest tests/test_translation_service.py::test_rejected_can_be_retranslated -v
```

**Step 5: Commit**

```bash
git add app/services/translation_service.py tests/test_translation_service.py
git commit -m "fix(translation): allow re-translation of rejected reviews"
```

---

### Task 6: Add `GET /translations/by-row` endpoint (single + multi row_id)

**Files:**
- Modify: `app/api/v1/translations.py`
- Modify: `app/api/v1/schemas/translation.py` (add response shape if needed)
- Test: `tests/integration/test_translations_api.py`

**Step 1: Write failing test**

```python
def test_by_row_returns_all_reviews_for_a_row(client, real_db, admin_token):
    bridge = make_bridge(real_db, description="赵州桥...")
    # Seed two reviews for the same bridge
    for field, status in [("name_en", "ai_generated"), ("description_en", "pending_ai")]:
        real_db.add(TranslationReview(
            table_name="bridges", row_id=bridge.id, field_name=field,
            source_text="src", status=status,
        ))
    real_db.commit()

    resp = client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={bridge.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    by_field = {it["field_name"]: it for it in items}
    assert by_field["name_en"]["status"] == "ai_generated"
    assert by_field["description_en"]["status"] == "pending_ai"


def test_by_row_supports_multiple_row_ids(client, real_db, admin_token):
    b1 = make_bridge(real_db); b2 = make_bridge(real_db)
    for b in (b1, b2):
        real_db.add(TranslationReview(
            table_name="bridges", row_id=b.id, field_name="name_en",
            source_text="src", status="pending_ai",
        ))
    real_db.commit()

    resp = client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={b1.id},{b2.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert {it["row_id"] for it in items} == {str(b1.id), str(b2.id)}
```

**Step 2: Run, expect FAIL** (404 not found)

**Step 3: Implement**

In `app/api/v1/translations.py`:

```python
from uuid import UUID

@router.get("/by-row", response_model=list[TranslationReviewItem])
def list_by_row(
    table: str = Query(..., min_length=1),
    row_id: str = Query(..., description="UUID, or comma-separated UUIDs"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TranslationReviewItem]:
    """Return all translation_reviews rows for one or more business rows.

    Used by Bridge / KP detail pages to populate inline cells in a single
    request. See docs/plans/2026-05-08-inline-translation-review-design.md §6.1.
    """
    if table not in TRANSLATABLE_FIELDS:
        raise HTTPException(400, detail=f"Unknown translatable table: {table}")

    try:
        ids = [UUID(s.strip()) for s in row_id.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(400, detail="Invalid row_id format")
    if not ids or len(ids) > 50:
        raise HTTPException(400, detail="row_id must be 1..50 UUIDs")

    rows = (
        db.query(TranslationReview)
        .filter(
            TranslationReview.table_name == table,
            TranslationReview.row_id.in_(ids),
        )
        .order_by(TranslationReview.field_name)
        .all()
    )
    return [_to_item(r) for r in rows]
```

**Step 4: Run, expect PASS**

```
pytest tests/integration/test_translations_api.py -k by_row -v
```

**Step 5: Commit**

```bash
git add app/api/v1/translations.py tests/integration/test_translations_api.py
git commit -m "feat(translations): GET /translations/by-row batched read"
```

---

### Task 7: Auto-upsert virtual `human_reviewed` for legacy rows

**Files:**
- Modify: `app/api/v1/translations.py` `list_by_row`
- Test: `tests/integration/test_translations_api.py`

**Step 1: Write failing test**

```python
def test_by_row_upserts_virtual_human_reviewed_for_legacy_data(client, real_db, admin_token):
    """A bridge with description_en already populated but no review row
    should yield a synthetic human_reviewed entry from /by-row."""
    bridge = make_bridge(
        real_db,
        description="赵州桥...",
        description_en="Zhaozhou Bridge is...",  # legacy populated
    )
    # No TranslationReview row exists for this combo
    real_db.commit()

    resp = client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={bridge.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    description_review = next(
        (i for i in items if i["field_name"] == "description_en"), None,
    )
    assert description_review is not None, "expected synthetic review for legacy en"
    assert description_review["status"] == "human_reviewed"
    assert description_review["reviewed_translation"] == "Zhaozhou Bridge is..."
    assert description_review["reviewed_by"] == "legacy"

    # Idempotent: a second call should not create duplicates
    real_db.expire_all()
    resp2 = client.get(
        f"/api/v1/translations/by-row?table=bridges&row_id={bridge.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len([i for i in resp2.json() if i["field_name"] == "description_en"]) == 1
```

**Step 2: Run, expect FAIL**

**Step 3: Add the upsert logic**

Refactor `list_by_row` to compute "expected fields - present fields" and
upsert virtual reviews:

```python
@router.get("/by-row", response_model=list[TranslationReviewItem])
def list_by_row(...):
    # ...validation as before...

    rows = db.query(TranslationReview).filter(
        TranslationReview.table_name == table,
        TranslationReview.row_id.in_(ids),
    ).all()
    by_key = {(r.row_id, r.field_name): r for r in rows}

    # For each business row, check each translatable field; if the *_en column
    # is populated but no review exists, upsert a virtual `human_reviewed` row.
    model_cls = _MODEL_BY_TABLE[table]
    fields = TRANSLATABLE_FIELDS[table]
    business_rows = db.query(model_cls).filter(model_cls.id.in_(ids)).all()

    created = []
    for biz in business_rows:
        for source_field, target_field in fields:
            if (biz.id, target_field) in by_key:
                continue
            target_value = getattr(biz, target_field, None)
            if not target_value:
                continue  # truly pending — leave for client to render as 🔴
            source_value = getattr(biz, source_field, None) or ""
            virtual = TranslationReview(
                table_name=table,
                row_id=biz.id,
                field_name=target_field,
                source_text=source_value,
                ai_translation=None,
                reviewed_translation=target_value,
                status=TRANSLATION_STATUS_HUMAN_REVIEWED,
                reviewed_by="legacy",
                reviewed_at=datetime.now(timezone.utc),
            )
            db.add(virtual)
            created.append(virtual)

    if created:
        # IntegrityError-safe: catch unique violation in case another request
        # raced us, then re-read.
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    rows = db.query(TranslationReview).filter(
        TranslationReview.table_name == table,
        TranslationReview.row_id.in_(ids),
    ).order_by(TranslationReview.field_name).all()

    return [_to_item(r) for r in rows]
```

(Imports needed: `from datetime import datetime, timezone`,
`from sqlalchemy.exc import IntegrityError`,
`from app.models.translation_review import TRANSLATION_STATUS_HUMAN_REVIEWED`.)

**Step 4: Run both by-row tests, expect PASS**

```
pytest tests/integration/test_translations_api.py -k by_row -v
```

**Step 5: Commit**

```bash
git add app/api/v1/translations.py tests/integration/test_translations_api.py
git commit -m "feat(translations): auto-upsert virtual review for legacy *_en data"
```

---

## Phase 3 — Frontend reusable components

> All frontend tasks live in `RAG/web/`. `cd RAG/web` for the rest of this
> phase, or run pnpm/npm with `--prefix web/` from `RAG/`.

### Task 8: Create `TranslationStatusBadge`

**Files:**
- Create: `web/src/components/translations/TranslationStatusBadge.tsx`
- Test: `web/src/components/translations/TranslationStatusBadge.test.tsx`

**Step 1: Test**

```tsx
import { render, screen } from "@testing-library/react"
import { TranslationStatusBadge } from "./TranslationStatusBadge"

describe("TranslationStatusBadge", () => {
  it.each([
    ["pending_ai", "待翻译", "bg-red-500"],
    ["ai_generated", "待审校", "bg-yellow-500"],
    ["human_reviewed", "已审校", "bg-green-500"],
    ["rejected", "已驳回", "bg-gray-700"],
  ] as const)("renders %s with correct dot + label", (status, label, dotClass) => {
    render(<TranslationStatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByTestId("tr-status-dot")).toHaveClass(dotClass)
  })
})
```

**Step 2: Run, expect FAIL**

**Step 3: Implement**

```tsx
import type { TranslationStatus } from "@/lib/types"

const PALETTE: Record<TranslationStatus, { dot: string; label: string }> = {
  pending_ai:    { dot: "bg-red-500",    label: "待翻译" },
  ai_generated:  { dot: "bg-yellow-500", label: "待审校" },
  human_reviewed:{ dot: "bg-green-500",  label: "已审校" },
  rejected:      { dot: "bg-gray-700",   label: "已驳回" },
}

export function TranslationStatusBadge({ status }: { status: TranslationStatus }) {
  const { dot, label } = PALETTE[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span data-testid="tr-status-dot" className={`h-2 w-2 rounded-full ${dot}`} />
      <span className="text-muted-foreground">{label}</span>
    </span>
  )
}
```

**Step 4: Test PASS**

**Step 5: Commit**

```bash
git add web/src/components/translations/
git commit -m "feat(web): TranslationStatusBadge component"
```

---

### Task 9: Create `TranslationCell` — state machine + actions

**Files:**
- Create: `web/src/components/translations/TranslationCell.tsx`
- Test: `web/src/components/translations/TranslationCell.test.tsx`
- Modify: `web/src/lib/api.ts` (add `generateTranslation` if missing — verify)

**Step 1: Test (state-by-state)**

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { TranslationCell } from "./TranslationCell"
import * as api from "@/lib/api"
import { vi } from "vitest"

const baseProps = {
  table: "bridges" as const,
  rowId: "00000000-0000-0000-0000-000000000001",
  fieldName: "description_en",
  sourceText: "赵州桥位于河北省赵县。",
}

describe("TranslationCell", () => {
  it("status=pending_ai shows only [AI 翻译] button", () => {
    render(<TranslationCell {...baseProps} reviewItem={null} />)
    expect(screen.getByRole("button", { name: /AI 翻译/ })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /通过/ })).not.toBeInTheDocument()
  })

  it("status=ai_generated shows approve / edit / reject / regenerate", () => {
    render(<TranslationCell {...baseProps} reviewItem={mkReview("ai_generated", "Zhaozhou...")} />)
    expect(screen.getByRole("button", { name: /^通过$/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /编辑后通过/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /驳回/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /AI 重译/ })).toBeInTheDocument()
  })

  it("clicking [AI 翻译] calls generate endpoint and propagates new review", async () => {
    const onChange = vi.fn()
    vi.spyOn(api, "generateTranslation").mockResolvedValue(mkReview("ai_generated", "AI text"))

    render(<TranslationCell {...baseProps} reviewItem={null} onChange={onChange} />)
    fireEvent.click(screen.getByRole("button", { name: /AI 翻译/ }))

    await waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(api.generateTranslation).toHaveBeenCalledWith({
      table_name: "bridges",
      row_id: baseProps.rowId,
      field_name: "description_en",
    })
  })

  it("optimistic update rolls back on failure", async () => {
    const onChange = vi.fn()
    vi.spyOn(api, "reviewTranslation").mockRejectedValue(new Error("boom"))

    render(
      <TranslationCell
        {...baseProps}
        reviewItem={mkReview("ai_generated", "Zhaozhou...")}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /^通过$/ }))

    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument())
    // onChange must NOT be called with a human_reviewed since it failed
    expect(onChange).not.toHaveBeenCalled()
  })
})

function mkReview(status, ai_translation) {
  return {
    id: "rev-1", table_name: "bridges",
    row_id: "00000000-0000-0000-0000-000000000001",
    field_name: "description_en",
    source_text: "src", ai_translation, reviewed_translation: null,
    status, reviewed_by: null, reviewed_at: null,
    created_at: new Date().toISOString(),
  }
}
```

**Step 2: Run, expect FAIL**

**Step 3: Implement** — see design doc §5.1 for the prop interface.
Render the en text (`reviewed_translation ?? ai_translation ?? "—"`),
the `<TranslationStatusBadge>` derived from `reviewItem?.status ?? "pending_ai"`,
a button group selected by status, and an inline `<Textarea>` that toggles
when "编辑后通过" is clicked. Mutations use existing
`generateTranslation`, `reviewTranslation` from `web/src/lib/api.ts`. All
buttons disable while a mutation is in flight; failures `setError(msg)`
and do **not** mutate parent state.

Add a `data-tr={fieldName}` attribute on the root element so
`useScrollToTr` (Task 11) can find it.

**Step 4: All tests PASS**

**Step 5: Commit**

```bash
git add web/src/components/translations/TranslationCell.tsx web/src/components/translations/TranslationCell.test.tsx web/src/lib/api.ts
git commit -m "feat(web): TranslationCell with state-driven action group"
```

---

### Task 10: Create `KeyPointTranslationRow`

**Files:**
- Create: `web/src/components/translations/KeyPointTranslationRow.tsx`
- Test: `web/src/components/translations/KeyPointTranslationRow.test.tsx`

**Step 1: Test**

```tsx
it("renders 4 cells (zh/en × summary/explanation) and isolates updates", () => {
  const onChange = vi.fn()
  render(
    <KeyPointTranslationRow
      keyPoint={{ id: "kp-1", summary: "圆弧", explanation: "几何因素..." }}
      reviews={{
        summary_en: mkReview("ai_generated", "Circular arches..."),
        explanation_en: null,  // pending_ai
      }}
      onChange={onChange}
    />,
  )
  expect(screen.getAllByTestId("tr-status-dot")).toHaveLength(2)
  // Two TranslationCells exist with distinct field names
  expect(screen.getByText("圆弧")).toBeInTheDocument()
  expect(screen.getByText(/Circular arches/)).toBeInTheDocument()
})
```

**Step 2: Run, expect FAIL**

**Step 3: Implement** — 2-row component, each row pairs a zh display with
a `TranslationCell`. Forward `onChange` per-cell with a `field` discriminator.

**Step 4: Test PASS**

**Step 5: Commit**

```bash
git add web/src/components/translations/KeyPointTranslationRow*
git commit -m "feat(web): KeyPointTranslationRow composite for 要点 zh/en pairs"
```

---

### Task 11: Add `useScrollToTr` hook (deep-link target)

**Files:**
- Create: `web/src/hooks/useScrollToTr.ts`
- Test: `web/src/hooks/useScrollToTr.test.tsx`

**Step 1: Test**

```tsx
function Probe() {
  useScrollToTr()
  return <div data-tr="description_en">target</div>
}

it("scrolls to and highlights the cell matching ?tr=", async () => {
  const scrollSpy = vi.fn()
  Element.prototype.scrollIntoView = scrollSpy

  render(<Probe />, { wrapper: ({ children }) => (
    <MemoryRouter initialEntries={["/?tr=description_en"]}>{children}</MemoryRouter>
  )})

  await waitFor(() => expect(scrollSpy).toHaveBeenCalledTimes(1))
  // Highlight class applied
  expect(screen.getByText("target")).toHaveClass("ring-highlight")
})
```

**Step 2: Run, expect FAIL**

**Step 3: Implement**

```ts
import { useEffect } from "react"
import { useSearchParams } from "react-router"

export function useScrollToTr() {
  const [params] = useSearchParams()
  const tr = params.get("tr")
  useEffect(() => {
    if (!tr) return
    const el = document.querySelector(`[data-tr="${CSS.escape(tr)}"]`) as HTMLElement | null
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "center" })
    el.classList.add("ring-highlight")
    const timer = setTimeout(() => el.classList.remove("ring-highlight"), 2000)
    return () => clearTimeout(timer)
  }, [tr])
}
```

Add a `.ring-highlight` utility to `web/src/index.css`:

```css
.ring-highlight {
  @apply ring-2 ring-yellow-400 ring-offset-2 transition-all duration-300;
}
```

**Step 4: Test PASS**

**Step 5: Commit**

```bash
git add web/src/hooks/useScrollToTr.ts web/src/hooks/useScrollToTr.test.tsx web/src/index.css
git commit -m "feat(web): useScrollToTr deep-link helper hook"
```

---

## Phase 4 — Page Integration

### Task 12: Wire `TranslationCell` into Bridge detail (name + description)

**Files:**
- Modify: `web/src/pages/BridgeDetailPage.tsx`
- Modify: `web/src/lib/api.ts` (add `fetchTranslationsByRow` if not yet)
- Test: `web/src/pages/BridgeDetailPage.test.tsx` (create or extend)

**Step 1: Test**

```tsx
it("renders TranslationCell for name_en and description_en", async () => {
  vi.spyOn(api, "fetchBridge").mockResolvedValue(mockBridge)
  vi.spyOn(api, "fetchTranslationsByRow").mockResolvedValue([
    mkReview("ai_generated", "Zhaozhou...", "description_en"),
    mkReview("human_reviewed", "Zhaozhou", "name_en"),
  ])
  render(<BridgeDetailPage />, { wrapper: routeWrapper("/bridges/abc") })

  await waitFor(() => expect(screen.getByText("Zhaozhou...")).toBeInTheDocument())
  // Two cells emit a status dot
  expect(screen.getAllByTestId("tr-status-dot")).toHaveLength(2)
})
```

**Step 2: Implement**

Add a `useApi` call paralleling the bridge fetch:

```tsx
const { data: reviews } = useApi(
  () => fetchTranslationsByRow({ table: "bridges", row_id: id! }),
  [id],
)
const reviewByField = useMemo(
  () => Object.fromEntries((reviews ?? []).map(r => [r.field_name, r])),
  [reviews],
)
```

Then for each translatable field, render the paired layout. Example for
description:

```tsx
<div className="grid grid-cols-2 gap-4">
  <div>
    <Label>简介 (zh)</Label>
    <div className="rounded-md border bg-muted/30 p-3">{bridge.description}</div>
  </div>
  <div>
    <Label>Description (en)</Label>
    <TranslationCell
      table="bridges"
      rowId={bridge.id}
      fieldName="description_en"
      sourceText={bridge.description ?? ""}
      reviewItem={reviewByField["description_en"] ?? null}
      onChange={() => { refetchBridge(); refetchReviews() }}
    />
  </div>
</div>
```

Call `useScrollToTr()` once in the component body.

**Step 3-4: Run tests**

```
npm run test -- BridgeDetailPage
```

**Step 5: Commit**

```bash
git add web/src/pages/BridgeDetailPage.tsx web/src/pages/BridgeDetailPage.test.tsx web/src/lib/api.ts
git commit -m "feat(web): inline TranslationCell on Bridge detail page"
```

---

### Task 13: Add read-only "相关知识点" section to Bridge detail

**Files:**
- Modify: `web/src/pages/BridgeDetailPage.tsx`

**Step 1: Test**

```tsx
it("lists related KPs with status indicators and a link to KP page", async () => {
  vi.spyOn(api, "fetchBridgeKnowledgePoints").mockResolvedValue([
    { id: "kp1", name: "拱圈", name_en: "Arch ring",
      summary: "拱圈是...", summary_en: "The arch ring is..." },
  ])
  render(<BridgeDetailPage />, { wrapper: routeWrapper("/bridges/abc") })
  await waitFor(() => expect(screen.getByText("拱圈")).toBeInTheDocument())
  expect(screen.getByRole("link", { name: /KP 页/ })).toHaveAttribute("href", "/knowledge-points/kp1")
})
```

**Step 2-4: Implement** a small section that fetches related KPs (use
existing `fetchKPBridges` in reverse, or add a dedicated endpoint —
verify what's already in `lib/api.ts`). Render each as:

```
拱圈   Arch ring   🟢🟢   [→ KP 页]
```

The two dots are derived from whether `name_en` and `summary_en` are
populated on the related-KP record (proxy for `human_reviewed`). No
edit affordance — read-only.

**Step 5: Commit**

```bash
git add web/src/pages/BridgeDetailPage.tsx
git commit -m "feat(web): related-KP read-only summary on Bridge detail"
```

---

### Task 14: Wire `TranslationCell` into KP detail (name + summary)

Same shape as Task 12 but for `knowledge_points`. File:
`web/src/pages/KnowledgePointDetailPage.tsx`. Tests follow the same
pattern. Commit:

```bash
git commit -m "feat(web): inline TranslationCell on KP detail page (name + summary)"
```

---

### Task 15: Wire `KeyPointTranslationRow` into KP detail

**Files:**
- Modify: `web/src/pages/KnowledgePointDetailPage.tsx`

**Step 1: Test**

```tsx
it("renders KeyPointTranslationRow for each key point", async () => {
  vi.spyOn(api, "fetchTranslationsByRow")
    .mockResolvedValueOnce([])  // KP-level
    .mockResolvedValueOnce([    // key_points-level (batched multi-id)
      mkReview("ai_generated", "Circular...", "summary_en", "kp-keypoint-1"),
    ])
  render(<KnowledgePointDetailPage />, { wrapper: routeWrapper("/knowledge-points/kp1") })

  await waitFor(() => expect(screen.getAllByTestId("tr-status-dot").length).toBeGreaterThan(0))
})
```

**Step 2-4: Implement** — fetch reviews for all key_points in a single
`fetchTranslationsByRow` call passing the comma-joined ID list. Build
`reviewsByKeyPointId[kpId][field_name]` and pass to each row.

**Step 5: Commit**

```bash
git commit -m "feat(web): KeyPointTranslationRow on KP detail (要点 zh/en)"
```

---

### Task 16: Wire flashcards inline + add related-bridge read-only

**Files:**
- Modify: `web/src/pages/KnowledgePointDetailPage.tsx`

Same pattern: fetch reviews for all flashcards (`fetchTranslationsByRow`
on `flashcards` with comma-joined IDs), render `TranslationCell` for each
of `front_title_en` and `back_answer_en`. Bridge-relations region: render
a read-only list mirroring Task 13's KP one but in reverse direction.

```bash
git commit -m "feat(web): flashcards + related-bridges sections on KP detail"
```

---

### Task 17: Refactor `/translations` page — remove dialog, deep-link rows

**Files:**
- Modify: `web/src/pages/translations/TranslationsList.tsx`
- Delete (or leave dead): `web/src/pages/translations/TranslationReviewDialog.tsx`

**Step 1: Test**

```tsx
it("clicking the action button navigates to the business page with ?tr=", () => {
  vi.spyOn(api, "fetchTranslations").mockResolvedValue({
    items: [{
      id: "r1", table_name: "bridges", row_id: "abc", field_name: "description_en",
      status: "ai_generated", source_text: "...", ai_translation: "...",
      reviewed_translation: null, reviewed_by: null, reviewed_at: null,
      created_at: "2026-05-08",
    }],
    total: 1, page: 1, page_size: 20, total_pages: 1,
  })
  render(<TranslationsList />, { wrapper: routeWrapper("/translations") })

  fireEvent.click(screen.getByRole("link", { name: /审校|前往/ }))
  expect(window.location.href).toContain("/bridges/abc?tr=description_en")
})
```

**Step 2-4: Implement**

Replace the `<Button onClick={() => setDialogItem(row)}>审校</Button>` with a
`<Link to={resolveTarget(row)}>前往审校</Link>` where `resolveTarget`
implements the table-name switch from design doc §5.2.

For nested types (`knowledge_point_key_points`, `flashcards`) the row's
`row_id` is the key_point/flashcard ID, but we need its parent KP ID for
the URL. Two options:

- **Option A (preferred)**: extend backend to include `parent_kp_id` in
  the response when applicable. Adds a join in the list endpoint —
  small cost.
- **Option B**: client looks up the parent via a separate request. N+1.

Pick Option A. Add a corresponding `parent_kp_id: str | None` field to
`TranslationReviewItem` (Pydantic schema + frontend type). For
`knowledge_point_key_points` rows, populate from
`KnowledgePointKeyPoint.knowledge_point_id`. For `flashcards`, from
`Flashcard.knowledge_point_id`. Null for other tables.

This is a small server change — bundle into the same commit:

```bash
git commit -m "feat(translations): deep-link rows to business pages, drop dialog"
```

---

## Phase 5 — Smoke + Doc Sync

### Task 18: Manual smoke checklist

Run on local dev (RAG `uvicorn` + `web/` `npm run dev`):

1. Schema migrated: `python scripts/migrate_db.py` → reports v14.
2. Bridge page on a known bridge:
   - Trigger `[♻ AI 翻译]` for `description_en` → status flips to 🟡.
   - Click `[✏ 编辑后通过]`, edit one word, save → status flips to 🟢.
   - Reload page → `bridges.description_en` reflects the edit.
3. KP page on a known KP with key_points:
   - For one key_point's `explanation_en`, trigger AI → 🟡.
   - Reject it → ⚫.
   - Click `[♻ AI 重译]` on the rejected cell → 🟡 with new content
     (regression guard for Task 5).
4. From `/translations`, click any row → lands on the right business
   page with the correct cell highlighted (yellow ring 2 s).
5. Inspect DB: `SELECT count(*) FROM translation_reviews WHERE
   table_name='knowledge_point_key_points'` ≥ 1.

Document any unexpected behavior in a follow-up issue, do **not**
extend this plan in-place.

---

### Task 19: Update `RAG/CLAUDE.md` gotchas

**Files:**
- Modify: `RAG/CLAUDE.md`

Add a bullet under the Gotchas section, keeping the established voice:

> **Inline translation review (PR #N)** — `TranslationCell` (`RAG/web/src/components/translations/`)
> renders one `*_en` field with status-driven actions. Pages
> (`BridgeDetailPage`, `KnowledgePointDetailPage`) load reviews via
> `GET /translations/by-row?table=&row_id=<csv>` (multi-row batched). Adding
> a new translatable field: (1) extend `TRANSLATABLE_FIELDS` in
> `app/services/translation_service.py`, (2) add `*_en` column via a fresh
> migration, (3) embed `<TranslationCell>` next to the zh display on the
> business page. The central `/translations` page is a queue/dashboard, not
> an editor — its row click deep-links to `/bridges/{id}?tr=<field>`.
> Never re-introduce `TranslationReviewDialog`. Background:
> `docs/plans/2026-05-08-inline-translation-review-{design,impl}.md`.

```bash
git add RAG/CLAUDE.md
git commit -m "docs(claude.md): inline translation review pattern + schema v14"
```

---

## Out-of-band notes

- **Backwards compat**: schema v14 is purely additive; rolling back to v13
  loses any user-reviewed `summary_en` / `explanation_en`. Do not roll back
  without exporting first.
- **CORS**: no new origins introduced; no env changes.
- **Audit trail**: `approve_review` / `reject_review` already audit via
  `AuditService.log` — no change needed.
- **Auth**: all new endpoints inherit admin gating from
  `get_current_user` on the v1 router. Verify before merging by curl-ing
  without a token; expect 401.

---

## Plan Sanity Snapshot

- 19 tasks · TDD on every code change · 1 commit per task
- Backend: 7 tasks (schema + service + API)
- Frontend reusable: 4 tasks (badge / cell / KP row / hook)
- Page integration: 6 tasks
- Smoke + docs: 2 tasks
