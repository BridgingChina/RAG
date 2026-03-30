# Mobile API Spec Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 10 blocking differences between `docs/api-spec.md` and the mobile API implementation so mobile client development can proceed using the spec as source of truth.

**Architecture:** Global error handler (path-scoped to `/api/mobile/`) + per-endpoint response structure adjustments. No database schema changes, no new models.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest

---

### Task 1: Global Mobile Error Handler

**Files:**
- Create: `app/api/mobile/v1/error_handlers.py`
- Modify: `app/main.py:49-51`
- Test: `tests/test_api_mobile_error_handler.py`

**Step 1: Write the failing test**

Create `tests/test_api_mobile_error_handler.py`:

```python
"""Tests for mobile API error response format."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_mobile_404_returns_spec_error_format():
    """Mobile 404 should return {"error": {"code": "NOT_FOUND", "message": "..."}}."""
    resp = client.get("/api/mobile/v1/bridges/00000000-0000-4000-8000-000000000000")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
    # Must NOT have FastAPI's default "detail" key at top level
    assert "detail" not in body


def test_mobile_400_returns_spec_error_format():
    """Mobile 400 should return BAD_REQUEST code."""
    resp = client.get("/api/mobile/v1/bridges/clusters",
                      params={"bounds_ne_lat": 30, "bounds_ne_lng": 120,
                              "bounds_sw_lat": 40, "bounds_sw_lng": 110, "zoom": 5})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "BAD_REQUEST"


def test_admin_api_preserves_default_error_format():
    """Admin API should NOT be affected by the mobile error handler."""
    resp = client.get("/api/v1/chunks/00000000-0000-4000-8000-000000000000",
                      headers={"Authorization": "Bearer invalid"})
    # Admin API returns FastAPI default format (401 with detail)
    assert resp.status_code == 401
    body = resp.json()
    assert "detail" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_error_handler.py -v`
Expected: FAIL — mobile endpoints currently return `{"detail": "..."}` not `{"error": {...}}`

**Step 3: Create the error handler**

Create `app/api/mobile/v1/error_handlers.py`:

```python
"""Mobile API error response handler.

Converts FastAPI's default HTTPException format to the mobile API spec format:
{"error": {"code": "NOT_FOUND", "message": "桥梁不存在"}}

Only applies to requests under /api/mobile/ — admin API is unaffected.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def register_mobile_error_handlers(app: FastAPI) -> None:
    """Register exception handlers that only affect mobile API routes."""

    @app.exception_handler(HTTPException)
    async def mobile_http_exception_handler(request: Request, exc: HTTPException):
        if not request.url.path.startswith("/api/mobile/"):
            # Preserve default FastAPI behavior for non-mobile routes
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )
        code = STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": exc.detail}},
        )
```

**Step 4: Register in main.py**

In `app/main.py`, after line 51 (`app.add_exception_handler(RateLimitExceeded, ...)`), add:

```python
from app.api.mobile.v1.error_handlers import register_mobile_error_handlers
register_mobile_error_handlers(app)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_mobile_error_handler.py -v`
Expected: All 3 tests PASS

**Step 6: Run existing tests to verify no regressions**

Run: `pytest tests/ -v --timeout=30`
Expected: No new failures

**Step 7: Commit**

```bash
git add app/api/mobile/v1/error_handlers.py app/main.py tests/test_api_mobile_error_handler.py
git commit -m "feat(mobile): add global error handler for spec-compliant error format"
```

---

### Task 2: Wrap search response with `results` + `suggestions`

**Files:**
- Modify: `app/api/mobile/v1/search.py:107-163`
- Test: `tests/test_api_mobile_search.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_search.py`:

```python
def test_search_response_has_results_and_suggestions_keys():
    """Search data should be wrapped: {"results": [...], "suggestions": [...]}."""
    from app.api.mobile.v1.search import search
    import inspect
    src = inspect.getsource(search)
    # Verify the function constructs the wrapped dict (static check)
    assert '"results"' in src or "'results'" in src
    assert '"suggestions"' in src or "'suggestions'" in src
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_search.py::test_search_response_has_results_and_suggestions_keys -v`
Expected: FAIL

**Step 3: Modify search.py**

In `search.py`, change all 3 return statements to wrap `results` in a dict:

