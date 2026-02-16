# P1 Design: Sources, Taxonomy, Bridge Merge, Dashboard Charts

**Date:** 2026-02-16
**Status:** Approved
**Depends on:** P0 Admin Dashboard (PR #8, merged)

---

## Scope

P1 delivers 4 independent feature slices:

| Slice | Feature | Risk |
|-------|---------|------|
| 1 | Sources browsing (list + detail) | Low |
| 2 | Taxonomy CRUD + yaml-to-DB migration | High |
| 3 | Bridge merge | Medium |
| 4 | Dashboard recharts upgrade | Low |

Each slice includes backend + frontend, ships as an independent PR.

---

## Slice 1: Sources Browsing

### Backend

**New file:** `app/api/v1/sources.py`

```
GET /api/v1/sources?page&page_size&q&type
    -> PaginatedResponse<SourceListItem>

GET /api/v1/sources/{id}
    -> SourceDetail
```

**New schema:** `app/api/v1/schemas/source.py`

```python
class SourceListItem(BaseModel):
    id: int
    type: str          # pdf | web | note
    title: str
    url: str | None
    chunk_count: int
    created_at: datetime

class SourceDetail(BaseModel):
    id: int
    type: str
    title: str
    url: str | None
    file_path: str | None
    accessed_at: datetime | None
    chunk_count: int
    created_at: datetime
```

Source is read-only (created by ingest flow). The detail page shows associated chunks via the existing `GET /api/v1/chunks?source_id=X` endpoint.

### Frontend

- `SourceListPage` — Table (type tag + title + chunk_count + created_at) + search + type filter
- `SourceDetailPage` — Metadata card at top + ChunkTable below (filtered by source_id)

### Route Registration

Add `sources_router` to `app/api/v1/__init__.py`. Add `/sources` and `/sources/:id` to router.tsx.

---

## Slice 2: Taxonomy CRUD + Migration

### Data Migration: yaml -> DB

**Current state:**
- `taxonomy.yaml` -> `constants.py` `@lru_cache load_taxonomy()` -> `tagger.py`
- `taxonomy_nodes` table exists but unused by business code

**Target state:**
- `taxonomy_nodes` table is the source of truth
- `constants.py` functions read from DB via `taxonomy_loader`
- `taxonomy.yaml` retained as initialization seed only
- `tagger.py` unchanged (calls constants.py functions)

**Migration steps:**
1. New module `app/core/taxonomy_loader.py` — reads taxonomy from DB, module-level cache with manual invalidation
2. Modify `constants.py` — `load_taxonomy()` etc. delegate to `taxonomy_loader`
3. Add seed logic — on startup, if `taxonomy_nodes` is empty, seed from yaml
4. Retain `taxonomy.yaml` as fallback seed file

**Cache strategy:** Module-level dict variable + `invalidate_taxonomy_cache()` function called after any CRUD operation. More flexible than `@lru_cache` for mutable data.

### Backend API

**New file:** `app/api/v1/taxonomy.py`

```
GET    /api/v1/taxonomy/tree
       -> TaxonomyTree (nested structure with per-node chunk_count)

POST   /api/v1/taxonomy/nodes
       <- {lvl1, lvl2?, lvl3?, description?}
       -> TaxonomyNodeDetail

PUT    /api/v1/taxonomy/nodes/{id}
       <- {description?}
       -> TaxonomyNodeDetail

DELETE /api/v1/taxonomy/nodes/{id}
       -> 204 (only if no chunks reference this node)

POST   /api/v1/taxonomy/batch-update
       <- {chunk_ids: [int], lvl1: str, lvl2?: str, lvl3?: str}
       -> {updated_count: int}
```

**New schema:** `app/api/v1/schemas/taxonomy.py`

```python
class TaxonomyNodeDetail(BaseModel):
    id: int
    lvl1: str
    lvl2: str | None
    lvl3: str | None
    description: str | None
    chunk_count: int

class TaxonomyTreeItem(BaseModel):
    label: str
    chunk_count: int
    children: list["TaxonomyTreeItem"]

class TaxonomyTree(BaseModel):
    items: list[TaxonomyTreeItem]

class TaxonomyBatchUpdate(BaseModel):
    chunk_ids: list[int]
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None

class TaxonomyBatchUpdateResult(BaseModel):
    updated_count: int
```

**Key decisions:**
- Node creation specifies lvl1/lvl2/lvl3 path directly (fixed 3-level depth, no parent_id)
- PUT only changes description, not path (moving nodes would break chunk associations)
- DELETE protected: fails if any chunk's lvl1/lvl2/lvl3 matches this node
- batch-update is the core operation: select multiple chunks, assign taxonomy labels

### Frontend

- `TaxonomyPage` — Left sidebar: TaxonomyTree + Right content: chunk list
- `TaxonomyTree` component — 3-level expandable tree, each node shows name + chunk_count badge
- Click leaf node -> right side shows chunks with that classification (reuse ChunkTable)
- Node actions: add child, edit description, delete
- Toolbar: batch-update (select chunks -> assign new taxonomy)

---

## Slice 3: Bridge Merge

### Backend

**Modify:** `app/api/v1/bridges.py`, add endpoint:

```
POST /api/v1/bridges/{target_id}/merge
     <- {source_bridge_id: int}
     -> BridgeDetail (target bridge, updated)
```

**New schema addition:** `BridgeMergeRequest` in `schemas/bridge.py`

```python
class BridgeMergeRequest(BaseModel):
    source_bridge_id: int
```

**Merge logic (single transaction):**
1. Update all chunks where `bridge_id = source_id` -> set `bridge_id = target_id`
2. Migrate all `chunk_bridge_links` from source -> target (skip duplicates: same chunk_id already linked to target)
3. Append source's `aliases` to target's `aliases`; also add source's `name` to target's `aliases`
4. Delete source bridge
5. Return updated target bridge detail

**Validation:**
- source_bridge_id must exist and differ from target_id
- Both bridges must exist; 404 if not found

### Frontend

- **`BridgeMergeDialog`** — Triggered by "Merge" button on BridgeDetailPage
- Dialog content: search dropdown to select source bridge, preview info (source chunk count, what will be migrated)
- Confirm -> execute merge -> refetch current bridge detail
- Destructive action: red confirm button with warning text

---

## Slice 4: Dashboard Recharts Upgrade

### Changes

- **New dependency:** `recharts`
- **Binding status:** Replace CSS `DistributionBar` -> recharts `PieChart` (with labels + legend)
- **Lvl1 distribution:** Replace inline CSS progress bars -> recharts `BarChart` (horizontal bars)
- **Unchanged:** StatCards, IngestTimeline, LoadingState

### New Components

- `BindingPieChart.tsx` — Replaces DistributionBar usage in DashboardPage
- `Lvl1BarChart.tsx` — Replaces inline CSS progress bars in DashboardPage

### Color Mapping

Binding status colors (matching design doc palette):
- primary: `#16A34A` (green-600)
- ambiguous: `#D97706` (amber-600)
- none: `#D6D3D1` (stone-300)

---

## File Inventory

### Slice 1 (Sources)
| Type | File | Action |
|------|------|--------|
| Backend | `app/api/v1/sources.py` | New |
| Schema | `app/api/v1/schemas/source.py` | New |
| Route | `app/api/v1/__init__.py` | Modify |
| Frontend | `web/src/pages/SourceListPage.tsx` | New |
| Frontend | `web/src/pages/SourceDetailPage.tsx` | New |
| API/Types | `web/src/lib/api.ts`, `web/src/lib/types.ts` | Modify |
| Router | `web/src/router.tsx` | Modify |

### Slice 2 (Taxonomy)
| Type | File | Action |
|------|------|--------|
| Core | `app/core/taxonomy_loader.py` | New |
| Core | `app/core/constants.py` | Modify |
| Backend | `app/api/v1/taxonomy.py` | New |
| Schema | `app/api/v1/schemas/taxonomy.py` | New |
| Route | `app/api/v1/__init__.py` | Modify |
| Seed | `app/core/database.py` or startup hook | Modify |
| Frontend | `web/src/pages/TaxonomyPage.tsx` | New |
| Frontend | `web/src/components/taxonomy/TaxonomyTree.tsx` | New |
| API/Types | `web/src/lib/api.ts`, `web/src/lib/types.ts` | Modify |
| Router | `web/src/router.tsx` | Modify |

### Slice 3 (Bridge Merge)
| Type | File | Action |
|------|------|--------|
| Backend | `app/api/v1/bridges.py` | Modify |
| Schema | `app/api/v1/schemas/bridge.py` | Modify |
| Frontend | `web/src/components/bridges/BridgeMergeDialog.tsx` | New |
| Frontend | `web/src/pages/BridgeDetailPage.tsx` | Modify |
| API/Types | `web/src/lib/api.ts`, `web/src/lib/types.ts` | Modify |

### Slice 4 (Dashboard Recharts)
| Type | File | Action |
|------|------|--------|
| Dependency | `web/package.json` | Modify |
| Frontend | `web/src/components/dashboard/BindingPieChart.tsx` | New |
| Frontend | `web/src/components/dashboard/Lvl1BarChart.tsx` | New |
| Frontend | `web/src/pages/DashboardPage.tsx` | Modify |

---

## Testing

### Backend
```bash
pytest tests/ -v                          # Regression
pytest tests/test_api_v1_sources.py -v    # Slice 1
pytest tests/test_api_v1_taxonomy.py -v   # Slice 2
pytest tests/test_api_v1_bridges.py -v    # Slice 3 (merge tests)
```

### Frontend
```bash
cd web && npm run build    # Type check + build
npm run dev                # Manual verification
```
