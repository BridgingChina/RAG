"""Mobile API: GET /config."""
from fastapi import APIRouter

from app.api.mobile.v1.schemas.common import MobileResponse

router = APIRouter()


@router.get("/config", response_model=MobileResponse[dict])
def get_config() -> MobileResponse[dict]:
    """Return app configuration for mobile client.

    Data sourced from config/facets.yaml + hardcoded map config.
    """
    from app.core.constants import load_facets

    facets = load_facets()
    return MobileResponse(data={
        "eras": facets.get("era", []),
        "bridge_types": facets.get("bridge_type", []),
        "regions": facets.get("region", []),
        "map": {
            "provider": None,       # TODO: configure map provider
            "approval_number": None,  # TODO: configure approval number
        },
    })
