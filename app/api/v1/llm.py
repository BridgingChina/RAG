"""Admin LLM routing API — /api/v1/llm/* (Phase D).

Eleven endpoints that let admins manage providers + task routes. All
require admin JWT (via the ``require_admin`` dep in ``v1/dependencies``,
reused transitively because this router is mounted inside the
protected sub-router in ``app.api.v1.__init__``).

Zero-key-exposure invariant: every response goes through
:class:`ProviderPublic` / :class:`TaskRoutePublic` whitelist schemas.
``api_key_env`` / ``extra_headers`` never leave this module's input path.

Audit: every mutation (create / update / delete / test / route change)
writes to ``audit_logs``. The audit log's ``detail`` column is JSONB,
so we keep it small and never include secret material.
"""
from __future__ import annotations

import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.llm import (
    ModelInfoPublic,
    ProviderCreate,
    ProviderPublic,
    ProviderTestResult,
    ProviderUpdate,
    TaskRouteBatchUpdate,
    TaskRoutePublic,
    TaskRouteUpdate,
)
from app.core.database import get_db
from app.core.llm_tasks import TASK_DESCRIPTIONS
from app.core.logging import logger
from app.core.rate_limit import limiter
from app.llm import router as task_router
from app.llm.registry import _registry
from app.models.current_user import CurrentUser
from app.models.llm import LLMProviderModel, LLMProviderRow, LLMTaskRoute
from app.providers._sanitize import register_sensitive_key, sanitize_error
from app.providers.config import ProviderConfig
from app.services.audit_service import AuditService


