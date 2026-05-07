"""V1 System API endpoint."""
import sys

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.schemas.system import FacetsResponse, SystemStatus
from app.core.config import settings
from app.core.constants import load_facets
from app.core.database import engine, get_current_schema_version, get_db
from app.services.hybrid_retriever import DEFAULT_QUOTA, RRF_K

router = APIRouter(prefix="/system")


@router.get("/status", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db)):
    """Return read-only system status and configuration."""
    db_connected = False
    schema_version = None
    try:
        db.execute(text("SELECT 1")).scalar()
        db_connected = True
        schema_version = get_current_schema_version(engine)
    except Exception:
        pass

    return SystemStatus(
        version="1.0.0",
        git_commit=settings.git_commit,
        git_date=settings.git_date,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        db_connected=db_connected,
        schema_version=schema_version,
        vector_dimension=1024,
        index_type="hnsw",
        llm_provider="zhipu",
        embedding_model=settings.embedding_model,
        chat_model=settings.chat_model,
        chunk_quota={
            "anchor": DEFAULT_QUOTA[0],
            "concept": DEFAULT_QUOTA[1],
            "analogy": DEFAULT_QUOTA[2],
        },
        rrf_k=RRF_K,
        api_key_configured=bool(settings.zhipu_api_key),
    )


@router.get("/facets", response_model=FacetsResponse)
def system_facets() -> FacetsResponse:
    """Return facet enums from config/facets.yaml.

    Single source of truth for admin form dropdowns (bridge_type, material,
    era, function) and any future filter UI. Cached in-process via
    @lru_cache on load_facets() — bumping facets.yaml requires a redeploy.
    """
    facets = load_facets()
    return FacetsResponse(
        bridge_types=facets.get("bridge_types", []),
        materials=facets.get("materials", []),
        eras=facets.get("eras", []),
        regions=facets.get("regions", []),
        functions=facets.get("functions", []),
    )
