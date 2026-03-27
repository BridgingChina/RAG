"""Mobile API dependencies."""
import uuid

from fastapi import Header, HTTPException


def require_device_id(x_device_id: str = Header(...)) -> uuid.UUID:
    """Validate X-Device-Id header format (UUID v4) and return it."""
    try:
        parsed = uuid.UUID(x_device_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid X-Device-Id format")
    if parsed.version != 4:
        raise HTTPException(400, detail="X-Device-Id must be UUID v4")
    return parsed
