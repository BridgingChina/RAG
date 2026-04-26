"""识景视觉识别 service — /v1/recognition 后端逻辑。"""
import json
import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class VisionFreeForm:
    bridge_name: str
    region: str
    bridge_type: str
    hints: list[str]


@dataclass(frozen=True)
class VisionResult:
    matched_name: str | None
    free_form: VisionFreeForm | None


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_vision_json(raw: str) -> VisionResult:
    """Tolerant parser — extract first {...} block, return empty on any failure.

    Never raises. Invalid input → VisionResult(None, None) so the endpoint can
    route to the 'fallback' branch instead of returning 5xx to the user.
    """
    m = _JSON_BLOCK_RE.search(raw or "")
    if not m:
        return VisionResult(matched_name=None, free_form=None)
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return VisionResult(matched_name=None, free_form=None)

    matched = obj.get("matched_name")
    if isinstance(matched, str):
        matched = matched.strip() or None
    else:
        matched = None

    ff_raw = obj.get("free_form")
    free_form: VisionFreeForm | None = None
    if isinstance(ff_raw, dict):
        name = (ff_raw.get("bridge_name") or "").strip()
        if name:
            free_form = VisionFreeForm(
                bridge_name=name,
                region=(ff_raw.get("region") or "").strip(),
                bridge_type=(ff_raw.get("bridge_type") or "").strip(),
                hints=[h for h in (ff_raw.get("hints") or []) if isinstance(h, str)],
            )

    return VisionResult(matched_name=matched, free_form=free_form)
