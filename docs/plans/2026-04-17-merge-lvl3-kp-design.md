# 合并 lvl3 节点与 KnowledgePoint 设计文档

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 `taxonomy_nodes` 里的 lvl3 层级废除，让 `knowledge_points` 成为"具体知识点"的唯一实体；`chunks.lvl3` 字符串字段替换为 `chunks.knowledge_point_id` FK。

**Architecture:** 三阶段渐进式迁移（双写期 → 切读期 → 清理期）。第一阶段只**新增**字段和 FK，回填数据，保持旧字段工作；第二阶段切查询/写入到 KP，兼容 mobile `/knowledge/tree` 旧响应形态；第三阶段 drop 冗余列和 lvl3 taxonomy 行，发 mobile 端兼容新版本后再做。

**Tech Stack:** PostgreSQL schema migration（`schema_version` bump + `migrate_db.py`）、SQLAlchemy ORM、FastAPI、React/TypeScript。

---

## 背景与决策依据

### 现状数据（生产库快照 2026-04-17）

| 项 | 数 | 备注 |
|---|---|---|
| `taxonomy_nodes` 总行数 | ~70 | lvl1/lvl2/lvl3 混在一张表 |
| lvl3 行 | 51 | 代表"具体知识点"分类 |
| `knowledge_points` | 50 | 每个 lvl3 对应一个同名 KP（1:1，1 个孤儿） |
| 孤儿 lvl3（无 KP） | 1 | 「形制与技术/结构体系/浮桥结构」— seed 遗漏 |
| `chunks` 总数 | 115 | 核心检索单元 |
| `chunks` 标到 lvl3 | 74（64%） | 每条的 lvl3 label **都能匹配**到同名 KP（零 orphan） |
| `chunks` 只到 lvl2 | 32（28%） | lvl3 字段为 NULL |

### 为什么要合并

**底层逻辑**：lvl3 节点和 KP 本质是同一个业务实体的两张脸 — 目录面 + 知识卡面。当前 1:1 同名镜像导致：

1. **双写维护成本**：seed/ingest 时要同时创建 lvl3 taxonomy 行 + KP 行
2. **删除 UX 错乱**：删 lvl3 节点永远 409（同名 KP 挂着），用户看不懂
3. **chunks.lvl3 是弱类型**：字符串字段无 FK 约束，理论上可以写入不存在的 lvl3 label（目前数据一致只是侥幸）
4. **心智负担**：管理员看到两个 "斜拉结构" 概念（分类 + 知识点）

### 为什么不能一次切

1. **Mobile API 已上线**：`GET /api/mobile/v1/knowledge/tree` 返回 `lvl1 → lvl2 → lvl3 → KP[]` 四层结构，移动端 app 强依赖。强切 = breaking change
2. **影响面 163 处**：25 个文件引用 `lvl3`（services、API、前端、tests、seed 脚本、文档）
3. **数据安全**：生产库变更需要可回滚策略

### 三阶段策略

```
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1（本 plan 覆盖）                                                │
│ 加 chunks.knowledge_point_id FK（nullable）+ 回填数据                 │
│ 补「浮桥结构」同名 KP 消灭孤儿                                        │
│ double-write：ingest/tagger 同时写 lvl3 字符串 + FK                   │
│ 零对外行为变化，只是冗余多一份                                         │
│ 回滚：drop 列即可                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Phase 2（后续 plan）                                                  │
│ 检索/admin API/前端都切到读 knowledge_point_id                       │
│ chunks.lvl3 降级为派生只读列（由 FK 反查填充，保持向后兼容）           │
│ mobile /knowledge/tree 端点 output 保持现状形态（app 不知情）         │
│ 管理后台 Taxonomy 页面砍掉 lvl3 层（UI 上只剩 lvl1/lvl2），            │
│ KP 列表页成为 lvl3 入口                                               │
├─────────────────────────────────────────────────────────────────────┤
│ Phase 3（发新 app 后）                                                │
│ Mobile API tree 响应结构重构为 lvl1 → lvl2 → KP[] 三层                │
│ Drop chunks.lvl3/lvl2/lvl1 字符串列（或保留 lvl1/lvl2）              │
│ Drop taxonomy_nodes 中 lvl3 行                                       │
│ 更新 CLAUDE.md 三级目录说明                                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 详细任务（本次 sprint 范围）

**Phase 1 Goal**：只加字段、只补数据、零破坏。完成后 chunk 双向可查（既能通过 lvl3 字符串、也能通过 knowledge_point_id FK），但所有线上行为保持现状。

**Phase 1 验收标准**：
1. `chunks.knowledge_point_id` 列存在且对 74 条有 lvl3 的 chunk 全部非 NULL
2. `knowledge_points` 50 → 51 条（补了「浮桥结构」孤儿）
3. 所有 pytest + tsc + 本地 UI 回归通过
4. `schema_version` 从 8 bump 到 9
5. 新 ingest/chunk 编辑同时写 lvl3 字符串 + FK（保持双写）

### Task 1：补「浮桥结构」同名 KP 孤儿

**Files:**
- Create: `scripts/backfill_missing_lvl3_kp.py`
- Test: 手工生产/staging 验证

**Step 1**：写脚本检测并创建缺失的同名 KP

```python
"""Backfill same-name KnowledgePoint for lvl3 taxonomy nodes missing one.

Usage: python3 scripts/backfill_missing_lvl3_kp.py --execute
"""
import click
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgePoint, TaxonomyNode


