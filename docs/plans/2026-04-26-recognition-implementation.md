# 识景端点实施计划 · `/v1/recognition`

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `feat/recognition-vision` 分支落地 `POST /v1/recognition`，接 OpenRouter Qwen3-VL，让 C 端识景页从 404 变可用。

**Architecture:** Sync FastAPI route → 调 `services/vision_recognition.py`（拼桥梁名录 → 调 OpenRouter → 三分支召回）→ 返 `{data:{candidates,fallback_suggestions?},meta}`。Provider 不扩 `ChatMessage` 协议，独立 service 走 `httpx.Client`，复用 `_secret/errors` helpers。

**Tech Stack:** FastAPI · SQLAlchemy 2 (sync Session) · httpx · Pydantic · pytest · OpenRouter (qwen/qwen3-vl-235b-a22b-instruct + qwen/qwen3-vl-30b-a3b-instruct fallback)

**前置参考：** 设计文档 `docs/plans/2026-04-26-recognition-design.md`（必读，含契约/分支/选型理由）

---

## 工作目录约定

所有命令在 worktree 根 `/Users/uu/Documents/Coding/4C2026/RAG/.worktrees/recognition-vision/` 内执行。
分支 `feat/recognition-vision`（已基于 `origin/main` 创建）。
DB 容器复用 `bridge_rag_db`（已运行）。

---

## Task 1: 加配置字段

**Files:**
- Modify: `app/core/config.py`（在现有 `Settings` 类内追加字段，紧邻其他外部 API key 字段）
- Modify: `.env.example`

**Step 1: Read current config to find insertion point**

Run: `grep -n "amap_api_key\|model_config" app/core/config.py`
Expected: 看到 `amap_api_key` 等字段位置；以及类底部。

**Step 2: 添加字段（在 `amap_api_key` 后追加一段）**

```python
# OpenRouter — 识景视觉模型（/v1/recognition）
openrouter_api_key: str = ""
openrouter_base_url: str = "https://openrouter.ai/api/v1"
openrouter_vision_model: str = "qwen/qwen3-vl-235b-a22b-instruct"
openrouter_vision_fallback_model: str = "qwen/qwen3-vl-30b-a3b-instruct"
recognition_max_image_bytes: int = 5 * 1024 * 1024
recognition_request_timeout: float = 30.0
```

**Step 3: 同步 `.env.example`**

```bash
cat >> .env.example <<'EOF'

# OpenRouter（/v1/recognition 识景）
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_VISION_MODEL=qwen/qwen3-vl-235b-a22b-instruct
OPENROUTER_VISION_FALLBACK_MODEL=qwen/qwen3-vl-30b-a3b-instruct
EOF
```

**Step 4: Verify import doesn't break**

Run: `python -c "from app.core.config import settings; print(settings.openrouter_vision_model)"`
Expected: `qwen/qwen3-vl-235b-a22b-instruct`

**Step 5: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat(recognition): add OpenRouter config fields"
```

---

## Task 2: 写 Pydantic 响应 schema

**Files:**
- Create: `app/api/public/v1/schemas/recognition.py`
- Test: `tests/test_recognition_schema.py`

**Step 1: Write failing test**

```python
# tests/test_recognition_schema.py
from app.api.public.v1.schemas.recognition import (
    RecognitionCandidate,
    RecognitionData,
    RecognitionFallback,
    RecognitionMeta,
)


def test_candidate_serializes_required_fields():
    c = RecognitionCandidate(
        bridge_id="abc-123",
        name="赵州桥",
        bridge_type="石拱桥",
        era="隋唐",
        region="河北",
        thumbnail=None,
        confidence_hints=["LLM exact match"],
    )
    dumped = c.model_dump()
    assert dumped["bridge_id"] == "abc-123"
    assert dumped["thumbnail"] is None


def test_data_allows_empty_candidates_with_fallback():
    d = RecognitionData(
        candidates=[],
        fallback_suggestions=RecognitionFallback(search_hint="某桥", region_hint=None),
    )
    assert d.candidates == []
    assert d.fallback_suggestions.search_hint == "某桥"


