"""Batch flashcard generation via LLM for knowledge points."""
import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Bridge, Flashcard, KnowledgePoint, KnowledgePointBridge, KnowledgePointKeyPoint
from app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class FlashcardBatchGenerator:
    """Generate flashcards for knowledge points using LLM."""

    async def generate_for_kp(
        self, db: Session, knowledge_point_id: UUID, provider: LLMProvider
    ) -> list[Flashcard]:
        """Generate flashcards for one knowledge point.

        Steps:
        1. Get KP + key_points + associated bridges (via knowledge_point_bridges)
        2. Build LLM prompt with key_points summaries + bridge names
        3. Call LLM to generate cards (JSON output)
        4. Parse and create Flashcard records
        5. Return created cards (not committed — caller commits)
        """
        # 1. Load KP
        kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == knowledge_point_id).first()
        if not kp:
            raise ValueError(f"Knowledge point {knowledge_point_id} not found")

        # Load key points
        key_points = (
            db.query(KnowledgePointKeyPoint)
            .filter(KnowledgePointKeyPoint.knowledge_point_id == knowledge_point_id)
            .order_by(KnowledgePointKeyPoint.order_index)
            .all()
        )

        # Load associated bridges
        kp_bridges = (
            db.query(KnowledgePointBridge)
            .filter(KnowledgePointBridge.knowledge_point_id == knowledge_point_id)
            .all()
        )
        bridge_ids = [kpb.bridge_id for kpb in kp_bridges]
        bridges = db.query(Bridge).filter(Bridge.id.in_(bridge_ids)).all() if bridge_ids else []
        bridge_name_map = {b.name: b.id for b in bridges}
        # Also build case-insensitive lookup
        bridge_name_lower_map = {b.name.lower(): b.id for b in bridges}
        bridge_names = [b.name for b in bridges]

        # 2. Build prompt
        if key_points:
            key_points_text = "\n".join(
                f"- {kpkp.summary}" + (f"：{kpkp.explanation}" if kpkp.explanation else "")
                for kpkp in key_points
            )
        else:
            key_points_text = "（暂无要点信息）"

        bridge_names_text = "、".join(bridge_names) if bridge_names else "（无关联桥梁）"

        identification_instruction = ""
        if bridge_names:
            identification_instruction = (
                '2. 1-2 张 identification 卡（基于桥梁关联，\u201c哪座桥体现了X？\u201d形式，'
                'example_bridge_name 必须是关联桥梁之一）\n'
            )
        else:
            identification_instruction = (
                "2. 不要生成 identification 卡（因为没有关联桥梁）\n"
            )

        prompt = (
            f"你是桥梁知识教育专家。为知识点「{kp.name}」生成学习卡片。\n\n"
            f"该知识点的核心要点：\n{key_points_text}\n\n"
            f"关联桥梁：{bridge_names_text}\n\n"
            "请生成以下卡片（JSON 格式）：\n"
            '1. 2-3 张 concept 卡（基于要点，\u201c什么是X？\u201d形式）\n'
            f"{identification_instruction}\n"
            '输出严格的 JSON 格式（不要输出任何其他内容）：\n'
            '{"cards": [\n'
            '  {\n'
            '    "card_type": "concept",\n'
            '    "front_title": "什么是拱桥？",\n'
            '    "front_hint": "最重要的古代桥梁结构形式",\n'
            '    "back_answer": "以拱圈为主要承重构件的桥梁...",\n'
            '    "back_key_features": ["拱圈承重", "轴向压力"],\n'
            '    "example_bridge_name": null\n'
            '  },\n'
            '  {\n'
            '    "card_type": "identification",\n'
            '    "front_title": "哪座桥是敞肩拱的典型代表？",\n'
            '    "front_hint": "隋代，河北",\n'
            '    "back_answer": "赵州桥（安济桥）",\n'
            '    "back_key_features": ["敞肩拱", "净跨37米"],\n'
            '    "example_bridge_name": "赵州桥"\n'
            '  }\n'
            ']}'
        )

        # 3. Call LLM
        from app.providers.base import ChatMessage

        response = await provider.chat([ChatMessage(role="user", content=prompt)])

        # 4. Parse JSON response
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)
        cards_data = parsed["cards"]

        if not isinstance(cards_data, list):
            raise ValueError("LLM returned malformed cards data")

        # 5. Parse cards first, then replace existing only if we have valid new ones
        created_cards: list[Flashcard] = []
        for item in cards_data:
            if not isinstance(item, dict):
                logger.warning("Skipping non-dict card item: %s", type(item))
                continue

            card_type = item.get("card_type", "concept")
            if card_type not in ("concept", "identification"):
                card_type = "concept"

            # Resolve example_bridge_name to bridge ID
            example_bridge_id = None
            bridge_name = item.get("example_bridge_name")
            if bridge_name and isinstance(bridge_name, str):
                # Try exact match first, then case-insensitive
                example_bridge_id = bridge_name_map.get(bridge_name)
                if not example_bridge_id:
                    example_bridge_id = bridge_name_lower_map.get(bridge_name.lower())

            card = Flashcard(
                knowledge_point_id=knowledge_point_id,
                card_type=card_type,
                front_title=item.get("front_title", ""),
                front_hint=item.get("front_hint"),
                back_answer=item.get("back_answer", ""),
                back_key_features=item.get("back_key_features"),
                back_example_bridge_id=example_bridge_id,
            )
            created_cards.append(card)

        if not created_cards:
            raise ValueError("LLM generated zero valid cards, keeping existing flashcards")

        # Delete existing only after confirming we have replacements
        db.query(Flashcard).filter(
            Flashcard.knowledge_point_id == knowledge_point_id
        ).delete(synchronize_session=False)

        for card in created_cards:
            db.add(card)

        return created_cards

    async def batch_generate(
        self, db: Session, knowledge_point_ids: list[UUID]
    ) -> dict:
        """Generate flashcards for multiple KPs. Returns summary."""
        from app.providers import ZhipuProvider

        provider = ZhipuProvider()
        total_generated = 0
        errors = []

        for kp_id in knowledge_point_ids:
            try:
                cards = await self.generate_for_kp(db, kp_id, provider)
                total_generated += len(cards)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Failed to generate flashcards for KP %s: %s", kp_id, e)
                errors.append({"kp_id": str(kp_id), "error": str(e)})

        return {"total_generated": total_generated, "errors": errors}
