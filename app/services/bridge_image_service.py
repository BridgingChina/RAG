"""Bridge image management service — presign upload, CRUD, reorder via R2."""

import os
import uuid

from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.bridge_image import BridgeImage
from app.services.r2_storage import R2StorageService


class BridgeImageService:
    def __init__(self, r2: R2StorageService):
        self.r2 = r2

    def presign_upload(
        self,
        db: Session,
        bridge_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> tuple[BridgeImage, str]:
        """Create BridgeImage record + return presigned upload URL.

        R2 key pattern: bridges/images/{bridge_id}/{uuid}.{ext}
        Returns (image_record, upload_url).
        """
        ext = os.path.splitext(filename)[1].lstrip(".") or "jpg"
        r2_key = f"bridges/images/{bridge_id}/{uuid.uuid4()}.{ext}"

        # Determine next order_index
        max_idx = (
            db.query(BridgeImage.order_index)
            .filter(BridgeImage.bridge_id == bridge_id)
            .order_by(BridgeImage.order_index.desc())
            .limit(1)
            .scalar()
        )
        next_idx = (max_idx + 1) if max_idx is not None else 0

        image = BridgeImage(
            bridge_id=bridge_id,
            r2_key=r2_key,
            order_index=next_idx,
        )
        db.add(image)
        db.flush()  # get the id

        upload_url = self.r2.generate_presigned_upload_url(r2_key, content_type)
        return image, upload_url

    def confirm_upload(
        self,
        db: Session,
        image_id: uuid.UUID,
        caption: str | None = None,
        image_type: str | None = None,
    ) -> BridgeImage:
        """Update caption/type after successful upload. Returns updated record."""
        image = db.query(BridgeImage).filter(BridgeImage.id == image_id).first()
        if not image:
            raise ValueError(f"BridgeImage {image_id} not found")
        if caption is not None:
            image.caption = caption
        if image_type is not None:
            image.type = image_type
        db.flush()
        return image

    def list_images(self, db: Session, bridge_id: uuid.UUID) -> list[BridgeImage]:
        """List images for a bridge, ordered by order_index."""
        return (
            db.query(BridgeImage)
            .filter(BridgeImage.bridge_id == bridge_id)
            .order_by(asc(BridgeImage.order_index))
            .all()
        )

    def reorder(
        self, db: Session, bridge_id: uuid.UUID, image_ids: list[uuid.UUID]
    ) -> None:
        """Reorder images: image_ids[0] gets order_index=0, etc."""
        for idx, image_id in enumerate(image_ids):
            db.query(BridgeImage).filter(
                BridgeImage.id == image_id,
                BridgeImage.bridge_id == bridge_id,
            ).update({BridgeImage.order_index: idx}, synchronize_session=False)
        db.flush()

    def delete(self, db: Session, image_id: uuid.UUID) -> str:
        """Delete image record + R2 object. Returns the r2_key for audit."""
        image = db.query(BridgeImage).filter(BridgeImage.id == image_id).first()
        if not image:
            raise ValueError(f"BridgeImage {image_id} not found")
        r2_key = image.r2_key
        # Delete from R2 (best effort — record deletion is authoritative)
        try:
            self.r2.delete_prefix(r2_key)  # works for single key too
        except Exception:
            pass  # R2 cleanup failure shouldn't block DB deletion
        db.delete(image)
        db.flush()
        return r2_key

    @staticmethod
    def get_public_url(r2_key: str) -> str:
        """If r2_public_url is set, return public URL. Otherwise presigned GET."""
        if settings.r2_public_url:
            return f"{settings.r2_public_url.rstrip('/')}/{r2_key}"
        # Fallback to presigned download URL
        r2 = R2StorageService()
        return r2.generate_presigned_download_url(r2_key, expires=3600)
