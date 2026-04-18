"""Public API dependencies.

Threat model for X-Device-Id
-----------------------------
X-Device-Id is a client-generated UUID v4 sent via HTTP header. It is NOT
a secret and provides NO authentication — any client that knows (or guesses)
another device's UUID can impersonate it. This is an accepted trade-off for
a public educational app with no user accounts on the public side:

- **What it guards:** favorites, review progress, and view history are
  partitioned by device_id so that one device's data does not leak into
  another's responses by default.
- **What it does NOT guard:** a malicious actor who obtains or brute-forces
  a device_id can read and modify that device's favorites/progress/history.
  Since this data has no PII and no monetary value, the risk is low.
- **Mitigation if needed later:** add HMAC signing of the device_id (e.g.
  ``X-Device-Id-Sig``) or migrate to a lightweight auth token.

All endpoints that accept X-Device-Id MUST include device_id in their
database WHERE clauses so that a request can only read/write rows belonging
to the presented device_id (ownership scoping).
"""
import uuid

from fastapi import Header, HTTPException


def require_device_id(x_device_id: str = Header(...)) -> uuid.UUID:
    """Validate X-Device-Id header format (UUID v4) and return it.

    Security note: this only validates *format* — it does not authenticate
    the caller. See module docstring for the full threat model.
    """
    try:
        parsed = uuid.UUID(x_device_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid X-Device-Id format")
    if parsed.version != 4:
        raise HTTPException(400, detail="X-Device-Id must be UUID v4")
    return parsed
