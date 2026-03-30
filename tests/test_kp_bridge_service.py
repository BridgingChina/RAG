"""Unit tests for KnowledgePointBridgeService (no DB/LLM needed)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.kp_bridge_service import KnowledgePointBridgeService


def _make_uuid():
    return uuid.uuid4()


def _mock_kp(taxonomy_node_id=None, name="拱桥结构"):
    kp = MagicMock()
    kp.id = _make_uuid()
    kp.taxonomy_node_id = taxonomy_node_id
    kp.name = name
    return kp


def _mock_taxonomy_node(lvl3="拱桥结构"):
    node = MagicMock()
    node.id = _make_uuid()
    node.lvl3 = lvl3
    return node


def _mock_bridge(name="赵州桥"):
    bridge = MagicMock()
    bridge.id = _make_uuid()
    bridge.name = name
    return bridge


class TestSyncFromChunks:
    """Tests for sync_from_chunks method."""

    @pytest.mark.asyncio
    async def test_derives_bridges_from_chunk_links(self):
        """sync_from_chunks should find bridges via chunk taxonomy → chunk_bridge_links."""
        svc = KnowledgePointBridgeService()

        taxonomy_node = _mock_taxonomy_node(lvl3="拱桥结构")
        kp = _mock_kp(taxonomy_node_id=taxonomy_node.id, name="拱桥结构")
        bridge1 = _mock_bridge("赵州桥")
        bridge2 = _mock_bridge("卢沟桥")

        # Mock db session
        db = MagicMock()

        # Setup query chains
        def query_side_effect(model):
            mock_q = MagicMock()
            if model.__name__ == "KnowledgePoint":
                mock_q.filter.return_value.first.return_value = kp
            elif model.__name__ == "TaxonomyNode":
                mock_q.filter.return_value.first.return_value = taxonomy_node
            elif model.__name__ == "Bridge":
                mock_q.filter.return_value.all.return_value = [bridge1, bridge2]
            elif model.__name__ == "KnowledgePointBridge":
                mock_q.filter.return_value.delete.return_value = 0
            return mock_q

        db.query.side_effect = query_side_effect

        # Mock the distinct query for bridge_ids (uses join)
        # This is tricky — the distinct query chain is:
        # db.query(distinct(ChunkBridgeLink.bridge_id)).join(...).filter(...).all()
        # We need to handle when query receives a non-model argument
        original_side_effect = db.query.side_effect

        def enhanced_side_effect(*args):
            # If it's not a model class (e.g., distinct(...)), return bridge_id results
            if not hasattr(args[0], "__name__"):
                mock_q = MagicMock()
                mock_q.join.return_value.filter.return_value.all.return_value = [
                    (bridge1.id,),
                    (bridge2.id,),
                ]
                return mock_q
            return original_side_effect(args[0])

        db.query.side_effect = enhanced_side_effect

        result = await svc.sync_from_chunks(db, kp.id, provider=None)

        assert len(result) == 2
        assert result[0].bridge_id == bridge1.id
        assert result[1].bridge_id == bridge2.id
        # Default notes when no provider
        assert result[0].relevance_note == "与拱桥结构相关"

    @pytest.mark.asyncio
    async def test_generates_default_note_without_provider(self):
        """Without a provider, relevance_note should use default text."""
        svc = KnowledgePointBridgeService()

        taxonomy_node = _mock_taxonomy_node(lvl3="桥墩设计")
        kp = _mock_kp(taxonomy_node_id=taxonomy_node.id, name="桥墩设计")
        bridge = _mock_bridge("洛阳桥")

        db = MagicMock()

        def query_side_effect(*args):
            if not hasattr(args[0], "__name__"):
                mock_q = MagicMock()
                mock_q.join.return_value.filter.return_value.all.return_value = [
                    (bridge.id,),
                ]
                return mock_q
            mock_q = MagicMock()
            model = args[0]
            if model.__name__ == "KnowledgePoint":
                mock_q.filter.return_value.first.return_value = kp
            elif model.__name__ == "TaxonomyNode":
                mock_q.filter.return_value.first.return_value = taxonomy_node
            elif model.__name__ == "Bridge":
                mock_q.filter.return_value.all.return_value = [bridge]
            elif model.__name__ == "KnowledgePointBridge":
                mock_q.filter.return_value.delete.return_value = 0
            return mock_q

        db.query.side_effect = query_side_effect

        result = await svc.sync_from_chunks(db, kp.id, provider=None)

        assert len(result) == 1
        assert result[0].relevance_note == "与桥墩设计相关"

    @pytest.mark.asyncio
    async def test_raises_when_no_taxonomy_node(self):
        """Should raise ValueError when KP has no taxonomy_node_id."""
        svc = KnowledgePointBridgeService()
        kp = _mock_kp(taxonomy_node_id=None)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = kp

        with pytest.raises(ValueError, match="no taxonomy_node_id"):
            await svc.sync_from_chunks(db, kp.id)


class TestReplaceAll:
    """Tests for replace_all method."""

    def test_creates_correct_records(self):
        """replace_all should delete existing and create new associations."""
        svc = KnowledgePointBridgeService()

        kp_id = _make_uuid()
        bridge_id_1 = _make_uuid()
        bridge_id_2 = _make_uuid()

        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 0

        items = [
            {"bridge_id": bridge_id_1, "relevance_note": "说明1", "order_index": 0},
            {"bridge_id": bridge_id_2, "relevance_note": "说明2", "order_index": 1},
        ]

        result = svc.replace_all(db, kp_id, items)

        assert len(result) == 2
        assert result[0].bridge_id == bridge_id_1
        assert result[0].relevance_note == "说明1"
        assert result[0].order_index == 0
        assert result[1].bridge_id == bridge_id_2
        assert result[1].order_index == 1
        assert db.add.call_count == 2

    def test_replace_with_empty_list(self):
        """replace_all with empty list should just delete existing."""
        svc = KnowledgePointBridgeService()
        kp_id = _make_uuid()

        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 3

        result = svc.replace_all(db, kp_id, [])

        assert len(result) == 0
        assert db.add.call_count == 0
