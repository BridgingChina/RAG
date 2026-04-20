"""Internal: cascade-purge a user's RAG-side state.

Called by the auth Worker's ``user.deleted`` webhook. Purges the three
user-scoped tables (favorites / review_progress / view_history) and
anonymises audit_logs (sets ``user_id`` to NULL so compliance records
survive but the principal is unlinkable).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/users", tags=["internal"])


def _verify_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """Gate the endpoint on a shared secret.

    Design note: the original plan preferred Cloudflare Access + IP allow-list
    so FastAPI wouldn't need any app-level auth. Shipping the shared-secret
    path first keeps the endpoint self-contained and testable; swapping in
    CF Access later is a deploy-only change that still leaves this check as
    defense-in-depth.
    """
    expected = settings.internal_api_secret
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Internal API not configured (INTERNAL_API_SECRET unset)",
        )
    if x_internal_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid internal token")


@router.post(
    "/{user_id}/purge",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_verify_internal_token)],
)
def purge_user(user_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete all user-scoped rows and anonymise the audit trail.

    Returns per-table row counts so the caller (auth Worker webhook) can
    log what was actually purged — useful when debugging a stale-state
    report from the reconcile cron.
    """
    counts: dict[str, int] = {}

    for table in ("favorites", "review_progress", "view_history"):
        result = db.execute(
            sql_text(f"DELETE FROM {table} WHERE user_id = :uid"),
            {"uid": user_id},
        )
        counts[table] = result.rowcount or 0

    # Compliance: retain the audit rows (legal evidence) but drop the link
    # so the row no longer identifies the deleted user.
    anon = db.execute(
        sql_text("UPDATE audit_logs SET user_id = NULL WHERE user_id = :uid"),
        {"uid": user_id},
    )
    counts["audit_logs_anonymised"] = anon.rowcount or 0

    db.commit()
    return {"user_id": user_id, "counts": counts}
