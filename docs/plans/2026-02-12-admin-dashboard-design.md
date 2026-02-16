# Bridge RAG Admin Dashboard — Design Document

**Date:** 2026-02-12
**Status:** Approved

---

## Context

当前 web/ 应用只有问答和入库两个 Tab 页，后端仅有 3 个端点（ask、ingest、health）。需要将其改造为功能丰富的后台管理面板，支持数据浏览、实体管理和系统监控。

**目标：** 7 个功能模块（Dashboard、Chunk Explorer、Bridge Manager、Ingest Management、Taxonomy、Q&A Playground、System Settings），分 P0/P1/P2 三期交付。

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Audience | Dev/ops + 领域专家 | Progressive disclosure: 简洁表面，高级功能可达 |
| Sidebar | 可折叠 + localStorage 持久化 | shadcn Sidebar `collapsible="icon"` 原生支持 |
| UI language | 全中文 | 领域专家为主要用户，中文桥梁数据 |
| Bridge merge | Backend P0, Frontend P1 | 降低 P0 范围，合并操作需谨慎设计 |
| Dashboard charts | P0 纯 CSS 进度条, P1 recharts | 减少 P0 依赖，stat cards + 列表已足够 |
| Chunk editing | 仅详情页编辑 | 列表页只读，避免误操作 |

---

## Aesthetic Direction: "石径" (Stone Path)

Swiss Minimalism + Chinese Engineering Heritage. 清晰网格布局、高信息密度，配合领域特色的暖色调。

### Color Palette

| Role | Color | Tailwind | Usage |
|------|-------|----------|-------|
| Primary | `#2563EB` | blue-600 | 链接、活跃导航、主要操作 |
| Background | `#F7F6F3` | custom warm-gray | 页面背景 |
| Surface | `#FFFFFF` | white | 卡片、侧边栏 |
| Text | `#1C1917` | stone-900 | 主要文本 |
| Muted text | `#57534E` | stone-600 | 次要标签 |
| Border | `#E7E5E4` | stone-200 | 分割线、卡片边框 |
| Accent/CTA | `#EA580C` | orange-600 | 危险操作、警告 |
| Success | `#16A34A` | green-600 | 已绑定状态 |
| Ambiguous | `#D97706` | amber-600 | 待消歧状态 |

### Typography

- **Primary:** Noto Sans SC (简体中文优化，300/400/500/700 四档)
- **Monospace:** 系统等宽字体（代码/ID 展示）
- **Font import:** `@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');`

### z-index Scale

| Level | z-index | Usage |
|-------|---------|-------|
| Sticky headers | z-10 | 表格固定表头 |
| Sidebar | z-20 | 侧边栏 |
| Page header | z-30 | 面包屑/标题栏 |
| Modals/Dialogs | z-50 | 弹窗 |

---

## Architecture

### Frontend

- **路由:** React Router v7 (`createBrowserRouter`)
- **布局:** 可折叠侧边栏 (shadcn Sidebar) + SidebarInset 主内容区
- **依赖 (P0):** `react-router` (无 recharts)
- **依赖 (P1):** `recharts`
- **shadcn 组件:** Card, Table, Select, Dialog, Separator, Skeleton, Sidebar, DropdownMenu, Tooltip, Pagination

### Backend

- **Schema 重构:** `schemas.py` → `schemas/` 包（`__init__.py` 保持向后兼容）
- **新端点:** stats.py, chunks.py, bridges.py (P0) + sources.py, taxonomy.py (P1) + system.py (P2)
- **通用分页:** `PaginatedResponse[T]` 泛型响应

### Routes

```
/                → Dashboard (仪表盘)
/chunks          → Chunk Explorer 列表
/chunks/:id      → Chunk 详情/编辑
/bridges         → Bridge Manager 列表
/bridges/new     → 创建桥梁
/bridges/:id     → 桥梁详情/编辑
/ingest          → 入库
/sources         → Source 历史列表 (P1)
/sources/:id     → Source 详情 (P1)
/taxonomy        → 知识分类管理 (P1)
/ask             → 问答测试台
/settings        → 系统设置 (P2)
```

---

## Component Architecture

### Layout

```
<RouterProvider>
  └─ <DashboardLayout>
       ├─ <SidebarProvider defaultOpen={true} open={persisted}>
       │    └─ <AppSidebar collapsible="icon">
       │         ├─ SidebarHeader  → logo/app name
       │         ├─ SidebarContent → nav groups
       │         └─ SidebarFooter  → version info
       └─ <SidebarInset>
            ├─ <PageHeader>      ← breadcrumb + SidebarTrigger + title
            └─ <main>            ← <Outlet>
```

### Sidebar Navigation

| Group | Items | Icon |
|-------|-------|------|
| 概览 | 仪表盘 | `LayoutDashboard` |
| 数据管理 | 知识块, 桥梁, 来源(P1) | `Blocks`, `Landmark`, `FileText` |
| 知识体系 | 分类目录(P1) | `FolderTree` |
| 工具 | 入库, 问答测试 | `Upload`, `MessageSquare` |
| 系统(P2) | 设置 | `Settings` |

