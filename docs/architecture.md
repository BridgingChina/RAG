# 系统架构

## 概述

Bridge RAG System 是一个面向桥梁知识的检索增强生成系统，采用三通道混合检索策略，支持精准问答和类比分析。

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                                │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/v1/ask │  │/api/v1/ingest│  │     /health        │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
└─────────┼────────────────┼──────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Services Layer                            │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ HybridRetriever│  │ MarkdownParser │  │   Generator    │  │
│  │  - Anchor      │  │ (parse_markdown)│ │ (generate_v2)  │  │
│  │  - Concept     │  │                │  │               │  │
│  │  - Analogy     │  │                │  │               │  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                   │                   │           │
│  ┌───────┴────────┐  ┌───────┴────────┐  ┌──────┴────────┐  │
│  │ FacetExtractor │  │    Chunker     │  │    Tagger      │  │
│  │ (extract)      │  │(SemanticChunker)│ │(MetadataTagger)│  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                   │                   │           │
│  ┌───────┴────────┐  ┌───────┴────────┐  ┌──────┴────────┐  │
│  │   Tokenizer    │  │ContextEnricher │  │    Ranker      │  │
│  │(jieba + userdict)││ (enrich)       │  │ (RRF + diversity)││
│  └────────────────┘  └────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Provider Layer                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   ZhipuProvider                          ││
│  │  - embed(): 2048-dim vectors (embedding-3)              ││
│  │  - chat(): GLM-4 generation                             ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              PostgreSQL + pgvector                       ││
│  │  - chunks: content, embedding, tsv, taxonomy            ││
│  │  - bridges: metadata, facets                            ││
│  │  - sources: type, title                                 ││
│  │  - taxonomy_nodes: lvl1/lvl2/lvl3                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 核心模块

### 检索层

| 模块 | 职责 |
|------|------|
| HybridRetriever | 三通道混合检索：Anchor + Concept + Analogy |
| FacetExtractor | 从问题提取结构化维度（桥型、材料、年代等） |
| Ranker | RRF 融合排序 + 多样性约束 |
| Tokenizer | jieba 分词 + 自定义词典 |

### 入库层

| 模块 | 职责 |
|------|------|
| MarkdownParser | 解析 Markdown + YAML front matter |
| Chunker | 语义切块（基于 embedding 相似度） |
| ContextEnricher | 为 chunk 生成上下文描述 |
| Tagger | LLM 自动标注 taxonomy |

### 生成层

| 模块 | 职责 |
|------|------|
| Generator | 基于证据生成回答，输出置信度 |

## 数据流

### 问答流程

```
Question → Facet提取 → 三通道检索 → LLM生成 → Response
              ↓              ↓
         bridge_type    Anchor: 本桥 (6条)
         material       Concept: 通用 (2条)
         era            Analogy: 类比 (2条)
         region
         function
```

### 入库流程

```
Markdown → Parse → Chunk → Enrich → Tag → Embed → Store
   ↓         ↓       ↓        ↓       ↓      ↓       ↓
 YAML    Sections  200-500  Context  lvl1  2048d   chunks
 front              chars   text    lvl2   vec    table
 matter                             lvl3
```

## 配置

- `config/taxonomy.yaml` - 三级知识分类体系
- `config/facets.yaml` - Facet 枚举值

## 技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步支持、自动 OpenAPI |
| 数据库 | PostgreSQL | 成熟稳定、pgvector 扩展 |
| 向量索引 | pgvector | 原生集成、无需额外服务 |
| LLM | 智谱 GLM-4 | 中文能力强、API 稳定 |
| Embedding | 智谱 embedding-3 | 2048 维、中文优化 |

