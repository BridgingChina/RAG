# 入库指南

本指南说明如何将桥梁知识资料导入 Bridge RAG 系统。

## 文档格式

### Markdown + YAML Front Matter

所有入库资料采用 Markdown 格式，并在文件开头使用 YAML front matter 声明元数据：

```markdown
---
bridge: 赵州桥
source_type: document
title: 赵州桥研究资料
---

# 概述

赵州桥位于河北省赵县...

# 结构特点

## 主拱设计

采用敞肩式结构...
```

### Front Matter 字段

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `bridge` | string | 建议 | 关联的桥梁名称，用于 Anchor 检索 |
| `source_type` | string | 否 | 来源类型：`document`、`note`、`web` 等 |
| `title` | string | 否 | 文档标题，默认使用文件名（API 入库时默认 `导入资料`） |

## 章节结构

### 推荐的章节划分

按桥梁知识的逻辑结构组织章节：

```markdown
# 概述
桥梁基本介绍...

# 结构特点
## 主拱/主梁设计
## 桥墩构造
## 桥面系统

# 历史沿革
## 始建背景
## 修缮记录

# 地理环境
地形、气候、水文...

# 文化价值
历史意义、保护情况...
```

### 章节层级

- 使用 `#` 标记一级章节
- 使用 `##` 标记二级章节
- 建议不超过三级嵌套

## 入库方式

### API 入库

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "---\nbridge: 赵州桥\ntitle: 测试\n---\n\n# 概述\n\n内容...",
    "source_type": "document"
  }'
```

### 批量入库

将多个 Markdown 文件放入目录，使用脚本批量导入：

```bash
# 将文件放入 data/seed/documents/
# 运行种子脚本
python scripts/seed_test_data.py --llm
```

## 处理流程

入库时系统自动执行以下处理：

1. **解析 Front Matter** - 提取桥梁名称、标题等元数据
2. **章节分割** - 按标题级别分割文档
3. **语义切块** - 将长章节切分为 200-500 字的块（相似度阈值 0.5）
4. **上下文增强** - 为每个块生成上下文描述（80-160字）
5. **Taxonomy 标注** - 自动分类到三级知识体系（lvl1/lvl2/lvl3）
6. **向量化** - 生成 1024 维 embedding
7. **FTS 索引** - 建立全文搜索索引（tsvector）

## 最佳实践

### 内容建议

- 每个文档聚焦一座桥梁
- 章节划分清晰，便于切块
- 避免过长的连续段落
- 关键数据用数字而非文字描述

### 避免的问题

- ❌ 不要在一个文档中混合多座桥梁的信息
- ❌ 不要使用纯图片内容（OCR 暂不支持）
- ❌ 不建议省略 front matter 中的 `bridge` 字段（会影响 Anchor 检索）
- ❌ 不要使用过深的章节嵌套

## 示例文档

完整示例见 `data/seed/documents/` 目录。

