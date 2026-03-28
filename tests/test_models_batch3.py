"""Unit tests for Batch 3 models (bridge_images, knowledge_point_bridges, geocode_source)."""

from sqlalchemy import inspect

from app.models.bridge import Bridge
from app.models.bridge_image import BridgeImage
from app.models.knowledge_point_bridge import KnowledgePointBridge


def test_bridge_image_tablename():
    assert BridgeImage.__tablename__ == "bridge_images"


def test_bridge_image_model_has_expected_columns():
    mapper = inspect(BridgeImage)
    columns = {c.key for c in mapper.columns}
    expected = {"id", "bridge_id", "r2_key", "caption", "type", "order_index", "created_at"}
    assert expected == columns


def test_knowledge_point_bridge_tablename():
    assert KnowledgePointBridge.__tablename__ == "knowledge_point_bridges"


def test_knowledge_point_bridge_model_has_expected_columns():
    mapper = inspect(KnowledgePointBridge)
    columns = {c.key for c in mapper.columns}
    expected = {"id", "knowledge_point_id", "bridge_id", "relevance_note", "order_index", "created_at"}
    assert expected == columns


def test_bridge_has_geocode_source_column():
    mapper = inspect(Bridge)
    columns = {c.key for c in mapper.columns}
    assert "geocode_source" in columns
