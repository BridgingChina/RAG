"""识景视觉识别 service — /v1/recognition 后端逻辑。"""
from sqlalchemy.orm import Session

from app.models import Bridge


def build_bridge_catalog(db: Session) -> str:
    """Render all bridges as a CSV string for prompt injection.

    Stable column order (name,region,era,bridge_type) and ORDER BY name so the
    OpenRouter prompt cache can hit on repeated requests as long as the catalog
    row set is unchanged.
    """
    rows = (
        db.query(Bridge.name, Bridge.region, Bridge.era, Bridge.bridge_type)
        .order_by(Bridge.name)
        .all()
    )
    lines = ["name,region,era,bridge_type"]
    for name, region, era, btype in rows:
        lines.append(f"{name},{region or ''},{era or ''},{btype or ''}")
    return "\n".join(lines)
