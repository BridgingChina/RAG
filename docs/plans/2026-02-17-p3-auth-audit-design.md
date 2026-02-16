# P3 — Authentication & Audit Log Design

## Overview

为 Bridge RAG 团队面板添加用户认证和写操作审计功能。

- **团队规模：** 2-5 人小团队
- **认证方式：** 用户名 + 密码，JWT access token
- **权限模型：** 平权，不区分角色
- **审计范围：** 所有写操作 + 登录成功/失败

## Data Model

### users 表

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID, PK | 主键 |
| `username` | VARCHAR(50), UNIQUE | 用户名 |
| `hashed_password` | VARCHAR(255) | bcrypt 哈希密码 |
| `display_name` | VARCHAR(100), nullable | 显示名称 |
| `is_active` | BOOLEAN, default TRUE | 是否启用 |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 更新时间 |

不做角色字段（平权），不做邮箱（小团队不需要密码重置流程）。

### audit_logs 表

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT, PK, auto | 自增主键 |
| `user_id` | UUID, FK → users, nullable | 操作人（登录失败时为 null） |
| `action` | VARCHAR(50) | 动作类型 |
| `resource_type` | VARCHAR(50) | 资源类型 |
| `resource_id` | VARCHAR(255), nullable | 资源 ID |
| `detail` | JSONB, nullable | 变更详情 |
| `ip_address` | VARCHAR(45), nullable | 请求 IP |
| `created_at` | TIMESTAMPTZ | 操作时间 |

索引：`created_at` DESC，支持按时间范围查询。

### 用户初始化

通过 CLI 脚本 `python scripts/create_user.py --username admin --password xxx` 创建用户。可在 `init_database()` 中 seed 默认 admin 用户。

## Authentication Flow (Backend)

### 新增依赖

- `python-jose[cryptography]` — JWT 编解码
- `passlib[bcrypt]` — 密码哈希

### JWT 设计

- Access Token 有效期 24 小时
- 无 Refresh Token（过期重新登录）
- Payload: `{ "sub": user_id, "username": "xxx", "exp": ... }`
- 签名密钥：`settings.SECRET_KEY`（`.env` 配置）

### API 端点

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | 登录 | 否 |
| `GET` | `/api/v1/auth/me` | 当前用户 | 是 |
| `PUT` | `/api/v1/auth/password` | 改密码 | 是 |

### 认证中间件

`get_current_user(token) → User` 作为 FastAPI `Depends()` 注入，从 `Authorization: Bearer <token>` 解析。

### 路由保护策略

- `/health` 和 `/api/v1/auth/login` — 公开
- 其余 `/api/v1/*` — 需要认证
- 在 `api/v1/__init__.py` 的 router 统一加 dependency，`/auth/login` 单独挂载在认证 dependency 之外

## Authentication Flow (Frontend)

### LoginPage

新增 `LoginPage.tsx`，用户名 + 密码表单，shadcn/ui Card 组件。

### Token 管理

- 登录成功后 `access_token` 存入 `localStorage`
- `api.ts` 请求 helper 自动附加 `Authorization: Bearer <token>`
- 收到 401 时清除 token 并跳转 `/login`

### 路由保护

React Router layout 层 `AuthGuard` 组件：

```
Routes
├── /login          — LoginPage（公开）
└── <AuthGuard>     — 验证 token
    ├── /           — Dashboard
    ├── /chunks     — ChunkList
    └── ...其余页面
```

AuthGuard 逻辑：检查 localStorage token → 调 `GET /auth/me` 验证 → 有效则渲染子路由，无效跳转 `/login`。

### 用户上下文

`AuthContext`（React Context）存储当前用户信息。侧边栏底部显示用户名 + 登出按钮。

### 不做的事

- 不做"记住我"、前端注册、密码强度检查

## Audit System

### audit_service

`audit_service.log(user_id, action, resource_type, resource_id, detail, ip)` 函数，在审计端点中调用。

### 审计操作表

| action | resource_type | 触发端点 |
|---|---|---|
| `login` | `auth` | `POST /auth/login` 成功 |
| `login_failure` | `auth` | `POST /auth/login` 失败（user_id=null, detail={"username": "xxx"}） |
| `change_password` | `auth` | `PUT /auth/password` |
| `ingest` | `source` | `POST /ingest` |
| `create` | `bridge` | `POST /bridges` |
| `update` | `bridge` | `PUT /bridges/{id}` |
| `delete` | `bridge` | `DELETE /bridges/{id}` |
| `merge` | `bridge` | `POST /bridges/{id}/merge` |
| `delete` | `chunk` | `DELETE /chunks/{id}` |
| `create` | `taxonomy` | `POST /taxonomy/nodes` |
| `update` | `taxonomy` | `PUT /taxonomy/nodes/{id}` |
| `delete` | `taxonomy` | `DELETE /taxonomy/nodes/{id}` |
| `batch_update` | `taxonomy` | `POST /taxonomy/batch-update` |
| `update` | `settings` | `PUT /system/settings` |

### 审计查询 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/audit-logs` | 分页查询，筛选：`user_id`, `action`, `resource_type`, `start`, `end` |

返回 `PaginatedResponse<AuditLog>`。

### 前端审计页面

`AuditLogPage.tsx`，包含：
- 筛选栏：用户、操作类型、资源类型、时间范围
- 表格：时间 / 用户 / 操作 / 资源类型 / 资源 ID / 详情
- 分页：复用现有分页组件
- 导航位置：Settings 旁边，路由 `/audit-logs`

### 不做的事

- 不做导出、不做删除（只增不删）、不做读操作审计
