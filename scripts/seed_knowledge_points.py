"""Seed test knowledge_points data for mobile client integration testing.

Creates 3 knowledge_points under existing lvl3 taxonomy_nodes,
each with 2-3 key_points.

Usage: python3 scripts/seed_knowledge_points.py
"""
import uuid

import click
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint


SEED_DATA = [
    {
        "lvl3": "拱桥结构",
        "name": "拱桥结构",
        "aliases": "拱券桥,拱形桥",
        "difficulty": "beginner",
        "summary": "以拱圈为主要承重构件，将荷载转化为轴向压力的桥梁形式",
        "key_points": [
            {
                "summary": "拱桥以拱圈为主要承重构件，将荷载转化为轴向压力",
                "explanation": "拱桥利用拱形结构将竖向荷载转化为沿拱轴的压力，传至两端拱脚。这种受力方式使得石材等抗压材料的优势得到充分发挥。",
                "order_index": 1,
            },
            {
                "summary": "按拱圈形式分为圆弧拱、尖拱、抛物线拱等",
                "explanation": "不同的拱轴线形状决定了拱桥的受力特性和建筑风格。圆弧拱施工简便，尖拱常见于西方哥特式建筑，抛物线拱最接近理想压力线。",
                "order_index": 2,
            },
            {
                "summary": "中国古代石拱桥以赵州桥为代表，创造性地采用了敞肩拱设计",
                "explanation": "赵州桥在拱肩设置四个小拱，减轻自重、节约石料、利于泄洪，是世界桥梁史上的重要创新。",
                "order_index": 3,
            },
        ],
    },
    {
        "lvl3": "桥墩设计",
        "name": "桥墩设计",
        "aliases": "桥墩,墩台",
        "difficulty": "intermediate",
        "summary": "桥梁下部结构中承受上部荷载并传递至基础的构件",
        "key_points": [
            {
                "summary": "桥墩按形式分为重力式、柱式、薄壁式等",
                "explanation": "重力式桥墩靠自重抵抗水平力，适用于大跨径桥梁；柱式桥墩轻巧美观，常用于公路桥；薄壁式桥墩兼顾强度与经济性。",
                "order_index": 1,
            },
            {
                "summary": "古代桥墩常采用分水尖和船形墩减少水流冲刷",
                "explanation": "分水尖将水流分向两侧，降低墩前水压。船形墩上游尖下游圆，进一步优化水力学性能。洛阳桥即采用了筏型基础和船形墩。",
                "order_index": 2,
            },
        ],
    },
    {
        "lvl3": "河流特征",
        "name": "河流与桥梁选址",
        "aliases": "水文条件,桥位选择",
        "difficulty": "beginner",
        "summary": "河流的水文特征对桥梁选址和设计具有决定性影响",
        "key_points": [
            {
                "summary": "桥梁选址需考虑河宽、水深、流速、洪水频率等水文参数",
                "explanation": "理想的桥位应选在河道顺直、河床稳定、岸基坚固的地方。弯道处水流冲刷不均，不利于桥墩安全。",
                "order_index": 1,
            },
            {
                "summary": "中国南北方河流特征差异导致桥梁形式的地域差异",
                "explanation": "北方河流季节性强、含沙量大，多采用简支梁桥；南方水网密布、水量充沛，发展出丰富的拱桥和廊桥形式。",
                "order_index": 2,
            },
        ],
    },
]


@click.command()
def main() -> None:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        result = db.execute(text("SELECT to_regclass('public.knowledge_points')"))
        if result.scalar_one() is None:
            click.echo("ERROR: knowledge_points table does not exist. Run migration first.")
            return

        count = db.execute(text("SELECT COUNT(*) FROM knowledge_points")).scalar_one()
        if count > 0:
            click.echo(f"knowledge_points already has {count} records. Skipping seed.")
            return

        created = 0
        for item in SEED_DATA:
            tax_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.lvl3 == item["lvl3"]
            ).first()

            if not tax_node:
                click.echo(f"  WARNING: lvl3 '{item['lvl3']}' not found in taxonomy_nodes, skipping")
                continue

            chunk_rows = db.execute(
                text("SELECT id FROM chunks WHERE lvl3 = :lvl3 LIMIT 5"),
                {"lvl3": item["lvl3"]},
            ).all()
            chunk_ids = [row[0] for row in chunk_rows] if chunk_rows else None

            kp = KnowledgePoint(
                taxonomy_node_id=tax_node.id,
                name=item["name"],
                aliases=item["aliases"],
                difficulty=item["difficulty"],
                summary=item["summary"],
            )
            db.add(kp)
            db.flush()

            for kp_data in item["key_points"]:
                key_point = KnowledgePointKeyPoint(
                    knowledge_point_id=kp.id,
                    summary=kp_data["summary"],
                    explanation=kp_data["explanation"],
                    order_index=kp_data["order_index"],
                    chunk_ids=chunk_ids,
                )
                db.add(key_point)

            created += 1
            click.echo(f"  Created: {item['name']} ({len(item['key_points'])} key points)")

        db.commit()
        click.echo(f"\nSeeded {created} knowledge points.")

    except Exception as e:
        db.rollback()
        click.echo(f"ERROR: {e}", err=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
