"""Unit tests for optimistic locking."""
import uuid
from datetime import datetime, timezone

import pytest

_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID42 = uuid.UUID("00000000-0000-0000-0000-000000000042")


def test_check_optimistic_lock_none_skips():
    """When expected is None, no exception is raised."""
    from app.services.chunk_editor import check_optimistic_lock

    class FakeChunk:
        id = _UUID1
        updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    check_optimistic_lock(FakeChunk(), expected=None)


def test_check_optimistic_lock_match_passes():
    """When expected matches updated_at, no exception is raised."""
    from app.services.chunk_editor import check_optimistic_lock

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    class FakeChunk:
        id = _UUID42
        updated_at = ts

    check_optimistic_lock(FakeChunk(), expected=ts)


def test_check_optimistic_lock_mismatch_raises_409():
    """When expected does not match updated_at, raise HTTPException 409."""
    from fastapi import HTTPException
    from app.services.chunk_editor import check_optimistic_lock

    class FakeChunk:
        id = _UUID42
        updated_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        check_optimistic_lock(
            FakeChunk(),
            expected=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert "chunk_id" in str(exc_info.value.detail)
