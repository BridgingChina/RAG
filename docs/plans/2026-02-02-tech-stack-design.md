# Bridge RAG System V0 — 技术选型设计

> 日期：2026-02-02
> 状态：已确认

---

## 1. 概述与核心选型

**项目**：Bridge RAG System V0 — 桥梁知识检索增强生成系统

**核心技术栈：**

| 层 | 选型 |
|-----|------|
| 数据库 + 向量 | PostgreSQL + pgvector |
| Embedding | 智谱 embedding（1024 维） |
| LLM 生成 | 智谱 GLM-4（封装 Provider 层，便于替换） |
| 后端框架 | Python + FastAPI |
| RAG 框架 | 不用，自己实现 |
| 部署 | 自有 VPS，Docker 部署 |

**设计原则：**

- 简单可落地，先跑通再优化
- 同库管理（结构化数据 + 向量在同一个 PostgreSQL）
- 抽象 LLM Provider 接口，方便后续替换模型

---

## 2. 入库流程与切块策略

**入库流程：**

```
采集资料（PDF / 网页 / 笔记）
  ↓
抽取文本（保留章节结构，如有）
  ↓
语义切块（按 embedding 相似度判断断点）
  ↓
LLM 自动标注 metadata（lvl1 / lvl2 / bridge_id）
  ↓
生成 embedding（智谱 API，1024 维）
  ↓
写入 PostgreSQL + pgvector
```

**切块配置：**

| 配置项 | 值 |
|--------|-----|
| 切块方式 | 语义切块 |
| 块大小参考 | 300-500 字（自适应） |
| 上下文前缀 | 保留章节标题 `[章节: xxx]` |

**LLM 标注规则：**

| 字段 | 处理方式 |
|------|---------|
| lvl1 | 必须标注（四大主线固定） |
| lvl2 | 尽量标注（已有部分） |
| lvl3 | V0 留空，后续补充 |
| bridge_id | LLM 判断是否关联具体桥梁 |

---

## 3. 问答检索与生成流程

**检索策略：先过滤后向量检索**

根据用户上下文决定过滤条件：

- 在桥梁页提问 → `WHERE bridge_id = ?`
- 在知识点页提问 → `WHERE lvl1 = ?` 或 `lvl2 = ?` 或 `lvl3 = ?`
- 无上下文 → 全库向量检索

然后：pgvector 相似度检索 top-k chunks（如 k=5）

**生成策略：**

调用 GLM-4，prompt 结构：

```
你是桥梁知识助手。根据以下证据回答问题。

证据：
[chunk1]
[chunk2]
...

问题：{user_question}

要求：
- 优先基于证据回答，标注引用 [1][2]
- 若证据不足，明确说明"未找到直接证据"
- 可附加常识解释，标注为"非引用"
```

**输出结构（便于移动端渐进式披露）：**

1. 要点大纲（3-6 条）
2. 展开解释 + 引用标注
3. Sources 列表（来源 + 页码/链接）

---

## 4. 数据模型（PostgreSQL 表结构）

**核心表：**

```sql
-- 桥梁档案
bridges (
  id, name, aliases, location, era, bridge_type,
  material, summary, created_at
)

-- 目录节点
taxonomy_nodes (
  id, lvl1, lvl2, lvl3, description
)

-- 来源
sources (
  id, type, -- 'pdf' | 'web' | 'note'
  title, url, file_path, accessed_at
)

-- 证据小段（核心检索单元）
chunks (
  id, source_id, content,
  section_title,  -- 章节标题前缀
  lvl1, lvl2, lvl3,
  bridge_id,      -- nullable
  page_range,     -- PDF 页码
  embedding vector(1024),
  created_at
)
```

**索引：**

- `chunks.embedding` → pgvector 的 HNSW 或 IVFFlat 索引
- `chunks(lvl1, lvl2, lvl3)` → 过滤查询加速
- `chunks(bridge_id)` → 桥梁页查询加速

---

## 5. API 设计

**核心接口：**

```
POST /ask
  输入：
    - question: string
    - context?: { bridge_id?, lvl1?, lvl2?, lvl3? }
  输出：
    - answer: { summary, details, sources }
    - citations: [{ chunk_id, source_title, page }]
    - evidence?: [chunks]

GET /bridges
  输出：桥梁列表

GET /bridges/:id
  输出：桥梁档案 + 相关知识点

GET /taxonomy
  输出：完整目录树（lvl1 / lvl2 / lvl3）

GET /taxonomy/:lvl1
GET /taxonomy/:lvl1/:lvl2
GET /taxonomy/:lvl1/:lvl2/:lvl3
  输出：该节点详情 + 下级节点 + 相关 chunks 摘要 + 相关桥例
```

**入库接口（内部/管理端）：**

```
POST /ingest/pdf
POST /ingest/web
POST /ingest/note
```

V0 可以先做成命令行脚本，不急着暴露 HTTP 接口。

---

## 6. 本地开发环境

**Docker Compose 配置：**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: bridge_rag
      POSTGRES_USER: bridge
      POSTGRES_PASSWORD: <dev_password>
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://bridge:<pwd>@db:5432/bridge_rag
      ZHIPU_API_KEY: ${ZHIPU_API_KEY}
    depends_on:
      - db

volumes:
  pgdata:
```

**项目结构：**

```
bridge-rag/
├── app/
│   ├── api/          # FastAPI 路由
│   ├── core/         # 配置、依赖
│   ├── models/       # SQLAlchemy 模型
│   ├── services/     # 业务逻辑
│   │   ├── chunker.py      # 语义切块
│   │   ├── embedder.py     # embedding 调用
│   │   ├── retriever.py    # 向量检索
│   │   └── generator.py    # LLM 生成
│   └── providers/    # LLM Provider 抽象层
├── scripts/          # 入库脚本
├── docker-compose.yml
└── requirements.txt
```

---

## 7. 待定项与后续迭代

**V0 待定项（后续确定）：**

| 项目 | 状态 |
|------|------|
| PDF 解析方案 | 根据实际资料选择（PyMuPDF / pdfplumber / LLM API） |
| 网页抓取方案 | 待讨论 |
| 移动端技术栈 | 待讨论 |
| API 认证方案 | 待讨论 |
| lvl3 目录定义 | 用户后续提供 |

**V1+ 迭代方向：**

- Reranker 提升检索精度
- Hybrid Search（关键词 + 向量）
- 桥梁页自动章节生成
- 常见问题缓存
- 检索命中率/引用率统计
