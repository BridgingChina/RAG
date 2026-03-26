"""Mobile API dependencies."""
import uuid

from fastapi import Header, HTTPException


def require_device_id(x_device_id: str = Header(...)) -> str:
    """Validate X-Device-Id header format (UUID v4) and return it."""
    try:
        uuid.UUID(x_device_id, version=4)
    except ValueError:
        raise HTTPException(400, detail="Invalid X-Device-Id format")
    return x_device_id
