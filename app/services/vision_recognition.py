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


def _coerce_str(v: object) -> str:
    """Defensive: LLMs occasionally return non-string scalars in JSON fields.

    Returns the stripped string if v is a str, otherwise empty string. Never
    raises — preserves the parser's "VisionResult(None, None) on bad input"
    invariant.
    """
    return v.strip() if isinstance(v, str) else ""


def parse_vision_json(raw: str) -> VisionResult:
    """Tolerant parser — extract the largest `{...}` envelope (greedy: first `{` to
    last `}`), return VisionResult(None, None) on any failure.

    Greedy is intentional: the dominant LLM failure pattern is one valid JSON
    object surrounded by prose ("Sure, here is the result: {...}"). Multi-block
    inputs intentionally degrade to fallback rather than guessing.
    """
    m = _JSON_BLOCK_RE.search(raw or "")
    if not m:
        return VisionResult(matched_name=None, free_form=None)
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return VisionResult(matched_name=None, free_form=None)

    matched_raw = obj.get("matched_name")
    matched = _coerce_str(matched_raw) or None

    ff_raw = obj.get("free_form")
    free_form: VisionFreeForm | None = None
    if isinstance(ff_raw, dict):
        name = _coerce_str(ff_raw.get("bridge_name"))
        if name:
            hints_raw = ff_raw.get("hints")
            hints = (
                [h for h in hints_raw if isinstance(h, str)]
                if isinstance(hints_raw, list)
                else []
            )
            free_form = VisionFreeForm(
                bridge_name=name,
                region=_coerce_str(ff_raw.get("region")),
                bridge_type=_coerce_str(ff_raw.get("bridge_type")),
                hints=hints,
            )

    return VisionResult(matched_name=matched, free_form=free_form)
