# V1.0.0 发布准备设计文档

日期：2026-02-05

## 背景与目标

将 Bridge RAG System 从开发版本正式发布为 V1.0.0，目标：
1. 准备生产部署
2. 方便团队成员接手
3. 为 V2 功能迭代打下干净基础

## 设计决策

### 1. 版本号与 API 路由

**版本号统一更新：**
- `pyproject.toml` → `version = "1.0.0"`
- `app/main.py` → `FastAPI(..., version="1.0.0")`

**API 路由重构：**

| 当前 | 新版 |
|------|------|
| `/health` | `/health`（保留，用于负载均衡探针） |
| `/ask` | 移除（V0 废弃） |
| `/ask/v2` | `/api/v1/ask` |
| 无 | `/api/v1/ingest`（新增） |

**目录结构变更：**
```
app/api/
├── __init__.py
├── v1/
│   ├── __init__.py
│   ├── ask.py
│   ├── ingest.py
│   └── schemas.py
```

### 2. 常量配置化（YAML）

**配置文件结构：**
```
config/
├── taxonomy.yaml       # 三级知识分类体系
└── facets.yaml         # Facet 枚举值
```

**taxonomy.yaml 结构：**
```yaml
taxonomy:
  形制与技术:
    结构体系:
      - 拱桥结构
      - 梁桥结构
      - 悬索结构
      - 斜拉结构
    构造细部:
      - 桥墩
      - 桥台
      - 栏杆
      - 桥面铺装
    # ...
  # 其他 lvl1 类似
```

**facets.yaml 结构：**
```yaml
bridge_types:
  - 石拱桥
  - 木拱桥
  - 铁桥
  # ...

materials:
  - 石
  - 木
  - 铁
  # ...

eras:
  - 先秦
  - 秦汉
  # ...

regions:
  - 华北
  - 华东
  # ...

functions:
  - 交通
  - 军事
  # ...
```

**加载机制：**
```python
# app/core/constants.py
import yaml
from pathlib import Path
from functools import lru_cache

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

@lru_cache
def load_taxonomy() -> dict[str, dict[str, list[str]]]:
    """返回 {lvl1: {lvl2: [lvl3, ...]}}"""
    with open(CONFIG_DIR / "taxonomy.yaml") as f:
        return yaml.safe_load(f)["taxonomy"]

@lru_cache
def load_facets() -> dict[str, list[str]]:
    with open(CONFIG_DIR / "facets.yaml") as f:
        return yaml.safe_load(f)
```

**清理：**
- 删除 `app/constants/facets.py`
- 删除 `scripts/ingest.py` 中的 `TAXONOMY_LVL2` 硬编码
- 更新引用这些常量的代码

### 3. 入库格式统一（Markdown）

**Markdown 入库格式规范：**
```markdown
---
bridge: 赵州桥
source_type: document
title: 赵州桥研究资料
---

# 结构特点

赵州桥是一座敞肩式石拱桥，主拱由28道拱券并列砌成...

## 主拱设计

跨度37.02米，矢高7.23米，矢跨比约1:5...

# 历史背景

建于隋代大业年间（公元605-616年），由工匠李春设计建造...
```

**解析逻辑：**
1. 提取 front matter → 获取 `bridge`、`source_type`、`title`
2. 按标题（`#`、`##`）分割章节
3. 每个章节内容送入 chunker 进一步切块
4. `section_title` = 最近的标题层级拼接（如 `结构特点 > 主拱设计`）

**新增模块：**
- `app/services/markdown_parser.py`

**API 入库端点：**
```
POST /api/v1/ingest
Content-Type: text/markdown

---
bridge: 赵州桥
...
---

# 内容...
```

### 4. 测试数据集

**规模：**
- 12 座虚构桥梁（覆盖所有桥型、材料、年代、区域）
- 约 120 个 chunks（平均每桥 10 个）
- 完整 taxonomy 节点（约 40-50 个三级分类）
- 配套提问示例（约 20 个问题，覆盖各种查询场景）

**数据文件结构：**
```
data/seed/
├── bridges.yaml         # 12 座桥的档案
├── taxonomy.yaml        # 完整三级分类节点
├── documents/           # 入库文档（Markdown 格式）
│   ├── 云渡桥.md
│   ├── 青石关桥.md
│   └── ...
└── questions.yaml       # 测试问题集
```

