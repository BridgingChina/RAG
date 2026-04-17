# Phase 2 实施计划 — 切读 + 防御 + admin UI 调整

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把所有**服务端读路径**从 `chunks.lvl3` 字符串切到 `chunks.knowledge_point_id` FK；给 KP delete 端点加 FK 计数保护；admin 前端砍掉 lvl3 层，KP 列表页承接"具体知识点"入口。Mobile `/knowledge/tree` 响应形态**保持不变**（Phase 3 才重构）。

**Architecture:** 读切换按"一个读点一次改动一次测试"的颗粒度推进，chunks.lvl3 字符串列**保留**（还有些地方当显示字段用），只是查询条件从字符串变 FK。KP 删除先加防御再允许 admin UI 暴露。完成后 `git grep "Chunk.lvl3 ==" app/` 只剩"验证 taxonomy path 存在"这类校验用法。

**Tech Stack:** FastAPI + SQLAlchemy（ORM join 从字符串改成 FK 关系），React/TypeScript（前端砍 lvl3 层 UI）。

---

## Phase 1 → Phase 2 状态交接

| 项 | 状态 |
|----|------|
| 生产 schema 版本 | v9 ✓ |
| `chunks.knowledge_point_id` 回填 | 74/74 ✓（0 脏数据已 SQL 确认） |
| `knowledge_points` 总数 | 51（含补齐的浮桥结构）✓ |
| 双写站点清单 | 已落 CLAUDE.md 5 条 ✓ |
| Phase 1 final review 遗留 | 无（PUT/{id} gap 已补、deprecated ingest 已补） |

## 当前仓库里所有 lvl3 读用法（审计）

`grep -rE "Chunk\.lvl3|c\.lvl3\s*==|chunk\.lvl3" app/` 结果分类：

**要切（读路径用 lvl3 字符串过滤 chunks）：**
1. `app/api/v1/taxonomy.py:54-56` — tree 聚合 `GROUP BY (lvl1, lvl2, lvl3)` 统计 chunk 数
2. `app/api/v1/taxonomy.py:363` — tree detail 按 lvl3 查本节点挂的 chunks
3. `app/api/v1/chunks.py:73` — chunks list 按 lvl3 query-param 过滤
4. `app/api/v1/knowledge_points.py:387` — `generate-key-points` 的 lvl3 chunks 检索
5. `app/services/kp_bridge_service.py:58` — 挂 KP-bridges 时按 lvl3 过滤
6. Mobile 层：`qa.py`, `knowledge.py`, `search.py` 内部用 lvl3 聚合/过滤 chunks

**保持不切（lvl3 仍是字符串列，这些是"taxonomy path 存在性校验"或"响应回显字段"）：**
- `app/api/v1/taxonomy.py:141, 319` — 验证 body.lvl3 是否在 taxonomy_nodes 里存在
- `app/api/v1/chunks.py:196, 206` — PUT 前验证 taxonomy 路径
- `app/api/v1/chunks.py:159` — response schema 里 `lvl3=chunk.lvl3`（对外输出）
- `app/services/ingest_task_service.py:558` — 写入 chunk.lvl3（已含同步 FK 写）
- `app/services/chunk_editor.py:126` — split 继承 lvl3（已含同步 FK 继承）

---

## Phase 2 任务拆解

**总工期估算：** 约 8-10 小时。每 task 独立 ship-able，出问题单独 revert。

### Task 1：KP delete 端点加 FK 计数保护 + savepoint

**动机：** final reviewer 风险表里唯一的 pre-Phase-2 防御任务。若 admin 删一个被 chunks 引用的 KP，现在 FK `ON DELETE SET NULL` 会静默 null 掉所有引用；Phase 2 后读路径切 FK，静默 null 会变成"chunk 读不到知识点"的线上 bug。对齐 `delete_taxonomy_node` 的 savepoint + 计数模式。

**Files:**
- Modify: `app/api/v1/knowledge_points.py` (delete 端点)
- Test: `tests/integration/test_knowledge_point_delete_fk.py` (new)

**Step 1 (TDD)**: 写测试

```python
def test_delete_kp_blocked_by_chunk_reference(db_session, test_source):
    # seed KP + chunk pointing at it → DELETE /{id} must 409
    ...
def test_delete_kp_allowed_when_no_chunks(db_session):
    # unreferenced KP → DELETE /{id} → 204
    ...
```

**Step 2**: 实现 — 在 delete 端点里加：

```python
chunk_count = (
    db.query(func.count(Chunk.id))
    .filter(Chunk.knowledge_point_id == kp_id)
    .scalar()
    or 0
)
if chunk_count > 0:
    raise HTTPException(
        status_code=409,
        detail=f"Cannot delete knowledge point with {chunk_count} associated chunk(s)",
    )
```

外加 savepoint 包住 `db.delete(kp)` 捕获 `IntegrityError` 回 409（与 `delete_taxonomy_node` 对齐）。

**Step 3**: pytest 过。

**Step 4**: Commit `feat(kp): reject delete when chunks reference the kp`。

---

### Task 2：admin chunks list 端点切到 FK filter

**Files:** `app/api/v1/chunks.py` line 73 附近。

**Step 1 (TDD)**: 写测试 — 创建 2 个 KP + 6 个 chunks，用 `?lvl1=...&lvl3=...` 过滤时只返回指向对应 KP 的 chunks。

**Step 2**: 改实现 — 保留 query param 字面量（向前兼容 API），内部 resolve → 用 `Chunk.knowledge_point_id == resolved_kp_id` filter。若 lvl3 无对应 KP 则 filter `Chunk.knowledge_point_id.is_(None)` 兜底（或 lvl3 字符串保底——根据测试结果决定）。

