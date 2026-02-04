"""Seed test data for integration testing."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base, Bridge, Chunk, Source, TaxonomyNode
from app.services.tokenizer import Tokenizer


def seed():
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")

        # Create taxonomy nodes
        nodes = [
            TaxonomyNode(lvl1="形制与技术", lvl2="结构体系"),
            TaxonomyNode(lvl1="形制与技术", lvl2="构造细部"),
            TaxonomyNode(lvl1="地域与环境", lvl2="水文地形"),
            TaxonomyNode(lvl1="功能与社会", lvl2="交通功能"),
            TaxonomyNode(lvl1="历史与演变", lvl2="建造年代"),
        ]
        session.add_all(nodes)

        # Create bridges
        bridges = [
            Bridge(
                name="赵州桥",
                aliases="安济桥",
                location="河北省赵县 华北",
                era="隋唐",
                bridge_type="石拱桥",
                material="石",
                function="交通",
                summary="中国现存最古老的石拱桥",
            ),
            Bridge(
                name="卢沟桥",
                location="北京市丰台区 华北",
                era="宋元",
                bridge_type="石拱桥",
                material="石",
                function="交通",
                summary="著名的联拱石桥",
            ),
        ]
        session.add_all(bridges)
        session.flush()

        # Create sources
        source = Source(type="note", title="桥梁知识笔记")
        session.add(source)
        session.flush()

        # Create chunks with embeddings
        chunks = [
            Chunk(
                source_id=source.id,
                content="[章节: 结构特点] 赵州桥是一座敞肩式石拱桥，主拱由28道拱券并列砌成，跨度37.02米。",
                section_title="结构特点",
                lvl1="形制与技术",
                lvl2="结构体系",
                bridge_id=bridges[0].id,
                embedding=[0.1] * 2048,
                search_text="[章节: 结构特点] 赵州桥是一座敞肩式石拱桥，主拱由28道拱券并列砌成，跨度37.02米。",
            ),
            Chunk(
                source_id=source.id,
                content="[章节: 历史背景] 赵州桥建于隋代大业年间（公元605-616年），由工匠李春设计建造。",
                section_title="历史背景",
                lvl1="历史与演变",
                lvl2="建造年代",
                bridge_id=bridges[0].id,
                embedding=[0.2] * 2048,
                search_text="[章节: 历史背景] 赵州桥建于隋代大业年间（公元605-616年），由工匠李春设计建造。",
            ),
            Chunk(
                source_id=source.id,
                content="[章节: 地理位置] 卢沟桥位于北京西南郊永定河上，是华北最长的古代石桥。",
                section_title="地理位置",
                lvl1="地域与环境",
                lvl2="水文地形",
                bridge_id=bridges[1].id,
                embedding=[0.3] * 2048,
                search_text="[章节: 地理位置] 卢沟桥位于北京西南郊永定河上，是华北最长的古代石桥。",
            ),
        ]
        session.add_all(chunks)

        session.flush()
        # Populate tsvector for FTS queries (uses GIN index on chunks.tsv).
        mappings = [
            {
                "id": chunk.id,
                "tsv_text": tokenizer.to_tsvector_text(chunk.search_text or chunk.content),
            }
            for chunk in chunks
        ]
        session.execute(
            text(
                "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
            ),
            mappings,
        )
        session.commit()

        print("Test data seeded successfully!")
        print(f"- {len(nodes)} taxonomy nodes")
        print(f"- {len(bridges)} bridges")
        print(f"- {len(chunks)} chunks")


if __name__ == "__main__":
    seed()
