# Phase 3 — 真正合并 lvl3 + KnowledgePoint

**Goal**：删除 `taxonomy_nodes` 里所有 lvl3 行；`knowledge_points` 承载"具体知识点"唯一实体；mobile `/knowledge/tree` 响应从 4 层变 3 层；admin 前端砍 lvl3 UI。

**Breaking change 已对上下游拉通**：
- EchoBridgeCQU/web issue #2
- EchoBridgeCQU/app issue #3

**本 Phase 不 drop 的列**：`chunks.lvl1 / lvl2 / lvl3` 字符串列保留（只读冗余，避免连锁改动）。FK `chunks.knowledge_point_id` 是唯一权威索引。

## 任务

### T1：schema v10 — knowledge_points 加 lvl1/lvl2 + 回填

**Files:** `app/models/knowledge_point.py`, `app/core/database.py`, `scripts/migrate_db.py`, `tests/integration/test_migrate_v10.py`

```sql
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl1 VARCHAR(100);
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl2 VARCHAR(100);
CREATE INDEX IF NOT EXISTS ix_kp_lvl1_lvl2 ON knowledge_points(lvl1, lvl2);

UPDATE knowledge_points kp
   SET lvl1 = tn.lvl1, lvl2 = tn.lvl2
  FROM taxonomy_nodes tn
 WHERE kp.taxonomy_node_id = tn.id
   AND kp.lvl1 IS NULL;
```

同步 `verify_schema_compatibility.required_schema["knowledge_points"]` 加 `lvl1`/`lvl2`。

### T2：`kp_resolver` 切源

改 `resolve_knowledge_point_id` — 不再 join `taxonomy_nodes`，直接查 `KnowledgePoint` by `(lvl1, lvl2, name=lvl3)`。保持函数签名和语义不变。

### T3：tree builder 改 3 层响应

**Files:** `app/api/mobile/v1/knowledge.py`, `app/api/v1/taxonomy.py::get_taxonomy_tree`

扫 `KnowledgePoint` 行（+ 它的 `lvl1/lvl2`），按 lvl1/lvl2 分组挂在 taxonomy_nodes 的 lvl2 行下。输出 3 层。

Admin `get_taxonomy_tree` 同步 — lvl2 节点的 children 是 KP 列表（`TaxonomyTreeItem.label = kp.name, node_id = kp.id`），chunk_count = 该 KP 下挂的 chunks 数。

### T4：admin taxonomy CRUD 禁 lvl3

`POST /taxonomy/nodes` 检查 `body.lvl3` → 422 "lvl3 taxonomy nodes are no longer supported; create a KnowledgePoint instead"。

### T5：schema v10 第二阶段 — DELETE taxonomy_nodes lvl3 行

放在独立 migration（让 T1-T4 先 ship 确认稳定，再执行 delete，以便 rollback）。或者打包进 v10 migration 但**必须在 T1-T4 代码全部上线后**才跑（否则 tree builder 会挂）。

保险起见：把 DELETE 放在单独的 `scripts/cleanup_lvl3_taxonomy_rows.py` 脚本，T1-T4 代码部署稳定后手动执行。

### T6：admin 前端 TaxonomyPage 砍 lvl3 UI 层

`web/src/pages/TaxonomyPage.tsx` + `web/src/components/taxonomy/TaxonomyTree.tsx` 改为只渲染 lvl1/lvl2 节点；点 lvl2 节点显示挂在该 lvl2 下的 KP 卡片列表（可链到 KnowledgePointDetailPage）。

### T7：部署 + comment issue

Push → GH Actions deploy → comment EchoBridgeCQU/web#2 和 EchoBridgeCQU/app#3 告知 ETA + 验证后端响应确实变 3 层。

## 风险 & 回滚

| 风险 | 缓解 |
|------|------|
| Migration 回填 knowledge_points.lvl1/lvl2 出错 | `ADD COLUMN IF NOT EXISTS` + `UPDATE WHERE lvl1 IS NULL` 幂等 |
| tree builder 切源后响应格式跟约定不符 | Integration 测试对比新旧响应的 3 层 shape |
| DELETE lvl3 taxonomy_nodes 不可回滚 | 放独立脚本延后执行；用 `DELETE ... RETURNING *` 打到日志便于审计 |
| mobile app 没来得及改就收到 3 层响应 | Issue 已开，部署前在 issue comment ETA；app 端可通过 try/catch 多层深度适配过渡 |