**Step 3**: pytest。

**Step 4**: Commit。

---

### Task 3：taxonomy tree chunk 计数改从 FK 聚合

**Files:** `app/api/v1/taxonomy.py:32-58`

**动机：** Tree 右侧的 chunk_count 徽标统计是高频读，字符串 GROUP BY 比 FK GROUP BY 慢、不走索引（lvl3 无 index；FK 有 `ix_chunks_knowledge_point_id`）。

**Step 1 (TDD)**: 写一个集成测试 — taxonomy_tree 响应里每个 lvl3 节点的 chunk_count == 指向对应 KP 的 chunks 数。

**Step 2**: 改 lvl3 维度的聚合：`GROUP BY knowledge_point_id → LEFT JOIN taxonomy_nodes via kp`。lvl1/lvl2 维度仍按字符串聚合（因为 lvl1/lvl2 没 FK）。

**Step 3 + 4**: pytest + commit。

---

### Task 4：taxonomy tree detail — chunks list 按 FK 查

**Files:** `app/api/v1/taxonomy.py:363`

**Step 1 (TDD)**: 集成测试覆盖。

**Step 2**: `query.filter(Chunk.knowledge_point_id == kp_id_of_this_node)`（先 resolve 节点对应 KP）。

---

### Task 5：knowledge_points.py `generate-key-points` + `kp_bridge_service` 切 FK

**Files:**
- `app/api/v1/knowledge_points.py:387`
- `app/services/kp_bridge_service.py:58`

**Step 1 (TDD)**: 测试 — 对同一 KP，新旧查询返回同 chunk set。

**Step 2**: 改 `.filter(Chunk.lvl3 == X)` → `.filter(Chunk.knowledge_point_id == kp.id)`。

---

### Task 6：Mobile QA/search/knowledge 内部切 FK（响应不变）

**Files:**
- `app/api/mobile/v1/qa.py:76` 附近
- `app/api/mobile/v1/search.py`
- `app/api/mobile/v1/knowledge.py:32,65,79,124`

**约束：** 响应结构 `lvl1 → lvl2 → lvl3 → KP[]` **不能变**（app 依赖），只改内部查询。对 `/knowledge/tree` 来说，大部分读本来就是 `taxonomy_nodes` 的 lvl3 节点——结构自然。对 `/qa` 和 `/search` 内部筛选 chunks 的地方，按本 Phase 模式切 FK。

---

### Task 7：前端 admin Taxonomy 页面砍 lvl3 层 UI

**Files:**
- `web/src/pages/TaxonomyPage.tsx`
- `web/src/components/taxonomy/TaxonomyTree.tsx`
- 相关类型：`web/src/lib/types.ts`

**UX 变化：** 原来 lvl1 → lvl2 → lvl3 三层树，现在只剩 lvl1 → lvl2；lvl3 层在 admin 端改由 **KnowledgePoint 列表页** 承接（lvl1/lvl2 做筛选，KP 卡片列表作为第三层）。Taxonomy CRUD 也只管 lvl1/lvl2，KP 的 CRUD 在 KnowledgePointPage。

**Step 1**: brainstorm UX（本 plan 后续有独立 design sketch）。
**Step 2**: 改 types + API call + 页面。
**Step 3**: 浏览器验证（真点一次）。
**Step 4**: Commit。

---

### Task 8：前端 ChunkDetailPage 展示 KP 入口 + 类型同步

**Files:** `web/src/pages/ChunkDetailPage.tsx`, `web/src/lib/types.ts`

**动机：** 现在 ChunkDetail 只显示 lvl1/lvl2/lvl3 文字；Phase 2 后 lvl3 可点进 KP 详情页（更符合"具体知识点"语义）。后端 chunks 详情 response 已经含 `knowledge_point_id`（Phase 1 就加了，response schema 要补暴露）。

---

### Task 9：生产部署 + 全量 SQL sanity + UI 浏览器回归

- push → GH Actions deploy
- SQL 验证读路径切换后 chunk_count 一致、查询结果一致
- 浏览器抽测 TaxonomyPage / KnowledgePointListPage / ChunkEditor / ask 检索

---

## 风险表

| 风险 | 缓解 |
|------|------|
| 切读后返回结果变化（FK null-ish 的 chunk 不再匹配） | Task 1-2 的测试要对比"新旧查询结果 set 相等"；Phase 1 已经保证 74/74 FK 精确匹配，理论上 set 不变 |
| KP 被删导致 chunks.knowledge_point_id SET NULL，切读后这些 chunk 查不到 | **Task 1 必须第一个做**，拦住 KP 误删 |
| Mobile 响应结构意外改变导致 app 崩 | Task 6 必须带响应 snapshot 测试，CI 比对 JSON 结构不变 |
| 前端砍 lvl3 层导致 admin 找不到知识点 | Task 7 前先确认 KnowledgePointListPage 已经有按 lvl1/lvl2 筛选（若没有要先加） |

## 回滚策略

- Task 1-6（后端读切换）：每 task 独立 commit，`git revert` 即回滚
- Task 7-8（前端）：同上
- 数据完整性：本 Phase **不改 schema、不改数据**，全是查询条件换列名。最坏情况 revert 代码，DB 原封不动

## Phase 3 预告（不在本 plan）

- Mobile `/knowledge/tree` response 重构为 `lvl1 → lvl2 → KP[]` 三层（breaking change，发 app 新版本配合）
- Drop `chunks.lvl1/lvl2/lvl3` 字符串列（schema v10）
- Drop `taxonomy_nodes` 中 lvl3 行（schema v10）
- CLAUDE.md 三级目录说明重写