def test_meta_branch_enum():
    m = RecognitionMeta(model="qwen/qwen3-vl-235b-a22b-instruct", latency_ms=1234, branch="exact")
    assert m.branch == "exact"
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/test_recognition_schema.py -v`
Expected: `ModuleNotFoundError: No module named 'app.api.public.v1.schemas.recognition'`

**Step 3: Implement schema**

```python
# app/api/public/v1/schemas/recognition.py
from typing import Literal

from pydantic import BaseModel


class RecognitionCandidate(BaseModel):
    bridge_id: str
    name: str
    bridge_type: str
    era: str
    region: str
    thumbnail: str | None
    confidence_hints: list[str]


class RecognitionFallback(BaseModel):
    search_hint: str | None
    region_hint: str | None


class RecognitionData(BaseModel):
    candidates: list[RecognitionCandidate]
    fallback_suggestions: RecognitionFallback | None = None


class RecognitionMeta(BaseModel):
    model: str
    latency_ms: int
    branch: Literal["exact", "fuzzy", "fallback"]
```

**Step 4: Run, expect PASS**

Run: `pytest tests/test_recognition_schema.py -v`
Expected: 3 passed.

**Step 5: Commit**

```bash
git add app/api/public/v1/schemas/recognition.py tests/test_recognition_schema.py
git commit -m "feat(recognition): add Pydantic response schemas"
```

---

## Task 3: 桥梁名录拼装

**Files:**
- Create: `app/services/vision_recognition.py`
- Test: `tests/test_vision_recognition.py`

**Step 1: Write failing test**

```python
# tests/test_vision_recognition.py
from app.models import Bridge
from app.services.vision_recognition import build_bridge_catalog


def test_catalog_csv_format(db_session):
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.add(Bridge(name="南京长江大桥", region="江苏", era="现代", bridge_type="公铁两用桁架桥"))
    db_session.flush()

    csv = build_bridge_catalog(db_session)

    assert csv.splitlines()[0] == "name,region,era,bridge_type"
    assert "赵州桥,河北,隋唐,石拱桥" in csv
    assert "南京长江大桥,江苏,现代,公铁两用桁架桥" in csv


def test_catalog_handles_null_columns(db_session):
    db_session.add(Bridge(name="X 桥", region=None, era=None, bridge_type=None))
    db_session.flush()
    csv = build_bridge_catalog(db_session)
    assert "X 桥,,," in csv
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/test_vision_recognition.py::test_catalog_csv_format -v`
Expected: `ImportError: cannot import name 'build_bridge_catalog'`

**Step 3: Implement**

```python
# app/services/vision_recognition.py
from sqlalchemy.orm import Session

from app.models import Bridge


def build_bridge_catalog(db: Session) -> str:
    """Render all bridges as a CSV string for prompt injection.

    Stable column order (name,region,era,bridge_type) so OpenRouter prompt
    cache can hit on repeated requests as long as the catalog row set is
    unchanged.
    """
    rows = db.query(Bridge.name, Bridge.region, Bridge.era, Bridge.bridge_type).order_by(Bridge.name).all()
    lines = ["name,region,era,bridge_type"]
    for name, region, era, btype in rows:
        lines.append(f"{name},{region or ''},{era or ''},{btype or ''}")
    return "\n".join(lines)
```

**Step 4: Run, expect PASS**

Run: `pytest tests/test_vision_recognition.py -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add app/services/vision_recognition.py tests/test_vision_recognition.py
git commit -m "feat(recognition): bridge catalog CSV builder"
```

---

## Task 4: LLM 输出 JSON 解析（含错误降级）

**Files:**
- Modify: `app/services/vision_recognition.py`
- Modify: `tests/test_vision_recognition.py`

**Step 1: Add failing tests**

```python
# 追加到 tests/test_vision_recognition.py
import pytest

from app.services.vision_recognition import VisionResult, parse_vision_json


def test_parse_matched_name():
    r = parse_vision_json('{"matched_name": "赵州桥", "free_form": null}')
    assert r.matched_name == "赵州桥"
    assert r.free_form is None


