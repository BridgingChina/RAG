"""Tests for Batch 2 models + Phase 2 identity-refactored user-scoped tables."""


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


def test_favorite_model():
    from app.models.favorite import Favorite
    columns = {c.name for c in Favorite.__table__.columns}
    assert {"id", "user_id", "target_type", "target_id", "created_at"}.issubset(columns)
    assert Favorite.__tablename__ == "favorites"


def test_review_progress_model():
    from app.models.review_progress import ReviewProgress
    columns = {c.name for c in ReviewProgress.__table__.columns}
    assert {
        "user_id", "flashcard_id", "mastery", "last_reviewed_at",
        "next_review_at", "interval_days", "ease_factor",
    }.issubset(columns)
    assert ReviewProgress.__tablename__ == "review_progress"


def test_view_history_model():
    from app.models.view_history import ViewHistory
    columns = {c.name for c in ViewHistory.__table__.columns}
    assert {"id", "user_id", "target_type", "target_id", "viewed_at"}.issubset(columns)
    assert ViewHistory.__tablename__ == "view_history"


def test_all_user_scoped_models_registered():
    from app.models import Flashcard, Favorite, ReviewProgress, ViewHistory
    assert Flashcard.__tablename__ == "flashcards"
    assert Favorite.__tablename__ == "favorites"
    assert ReviewProgress.__tablename__ == "review_progress"
    assert ViewHistory.__tablename__ == "view_history"


def test_schema_version_is_11():
    from app.core.database import LATEST_SCHEMA_VERSION
    assert LATEST_SCHEMA_VERSION == 11
