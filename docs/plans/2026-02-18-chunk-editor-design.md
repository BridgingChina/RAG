# Chunk Editor — 手动校对面板设计

日期：2026-02-18

## 概述

为入库文档提供 chunk 级别的手动校对能力，支持内容编辑、标注修改、拆分/合并、批量操作和重索引。解决自动切块+标注效果不理想时的人工介入需求。

## 需求

- **全套编辑**：chunk 内容编辑 + taxonomy tags + bridge_links + 拆分/合并
- **双入口**：Ingest 完成后跳转 + Source 详情页随时进入
- **混合重索引**：tsv 即时更新；embedding/contextual_text 标记脏位，支持手动触发 + 每日自动重算
- **继承策略**：拆分时子 chunks 继承父元数据，合并保留第一个 chunk 的元数据
- **双栏布局**：左侧 chunk 列表，右侧编辑面板
- **完整批量操作**：多选 + 批量改 tag/bridge/删除/合并

## 后端 API

### 模型变更

`chunks` 表新增列：

```
needs_reindex  BOOLEAN  NOT NULL  DEFAULT FALSE
```

schema_version 升至 4。

### 扩展现有端点

**`PUT /chunks/{id}`** — 扩展 `ChunkUpdate`：

```python
class ChunkUpdate(BaseModel):
    # 现有
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None
    # 新增
    content: str | None = None
    section_title: str | None = None
    bridge_links: list[BridgeLinkInput] | None = None

class BridgeLinkInput(BaseModel):
    bridge_id: int
    role: Literal["primary", "secondary", "candidate"]
    confidence: float = 1.0
    method: Literal["hint", "rule", "llm", "manual"] = "manual"
```

当 `content` 被修改时：
- 即时重算 `search_text`（contextual_text + "\n" + content）
- 即时重算 `tsv`（jieba 分词）
- 设 `needs_reindex = True`

当 `bridge_links` 被传入时：
- 删除该 chunk 所有现有 `chunk_bridge_links`
- 插入新 links
- 同步 `chunk.bridge_id`（取 role=primary 的第一个）

### 新增端点

**`POST /chunks/{id}/split`**

```python
class ChunkSplitRequest(BaseModel):
    position: int  # 字符位置

class ChunkSplitResponse(BaseModel):
    chunks: list[ChunkDetail]  # 固定长度 2
```

- 按 position 拆为两段
- 两个新 chunks 继承原 chunk 的 source_id、tags、bridge_links
- 各自算 search_text + tsv，设 needs_reindex = True
- 删除原 chunk，审计记录 `chunk.split`

**`POST /chunks/merge`**

```python
class ChunkMergeRequest(BaseModel):
    chunk_ids: list[int]  # ≥2，必须同 source_id，按顺序合并
```

- 验证同 source_id
- 拼接 content（"\n\n" 分隔）
- 就地更新第一个 chunk，保留其 tags/bridge_links
- 重算 search_text + tsv，设 needs_reindex = True
- 删除其余 chunks
- 审计记录 `chunk.merge`，返回更新后的 ChunkDetail

**`PATCH /chunks/batch`**

```python
class ChunkBatchRequest(BaseModel):
    chunk_ids: list[int]
    action: Literal["update", "delete"]
    updates: ChunkBatchUpdate | None = None

class ChunkBatchUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None
```

审计记录 `chunk.batch_update` / `chunk.batch_delete`。

**`POST /sources/{id}/reindex`**

```python
# 查询参数: ?force=false
# force=false: 仅重算 needs_reindex=True 的 chunks
# force=true: 强制重算该 source 所有 chunks

class ReindexResponse(BaseModel):
    source_id: int
    chunks_reindexed: int
    chunks_failed: list[int]
```

对每个目标 chunk：contextual_text → search_text → embedding → tsv → needs_reindex = False。

### 定时重索引

用 FastAPI lifespan + asyncio 后台循环，每日 03:00 自动重算所有 `needs_reindex=True` 的 chunks。不引入额外调度依赖。

### 审计日志

| 操作 | action |
|------|--------|
| 编辑 chunk | `chunk.update` |
| 拆分 | `chunk.split`（detail 含原 id → 新 ids） |
| 合并 | `chunk.merge`（detail 含源 ids → 目标 id） |
| 批量更新 | `chunk.batch_update`（detail 含 chunk_ids） |
| 批量删除 | `chunk.batch_delete`（detail 含 chunk_ids） |
| 重索引 | `source.reindex`（detail 含 count） |