@click.command()
@click.option("--execute", is_flag=True, help="Actually write; omit for dry-run")
def main(execute: bool) -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        orphans = (
            session.query(TaxonomyNode)
            .outerjoin(KnowledgePoint, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id)
            .filter(TaxonomyNode.lvl3.isnot(None), KnowledgePoint.id.is_(None))
            .all()
        )
        print(f"Found {len(orphans)} lvl3 node(s) without a matching KnowledgePoint:")
        for node in orphans:
            print(f"  - {node.lvl1} / {node.lvl2} / {node.lvl3}  (id={node.id})")
        if not orphans:
            return
        if not execute:
            print("Dry-run complete. Re-run with --execute to write.")
            return
        for node in orphans:
            session.add(KnowledgePoint(
                name=node.lvl3,
                taxonomy_node_id=node.id,
                summary=f"（占位）{node.lvl3}相关的桥梁知识点。",
            ))
        session.commit()
        print(f"Inserted {len(orphans)} KnowledgePoint(s).")


if __name__ == "__main__":
    main()
```

**Step 2**：本地 dry-run

```bash
python3 scripts/backfill_missing_lvl3_kp.py
# Expected: "Found 1 lvl3 node(s)..." + 「浮桥结构」
```

**Step 3**：生产 dry-run → execute

```bash
ssh netcup "docker exec bridge_rag_api python3 /app/scripts/backfill_missing_lvl3_kp.py"
# Review output, confirm only 「浮桥结构」
ssh netcup "docker exec bridge_rag_api python3 /app/scripts/backfill_missing_lvl3_kp.py --execute"
```

**Step 4**：验证

```bash
ssh netcup "docker exec bridge_rag_db psql -U bridge -d bridge_rag -c 'SELECT COUNT(*) FROM knowledge_points;'"
# Expected: 51
```

**Step 5**：Commit 脚本

```bash
git add scripts/backfill_missing_lvl3_kp.py
git commit -m "feat(scripts): backfill missing lvl3-KP orphan (浮桥结构)"
```

---

### Task 2：Schema v9 迁移 — 加 `chunks.knowledge_point_id`

**Files:**
- Modify: `app/models/chunk.py` — 加 `knowledge_point_id` mapped column
- Modify: `app/core/database.py` — `SCHEMA_VERSION = 9`，`SCHEMA_DESCRIPTIONS[9]`
- Modify: `scripts/migrate_db.py` — `MIGRATIONS[9]` 函数（ALTER TABLE + 回填）
- Test: `tests/integration/test_migrate_v9.py` (new)

**Step 1**：写迁移函数（增量）

```python
# scripts/migrate_db.py 新增
def migrate_to_v9(engine) -> None:
    """v8 → v9: add chunks.knowledge_point_id FK + backfill from lvl3 strings."""
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE chunks
            ADD COLUMN IF NOT EXISTS knowledge_point_id UUID
              REFERENCES knowledge_points(id) ON DELETE SET NULL
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_chunks_knowledge_point_id
              ON chunks(knowledge_point_id)
        """))
        # Backfill: match chunks.lvl3 → knowledge_points.name via taxonomy path
        conn.execute(text("""
            UPDATE chunks c
               SET knowledge_point_id = kp.id
              FROM knowledge_points kp
              JOIN taxonomy_nodes tn ON tn.id = kp.taxonomy_node_id
             WHERE c.lvl1 = tn.lvl1
               AND c.lvl2 = tn.lvl2
               AND c.lvl3 = tn.lvl3
               AND c.knowledge_point_id IS NULL
        """))

MIGRATIONS[9] = migrate_to_v9
```

**Step 2**：改 SQLAlchemy 模型

```python
# app/models/chunk.py —— class Chunk 新增字段
knowledge_point_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("knowledge_points.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
```

**Step 3**：写迁移测试

```python
# tests/integration/test_migrate_v9.py
def test_v9_adds_column_and_backfills(db_engine):
    """Schema v9 must add chunks.knowledge_point_id and backfill from lvl3."""
    from scripts.migrate_db import migrate_to_v9
    # setup: fresh db at v8, seed one lvl3 node + KP + matching chunk
    # ... (fixture setup)
    migrate_to_v9(db_engine)
    # assert chunks.knowledge_point_id is populated
```

**Step 4**：本地跑 pytest

```bash
pytest tests/integration/test_migrate_v9.py -v
# Expected: PASS
```

**Step 5**：Commit

```bash
git add app/models/chunk.py app/core/database.py scripts/migrate_db.py tests/integration/test_migrate_v9.py
git commit -m "feat(schema): v9 adds chunks.knowledge_point_id FK with backfill"
```

---

### Task 3：Ingest/Tagger/ChunkEditor double-write

**Files:**
- Modify: `app/services/tagger.py` — 打完 lvl3 标签后 resolve KP id 并赋值
- Modify: `app/services/ingest_task_service.py` — 创建 Chunk 时带上 knowledge_point_id
- Modify: `app/services/chunk_editor.py` — 批量改 lvl3 时同步更新 FK
- Test: `tests/test_tagger.py`, `tests/integration/test_chunk_editor.py` 补用例

**Step 1**：写 helper

```python
# app/services/tagger.py 或新建 app/services/kp_resolver.py
def resolve_knowledge_point_id(
    db: Session, lvl1: str | None, lvl2: str | None, lvl3: str | None
) -> uuid.UUID | None:
    """Given a taxonomy path, return the matching KnowledgePoint id (if any)."""
    if not lvl3:
        return None
    row = (
        db.query(KnowledgePoint.id)
        .join(TaxonomyNode, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id)
        .filter(TaxonomyNode.lvl1 == lvl1, TaxonomyNode.lvl2 == lvl2, TaxonomyNode.lvl3 == lvl3)
        .first()
    )
    return row[0] if row else None
```

**Step 2-4**：为每个调用点添加/修改测试 + 实现 + 验证。

**Step 5**：Commit

```bash
git commit -m "feat(ingest): double-write knowledge_point_id on chunk create/update"
```

---

### Task 4：Batch-taxonomy-update 端点同步 FK

**Files:**
- Modify: `app/api/v1/taxonomy.py::batch_update_chunks` (line 267+)

**Step 1**：在 `.update({...})` 里加 `Chunk.knowledge_point_id: resolve_knowledge_point_id(db, ...)`

**Step 2**：写集成测试：批量改 10 个 chunk 的 lvl3 → 它们的 knowledge_point_id 也被同步

**Step 5**：Commit

```bash
git commit -m "feat(taxonomy): batch-update syncs chunks.knowledge_point_id"
```

---

### Task 5：生产数据 sanity check + 完整回归

**Files:** 无代码改动，纯 ops

**Step 1**：部署到生产（push 到 main 触发 GH Actions）

**Step 2**：跑 migration（entrypoint 自动）

**Step 3**：SQL 验证

```sql
-- 应该 74 条（和 chunks_with_lvl3 相等）
SELECT COUNT(*) FROM chunks WHERE knowledge_point_id IS NOT NULL;

-- 应该 0（所有有 lvl3 的 chunk 都 resolved 到 KP）
SELECT COUNT(*) FROM chunks WHERE lvl3 IS NOT NULL AND knowledge_point_id IS NULL;
```

**Step 4**：浏览器回归 — 打开 ChunkEditor 修改 chunk 的 lvl3 → DB 查该 chunk 的 knowledge_point_id 也变了

**Step 5**：交付 Phase 1 闭环报告

---

## Phase 2/3 占位（后续 plan 扩展）

这两阶段**不在本 plan 内**，单独立 plan 文档。

- **Phase 2**：切读（admin API + chunks detail + 前端列表 / 详情 / 编辑）；mobile `/knowledge/tree` 不动（app 不知情）；TaxonomyPage UI 删 lvl3 层
- **Phase 3**：发新 app → mobile tree 响应结构三层化 → drop `chunks.lvl3` 字符串列 → drop lvl3 taxonomy 行 → 更新 CLAUDE.md

---

## 风险与回滚

| 风险 | 缓解 |
|------|------|
| backfill UPDATE 卡长事务 | chunks 只有 115 行，量小；若将来数据大可批处理 |
| 新增 FK ON DELETE SET NULL 导致 KP 误删波及 chunks | 本 phase 不允许删 KP；Phase 2 前加 KP delete 端点的 FK 计数保护（参考 taxonomy delete 的同款 savepoint 模式） |
| mobile app 意外调用新字段 | Phase 1 不改任何 API 响应，只加 DB 列 |
| 生产迁移失败 | migrate_to_v9 全程幂等（IF NOT EXISTS + IS NULL 过滤），失败后重跑即可；极端可 DROP COLUMN 回滚 |

## Gotchas 已写入 CLAUDE.md

Phase 1 完成后要加：
- "chunks 有两种打 lvl3 的方式（字符串 lvl3 + FK knowledge_point_id），过渡期双写；Phase 2 后 FK 为准"
- "新增 knowledge_points 时必须同步创建同名 lvl3 taxonomy_node（Phase 2 前保持），否则 chunks.lvl3 字符串路径会找不到"

---

## 工期估算

| Task | 估时 | 依赖 |
|------|------|------|
| 1 补孤儿 KP | 30 min | 无 |
| 2 schema v9 + 回填 | 2 h | Task 1 |
| 3 Ingest/Tagger/Editor double-write | 3 h | Task 2 |
| 4 batch-update 同步 | 1 h | Task 3 |
| 5 生产验证 | 1 h | 1-4 |
| **Phase 1 合计** | **~7.5 h** | — |

Phase 2 独立 plan 后再估。
