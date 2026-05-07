"""Tests for KnowledgePoint and KnowledgePointKeyPoint models."""
import uuid

from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint


def test_knowledge_point_model_structure():
    """Test KnowledgePoint has correct table name and fields."""
    assert KnowledgePoint.__tablename__ == "knowledge_points"
    columns = {c.name for c in KnowledgePoint.__table__.columns}
    assert columns == {
        "id", "taxonomy_node_id", "name", "aliases", "difficulty",
        "summary", "l2_content", "created_at", "updated_at",
        # v10: lvl3→KP merge moved lvl1/lvl2 onto the KP row
        "lvl1", "lvl2",
        # v12: i18n translation pair for the display name + summary
        "name_en", "summary_en",
        # v16: aliases mirror so "Also known as:" line en-localizes
        "aliases_en",
    }


def test_knowledge_point_key_point_model_structure():
    """Test KnowledgePointKeyPoint has correct table name and fields."""
    assert KnowledgePointKeyPoint.__tablename__ == "knowledge_point_key_points"
    columns = {c.name for c in KnowledgePointKeyPoint.__table__.columns}
    assert columns == {
        "id", "knowledge_point_id", "summary", "explanation",
        # v15: i18n translation pair for inline审校 of 要点
        "summary_en", "explanation_en",
        "order_index", "chunk_ids", "illustration_urls",
        "related_term_ids", "created_at",
    }


def test_knowledge_point_importable_from_models():
    """Test models are registered in __init__.py."""
    from app.models import KnowledgePoint, KnowledgePointKeyPoint
    assert KnowledgePoint is not None
    assert KnowledgePointKeyPoint is not None