def test_parse_free_form_only():
    raw = '{"matched_name": null, "free_form": {"bridge_name": "某桥", "region": "X 省", "bridge_type": "拱桥", "hints": ["a", "b"]}}'
    r = parse_vision_json(raw)
    assert r.matched_name is None
    assert r.free_form.bridge_name == "某桥"
    assert r.free_form.hints == ["a", "b"]


def test_parse_all_null_means_not_a_bridge():
    r = parse_vision_json('{"matched_name": null, "free_form": null}')
    assert r.matched_name is None
    assert r.free_form is None


def test_parse_invalid_json_returns_empty():
    """Don't 5xx the user — degrade to fallback branch."""
    r = parse_vision_json("not json at all {")
    assert r.matched_name is None
    assert r.free_form is None


def test_parse_partial_json_with_extra_text():
    """Some models prepend 'Sure, here is...' before JSON. Extract first {...} block."""
    raw = 'Sure! Here is the result:\n{"matched_name": "赵州桥", "free_form": null}\nDone.'
    r = parse_vision_json(raw)
    assert r.matched_name == "赵州桥"
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/test_vision_recognition.py::test_parse_matched_name -v`
Expected: `ImportError: cannot import name 'parse_vision_json'`

**Step 3: Implement**

```python
# 追加到 app/services/vision_recognition.py
import json
import re
from dataclasses import dataclass


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
    """Tolerant parser — extract first {...} block, return empty on any failure."""
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
```

**Step 4: Run, expect PASS**

Run: `pytest tests/test_vision_recognition.py -v`
Expected: 7 passed.

**Step 5: Commit**

```bash
git add app/services/vision_recognition.py tests/test_vision_recognition.py
git commit -m "feat(recognition): tolerant LLM JSON parser"
```

---

## Task 5: 三分支召回路由

**Files:**
- Modify: `app/services/vision_recognition.py`
- Modify: `tests/test_vision_recognition.py`

**Step 1: Add failing tests**

```python
# 追加到 tests/test_vision_recognition.py
from app.services.vision_recognition import (
    VisionFreeForm,
    VisionResult,
    route_candidates,
)


def test_route_branch_exact(db_session):
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(matched_name="赵州桥", free_form=None)

    candidates, fallback, branch = route_candidates(res, db_session)

    assert branch == "exact"
    assert len(candidates) == 1
    assert candidates[0].name == "赵州桥"
    assert candidates[0].confidence_hints == ["LLM 命中已知桥梁名录"]
    assert fallback is None


