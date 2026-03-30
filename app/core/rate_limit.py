"""Global rate limiter (slowapi).

Import ``limiter`` wherever a ``@limiter.limit()`` decorator is needed.
The instance is attached to the FastAPI app in ``app.main``.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
