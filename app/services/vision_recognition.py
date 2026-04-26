"""识景视觉识别 service — /v1/recognition 后端逻辑。"""
import json
import re
from dataclasses import dataclass

from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.recognition import RecognitionCandidate, RecognitionFallback
from app.api.public.v1.utils import escape_like
from app.models import Bridge
from app.models.bridge_image import BridgeImage
from app.services.bridge_image_service import BridgeImageService


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


def _bridge_to_candidate(bridge: Bridge, hints: list[str], db: Session) -> RecognitionCandidate:
    img = (
        db.query(BridgeImage)
        .filter(BridgeImage.bridge_id == bridge.id)
        .order_by(BridgeImage.order_index.asc())
        .first()
    )
    thumbnail = BridgeImageService.get_public_url(img.r2_key) if img else None
    return RecognitionCandidate(
        bridge_id=bridge.id,
        name=bridge.name,
        bridge_type=bridge.bridge_type or "",
        era=bridge.era or "",
        region=bridge.region or "",
        thumbnail=thumbnail,
        confidence_hints=hints,
    )


def route_candidates(
    result: VisionResult,
    db: Session,
) -> tuple[list[RecognitionCandidate], RecognitionFallback | None, str]:
    """Three-branch dispatcher for /v1/recognition. See design doc §4 / §7."""

    # 分支①: exact match by matched_name
    if result.matched_name:
        bridge = (
            db.query(Bridge)
            .filter(or_(Bridge.name == result.matched_name, Bridge.name_en == result.matched_name))
            .first()
        )
        if bridge:
            return (
                [_bridge_to_candidate(bridge, ["LLM 命中已知桥梁名录"], db)],
                None,
                "exact",
            )
        # matched_name set but DB miss → degrade to fuzzy on same name
        result = VisionResult(
            matched_name=None,
            free_form=VisionFreeForm(
                bridge_name=result.matched_name, region="", bridge_type="", hints=[]
            ),
        )

    # 分支②: fuzzy ILIKE on free_form.bridge_name
    if result.free_form and result.free_form.bridge_name:
        ff = result.free_form
        escaped = escape_like(ff.bridge_name)
        like_contains = f"%{escaped}%"
        score = case(
            (Bridge.name.ilike(escaped), 100),
            (Bridge.name.ilike(f"{escaped}%"), 80),
            (Bridge.name.ilike(like_contains), 60),
            else_=40,
        ).label("score")
        rows = (
            db.query(Bridge, score)
            .filter(or_(Bridge.name.ilike(like_contains), Bridge.name_en.ilike(like_contains)))
            .order_by(score.desc(), Bridge.name)
            .limit(5)
            .all()
        )
        if rows:
            hints = ff.hints if ff.hints else ["LLM 自由识别匹配"]
            candidates = [_bridge_to_candidate(b, hints, db) for b, _ in rows]
            return candidates, None, "fuzzy"
        return (
            [],
            RecognitionFallback(search_hint=ff.bridge_name, region_hint=ff.region or None),
            "fallback",
        )

    # 分支③: nothing actionable → empty
    return [], None, "fallback"