### Shared Patterns

- **`useApi<T>(fetcher, deps)`** — `{data, loading, error, refetch}` hook
- **`<Skeleton>`** — 所有数据加载使用骨架屏
- **`<PageHeader>`** — 统一页面标题 + 操作按钮区
- **`PaginatedResponse<T>`** — 统一分页响应 + `<Pagination>` 组件

---

## Page Layouts

### Dashboard (仪表盘)

- **4 个 StatCard:** 知识块总数、桥梁总数、来源总数、待消歧率
- **绑定状态分布:** 纯 CSS 进度条 (primary/ambiguous/none)
- **分类覆盖 (lvl1):** 横向条形进度条 + 数字
- **最近入库:** 简单列表（来源标题、块数、时间）

### Chunk Explorer

- **列表页:** 筛选栏 (bridge_id/lvl1/binding_status/搜索) + Table + Pagination
- **详情页:** 左 60% 内容展示 (Markdown rendered) + 右 40% 元数据编辑 (Select 下拉) + 底部 bridge_links 表格
- **操作:** 保存修改、删除（确认弹窗）

### Bridge Manager

- **列表页:** 搜索 + Table (名称/类型/材料/年代/知识块数) + "新建桥梁" 按钮
- **详情页:** BridgeForm (编辑) + 关联知识块列表 (按 role 分组)
- **创建页:** BridgeForm (空白) → 提交后跳转详情

---

## API Contracts

### Stats

```
GET /api/v1/stats/dashboard → DashboardStats
{
  chunk_count, bridge_count, source_count, ambiguous_ratio,
  binding_distribution: {primary, ambiguous, none},
  lvl1_distribution: [{label, count}],
  recent_ingests: [{source_id, title, chunk_count, created_at}]
}
```

### Chunks

```
GET    /api/v1/chunks?page&page_size&bridge_id&lvl1&lvl2&binding_status&source_id&q
       → PaginatedResponse<ChunkListItem>
GET    /api/v1/chunks/{id}  → ChunkDetail
PUT    /api/v1/chunks/{id}  ← {lvl1?, lvl2?, lvl3?, bridge_id?, binding_status?}
DELETE /api/v1/chunks/{id}  → 204
```

### Bridges

```
GET    /api/v1/bridges?page&page_size&q → PaginatedResponse<BridgeListItem>
GET    /api/v1/bridges/{id}              → BridgeDetail
POST   /api/v1/bridges                   ← BridgeCreate
PUT    /api/v1/bridges/{id}              ← BridgeUpdate
DELETE /api/v1/bridges/{id}              → 204 (仅当 chunk_count=0)
POST   /api/v1/bridges/{id}/merge        ← {source_bridge_id} (P1)
GET    /api/v1/bridges/{id}/chunks       → PaginatedResponse<ChunkListItem>
```

### Generic Pagination

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
```

---

## Sprint Plan

### Sprint 1: P0 Backend

1. Schema 包重构 (`schemas.py` → `schemas/`)
2. Stats 端点 (`GET /api/v1/stats/dashboard`)
3. Chunks CRUD (`GET/PUT/DELETE /api/v1/chunks`)
4. Bridges CRUD (`GET/POST/PUT/DELETE /api/v1/bridges`)
5. 注册路由

### Sprint 2: P0 Frontend Scaffolding

1. 安装 `react-router` + shadcn 组件
2. Router + DashboardLayout + AppSidebar
3. API 客户端扩展
4. 类型定义扩展
5. `useApi` hook

### Sprint 3: P0 Frontend Pages

1. Dashboard 页 (stat cards + distribution bars + recent list)
2. Chunk Explorer (list + detail)
3. Bridge Manager (list + detail + create)
4. Ingest & Ask 页面包装

### Sprint 4: P1 — Sources, Taxonomy, Charts

1. Sources backend + frontend
2. Taxonomy backend + frontend (tree component)
3. Bridge merge dialog
4. Dashboard 升级为 recharts 图表

### Sprint 5: P2 — Q&A Debug, System Settings

1. Ask endpoint debug 模式
2. System status endpoint
3. Enhanced AskPage
4. SettingsPage

---

## File Inventory

### New Files (~40)

| Sprint | Category | Count |
|--------|----------|-------|
| S1 | Backend schemas | 7 |
| S1 | Backend endpoints | 3 |
| S2 | Frontend infra | 2 |
| S2 | Frontend layout | 3 |
| S2 | shadcn components | ~10 |
| S3 | Frontend pages | 8 |
| S3 | Frontend components | 6 |
| S4 | Backend | 4 |
| S4 | Frontend | 5 |
| S5 | Backend | 2 |
| S5 | Frontend | 1 |

### Modified Files (~8)

- `app/api/v1/__init__.py`
- `app/api/v1/ask.py`
- `app/api/v1/ingest.py`
- `web/src/main.tsx`
- `web/src/App.tsx`
- `web/src/lib/api.ts`
- `web/src/lib/types.ts`
- `web/src/index.css`
