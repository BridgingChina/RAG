# WebUI Design — Bridge RAG 前端界面

> 日期: 2026-02-08
> 状态: 已验证

## 概述

为 Bridge RAG System 增加 WebUI，支持问答（Ask）和入库（Ingest）两个核心功能。前端放在 `web/` 子目录，单仓库管理。

## 技术选型

- **框架:** React + Vite + TypeScript
- **UI 库:** shadcn/ui + Tailwind CSS
- **字体:** Libre Bodoni (标题 serif) + Public Sans (正文/UI sans-serif)
- **图标:** Lucide React
- **Markdown 渲染:** react-markdown
- **无路由库**, 无状态管理库, 无 axios — 保持极简

## 视觉方向

Swiss Modernism 2.0 — 严谨网格、清晰层级、大量留白、单一强调色。像一本排版精良的学术工具书。

### 色彩体系

| 角色 | 色值 | 用途 |
|------|------|------|
| Primary | `#1E293B` (slate-800) | 标题、主文字 |
| Accent | `#3B82F6` (blue-500) | 链接、聚焦态 |
| CTA | `#F97316` (orange-500) | 提交按钮、关键操作 |
| Background | `#F8FAFC` (slate-50) | 页面底色 |
| Surface | `#FFFFFF` | 卡片、面板 |
| Border | `#E2E8F0` (slate-200) | 分割线、卡片边框 |
| 置信度 high | `#22C55E` | 绿底白字 |
| 置信度 medium | `#EAB308` | 黄底深字 |
| 置信度 low | `#EF4444` | 红底白字 |

### 字体配置

```ts
// tailwind.config.ts
fontFamily: {
  serif: ['Libre Bodoni', 'serif'],
  sans: ['Public Sans', 'sans-serif'],
}
```

```css
/* index.css */
@import url('https://fonts.googleapis.com/css2?family=Libre+Bodoni:wght@400;500;600;700&family=Public+Sans:wght@300;400;500;600;700&display=swap');
```

## 页面设计

### 布局

- 居中单栏 `max-w-3xl`
- 顶部 Tab 导航（问答 / 入库），用 `useState` 切换，无路由
- 页面底色 slate-50，内容卡片白色

### 问答页 (Ask)

**输入区:**
- 大输入框，`placeholder="输入关于桥梁的问题…"`
- 底部右侧橙色 CTA 提交按钮，回车可提交
- 折叠的"筛选条件"行：展开后显示 `target_bridge_id` 数字输入

**加载态:**
- skeleton 骨架屏（pulse 动画），模拟回答区结构

**回答区（自上而下）:**

1. **降级警告** — 若 `degraded` 非空，黄色 banner 提示
2. **置信度标签** — 左上角小胶囊 (high 绿 / medium 黄 / low 红)，旁边灰字 reason
3. **Summary** — Libre Bodoni `text-2xl font-semibold`
4. **Details** — Public Sans 正文，react-markdown 渲染
5. **Analogy** — 左侧蓝色竖线 blockquote 样式（若有）
6. **三通道证据网格** — 三等分栏：
   - 每栏顶部 4px 色条：蓝色（本桥资料）/ 灰色（通用知识）/ 琥珀色（类比案例）
   - 栏标题 `text-xs uppercase tracking-wider`
   - 每条证据小卡片：preview + bridge_name
   - 移动端堆叠为单列
7. **引用列表** — 分割线后小字，source_title + page_range

### 入库页 (Ingest)

**输入区:**
- 大 textarea，`font-mono`，`min-h-[300px]`，可调整高度
- 上方一行：左侧标签"Markdown 内容"，右侧 `source_type` Select 下拉
- 底部右对齐橙色提交按钮

**结果区:**
- 总结卡片：桥梁名 (Libre Bodoni 大字) + 来源标题 (灰字) + "共 N 个知识块"
- chunk 列表：`content_preview`（单行 ellipsis）+ `lvl1`/`lvl2` 标签胶囊 + `bridge_name`
- 错误时红色 banner

## 项目结构

```
web/
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   └── TabNav.tsx          # 顶部双 Tab 导航
│   │   ├── ask/
│   │   │   ├── AskPanel.tsx        # 问答页主容器
│   │   │   ├── AnswerDisplay.tsx   # summary + details + analogy
│   │   │   ├── EvidenceGrid.tsx    # 三通道三栏证据网格
│   │   │   └── ConfidenceBadge.tsx # 置信度胶囊
│   │   └── ingest/
│   │       ├── IngestPanel.tsx     # 入库页主容器
│   │       └── ChunkList.tsx       # chunk 条目列表
│   ├── lib/
│   │   └── api.ts                  # fetch 封装
│   ├── App.tsx                     # Tab 状态切换
│   ├── index.css                   # Tailwind + Google Fonts
│   └── main.tsx
├── components.json                 # shadcn/ui 配置
├── package.json
├── tsconfig.json
├── vite.config.ts                  # proxy 配置
└── tailwind.config.ts              # 字体配置
```

## 依赖

- `react`, `react-dom`
- `tailwindcss`, `shadcn/ui` (Button, Input, Textarea, Select, Tabs, Badge)
- `react-markdown`
- `lucide-react` (Search, Upload, AlertTriangle, ChevronDown)

## API 封装

```ts
// lib/api.ts
askQuestion(question: string, targetBridgeId?: number): Promise<AskResponse>
ingestDocument(content: string, sourceType: string): Promise<IngestResponse>
```

统一错误处理：非 2xx 时抛出带 message 的 Error。

## Vite Proxy

```ts
// vite.config.ts
server: {
  proxy: {
    '/api': 'http://localhost:8000'
  }
}
```

## 后端改动

`app/main.py` 添加 `CORSMiddleware`，`allow_origins=["http://localhost:5173"]`。

## shadcn/ui 组件清单

按需引入，不全量安装：
- `Button` — 提交按钮
- `Input` — 问题输入、bridge_id 输入
- `Textarea` — Markdown 输入
- `Select` — source_type 下拉
- `Tabs` — 顶部页面切换
- `Badge` — 置信度标签、taxonomy 标签
