# Async Ingest Pipeline Design

日期: 2026-02-21

## 概述

将入库流程从同步单步改造为异步多阶段任务。集成 Cloudflare R2（文件存储）和智谱文件解析服务（PDF → Markdown），支持用户在分块后确认/编辑再完成入库。

## 支持格式

- **PDF** → 智谱 Expert 解析（0.012 元/页，返回 Markdown + 图片）
- **Markdown** → 跳过解析，直接进入分块

## 任务阶段

```
uploading → syncing → parsing → chunked → indexing → completed
                                                  ↘ failed
```

| 状态 | 含义 | 触发方 |
|------|------|--------|
| `uploading` | 前端正在上传文件到 R2 | 前端（presigned URL） |
| `syncing` | 后端从 R2 取文件，提交智谱解析 | BackgroundTask |
| `parsing` | 智谱正在解析文件 | BackgroundTask 轮询 |
| `chunked` | 分块完成，等待用户确认 | BackgroundTask |
| `indexing` | 用户确认后，执行 embedding/标注/入库 | BackgroundTask |
| `completed` | 入库完成 | BackgroundTask |
| `failed` | 任意阶段失败 | BackgroundTask |

Markdown 文件跳过 `syncing` → `parsing`，直接从 R2 读取内容后进入分块。

## 数据模型

### 新增 `ingest_tasks` 表（Schema v6）

```sql
CREATE TABLE ingest_tasks (
    id              SERIAL PRIMARY KEY,
    status          VARCHAR(20) NOT NULL DEFAULT 'uploading',
    file_name       VARCHAR(255) NOT NULL,
    file_type       VARCHAR(10) NOT NULL,    -- pdf / md
    file_size       INTEGER,                 -- bytes
    r2_raw_key      VARCHAR(512),            -- raw/{task_id}/{filename}
    r2_parsed_prefix VARCHAR(512),           -- parsed/{task_id}/
    zhipu_task_id   VARCHAR(128),            -- 智谱解析 task_id
    source_id       INTEGER REFERENCES sources(id),
    parsed_content  TEXT,                    -- 解析后 Markdown（图片链接已改写为 R2 URL）
    chunk_count     INTEGER,
    image_count     INTEGER DEFAULT 0,
    error_message   TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT now(),
    updated_at      TIMESTAMP DEFAULT now()
);
```

### R2 存储结构

```
raw/{task_id}/{原始文件名}           ← 原始上传文件
parsed/{task_id}/result.md          ← 解析后 Markdown
parsed/{task_id}/images/            ← 解析提取的图片
    ├── img_001.png
    ├── img_002.png
    └── ...
```

## API 端点

```
POST   /api/v1/ingest-tasks/presign       ← 获取 R2 presigned upload URL
POST   /api/v1/ingest-tasks               ← 创建入库任务（上传完成后调用）
GET    /api/v1/ingest-tasks/{id}          ← 查询任务状态（前端轮询）
GET    /api/v1/ingest-tasks               ← 任务列表（分页）
POST   /api/v1/ingest-tasks/{id}/confirm  ← 用户确认分块，触发标识阶段
DELETE /api/v1/ingest-tasks/{id}          ← 取消/删除任务
```

所有端点需 JWT Bearer token 认证。

### 流程时序

