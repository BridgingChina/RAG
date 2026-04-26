"""Public API: 识景 — POST /v1/recognition."""
import base64
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.common import PublicResponse
from app.api.public.v1.schemas.recognition import RecognitionData
from app.core.config import settings
from app.core.database import get_db
from app.providers.errors import ProviderConfigurationError, ProviderUnavailableError

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_MIME = {"image/jpeg", "image/png"}


@router.post("", response_model=PublicResponse[RecognitionData])
def recognize(
    image: Annotated[UploadFile, File()],
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
    db: Session = Depends(get_db),
) -> PublicResponse[RecognitionData]:
    # Imported lazily to avoid a circular import: vision_recognition imports
    # app.api.public.v1.schemas.recognition, which initializes the public v1
    # package (including this module).
    from app.services.vision_recognition import (
        build_bridge_catalog,
        call_openrouter_vision,
        parse_vision_json,
        route_candidates,
    )

    if image.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            415,
            detail={
                "code": "unsupported_media_type",
                "message": "仅支持 image/jpeg 与 image/png",
            },
        )

    raw_bytes = image.file.read()
    if len(raw_bytes) > settings.recognition_max_image_bytes:
        max_mb = settings.recognition_max_image_bytes // (1024 * 1024)
        raise HTTPException(
            413,
            detail={
                "code": "file_too_large",
                "message": f"图片不能超过 {max_mb} MB",
            },
        )

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
        raise HTTPException(
            503,
            detail={"code": "vision_disabled", "message": "识景服务未配置"},
        ) from exc
    except ProviderUnavailableError as exc:
        logger.warning("recognition upstream failed: %s", exc)
        raise HTTPException(
            503,
            detail={
                "code": "vision_unavailable",
                "message": "识景服务暂时不可用，请稍后再试",
            },
        ) from exc

    parsed = parse_vision_json(raw_content)
    candidates, fallback, branch = route_candidates(parsed, db)
    latency_ms = int((time.perf_counter() - started) * 1000)

    logger.info(
        "recognition served: model=%s branch=%s candidates=%d latency_ms=%d",
        model_used,
        branch,
        len(candidates),
        latency_ms,
    )

    return PublicResponse(
        data=RecognitionData(
            candidates=candidates,
            fallback_suggestions=fallback,
        ),
    )