**bridges.yaml 示例：**
```yaml
bridges:
  - name: 云渡桥
    aliases: 云桥
    location: 云南省大理市 西南
    era: 明清
    bridge_type: 石拱桥
    material: 石
    function: 交通
    summary: 横跨苍山溪流的三孔石拱桥，以云雾缭绕著称

  - name: 铁索寒桥
    aliases: 寒江桥
    location: 四川省甘孜州 西南
    era: 近现代
    bridge_type: 索桥
    material: 铁
    function: 交通
    summary: 高原峡谷铁索桥，冬季常有冰凌
```

**questions.yaml 示例：**
```yaml
questions:
  # Anchor 查询（指定桥梁）
  - question: 云渡桥的结构特点是什么？
    target_bridge: 云渡桥
    expected_channel: anchor

  # Concept 查询（通用知识）
  - question: 石拱桥的主拱是如何建造的？
    expected_channel: concept

  # Analogy 查询（类比）
  - question: 有没有和云渡桥结构类似的桥？
    target_bridge: 云渡桥
    expected_channel: analogy

  # Facet 过滤
  - question: 明清时期的木桥有哪些？
    expected_facets:
      era: 明清
      material: 木
```

### 5. 代码清理

**需要排查的潜在废弃代码：**

| 文件 | 待确认内容 |
|------|-----------|
| `app/api/ask.py` | V0 端点 `/ask` 及相关函数 `ask()` |
| `app/services/retriever.py` | V0 检索器 `Retriever`，检查是否仍被引用 |
| `app/api/schemas.py` | V0 相关 schema（如 `AskResponse` vs `AskResponseV2`） |
| `app/constants/` | 整个目录迁移到 YAML 后删除 |

**实施时的审计步骤：**
1. 用 grep 检查每个待删模块的引用
2. 确认测试文件中的引用（测试也要同步更新或删除）
3. 检查 `lvl3` 是否在所有流程中正确传递（而非被忽略）

### 6. 数据库处理

**策略：清空重建**

提供 `scripts/reset_db.py` 脚本，清空所有表并重建 schema。

理由：
- 测试数据会完全替换
- 避免脏数据干扰
- V1.0.0 是正式版本，干净起步

### 7. 文档体系

**文档目录结构：**
```
docs/
├── README.md              # 项目总览
├── getting-started.md     # 快速开始指南
├── api/
│   └── v1.md              # API 参考文档
├── architecture.md        # 系统架构设计
├── deployment.md          # 部署指南
├── development.md         # 开发者指南
├── ingest-guide.md        # 入库指南
└── plans/                 # 设计文档
```

**各文档内容概要：**

| 文档 | 主要内容 |
|------|---------|
| README.md | 项目介绍、特性列表、快速安装、基本用法、链接到其他文档 |
| getting-started.md | 环境准备、依赖安装、数据库启动、seed 数据、第一次调用 API |
| api/v1.md | 每个端点详细说明：URL、Method、请求体、响应体、示例、错误码 |
| architecture.md | 系统设计图、数据流、模块职责、关键抽象 |
| deployment.md | Docker Compose 生产配置、环境变量说明、PostgreSQL 配置、反向代理示例 |
| development.md | 本地开发流程、代码结构、测试方法、提交规范、常见问题 |
| ingest-guide.md | 入库格式规范、章节结构建议、元数据标注、桥梁关联、批量入库、示例文档 |

## 文件变更清单

### 新增

```
config/
├── taxonomy.yaml
└── facets.yaml

app/api/v1/
├── __init__.py
├── ask.py
├── ingest.py
└── schemas.py

app/services/markdown_parser.py
app/core/constants.py
scripts/reset_db.py

data/seed/
├── bridges.yaml
├── taxonomy.yaml
├── documents/*.md (12个)
└── questions.yaml

docs/
├── README.md
├── getting-started.md
├── api/v1.md
├── architecture.md
├── deployment.md
├── development.md
└── ingest-guide.md
```

### 删除

```
app/constants/  (整个目录)
app/api/ask.py  (迁移后删除)
app/api/schemas.py  (迁移后删除)
app/services/retriever.py  (如确认无引用)
```

### 修改

```
pyproject.toml  (版本号)
app/main.py  (版本号 + 路由)
CLAUDE.md  (已更新)
```

## 依赖变更

新增依赖：
- `pyyaml>=6.0` — YAML 配置文件解析

## 实施顺序建议

1. 常量配置化（config/ + app/core/constants.py）
2. API 路由重构（app/api/v1/）
3. Markdown 解析器（app/services/markdown_parser.py）
4. 代码清理（删除废弃代码）
5. 数据库重建脚本（scripts/reset_db.py）
6. 测试数据集（data/seed/）
7. 文档完善（docs/）
8. 版本号更新 + 最终测试