router = APIRouter(prefix="/llm", tags=["llm"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_key_configured(api_key_env: str) -> bool:
    """Return ``True`` iff ``os.environ[api_key_env]`` is set and non-empty.

    Matches ``_secret.resolve_api_key`` semantics — a whitespace-only value
    is treated as absent.
    """
    val = os.environ.get(api_key_env, "")
    return bool(val and val.strip())


def _provider_to_public(
    row: LLMProviderRow,
    *,
    model_count: int,
) -> ProviderPublic:
    return ProviderPublic(
        id=row.id,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        base_url=row.base_url,
        enabled=row.enabled,
        timeout_read=row.timeout_read,
        has_api_key_configured=_has_key_configured(row.api_key_env),
        last_tested_at=row.last_tested_at,
        last_test_ok=row.last_test_ok,
        last_test_error=row.last_test_error,
        model_count=model_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _model_counts_by_provider(
    db: Session, provider_ids: list[UUID]
) -> dict[UUID, int]:
    """Batch count ``llm_provider_models`` rows for the given provider ids."""
    if not provider_ids:
        return {}
    rows = (
        db.query(
            LLMProviderModel.provider_id,
            func.count(LLMProviderModel.id).label("cnt"),
        )
        .filter(LLMProviderModel.provider_id.in_(provider_ids))
        .group_by(LLMProviderModel.provider_id)
        .all()
    )
    return {pid: cnt for pid, cnt in rows}


def _get_provider_row(db: Session, provider_id: UUID) -> LLMProviderRow:
    row = db.query(LLMProviderRow).filter(LLMProviderRow.id == provider_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return row


def _task_route_to_public(route: LLMTaskRoute, provider_name: str) -> TaskRoutePublic:
    return TaskRoutePublic(
        task_key=route.task_key,
        description=TASK_DESCRIPTIONS.get(route.task_key, ""),
        provider_id=route.provider_id,
        provider_name=provider_name,
        model_id=route.model_id,
        updated_at=route.updated_at,
        updated_by=route.updated_by,
    )


# ---------------------------------------------------------------------------
# Providers — CRUD (5 endpoints)
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[ProviderPublic])
def list_providers(
    enabled: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ProviderPublic]:
    """List all providers. Optional ``?enabled=true|false`` filter."""
    query = db.query(LLMProviderRow).order_by(LLMProviderRow.created_at.desc())
    if enabled is not None:
        query = query.filter(LLMProviderRow.enabled == enabled)
    rows = query.all()
    counts = _model_counts_by_provider(db, [r.id for r in rows])
    return [_provider_to_public(r, model_count=counts.get(r.id, 0)) for r in rows]


@router.post("/providers", response_model=ProviderPublic, status_code=201)
def create_provider(
    body: ProviderCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProviderPublic:
    """Register a new provider.

    ``api_key_env`` names an environment variable — NOT the key itself.
    After INSERT we call :func:`register_sensitive_key` so future sanitizer
    passes can redact that env's value if it ever surfaces in an exception.
    """
    row = LLMProviderRow(
        name=body.name,
        kind=body.kind,
        base_url=str(body.base_url),
        api_key_env=body.api_key_env,
        extra_headers=body.extra_headers,
        enabled=body.enabled,
        timeout_read=body.timeout_read,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Provider with this name already exists",
        ) from e

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="llm_provider",
        user_id=current_user.id,
        resource_id=str(row.id),
        detail={"name": row.name, "kind": row.kind},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(row)

    # Seed the sanitizer blacklist with this env's current value.
    register_sensitive_key(body.api_key_env)

    return _provider_to_public(row, model_count=0)


@router.get("/providers/{provider_id}", response_model=ProviderPublic)
def get_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
) -> ProviderPublic:
    """Fetch a single provider by id."""
    row = _get_provider_row(db, provider_id)
    counts = _model_counts_by_provider(db, [row.id])
    return _provider_to_public(row, model_count=counts.get(row.id, 0))


@router.patch("/providers/{provider_id}", response_model=ProviderPublic)
def update_provider(
    provider_id: UUID,
    body: ProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProviderPublic:
    """Partial update. Only provided fields get written."""
    row = _get_provider_row(db, provider_id)

    data = body.model_dump(exclude_unset=True)
    env_changed = False
    new_env: str | None = None

    if "name" in data and data["name"] is not None:
        row.name = data["name"]
    if "base_url" in data and data["base_url"] is not None:
        row.base_url = str(data["base_url"])
    if "api_key_env" in data and data["api_key_env"] is not None:
        if data["api_key_env"] != row.api_key_env:
            env_changed = True
            new_env = data["api_key_env"]
        row.api_key_env = data["api_key_env"]
    if "extra_headers" in data and data["extra_headers"] is not None:
        row.extra_headers = data["extra_headers"]
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = data["enabled"]
    if "timeout_read" in data and data["timeout_read"] is not None:
        row.timeout_read = data["timeout_read"]

    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Provider update violates a unique constraint",
        ) from e

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="llm_provider",
        user_id=current_user.id,
        resource_id=str(provider_id),
        detail={"fields": sorted(data.keys())},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(row)

    # Registry must rebuild the cached Provider instance with fresh config.
    _registry.invalidate(str(provider_id))
    # All task routes pointing at this provider need a fresh resolver hit too —
    # dropping the whole route cache is the cheap correct thing to do.
    task_router.invalidate_all()

    if env_changed and new_env:
        register_sensitive_key(new_env)

    counts = _model_counts_by_provider(db, [row.id])
    return _provider_to_public(row, model_count=counts.get(row.id, 0))


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a provider.

    Hard-blocks on in-use — returns 409 with ``task_keys`` enumeration
    so the UI can tell the admin exactly which routes to re-point first.
    The RESTRICT FK on ``llm_task_routes.provider_id`` would catch this
    at the DB level, but we surface a structured error ahead of the FK
    so the admin doesn't have to parse a driver exception.
    """
    row = _get_provider_row(db, provider_id)

    in_use = (
        db.query(LLMTaskRoute.task_key)
        .filter(LLMTaskRoute.provider_id == provider_id)
        .order_by(LLMTaskRoute.task_key)
        .all()
    )
    if in_use:
        task_keys = [r[0] for r in in_use]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "provider_in_use",
                "message": (
                    f"Provider {row.name!r} is still used by "
                    f"{len(task_keys)} task(s). Re-route them before deleting."
                ),
                "task_keys": task_keys,
            },
        )

    # Defense-in-depth: nested txn catches any unchecked FK references (e.g.
    # new FK added to llm_providers in a future migration without updating the
    # enumeration above). Mirrors the taxonomy delete pattern.
    try:
        with db.begin_nested():
            db.delete(row)
            db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "provider_in_use",
                "message": "Cannot delete provider due to existing references",
            },
        ) from e

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="llm_provider",
        user_id=current_user.id,
        resource_id=str(provider_id),
        detail={"name": row.name},
        ip_address=get_client_ip(request),
    )
    db.commit()

    _registry.invalidate(str(provider_id))
    task_router.invalidate_all()


# ---------------------------------------------------------------------------
# Test & Models (2 endpoints)
# ---------------------------------------------------------------------------


@router.post("/providers/{provider_id}/test", response_model=ProviderTestResult)
@limiter.limit("10/minute")
async def test_provider(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProviderTestResult:
    """Probe the upstream and refresh the cached model list.

    Success path:
      1. ``provider.list_models()`` returns a non-empty list.
      2. We DELETE existing ``llm_provider_models`` rows for this provider.
      3. Bulk-INSERT the fresh list.
      4. Update ``last_tested_at / last_test_ok=True / last_test_error=None``.

    Failure path catches every exception (``ProviderConfigurationError``,
    ``ProviderUnavailableError``, network hiccups, surprise RuntimeError)
    and runs the sanitizer on the message. The row's
    ``last_test_ok`` flips False with the reason recorded. HTTP response is
    still 200 — the failure is operational state, not a transport failure
    of this endpoint itself.
    """
    row = _get_provider_row(db, provider_id)

    # Guard: disabled provider — let the admin re-enable before testing.
    if not row.enabled:
        raise HTTPException(
            status_code=409,
            detail="Provider is disabled; enable it before testing",
        )

    config = ProviderConfig(
        provider_id=str(row.id),
        kind=row.kind,
        base_url=row.base_url,
        api_key_env=row.api_key_env,
        extra_headers=row.extra_headers or {},
        timeout_read=row.timeout_read,
    )

    try:
        provider_instance = _registry.get_or_build(config)
        models = await provider_instance.list_models()
    except Exception as exc:  # noqa: BLE001 — sanitize-and-surface is the policy
        reason = sanitize_error(exc)
        row.last_tested_at = func.now()
        row.last_test_ok = False
        row.last_test_error = reason
        db.flush()
        AuditService.log(
            db,
            action="test_provider",
            resource_type="llm_provider",
            user_id=current_user.id,
            resource_id=str(provider_id),
            detail={"status": "fail", "reason": reason},
            ip_address=get_client_ip(request),
        )
        db.commit()
        logger.info(
            "LLM provider test failed: provider_id=%s reason=%s",
            provider_id,
            reason,
        )
        return ProviderTestResult(status="fail", reason=reason)

    # Success — refresh the cached model list.
    db.query(LLMProviderModel).filter(
        LLMProviderModel.provider_id == provider_id
    ).delete(synchronize_session=False)
    for m in models:
        db.add(
            LLMProviderModel(
                provider_id=provider_id,
                model_id=m.id,
                display_name=m.display_name,
                kind=m.kind,
                context_window=m.context_window,
                extra=m.extra or {},
            )
        )
    row.last_tested_at = func.now()
    row.last_test_ok = True
    row.last_test_error = None
    db.flush()

    AuditService.log(
        db,
        action="test_provider",
        resource_type="llm_provider",
        user_id=current_user.id,
        resource_id=str(provider_id),
        detail={"status": "ok", "model_count": len(models)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return ProviderTestResult(status="ok", model_count=len(models))


@router.get(
    "/providers/{provider_id}/models",
    response_model=list[ModelInfoPublic],
)
def list_provider_models(
    provider_id: UUID,
    db: Session = Depends(get_db),
) -> list[ModelInfoPublic]:
    """Return the cached model list. No upstream call — pure DB read."""
    _get_provider_row(db, provider_id)  # 404 if missing
    rows = (
        db.query(LLMProviderModel)
        .filter(LLMProviderModel.provider_id == provider_id)
        .order_by(LLMProviderModel.kind, LLMProviderModel.model_id)
        .all()
    )
    return [ModelInfoPublic.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Tasks (3 endpoints)
#
# NB: literal paths (``/batch-update``) are registered BEFORE the parametric
# ``/tasks/{task_key}`` to avoid FastAPI routing ``batch-update`` as a key.
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskRoutePublic])
def list_task_routes(db: Session = Depends(get_db)) -> list[TaskRoutePublic]:
    """List every task route with its provider_name joined in."""
    rows = (
        db.query(LLMTaskRoute, LLMProviderRow.name)
        .join(LLMProviderRow, LLMTaskRoute.provider_id == LLMProviderRow.id)
        .order_by(LLMTaskRoute.task_key)
        .all()
    )
    return [_task_route_to_public(route, name) for route, name in rows]


@router.post("/tasks/batch-update", response_model=list[TaskRoutePublic])
def batch_update_task_routes(
    body: TaskRouteBatchUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TaskRoutePublic]:
    """Atomic multi-row update. All succeed or the whole txn rolls back."""
    if not body.updates:
        raise HTTPException(status_code=422, detail="updates must not be empty")

    # Duplicate task_key check first — user bug, not an internal state one.
    seen: set[str] = set()
    for u in body.updates:
        if u.task_key in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate task_key in batch: {u.task_key!r}",
            )
        seen.add(u.task_key)

    # Pre-validate every provider_id exists + is enabled BEFORE touching rows.
    provider_ids = {u.provider_id for u in body.updates}
    providers = (
        db.query(LLMProviderRow)
        .filter(LLMProviderRow.id.in_(provider_ids))
        .all()
    )
    pmap = {p.id: p for p in providers}
    missing = provider_ids - pmap.keys()
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider_id(s): {sorted(str(p) for p in missing)}",
        )
    disabled = [p for p in providers if not p.enabled]
    if disabled:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot route to disabled provider(s): "
                f"{sorted(p.name for p in disabled)}"
            ),
        )

    # Apply all updates in one txn.
    affected_routes: list[LLMTaskRoute] = []
    for u in body.updates:
        route = (
            db.query(LLMTaskRoute)
            .filter(LLMTaskRoute.task_key == u.task_key)
            .first()
        )
        if route is None:
            raise HTTPException(
                status_code=404,
                detail=f"task_key {u.task_key!r} not found",
            )
        # model_id existence is warn-only — a provider temporarily missing
        # the model from list_models() must not block config fixups.
        cached = (
            db.query(LLMProviderModel)
            .filter(
                LLMProviderModel.provider_id == u.provider_id,
                LLMProviderModel.model_id == u.model_id,
            )
            .first()
        )
        if cached is None:
            logger.warning(
                "Task route updated to model_id %r not in cache for provider %s",
                u.model_id,
                u.provider_id,
            )
        route.provider_id = u.provider_id
        route.model_id = u.model_id
        route.updated_by = None  # Better Auth id is a base64 str, not UUID;
        # leave null until we widen the column (tracked in Phase E follow-up).
        affected_routes.append(route)

    db.flush()

    AuditService.log(
        db,
        action=AuditService.BATCH_UPDATE,
        resource_type="llm_task_route",
        user_id=current_user.id,
        detail={
            "task_keys": sorted(u.task_key for u in body.updates),
        },
        ip_address=get_client_ip(request),
    )
    db.commit()
    for r in affected_routes:
        db.refresh(r)

    # Invalidate every touched task key + the registry (since a new provider
    # may be in play for any of them).
    for u in body.updates:
        task_router.invalidate(u.task_key)

    return [
        _task_route_to_public(route, pmap[route.provider_id].name)
        for route in affected_routes
    ]


@router.put("/tasks/{task_key}", response_model=TaskRoutePublic)
def update_task_route(
    task_key: str,
    body: TaskRouteUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TaskRoutePublic:
    """Re-point a single task to a different provider/model."""
    if body.task_key != task_key:
        raise HTTPException(
            status_code=422,
            detail="Body task_key must match URL path task_key",
        )

    route = (
        db.query(LLMTaskRoute)
        .filter(LLMTaskRoute.task_key == task_key)
        .first()
    )
    if route is None:
        raise HTTPException(
            status_code=404,
            detail=f"task_key {task_key!r} not found",
        )

    provider = _get_provider_row(db, body.provider_id)
    if not provider.enabled:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot route to disabled provider {provider.name!r}",
        )

    # Warn-only: model_id not in cache is a soft signal (see batch endpoint
    # for the same rationale).
    cached = (
        db.query(LLMProviderModel)
        .filter(
            LLMProviderModel.provider_id == body.provider_id,
            LLMProviderModel.model_id == body.model_id,
        )
        .first()
    )
    if cached is None:
        logger.warning(
            "Task route %s updated to model_id %r not in cache for provider %s",
            task_key,
            body.model_id,
            body.provider_id,
        )

    route.provider_id = body.provider_id
    route.model_id = body.model_id
    route.updated_by = None
    db.flush()

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="llm_task_route",
        user_id=current_user.id,
        resource_id=task_key,
        detail={
            "provider_id": str(body.provider_id),
            "model_id": body.model_id,
        },
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(route)

    task_router.invalidate(task_key)

    return _task_route_to_public(route, provider.name)


# ---------------------------------------------------------------------------
# Cache control (1 endpoint)
# ---------------------------------------------------------------------------


@router.post("/routes/invalidate-cache", status_code=204)
def invalidate_all_caches(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Drop every cached Provider instance + every cached task route.

    Intended as a "seat belt" for ops — after a direct DB patch or a
    config reload that bypassed the API, one POST here lets the next call
    rebuild from scratch.
    """
    _registry.invalidate_all()
    task_router.invalidate_all()

    # This is a no-DB admin action; we still log so the audit trail records
    # who triggered a cache wipe. We open an ad-hoc session purely for the
    # audit entry — follow the usual pattern (flush, then commit).
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        AuditService.log(
            db,
            action="invalidate_cache",
            resource_type="llm_router",
            user_id=current_user.id,
            ip_address=get_client_ip(request),
        )
        db.commit()
