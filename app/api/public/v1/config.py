"""Public API: GET /config."""
from fastapi import APIRouter

from app.api.public.v1.schemas.common import PublicResponse

router = APIRouter()


@router.get("/config", response_model=PublicResponse[dict])
def get_config() -> PublicResponse[dict]:
    """Return app configuration for public client.

    Data sourced from config/facets.yaml + hardcoded map config.
    """
    from app.core.constants import load_facets

    facets = load_facets()
    return PublicResponse(data={
        "eras": facets.get("era", []),
        "bridge_types": facets.get("bridge_type", []),
        "regions": facets.get("region", []),
        "map": {
            "provider": None,       # TODO: configure map provider
            "approval_number": None,  # TODO: configure approval number
        },
    })
