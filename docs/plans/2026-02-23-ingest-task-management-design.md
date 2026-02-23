# Ingest Task Management Redesign

Date: 2026-02-23

## Goal

将入库页面重构为以任务列表为核心的管理界面，提供完善的任务生命周期管理、审计日志、文件下载等功能。

## Current State

- 入库页面：FileUploadZone（拖拽上传区）+ IngestTaskList（卡片列表）
- 审计日志仅覆盖 3 个时刻：创建(ingest)、确认(confirm_ingest)、删除(delete)
- 后台状态变更无审计记录
- 删除为物理删除（清除 task 记录 + R2 文件）
- 所有端点按用户所有权过滤（仅看自己的任务）

## Design

### 1. Backend API Changes

#### 1.1 Remove User Ownership Filter

所有 ingest-tasks 端点去掉 `created_by == current_user.id` 过滤。任意已认证用户可查看/操作任何任务。

#### 1.2 List Endpoint Enhancement

`GET /ingest-tasks` 新增参数：

- `file_name: str | None` — 模糊搜索（`ILIKE %keyword%`）
- 现有 `status` 参数不变
- 默认排除 `deleted` 状态（除非 `status=deleted` 显式请求）

#### 1.3 Soft Delete

`DELETE /ingest-tasks/{task_id}` 改为软删除：

- 状态守卫不变：`syncing` / `parsing` / `indexing` 禁止删除
- 清理关联数据：`chunk_bridge_links` → `chunks` → `sources`
- 置空 `task.source_id`、设 `task.status = "deleted"`
- **保留** `ingest_tasks` 记录和 R2 文件
- 记审计日志

#### 1.4 Retry Endpoint

`POST /ingest-tasks/{task_id}/retry`

- 仅允许 `failed` 和 `deleted` 状态
- 清理关联 chunks/source（如有）
- 重置：`status="syncing"`, `error_message=None`, `source_id=None`, `chunk_count=None`, `parsed_content=None`
- 触发 BackgroundTask 重新跑 `sync_and_parse`
- 记审计日志 `action="retry_ingest"`

#### 1.5 Batch Delete Endpoint

`POST /ingest-tasks/batch-delete`

- Body: `{ "task_ids": [1, 2, 3] }`
- 逐个执行软删除逻辑，跳过 running 状态的
- 返回 `{ "deleted": [1,2], "skipped": [3] }`
- 每个成功删除的记审计日志

#### 1.6 File Download Endpoint

`GET /ingest-tasks/{task_id}/download-url`

- Query 参数 `type`: `raw`（原始文件）或 `parsed`（解析后 markdown）
- 生成 R2 presigned GET URL（有效期 1 小时）
- 返回 `{ "url": "..." }`
- `r2_raw_key` / `r2_parsed_prefix` 为空时 404，R2 未配置时 503

#### 1.7 Audit Log Enhancement

在 `ingest_task_service.py` 的后台任务中补全审计日志：

| Transition | Action |
|---|---|
| syncing → parsing | `ingest_parse_start` |
| parsing → chunked | `ingest_parse_done` |
| indexing → completed | `ingest_index_done` |
| any → failed | `ingest_failed` (detail 含 error_message) |

触发后台任务的端点（create、confirm、retry）在请求阶段捕获 `ip_address`，作为参数传入后台函数。后台任务用独立 `SessionLocal()`，`user_id` 取 `task.created_by`，`ip_address` 取传入值。

### 2. Frontend Changes

#### 2.1 IngestPage Refactor (Task List)

**页面布局：**

1. **工具栏**
   - 左侧：状态筛选 tabs（全部 / 进行中 / 待确认 / 已完成 / 失败）— "进行中"合并 uploading/syncing/parsing/indexing
   - 右侧：文件名搜索框 + "新建任务"按钮

2. **表格列：**
   - 勾选框（批量选择）
   - ID
   - 文件名（可点击进入详情页）
   - 类型（PDF / MD 徽章）
   - 状态（彩色徽章，进行中带 spinner）
   - Source（链接到 Source 详情，无则 `—`）
   - 创建时间（相对时间）
   - 操作按钮组

3. **操作按钮（按状态条件显示）：**
   - `chunked`: 校对 + 确认
   - `failed` / `completed` / `deleted`: 重运行
   - `uploading` / `chunked` / `completed` / `failed` / `deleted`: 删除
   - `syncing` / `parsing` / `indexing`: 无操作

4. **批量操作栏：** 选中后顶部浮现 "已选 N 项 — 批量删除"

5. **分页：** 复用现有分页组件

6. **自动轮询：** 有 running 状态任务时 3 秒轮询刷新

#### 2.2 Upload Dialog

点击"新建任务"弹出 Dialog，复用 FileUploadZone 逻辑（presign → R2 上传 → 创建任务）。完成后关闭并刷新表格。

#### 2.3 IngestTaskDetailPage (New)

路由：`/ingest-tasks/:id`

**三个区域：**

1. **任务信息卡片** — ID、文件名、类型、大小、状态、时间、Source 链接、错误信息、操作按钮
2. **文件下载** — "下载原始文件"和"下载解析结果"按钮（调用 download-url 端点）
3. **审计日志时间线** — 调用 `GET /audit-logs?resource_type=ingest_task&resource_id={id}`，按时间倒序

#### 2.4 R2 Fallback

保留现有逻辑：presign 返回 503 时显示 legacy IngestPanel。

### 3. State Machine

```
uploading → syncing → parsing → chunked → indexing → completed
                                    │
                 (any non-running) ──┴──→ deleted
                 (any) ─────────────────→ failed (异常时自动)

retry: failed/deleted → syncing (重跑流水线)
```

"non-running" = 不在 syncing / parsing / indexing 中的任何状态。

### 4. Edge Cases

- **batch-delete 部分跳过：** running 状态的任务跳过，返回 `skipped` 列表，前端提示
- **retry 清理：** 重跑前先清理已有 chunks/source，R2 原始文件保留可直接重用
- **download 404：** R2 key 为空时返回 404（如 MD 文件无 parsed 产出）
- **list 默认排除 deleted：** 除非显式 `status=deleted`
