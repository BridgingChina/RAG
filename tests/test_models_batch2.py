"""Tests for Batch 2 models."""


def test_flashcard_model_has_expected_columns():
    from app.models.flashcard import Flashcard
    columns = {c.name for c in Flashcard.__table__.columns}
    expected = {
        "id", "knowledge_point_id", "card_type", "front_title", "front_hint",
        "back_answer", "back_key_features", "back_example_bridge_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(columns)
    assert Flashcard.__tablename__ == "flashcards"


def test_device_favorite_model():
    from app.models.device_favorite import DeviceFavorite
    columns = {c.name for c in DeviceFavorite.__table__.columns}
    assert {"id", "device_id", "target_type", "target_id", "created_at"}.issubset(columns)
    assert DeviceFavorite.__tablename__ == "device_favorites"


def test_device_review_progress_model():
    from app.models.device_review_progress import DeviceReviewProgress
    columns = {c.name for c in DeviceReviewProgress.__table__.columns}
    assert {"id", "device_id", "flashcard_id", "mastery", "last_reviewed_at", "interval", "ease_factor"}.issubset(columns)
    assert DeviceReviewProgress.__tablename__ == "device_review_progress"


def test_device_view_history_model():
    from app.models.device_view_history import DeviceViewHistory
    columns = {c.name for c in DeviceViewHistory.__table__.columns}
    assert {"id", "device_id", "target_type", "target_id", "viewed_at"}.issubset(columns)
    assert DeviceViewHistory.__tablename__ == "device_view_history"


def test_all_batch2_models_registered():
    from app.models import Flashcard, DeviceFavorite, DeviceReviewProgress, DeviceViewHistory
    assert Flashcard.__tablename__ == "flashcards"
    assert DeviceFavorite.__tablename__ == "device_favorites"
    assert DeviceReviewProgress.__tablename__ == "device_review_progress"
    assert DeviceViewHistory.__tablename__ == "device_view_history"


def test_schema_version_is_8():
    from app.core.database import LATEST_SCHEMA_VERSION
    assert LATEST_SCHEMA_VERSION == 8