### 错误处理

| 场景 | 响应 |
|------|------|
| split position 越界 | 400 |
| merge 跨 source | 400 |
| merge < 2 个 ids | 400 |
| batch 中 chunk_id 不存在 | 400，列出不存在的 ids |
| reindex LLM/embedding 失败 | 逐条处理，失败的记入 chunks_failed |
| 并发编辑冲突 | 409（基于 updated_at 乐观锁） |

## 前端

### 路由

```
/sources/:sourceId/chunks/edit → ChunkEditorPage
```

### 页面布局（双栏）

```
┌──────────────────────────────────────────────────────────┐
│  PageHeader: 校对 Chunks — {source_title}  [重新索引 (n)] │
├────────────────────┬─────────────────────────────────────┤
│  左栏: Chunk 列表   │  右栏: 编辑面板                      │
│  ┌──────────────┐  │  ┌─────────────────────────────────┐│
│  │ □ #12 预览... │  │  │ ⚠ 内容已修改，embedding 待更新   ││
│  │   badges      │  │  ├─────────────────────────────────┤│
│  ├──────────────┤  │  │ 内容编辑 (textarea)              ││
│  │ □ #13 预览...◀│──│  │ 章节标题                         ││
│  │   🟠待索引    │  │  │ Taxonomy: lvl1→lvl2→lvl3 联动    ││
│  ├──────────────┤  │  │ Bridge Links: 增删改表格          ││
│  │ □ #14 预览... │  │  ├─────────────────────────────────┤│
│  └──────────────┘  │  │ [保存] [拆分] [删除]              ││
│                    │  └─────────────────────────────────┘│
│  批量操作栏 (多选时) │                                     │
│  [改Tag][改Bridge]  │                                     │
│  [合并][删除]       │                                     │
└────────────────────┴─────────────────────────────────────┘
```

### 左栏

- 按 chunk id 升序（文档自然顺序）
- 每项：checkbox、id、content 前 60 字、lvl1 badge、bridge badge
- `needs_reindex=True` 显示橙色「待索引」标记
- 选中项高亮，右栏加载详情
- 多选时底部出现批量操作栏

### 右栏

选中单个 chunk：
1. **提示条**（needs_reindex 时）：⚠ 内容已修改，embedding 待更新
2. **内容编辑**：textarea 编辑 chunk 文本
3. **章节标题**：文本输入
4. **Taxonomy**：lvl1→lvl2→lvl3 级联下拉（从 taxonomy tree API 动态加载）
5. **Bridge Links**：小表格，每行可编辑 bridge/role/confidence，支持增删行
6. **操作**：保存、拆分（textarea 光标定位分割点）、删除（确认弹窗）

### 批量操作栏

多选 ≥ 2 时：改 Tag（弹窗）、改 Bridge（弹窗）、合并、删除

### 入口

1. IngestPage 成功后增加「去校对」按钮 → `/sources/{sourceId}/chunks/edit`
2. SourceDetailPage 增加「校对 Chunks」按钮

### 重新索引按钮

PageHeader 右侧，显示待更新数量，调用 `POST /sources/{id}/reindex`，loading 状态，完成后刷新。

## 数据流

```
编辑 content → PUT /chunks/{id}
                 ├─ content 更新
                 ├─ search_text = contextual_text + "\n" + content  (即时)
                 ├─ tsv = jieba(search_text)                        (即时)
                 └─ needs_reindex = True

手动重索引 / 每日 03:00 → 找 needs_reindex=True 的 chunks
                 ├─ contextual_text = ContextEnricher.enrich(content)
                 ├─ search_text = contextual_text + "\n" + content
                 ├─ embedding = provider.embed(search_text)
                 ├─ tsv = jieba(search_text)
                 └─ needs_reindex = False
```

## 测试

**单元测试：**
- split position 边界校验
- merge 输入校验（跨 source、单条）
- batch request 校验
- search_text 拼接逻辑
- needs_reindex 标记逻辑

**集成测试：**
- split 后新 chunks 正确、bridge_links 继承、原 chunk 已删
- merge 后 content 拼接、元数据继承、被合并 chunks 已删
- reindex 后所有派生字段更新、needs_reindex 清除
- batch 操作正确执行
- 并发 409 冲突

**路由烟雾测试：**
- 新端点存在于 app.routes
