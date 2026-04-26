"""识景视觉识别 service — /v1/recognition 后端逻辑。"""
import json
import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.recognition import RecognitionCandidate, RecognitionFallback
from app.api.public.v1.utils import escape_like
from app.core.config import settings
from app.models import Bridge
from app.models.bridge_image import BridgeImage
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError
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


logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_TEMPLATE = """你是中国桥梁识别助手。下方是已知桥梁名录（CSV，每行一座桥）：
{catalog}

任务：识别用户上传的图片中的桥梁。
- 若能在名录里精确对应到某座桥，把 matched_name 填那一行的 name；
- 若无法对应名录（包括"图中的桥不在名录里"和"图中根本不是桥"），matched_name 设为 null；
- 当 matched_name=null 但确实是一座桥，给出 free_form 自由识别；
- 当根本不是桥，free_form 也设为 null。

只输出 JSON，不要其他文本：
{{
  "matched_name": string | null,
  "free_form": {{
    "bridge_name": string,
    "region": string,
    "bridge_type": string,
    "hints": string[]
  }} | null
}}"""


def _build_messages(
    catalog_csv: str,
    image_b64: str,
    mime: str,
    latitude: float | None,
    longitude: float | None,
) -> list[dict]:
    if latitude is not None and longitude is not None:
        user_text = f"可选位置：纬度 {latitude}，经度 {longitude}"
    else:
        user_text = "请识别这张图片中的桥梁。"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(catalog=catalog_csv)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        },
    ]


def _post_openrouter(model: str, messages: list[dict]) -> str:
    """Single-shot POST. Raises httpx.HTTPStatusError on non-2xx."""
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bridgingchina.net",
        "X-Title": "BridgingChina-Recognition",
    }
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 512,
    }
    with httpx.Client(timeout=settings.recognition_request_timeout) as client:
        resp = client.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        # Malformed 2xx body — treat as upstream failure so the caller
        # can try the fallback model instead of 5xx-ing the user.
        raise httpx.HTTPStatusError(
            f"OpenRouter returned 200 with unexpected body shape: {data!r}",
            request=resp.request,
            response=httpx.Response(502, request=resp.request),
        ) from exc


def call_openrouter_vision(
    image_b64: str,
    mime: str,
    catalog_csv: str,
    latitude: float | None,
    longitude: float | None,
) -> tuple[str, str]:
    """Call OpenRouter Qwen3-VL with primary→fallback model chain.

    Returns (raw_content, model_used). Raises:
    - ProviderConfigurationError if OPENROUTER_API_KEY is unset
    - ProviderUnavailableError if both primary and fallback models fail
    - httpx.HTTPStatusError if a non-retryable 4xx (not 429) occurs
    """
    if not settings.openrouter_api_key:
        raise ProviderConfigurationError(
            "OPENROUTER_API_KEY not set — /v1/recognition disabled"
        )

    messages = _build_messages(catalog_csv, image_b64, mime, latitude, longitude)

    for model in (
        settings.openrouter_vision_model,
        settings.openrouter_vision_fallback_model,
    ):
        try:
            return _post_openrouter(model, messages), model
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status < 500 and status != 429:
                # 4xx (other than 429) means the request itself is broken
                # — fallback model would fail the same way. Propagate.
                raise
            logger.warning(
                "OpenRouter %s failed (status=%s) — trying next model",
                model,
                status,
            )
        except httpx.TransportError as exc:
            logger.warning(
                "OpenRouter %s transport error: %s — trying next model", model, exc
            )

    raise ProviderUnavailableError(
        "OpenRouter vision: both primary and fallback models failed"
    )