```
前端                        后端 API                    R2              智谱
 │  POST /presign            │                          │                │
 │──────────────────────────>│                          │                │
 │  { upload_url, key }      │                          │                │
 │<──────────────────────────│                          │                │
 │                           │                          │                │
 │  PUT upload_url (直传)     │                          │                │
 │─────────────────────────────────────────────────────>│                │
 │                           │                          │                │
 │  POST /ingest-tasks       │                          │                │
 │──────────────────────────>│  创建 task, status=syncing│                │
 │  { task_id }              │                          │                │
 │<──────────────────────────│                          │                │
 │                           │  ── BackgroundTask ──    │                │
 │                           │  GET file from R2        │                │
 │                           │─────────────────────────>│                │
 │                           │  file bytes              │                │
 │                           │<─────────────────────────│                │
 │                           │                          │                │
 │                           │  POST /files/parser/create                │
 │                           │  status=parsing          │───────────────>│
 │                           │                          │  { task_id }    │
 │                           │  轮询智谱结果             │                │
 │                           │─────────────────────────────────────────>│
 │                           │  status=succeeded        │                │
 │                           │<─────────────────────────────────────────│
 │                           │                          │                │
 │                           │  下载 Markdown + 图片     │                │
 │                           │  改写图片链接             │                │
 │                           │  存 R2 parsed/           │                │
 │                           │─────────────────────────>│                │
 │                           │  分块 (SemanticChunker)   │                │
 │                           │  写入 chunks (无 embedding)│                │
 │                           │  status=chunked          │                │
 │                           │                          │                │
 │  轮询: GET /{id}          │                          │                │
 │──────────────────────────>│                          │                │
 │  status=chunked           │                          │                │
 │  → 跳转 ChunkEditor       │                          │                │
 │                           │                          │                │
 │  POST /{id}/confirm       │                          │                │
 │──────────────────────────>│  ── BackgroundTask ──    │                │
 │                           │  status=indexing         │                │
 │                           │  embedding + 标注 + tsv   │                │
 │                           │  bridge linking          │                │
 │                           │  status=completed        │                │
```

## Provider & 服务层

### FileParserProvider（新建）

```python
# app/providers/file_parser.py
class FileParserProvider:
    """智谱文件解析服务封装。独立于 LLMProvider（不共享接口，职责不同）。"""

    base_url = "https://open.bigmodel.cn/api/paas/v4/files/parser"
    # 复用 settings.zhipu_api_key

    async def create_task(self, file_bytes, file_name, file_type, tool_type) -> str:
        """上传文件创建解析任务，返回 zhipu_task_id"""

    async def get_result(self, task_id, format_type="download_link") -> ParseResult:
        """查询解析结果"""

    async def poll_until_done(self, task_id, timeout=300, interval=3) -> ParseResult:
        """轮询直到完成或超时"""
```

### R2StorageService（新建）

```python
# app/services/r2_storage.py — 使用 boto3（S3 兼容）
class R2StorageService:
    def generate_presigned_upload_url(self, key, content_type, expires=3600) -> str
    def generate_presigned_download_url(self, key, expires=3600) -> str
    async def upload(self, key, data: bytes, content_type) -> None
    async def download(self, key) -> bytes
    async def delete_prefix(self, prefix: str) -> None
```

### IngestTaskService（新建）

```python
# app/services/ingest_task_service.py — 核心编排
class IngestTaskService:
    async def start_sync_and_parse(self, task_id: int):
        """[syncing → parsing → chunked]"""

    async def start_indexing(self, task_id: int):
        """[indexing → completed]"""
```

## 前端 UI

改造 IngestPage 为任务仪表板 + 文件上传入口：

- **上传区**：拖拽/点击，支持 .pdf / .md
- **任务列表**：按时间倒序，显示文件名 + 状态 + 元信息
  - 进行中状态（uploading/syncing/parsing/indexing）：spinner + 状态文字，无进度条
  - `uploading` 例外：可显示真实上传进度（浏览器 XHR progress 事件）
  - `chunked`：显示"去校对"按钮 → 跳转 ChunkEditorPage
  - `completed`：显示 ✓
  - `failed`：显示错误信息 + 重试按钮
- **轮询**：仅对进行中任务轮询，间隔 3 秒

## 配置

`.env` 新增：

```bash
# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=bridge-rag
R2_PUBLIC_URL=                              # 可选，公开访问域名

# 智谱文件解析
ZHIPU_PARSER_TOOL_TYPE=expert               # lite / expert / prime
```

`Settings` 中 R2 字段全部可选，未配置时文件上传功能不可用。

## 向后兼容

- 旧的 `POST /api/v1/ingest` 端点保留，文本粘贴入库继续工作
- 新流程通过 `/api/v1/ingest-tasks` 独立运作
- 前端 IngestPage 以文件上传为主；R2 未配置时降级显示旧 Markdown 文本框

## 后台任务机制

使用 FastAPI `BackgroundTasks`：
- `POST /ingest-tasks` 触发 `start_sync_and_parse`
- `POST /ingest-tasks/{id}/confirm` 触发 `start_indexing`
- 任何阶段失败 → `status=failed` + `error_message`
- 任务状态持久化在 DB，页面刷新/重开可恢复查看
