"""Service for managing knowledge_point ↔ bridge associations."""
import json
import logging
from uuid import UUID

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.models import (
    Bridge,
    Chunk,
    ChunkBridgeLink,
    KnowledgePoint,
    KnowledgePointBridge,
    TaxonomyNode,
)

logger = logging.getLogger(__name__)


class KnowledgePointBridgeService:
    """Manage KnowledgePoint-Bridge associations."""

    async def sync_from_chunks(
        self,
        db: Session,
        knowledge_point_id: UUID,
        provider=None,
    ) -> list[KnowledgePointBridge]:
        """Auto-derive KP-bridge associations from chunk taxonomy tags.

        1. Get KP's taxonomy_node → lvl3 value
        2. Find chunks with matching lvl3
        3. Join chunk_bridge_links → get distinct bridge_ids
        4. Optionally call LLM to generate relevance_note
        5. Delete existing associations, insert new ones
        """
        # 1. Get KP and its taxonomy node's lvl3
        kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == knowledge_point_id).first()
        if not kp:
            raise ValueError(f"KnowledgePoint {knowledge_point_id} not found")

        if not kp.taxonomy_node_id:
            raise ValueError("KnowledgePoint has no taxonomy_node_id")

        taxonomy_node = (
            db.query(TaxonomyNode)
            .filter(TaxonomyNode.id == kp.taxonomy_node_id)
            .first()
        )
        if not taxonomy_node or not taxonomy_node.lvl3:
            raise ValueError("Taxonomy node not found or has no lvl3 value")

        # 2-3. Find distinct bridge_ids via chunks → chunk_bridge_links.
        # Phase 2: pin to this KP via the FK instead of the lvl3 string.
        bridge_ids = (
            db.query(distinct(ChunkBridgeLink.bridge_id))
            .join(Chunk, Chunk.id == ChunkBridgeLink.chunk_id)
            .filter(Chunk.knowledge_point_id == kp.id)
            .all()
        )
        bridge_ids = [row[0] for row in bridge_ids]

        if not bridge_ids:
            # No bridges found — clear existing and return empty
            db.query(KnowledgePointBridge).filter(
                KnowledgePointBridge.knowledge_point_id == knowledge_point_id
            ).delete(synchronize_session=False)
            return []

        # Get bridge names for note generation
        bridges = db.query(Bridge).filter(Bridge.id.in_(bridge_ids)).all()
        bridge_map = {b.id: b for b in bridges}

        # 4. Generate relevance notes
        notes: dict[UUID, str] = {}
        default_note = f"与{kp.name}相关"

        if provider and bridges:
            try:
                from app.providers import ChatMessage

                bridge_names = [b.name for b in bridges]
                prompt = (
                    f"为知识点「{kp.name}」生成每座关联桥梁的一句话关联说明（20-40字）。\n\n"
                    f"桥梁列表：\n"
                    + "\n".join(f"- {name}" for name in bridge_names)
                    + "\n\n"
                    '输出严格的 JSON 格式（不要输出任何其他内容）：\n'
                    '{"notes": {"桥梁名称": "关联说明", ...}}'
                )
                response = await provider.chat([
                    ChatMessage(role="user", content=prompt),
                ])
                # Parse response
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()
                parsed = json.loads(text)
                llm_notes = parsed.get("notes", {})
                for b in bridges:
                    notes[b.id] = llm_notes.get(b.name, default_note)
            except Exception:
                logger.warning(
                    "LLM relevance note generation failed for KP %s, using defaults",
                    knowledge_point_id,
                    exc_info=True,
                )
                for b in bridges:
                    notes[b.id] = default_note
        else:
            for b in bridges:
                notes[b.id] = default_note

        # 5. Delete existing, insert new
        db.query(KnowledgePointBridge).filter(
            KnowledgePointBridge.knowledge_point_id == knowledge_point_id
        ).delete(synchronize_session=False)

        created = []
        for idx, bid in enumerate(bridge_ids):
            record = KnowledgePointBridge(
                knowledge_point_id=knowledge_point_id,
                bridge_id=bid,
                relevance_note=notes.get(bid, default_note),
                order_index=idx,
            )
            db.add(record)
            created.append(record)

        return created

    def list_bridges(
        self, db: Session, knowledge_point_id: UUID
    ) -> list[dict]:
        """List associated bridges with relevance notes, ordered by order_index."""
        results = (
            db.query(KnowledgePointBridge, Bridge.name)
            .join(Bridge, Bridge.id == KnowledgePointBridge.bridge_id)
            .filter(KnowledgePointBridge.knowledge_point_id == knowledge_point_id)
            .order_by(KnowledgePointBridge.order_index)
            .all()
        )
        return [
            {
                "id": kpb.id,
                "bridge_id": kpb.bridge_id,
                "bridge_name": bridge_name,
                "relevance_note": kpb.relevance_note,
                "order_index": kpb.order_index,
            }
            for kpb, bridge_name in results
        ]

    def replace_all(
        self,
        db: Session,
        knowledge_point_id: UUID,
        items: list[dict],
    ) -> list[KnowledgePointBridge]:
        """Replace all associations. items = [{bridge_id, relevance_note, order_index}]"""
        db.query(KnowledgePointBridge).filter(
            KnowledgePointBridge.knowledge_point_id == knowledge_point_id
        ).delete(synchronize_session=False)

        created = []
        for item in items:
            record = KnowledgePointBridge(
                knowledge_point_id=knowledge_point_id,
                bridge_id=item["bridge_id"],
                relevance_note=item.get("relevance_note"),
                order_index=item.get("order_index", 0),
            )
            db.add(record)
            created.append(record)

        return created