Replace line 118-121 (bridge-only):
```python
        return MobilePaginatedResponse(
            data={"results": [r.model_dump() for r in results], "suggestions": []},
            meta=MobileMeta(total=total, page=page, page_size=page_size),
        )
```

Replace line 128-131 (kp-only):
```python
        return MobilePaginatedResponse(
            data={"results": [r.model_dump() for r in results], "suggestions": []},
            meta=MobileMeta(total=total, page=page, page_size=page_size),
        )
```

Replace line 160-163 (type=all):
```python
    return MobilePaginatedResponse(
        data={"results": [r.model_dump() for r in results], "suggestions": []},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```

Also update the return type annotation on line 107 from `MobilePaginatedResponse[list[SearchResultItem]]` to `MobilePaginatedResponse[dict]`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_mobile_search.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/search.py tests/test_api_mobile_search.py
git commit -m "feat(mobile): wrap search response with results + suggestions keys"
```

---

### Task 3: Wrap favorites response with `items`

**Files:**
- Modify: `app/api/mobile/v1/favorites.py:76-90`
- Test: `tests/test_api_mobile_favorites.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_favorites.py`:

```python
def test_favorites_list_response_wraps_items():
    """Favorites list data should be wrapped: {"items": [...]}."""
    from app.api.mobile.v1.favorites import list_favorites
    import inspect
    src = inspect.getsource(list_favorites)
    assert '"items"' in src or "'items'" in src
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_favorites.py::test_favorites_list_response_wraps_items -v`
Expected: FAIL

**Step 3: Modify favorites.py**

In `favorites.py`, change line 87-90 from:
```python
    return MobilePaginatedResponse(
        data=data,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```
to:
```python
    return MobilePaginatedResponse(
        data={"items": data},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```

Update return type on line 49 from `MobilePaginatedResponse[list[dict]]` to `MobilePaginatedResponse[dict]`.

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_favorites.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/favorites.py tests/test_api_mobile_favorites.py
git commit -m "feat(mobile): wrap favorites list response with items key"
```

---

### Task 4: Wrap history response with `items`

**Files:**
- Modify: `app/api/mobile/v1/history.py:63-77`
- Test: `tests/test_api_mobile_history.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_history.py`:

```python
def test_history_list_response_wraps_items():
    """History list data should be wrapped: {"items": [...]}."""
    from app.api.mobile.v1.history import list_history
    import inspect
    src = inspect.getsource(list_history)
    assert '"items"' in src or "'items'" in src
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_history.py::test_history_list_response_wraps_items -v`
Expected: FAIL

**Step 3: Modify history.py**

Change line 74-77 from:
```python
    return MobilePaginatedResponse(
        data=items,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```
to:
```python
    return MobilePaginatedResponse(
        data={"items": items},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```

Update return type on line 34 from `MobilePaginatedResponse[dict]` to `MobilePaginatedResponse[dict]` (already dict, OK).

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_history.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/history.py tests/test_api_mobile_history.py
git commit -m "feat(mobile): wrap history list response with items key"
```

---

### Task 5: Wrap review/today with `cards` + `total_due`, and review/cards with `cards`

**Files:**
- Modify: `app/api/mobile/v1/review.py:43-113`
- Test: `tests/test_api_mobile_review.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_review.py`:

```python
def test_review_today_response_wraps_cards_and_total_due():
    """review/today data should be: {"cards": [...], "total_due": N}."""
    from app.api.mobile.v1.review import get_today_queue
    import inspect
    src = inspect.getsource(get_today_queue)
    assert '"cards"' in src or "'cards'" in src
    assert '"total_due"' in src or "'total_due'" in src


def test_review_cards_response_wraps_cards():
    """review/cards data should be: {"cards": [...]}."""
    from app.api.mobile.v1.review import list_review_cards
    import inspect
    src = inspect.getsource(list_review_cards)
    assert '"cards"' in src or "'cards'" in src
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_mobile_review.py::test_review_today_response_wraps_cards_and_total_due tests/test_api_mobile_review.py::test_review_cards_response_wraps_cards -v`
Expected: FAIL

**Step 3: Modify review.py**

For `get_today_queue` (around line 75-76), change:
```python
    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobileResponse(data=cards)
```
to:
```python
    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobileResponse(data={"cards": cards, "total_due": len(cards)})
```

For `list_review_cards` (around line 109-113), change:
```python
    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobilePaginatedResponse(
        data=cards,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```
to:
```python
    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobilePaginatedResponse(
        data={"cards": cards},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
```

Update return type on line 85 from `MobilePaginatedResponse[list[dict]]` to `MobilePaginatedResponse[dict]`.

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_review.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/review.py tests/test_api_mobile_review.py
git commit -m "feat(mobile): wrap review responses with cards key + total_due"
```

---

### Task 6: Fix flashcard field names in review.py

**Files:**
- Modify: `app/api/mobile/v1/review.py:23-40` (`_format_card`), `review.py:155-159` (progress response)
- Test: `tests/test_api_mobile_review.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_review.py`:

```python
def test_format_card_uses_id_not_flashcard_id():
    """_format_card should use 'id' key, not 'flashcard_id'."""
    from app.api.mobile.v1.review import _format_card
    import inspect
    src = inspect.getsource(_format_card)
    assert '"id"' in src
    assert '"flashcard_id"' not in src


def test_format_card_uses_example_bridge_object():
    """_format_card should return example_bridge as {id, name}, not example_bridge_id."""
    from app.api.mobile.v1.review import _format_card
    import inspect
    src = inspect.getsource(_format_card)
    assert '"example_bridge"' in src or "'example_bridge'" in src
    assert '"example_bridge_id"' not in src and "'example_bridge_id'" not in src


def test_update_progress_uses_reviewed_at():
    """PUT /review/progress should return 'reviewed_at', not 'last_reviewed_at'."""
    from app.api.mobile.v1.review import update_review_progress
    import inspect
    src = inspect.getsource(update_review_progress)
    assert '"reviewed_at"' in src or "'reviewed_at'" in src
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_mobile_review.py::test_format_card_uses_id_not_flashcard_id tests/test_api_mobile_review.py::test_format_card_uses_example_bridge_object tests/test_api_mobile_review.py::test_update_progress_uses_reviewed_at -v`
Expected: FAIL

**Step 3: Modify `_format_card` and callers**

Change `_format_card` signature (line 23) to accept a bridge name map:

```python
def _format_card(fc: Flashcard, rp: DeviceReviewProgress | None, bridge_names: dict | None = None) -> dict:
    """Build card dict with front/back structure."""
    example_bridge = None
    if fc.back_example_bridge_id:
        bridge_name = (bridge_names or {}).get(fc.back_example_bridge_id)
        example_bridge = {"id": str(fc.back_example_bridge_id), "name": bridge_name}
    return {
        "id": str(fc.id),
        "knowledge_point_id": str(fc.knowledge_point_id),
        "card_type": fc.card_type,
        "front": {
            "title": fc.front_title,
            "hint": fc.front_hint,
        },
        "back": {
            "answer": fc.back_answer,
            "key_features": fc.back_key_features,
            "example_bridge": example_bridge,
        },
        "mastery": rp.mastery if rp else None,
        "last_reviewed_at": rp.last_reviewed_at.isoformat() if rp and rp.last_reviewed_at else None,
    }
```

In both `get_today_queue` and `list_review_cards`, add batch bridge name lookup before building cards:

```python
    # Batch-resolve bridge names for example_bridge
    from app.models import Bridge
    bridge_ids = {fc.back_example_bridge_id for fc, rp in rows if fc.back_example_bridge_id}
    bridge_names: dict = {}
    if bridge_ids:
        name_rows = db.query(Bridge.id, Bridge.name).filter(Bridge.id.in_(bridge_ids)).all()
        bridge_names = {r.id: r.name for r in name_rows}
    cards = [_format_card(fc, rp, bridge_names) for fc, rp in rows]
```

For `update_review_progress` response (around line 155-159), change `"last_reviewed_at"` to `"reviewed_at"`:

```python
    return MobileResponse(data={
        "flashcard_id": str(rp.flashcard_id),
        "mastery": rp.mastery,
        "reviewed_at": rp.last_reviewed_at.isoformat() if rp.last_reviewed_at else None,
    })
```

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_review.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/review.py tests/test_api_mobile_review.py
git commit -m "fix(mobile): align flashcard field names with spec (id, example_bridge, reviewed_at)"
```

---

### Task 7: Fix flashcard example_bridge name in knowledge.py

**Files:**
- Modify: `app/api/mobile/v1/knowledge.py:237-257`
- Test: `tests/test_api_mobile_knowledge.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_knowledge.py`:

```python
def test_flashcards_resolve_example_bridge_name():
    """Flashcard example_bridge should resolve bridge name, not return null."""
    from app.api.mobile.v1.knowledge import get_knowledge_point_flashcards
    import inspect
    src = inspect.getsource(get_knowledge_point_flashcards)
    # Should batch-query Bridge names
    assert "Bridge.name" in src or "bridge_names" in src
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_knowledge.py::test_flashcards_resolve_example_bridge_name -v`
Expected: FAIL

**Step 3: Modify knowledge.py**

In `get_knowledge_point_flashcards` (after line 241 `flashcards = query...`), add bridge name resolution:

```python
    flashcards = query.order_by(Flashcard.created_at).all()

    # Batch-resolve bridge names for example_bridge
    from app.models import Bridge
    bridge_ids = {fc.back_example_bridge_id for fc in flashcards if fc.back_example_bridge_id}
    bridge_names: dict = {}
    if bridge_ids:
        name_rows = db.query(Bridge.id, Bridge.name).filter(Bridge.id.in_(bridge_ids)).all()
        bridge_names = {r.id: r.name for r in name_rows}
```

Then update the card building (around line 244-255) to use the resolved names:

```python
    cards = []
    for fc in flashcards:
        example_bridge = None
        if fc.back_example_bridge_id:
            example_bridge = {
                "id": str(fc.back_example_bridge_id),
                "name": bridge_names.get(fc.back_example_bridge_id),
            }
        cards.append({
            "id": str(fc.id),
            "knowledge_point_id": str(fc.knowledge_point_id),
            "card_type": fc.card_type,
            "front": {"title": fc.front_title, "hint": fc.front_hint},
            "back": {
                "answer": fc.back_answer,
                "key_features": fc.back_key_features or [],
                "example_bridge": example_bridge,
            },
        })
```

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_knowledge.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/knowledge.py tests/test_api_mobile_knowledge.py
git commit -m "fix(mobile): resolve example_bridge name in flashcard endpoint"
```

---

### Task 8: Add target_summary and thumbnail to favorites

**Files:**
- Modify: `app/api/mobile/v1/favorites.py:42-90`
- Test: `tests/test_api_mobile_favorites.py`

**Step 1: Write the failing test**

Append to `tests/test_api_mobile_favorites.py`:

```python
def test_favorites_list_includes_target_summary_and_thumbnail():
    """Each favorite item should include target_summary and thumbnail fields."""
    from app.api.mobile.v1.favorites import list_favorites
    import inspect
    src = inspect.getsource(list_favorites)
    assert '"target_summary"' in src or "'target_summary'" in src
    assert '"thumbnail"' in src or "'thumbnail'" in src
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_mobile_favorites.py::test_favorites_list_includes_target_summary_and_thumbnail -v`
Expected: FAIL

**Step 3: Modify favorites.py**

Expand the batch resolve block (around line 67-82). Replace the current name resolution with a richer one:

```python
    # Batch-resolve target details (name, summary, thumbnail)
    details: dict[UUID, dict] = {}  # target_id -> {name, summary, thumbnail}

    # Bridges
    bridge_ids = [f.target_id for f in favs if f.target_type == "bridge"]
    if bridge_ids:
        rows = db.query(
            Bridge.id, Bridge.name, Bridge.region, Bridge.era, Bridge.bridge_type,
        ).filter(Bridge.id.in_(bridge_ids)).all()
        for r in rows:
            summary_parts = [p for p in [r.region, f"{r.era}{r.bridge_type}" if r.era and r.bridge_type else r.era or r.bridge_type] if p]
            details[r.id] = {
                "name": r.name,
                "summary": "，".join(summary_parts) if summary_parts else None,
                "thumbnail": None,  # No bridge_images table yet
            }

    # Knowledge points
    kp_ids = [f.target_id for f in favs if f.target_type == "knowledge_point"]
    if kp_ids:
        rows = db.query(
            KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.summary,
        ).filter(KnowledgePoint.id.in_(kp_ids)).all()
        for r in rows:
            details[r.id] = {
                "name": r.name,
                "summary": (r.summary[:50] + "…") if r.summary and len(r.summary) > 50 else r.summary,
                "thumbnail": None,
            }

    # Flashcards
    fc_ids = [f.target_id for f in favs if f.target_type == "flashcard"]
    if fc_ids:
        rows = db.query(
            Flashcard.id, Flashcard.front_title,
        ).filter(Flashcard.id.in_(fc_ids)).all()
        for r in rows:
            details[r.id] = {
                "name": r.front_title,
                "summary": r.front_title,
                "thumbnail": None,
            }

    data = [
        {
            "id": str(f.id),
            "target_type": f.target_type,
            "target_id": str(f.target_id),
            "target_name": (details.get(f.target_id) or {}).get("name"),
            "target_summary": (details.get(f.target_id) or {}).get("summary"),
            "thumbnail": (details.get(f.target_id) or {}).get("thumbnail"),
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in favs
    ]
```

Remove the old `names` dict and `_TARGET_MODELS` usage in the list function (keep `_TARGET_MODELS` for other usages if any, otherwise remove).

**Step 4: Run tests**

Run: `pytest tests/test_api_mobile_favorites.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/favorites.py tests/test_api_mobile_favorites.py
git commit -m "feat(mobile): add target_summary and thumbnail to favorites list"
```

---

### Task 9: Fix clusters representative structure

**Files:**
- Verify: `app/api/mobile/v1/bridges.py:141-159`
- Test: `tests/test_api_mobile_bridges.py`

**Step 1: Verify current implementation**

Check `bridges.py` line 152-157. The current code already outputs:
```python
"representative": {"id": str(rep.id), "name": rep.name} if rep else None,
```

This **already matches the spec**. No code change needed — the original audit found `representative_ids` but the code was actually updated in batch 3. Verify with a test.

**Step 2: Write the confirmation test**

Append to `tests/test_api_mobile_bridges.py`:

```python
def test_clusters_representative_is_object_not_array():
    """Cluster representative should be {id, name} object, not an array of IDs."""
    from app.api.mobile.v1.bridges import get_bridge_clusters
    import inspect
    src = inspect.getsource(get_bridge_clusters)
    assert '"representative"' in src or "'representative'" in src
    assert "representative_ids" not in src
```

**Step 3: Run test**

Run: `pytest tests/test_api_mobile_bridges.py -v`
Expected: PASS (already correct)

**Step 4: Commit**

```bash
git add tests/test_api_mobile_bridges.py
git commit -m "test(mobile): add cluster representative structure verification"
```

---

### Task 10: Update api-spec.md §0.2 X-Device-Id scope

**Files:**
- Modify: `docs/api-spec.md:22`

**Step 1: Edit the spec**

Change line 22 from:
```
| `X-Device-Id` | 是 | 客户端首次启动时生成的 UUID v4，持久存储在本地，用于关联收藏/复习等个人数据 |
```
to:
```
| `X-Device-Id` | 条件必选 | 客户端首次启动时生成的 UUID v4，持久存储在本地。仅 `/favorites`、`/review`、`/history` 端点必选，其余端点不要求 |
```

**Step 2: Commit**

```bash
git add docs/api-spec.md
git commit -m "docs: correct X-Device-Id scope in api-spec.md (conditional, not required for all)"
```

---

### Task 11: Final regression test

**Step 1: Run all tests**

Run: `pytest tests/ -v --timeout=30`
Expected: All tests pass, no regressions.

**Step 2: Quick manual smoke test**

Run the dev server and verify key endpoints:
```bash
# Start server
uvicorn app.main:app --reload &

# Test error format
curl -s http://localhost:8000/api/mobile/v1/bridges/00000000-0000-4000-8000-000000000000 | python3 -m json.tool

# Test search wrapping
curl -s "http://localhost:8000/api/mobile/v1/search?q=test" | python3 -m json.tool

# Kill server
kill %1
```

Expected: Error returns `{"error": {"code": "NOT_FOUND", ...}}`, search returns `{"data": {"results": [...], "suggestions": [...]}, "meta": {...}}`.

**Step 3: Final commit (if any fixups needed)**

Otherwise, all tasks complete.
