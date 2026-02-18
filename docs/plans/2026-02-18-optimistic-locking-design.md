# Chunk 编辑乐观锁设计

日期：2026-02-18

## 概述

为 Chunk Editor 写操作添加乐观锁（optimistic locking），防止多用户并发编辑时互相覆盖。采用 `updated_at` 时间戳方案，前端发送 `expected_updated_at`，后端比对后决定放行或返回 409。

## Schema 变更

`chunks` 表新增列：

```
updated_at  TIMESTAMPTZ  NOT NULL  DEFAULT now()
```

- schema_version 升至 5
- 仅 `chunks` 表加此列，其他表暂无并发编辑需求
- 迁移脚本 backfill 现有行：`UPDATE chunks SET updated_at = created_at WHERE updated_at IS NULL`

Model 变化：

```python
# app/models/chunk.py
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

`onupdate=func.now()` 使 ORM UPDATE 自动刷新时间戳。Raw SQL UPDATE（batch 等）需手动 `SET updated_at = now()`。

## API 契约

### 响应侧

`ChunkDetail` 和 `ChunkListItem` 增加 `updated_at: datetime` 字段。

### 请求侧

仅单条写操作传递版本信息：

| 端点 | 新增字段 | 说明 |
|------|----------|------|
| `PUT /chunks/{id}` | `expected_updated_at: datetime \| None` | 传则校验，不传跳过 |
| `POST /chunks/{id}/split` | `expected_updated_at: datetime \| None` | 同上 |
| `DELETE /chunks/{id}` | Query param `?expected_updated_at=` | 同上 |

`POST /chunks/merge` 和 `PATCH /chunks/batch` **不做**乐观锁——批量操作场景复杂度高收益低。

### 409 响应

```json
{
  "detail": "Chunk has been modified by another user",
  "current_updated_at": "2026-02-18T12:34:56Z",
  "chunk_id": 42
}
```

## 后端校验逻辑

`chunk_editor.py` 新增：

```python
def check_optimistic_lock(chunk: Chunk, expected: datetime | None) -> None:
    if expected is None:
        return
    if chunk.updated_at != expected:
        raise HTTPException(status_code=409, detail={...})
```

在 `update_chunk`、`split_chunk_endpoint`、`delete_chunk` 中查询 chunk 后立即调用。

所有写操作（split 创建新 chunk、merge 更新主 chunk、batch update）完成后确保 `updated_at` 被刷新。

## 前端变更

### 类型

- `ChunkDetail` / `ChunkListItem` 增加 `updated_at: string`
- `ChunkUpdateRequest` 增加 `expected_updated_at?: string`
- `ChunkSplitRequest` 增加 `expected_updated_at?: string`

### ChunkEditorPage

- 加载 chunk 详情时记录 `updated_at`
- 保存/拆分/删除时携带 `expected_updated_at`
- 捕获 409 响应后弹出冲突对话框

### 冲突对话框

```
┌──────────────────────────────────┐
│  ⚠ 编辑冲突                      │
│                                  │
│  该 Chunk 已被其他用户修改。       │
│  您可以强制覆盖或放弃本次更改。    │
│                                  │
│       [放弃修改]  [强制覆盖]      │
└──────────────────────────────────┘
```

- **放弃修改**：重新拉取最新数据
- **强制覆盖**：不传 `expected_updated_at` 重新提交

## 测试

**单元测试：**
- `check_optimistic_lock`：匹配通过、不匹配 409、None 跳过

**集成测试：**
- 更新 chunk → 不刷新 expected → 再次更新 → 409
- split/delete 的 409 校验

**路由烟雾测试：**
- 409 响应格式正确

## 不做的事情

- 不给其他表加 `updated_at`
- 不用 ETag/If-Match
- merge/batch 不做乐观锁
- 不做 websocket 实时推送