def test_route_branch_fuzzy(db_session):
    db_session.add(Bridge(name="安济桥（赵州桥）", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()
    res = VisionResult(
        matched_name=None,
        free_form=VisionFreeForm(bridge_name="赵州", region="河北", bridge_type="石拱桥", hints=["跨度大", "唐代"]),
    )

    candidates, fallback, branch = route_candidates(res, db_session)

    assert branch == "fuzzy"
    assert any("安济桥" in c.name for c in candidates)
    assert candidates[0].confidence_hints == ["跨度大", "唐代"]
    assert fallback is None


def test_route_branch_fallback_unknown_bridge(db_session):
    """No DB match — return empty candidates + fallback hints."""
    res = VisionResult(
        matched_name=None,
        free_form=VisionFreeForm(bridge_name="不存在桥", region="火星", bridge_type="", hints=[]),
    )

    candidates, fallback, branch = route_candidates(res, db_session)

    assert branch == "fallback"
    assert candidates == []
    assert fallback.search_hint == "不存在桥"
    assert fallback.region_hint == "火星"


def test_route_branch_fallback_not_a_bridge(db_session):
    res = VisionResult(matched_name=None, free_form=None)
    candidates, fallback, branch = route_candidates(res, db_session)
    assert branch == "fallback"
    assert candidates == []
    assert fallback is None  # 没线索给前端
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/test_vision_recognition.py::test_route_branch_exact -v`

**Step 3: Implement**

```python
# 追加到 app/services/vision_recognition.py
from sqlalchemy import case, or_

from app.api.public.v1.schemas.recognition import RecognitionCandidate, RecognitionFallback
from app.api.public.v1.utils import escape_like
from app.models.bridge_image import BridgeImage
from app.services.bridge_image_service import BridgeImageService


def _bridge_to_candidate(bridge: Bridge, hints: list[str], db: Session) -> RecognitionCandidate:
    img = (
        db.query(BridgeImage)
        .filter(BridgeImage.bridge_id == bridge.id)
        .order_by(BridgeImage.order_index.asc())
        .first()
    )
    thumbnail = BridgeImageService.get_public_url(img.r2_key) if img else None
    return RecognitionCandidate(
        bridge_id=str(bridge.id),
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
    """Three-branch dispatcher. See design doc §4 / §7."""

    # 分支①: exact
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
        # matched_name 但库里没有 → 视为 free_form 走分支②
        result = VisionResult(
            matched_name=None,
            free_form=VisionFreeForm(
                bridge_name=result.matched_name, region="", bridge_type="", hints=[]
            ),
        )

    # 分支②: fuzzy
    if result.free_form and result.free_form.bridge_name:
        ff = result.free_form
        like_contains = f"%{escape_like(ff.bridge_name)}%"
        score = case(
            (Bridge.name.ilike(ff.bridge_name), 100),
            (Bridge.name.ilike(f"{escape_like(ff.bridge_name)}%"), 80),
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
            candidates = [_bridge_to_candidate(b, ff.hints or ["LLM 自由识别匹配"], db) for b, _ in rows]
            return candidates, None, "fuzzy"
        # 无库内匹配 → 分支③
        return (
            [],
            RecognitionFallback(search_hint=ff.bridge_name, region_hint=ff.region or None),
            "fallback",
        )

    # 分支③: 全空（不是桥）
    return [], None, "fallback"
```

**Step 4: Run, expect PASS**

Run: `pytest tests/test_vision_recognition.py -v`
Expected: 11 passed.

**Step 5: Commit**

```bash
git add app/services/vision_recognition.py tests/test_vision_recognition.py
git commit -m "feat(recognition): three-branch candidate router"
```

---

## Task 6: OpenRouter HTTP 调用 + 降级链

**Files:**
- Modify: `app/services/vision_recognition.py`
- Modify: `tests/test_vision_recognition.py`

**Step 1: Add failing tests（mock httpx）**

```python
# 追加到 tests/test_vision_recognition.py
import httpx
import pytest
import respx

from app.core.config import settings
from app.services.vision_recognition import call_openrouter_vision


@respx.mock
def test_openrouter_primary_success():
    settings.openrouter_api_key = "test-key"
    respx.post(f"{settings.openrouter_base_url}/chat/completions").respond(
        200,
        json={"choices": [{"message": {"content": '{"matched_name": "赵州桥", "free_form": null}'}}]},
    )
    raw, model_used = call_openrouter_vision(
        image_b64="fake", mime="image/jpeg", catalog_csv="name,region,era,bridge_type\n",
        latitude=None, longitude=None,
    )
    assert "赵州桥" in raw
    assert model_used == settings.openrouter_vision_model


@respx.mock
def test_openrouter_falls_back_on_5xx():
    settings.openrouter_api_key = "test-key"
    route = respx.post(f"{settings.openrouter_base_url}/chat/completions")
    route.side_effect = [
        httpx.Response(503, json={"error": "down"}),
        httpx.Response(200, json={"choices": [{"message": {"content": '{"matched_name":null,"free_form":null}'}}]}),
    ]
    raw, model_used = call_openrouter_vision(
        image_b64="fake", mime="image/jpeg", catalog_csv="x", latitude=None, longitude=None,
    )
    assert model_used == settings.openrouter_vision_fallback_model


@respx.mock
def test_openrouter_both_models_503_raises():
    from app.providers.errors import ProviderUnavailableError
    settings.openrouter_api_key = "test-key"
    respx.post(f"{settings.openrouter_base_url}/chat/completions").respond(503, json={"error": "x"})
    with pytest.raises(ProviderUnavailableError):
        call_openrouter_vision(
            image_b64="fake", mime="image/jpeg", catalog_csv="x", latitude=None, longitude=None,
        )


def test_openrouter_missing_api_key_raises():
    from app.providers.errors import ProviderConfigurationError
    settings.openrouter_api_key = ""
    with pytest.raises(ProviderConfigurationError):
        call_openrouter_vision(
            image_b64="fake", mime="image/jpeg", catalog_csv="x", latitude=None, longitude=None,
        )
```

**Step 2: Install respx if missing**

Run: `pip show respx >/dev/null 2>&1 || pip install respx`

**Step 3: Run, expect FAIL**

Run: `pytest tests/test_vision_recognition.py::test_openrouter_primary_success -v`
Expected: `ImportError: cannot import name 'call_openrouter_vision'`

**Step 4: Implement**

```python
# 追加到 app/services/vision_recognition.py
import logging

import httpx

from app.core.config import settings
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError

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


def _build_messages(catalog_csv: str, image_b64: str, mime: str, latitude: float | None, longitude: float | None) -> list[dict]:
    user_text = ""
    if latitude is not None and longitude is not None:
        user_text = f"可选位置：纬度 {latitude}，经度 {longitude}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(catalog=catalog_csv)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text or "请识别这张图片中的桥梁。"},
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
    return data["choices"][0]["message"]["content"]


def call_openrouter_vision(
    image_b64: str,
    mime: str,
    catalog_csv: str,
    latitude: float | None,
    longitude: float | None,
) -> tuple[str, str]:
    """Call OpenRouter Qwen3-VL with primary→fallback model chain.

    Returns (raw_content, model_used). Raises ProviderUnavailableError if
    both models fail with 5xx/429/transport.
    """
    if not settings.openrouter_api_key:
        raise ProviderConfigurationError("OPENROUTER_API_KEY not set — /v1/recognition disabled")

    messages = _build_messages(catalog_csv, image_b64, mime, latitude, longitude)

    for model in (settings.openrouter_vision_model, settings.openrouter_vision_fallback_model):
        try:
            return _post_openrouter(model, messages), model
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status is not None and status < 500 and status != 429:
                # 4xx (other than 429) is not retryable — propagate
                raise
            logger.warning("OpenRouter %s failed (status=%s) — trying next model", model, status)

    raise ProviderUnavailableError("OpenRouter vision: both primary and fallback models failed")
```

**Step 5: Run, expect PASS**

Run: `pytest tests/test_vision_recognition.py -v`
Expected: 15 passed.

**Step 6: Commit**

```bash
git add app/services/vision_recognition.py tests/test_vision_recognition.py
git commit -m "feat(recognition): OpenRouter call with primary→fallback chain"
```

---

## Task 7: FastAPI 路由 + 注册

**Files:**
- Create: `app/api/public/v1/recognition.py`
- Modify: `app/api/public/v1/__init__.py`（追加 import + include_router）
- Test: `tests/test_api_public_recognition.py`

**Step 1: Write failing route-existence test**

```python
# tests/test_api_public_recognition.py
from app.main import app


def test_recognition_route_registered():
    paths = [r.path for r in app.routes]
    assert "/v1/recognition" in paths
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/test_api_public_recognition.py::test_recognition_route_registered -v`
Expected: `assert '/v1/recognition' in [...]` AssertionError.

**Step 3: Create route file**

```python
# app/api/public/v1/recognition.py
"""Public API: 识景 — POST /v1/recognition."""
import base64
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.common import PublicMeta, PublicResponse
from app.api.public.v1.schemas.recognition import RecognitionData, RecognitionMeta
from app.core.config import settings
from app.core.database import get_db
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError
from app.services.vision_recognition import (
    build_bridge_catalog,
    call_openrouter_vision,
    parse_vision_json,
    route_candidates,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_MIME = {"image/jpeg", "image/png"}


@router.post("", response_model=PublicResponse[RecognitionData])
def recognize(
    image: Annotated[UploadFile, File()],
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
    db: Session = Depends(get_db),
):
    if image.content_type not in _ALLOWED_MIME:
        raise HTTPException(415, detail={"code": "unsupported_media_type", "message": "仅支持 image/jpeg 与 image/png"})

    raw_bytes = image.file.read()
    if len(raw_bytes) > settings.recognition_max_image_bytes:
        raise HTTPException(413, detail={"code": "file_too_large", "message": f"图片不能超过 {settings.recognition_max_image_bytes // (1024 * 1024)} MB"})

    image_b64 = base64.b64encode(raw_bytes).decode()
    catalog = build_bridge_catalog(db)

    started = time.perf_counter()
    try:
        raw_content, model_used = call_openrouter_vision(
            image_b64=image_b64,
            mime=image.content_type,
            catalog_csv=catalog,
            latitude=latitude,
            longitude=longitude,
        )
    except ProviderConfigurationError as exc:
        logger.error("recognition disabled: %s", exc)
        raise HTTPException(503, detail={"code": "vision_disabled", "message": "识景服务未配置"}) from exc
    except ProviderUnavailableError as exc:
        logger.warning("recognition upstream failed: %s", exc)
        raise HTTPException(503, detail={"code": "vision_unavailable", "message": "识景服务暂时不可用，请稍后再试"}) from exc

    parsed = parse_vision_json(raw_content)
    candidates, fallback, branch = route_candidates(parsed, db)
    latency_ms = int((time.perf_counter() - started) * 1000)

    return PublicResponse(
        data=RecognitionData(candidates=candidates, fallback_suggestions=fallback),
        meta=PublicMeta(
            extra={
                "recognition": RecognitionMeta(model=model_used, latency_ms=latency_ms, branch=branch).model_dump()
            }
        ),
    )
```

> **Note:** `PublicResponse` / `PublicMeta` 的精确签名以 `app/api/public/v1/schemas/common.py` 为准 —— 若 `PublicMeta(extra=...)` 不接受 dict，改成 `model_dump_json()` 直接返回 raw dict 也可。先用此形态跑，CI 出错按 schemas/common 修。

**Step 4: Register router**

修改 `app/api/public/v1/__init__.py`：

```python
# 在 import 行追加 recognition
from app.api.public.v1 import bridges, config, favorites, history, knowledge, qa, recognition, review, search

# 在 include_router 段追加
router.include_router(recognition.router, prefix="/recognition")
```

**Step 5: Run, expect PASS**

Run: `pytest tests/test_api_public_recognition.py::test_recognition_route_registered -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add app/api/public/v1/recognition.py app/api/public/v1/__init__.py tests/test_api_public_recognition.py
git commit -m "feat(recognition): wire /v1/recognition route"
```

---

## Task 8: 端到端 happy path 测试（mock OpenRouter）

**Files:**
- Modify: `tests/test_api_public_recognition.py`

**Step 1: Add failing tests**

```python
# 追加到 tests/test_api_public_recognition.py
import io

import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import settings
from app.main import app
from app.models import Bridge


@respx.mock
def test_recognition_exact_happy_path(db_session, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": '{"matched_name":"赵州桥","free_form":null}'}}]})
    )

    client = TestClient(app)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fake"), "image/jpeg")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["candidates"][0]["name"] == "赵州桥"
    assert body["data"]["fallback_suggestions"] is None


@respx.mock
def test_recognition_413_oversize(db_session, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "recognition_max_image_bytes", 100)

    client = TestClient(app)
    big = io.BytesIO(b"x" * 200)
    resp = client.post("/v1/recognition", files={"image": ("big.jpg", big, "image/jpeg")})

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "file_too_large"


def test_recognition_415_wrong_mime(db_session):
    client = TestClient(app)
    resp = client.post("/v1/recognition", files={"image": ("evil.gif", io.BytesIO(b"GIF89a"), "image/gif")})
    assert resp.status_code == 415


@respx.mock
def test_recognition_fallback_branch(db_session, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    respx.post(f"{settings.openrouter_base_url}/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": '{"matched_name":null,"free_form":null}'}}]})
    )

    client = TestClient(app)
    resp = client.post("/v1/recognition", files={"image": ("cat.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json()["data"]["candidates"] == []


@respx.mock
def test_recognition_503_when_both_models_fail(db_session, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.flush()

    respx.post(f"{settings.openrouter_base_url}/chat/completions").respond(503, json={"error": "x"})

    client = TestClient(app)
    resp = client.post("/v1/recognition", files={"image": ("x.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "vision_unavailable"
```

**Step 2: Run, expect ALL PASS**

Run: `pytest tests/test_api_public_recognition.py -v`
Expected: 5 passed.

> 若 4 号 test 因 fixture session 与 TestClient 走两个 DB 连接而看不到 Bridge → 改用 `app.dependency_overrides[get_db]` 注入 `db_session`，参考其他 `tests/test_api_public_*.py` 同款用法。

**Step 3: Commit**

```bash
git add tests/test_api_public_recognition.py
git commit -m "test(recognition): end-to-end happy path + error cases"
```

---

## Task 9: 跑全量测试 + 手动 e2e

**Step 1: 全量回归**

Run: `pytest tests/ -v --maxfail=3 2>&1 | tail -40`
Expected: 全绿（或在已知 unrelated failures 范围内）。

**Step 2: 启服务**

```bash
export OPENROUTER_API_KEY=<真 key>   # 没有就跳过 e2e，依赖单测验证
uvicorn app.main:app --reload --port 8000
```

**Step 3: 真实图片 e2e**

```bash
# 假定本地 ./赵州桥.jpg 存在
curl -sX POST http://localhost:8000/v1/recognition \
  -F "image=@./赵州桥.jpg;type=image/jpeg" | jq .
```

Expected: `data.candidates[0].name == "赵州桥"`，`meta.recognition.branch == "exact"`。

**Step 4: 启 web，手动跑识景页**

```bash
cd /Users/uu/Documents/Coding/4C2026/web
npm run dev   # http://localhost:3000/zh-CN/recognize
```

打开页面拖一张桥梁图 → 应看到候选；拖一张猫图 → 应看到 fallback。

**Step 5: Commit checkpoint（如有零碎修复）**

```bash
git add -A && git commit -m "fix(recognition): post-e2e adjustments" || echo "no changes"
```

---

## Task 10: 收口 PR

**Step 1: Push 分支**

```bash
git push -u origin feat/recognition-vision
```

**Step 2: gh pr create**

```bash
gh pr create --title "feat(recognition): /v1/recognition with OpenRouter Qwen3-VL" --body "$(cat <<'EOF'
## Summary
- 接 RAG#170：补齐 C 端识景页缺失的后端 `/v1/recognition`
- 模型：OpenRouter `qwen/qwen3-vl-235b-a22b-instruct`，限流降级到 `qwen3-vl-30b-a3b-instruct`
- 策略 C 混合召回：注入桥梁名录 + LLM 输出 matched_name/free_form → 三分支（exact/fuzzy/fallback）

设计：`docs/plans/2026-04-26-recognition-design.md`
实施：`docs/plans/2026-04-26-recognition-implementation.md`

## Test plan
- [ ] `pytest tests/test_recognition_schema.py tests/test_vision_recognition.py tests/test_api_public_recognition.py -v` 全绿
- [ ] 配置 `OPENROUTER_API_KEY` 后 curl 真实赵州桥图片返回 exact 命中
- [ ] curl 猫图返回 fallback、`candidates=[]`
- [ ] 6MB 图返回 413、`image/gif` 返回 415
- [ ] `web/` 识景页手动 e2e：拖图看到候选 / fallback
EOF
)"
```

---

## Post-merge cleanup

合并到 main 后，回原工作树清理 worktree：

```bash
cd /Users/uu/Documents/Coding/4C2026/RAG
git worktree remove .worktrees/recognition-vision
git branch -d feat/recognition-vision
```

---

## Risk Matrix

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| OpenRouter Qwen3-VL 偶发限流 | 中 | 用户感知卡顿 | 已有降级链 235B → 30B-A3B |
| LLM 返回非 JSON | 低 | 用户看到 fallback 而非 candidates | `parse_vision_json` 容错→ branch=fallback，不 5xx |
| `bridges` 表涨到 1000+ 行致 prompt 超长 | 远期 | prompt 偏贵但不超 context | 加地理半径过滤是 P1，本期不做 |
| OpenRouter prompt cache 未命中 | 低 | 单次贵 ~$0.003 | 系统 prompt 字面量保持稳定，靠拼装顺序保 |
| `PublicMeta(extra=...)` 签名不兼容 | 低 | Task 7 单测红 | 按 schemas/common.py 真实签名调（任务 7 step 3 已留 note） |

---

**总计：10 任务 · ~50 步 · TDD · 每任务结束有 commit · 单测 + e2e 双闭环**
