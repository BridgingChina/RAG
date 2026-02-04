# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bridge RAG System v1.0.0 — 桥梁知识检索增强生成系统。云端 RAG 服务，支持带引用的问答。

基于上下文增强索引 + FTS 全文检索 + 三通道混合检索（Anchor 本桥 / Concept 通用 / Analogy 类比）。

## Commands

```bash
# Start database (PostgreSQL + pgvector on port 5433)
docker compose up -d db

# Install dependencies
pip install -e ".[dev]"

# Run server
uvicorn app.main:app --reload

# Run all tests
pytest tests/ -v

# Run single test file
pytest tests/test_chunker.py -v

# Run single test
pytest tests/test_chunker.py::test_chunk_simple_text -v

# Seed test data
python scripts/seed_test_data.py

# Reset database (drop all tables and recreate)
python scripts/reset_db.py
```

## Architecture

**Tech Stack:** Python 3.11+ + FastAPI, PostgreSQL + pgvector, 智谱 API (embedding-3 + GLM-4)

**Core Flow:**
```
入库: Markdown资料 → 解析 → 切块 → 上下文增强(ContextEnricher) → 标注 → 组装search_text → jieba分词 → embedding+tsv → PostgreSQL
问答: 问题 → 向量化 + Facet抽取 → 三通道召回(Anchor/Concept/Analogy) → RRF融合 → LLM生成(带confidence)
```

**Key Abstractions:**

- `app/providers/` — LLM Provider 抽象层，`embed()` 返回 2048 维向量（智谱 embedding-3）
- `app/services/markdown_parser.py` — Markdown 解析，提取 front matter 和章节结构
- `app/services/chunker.py` — 语义切块，按 embedding 相似度判断断点
- `app/services/tagger.py` — LLM 自动标注 lvl1/lvl2/lvl3/bridge_id
- `app/services/context_enricher.py` — 为 chunk 生成上下文描述（80-160字），包含来源、主题、指代消歧
- `app/services/tokenizer.py` — jieba 中文分词，支持自定义词典
- `app/services/facet_extractor.py` — 从问题抽取结构化维度（bridge_type/material/era/region/function），带枚举约束
- `app/services/hybrid_retriever.py` — 三通道检索：Anchor(本桥) + Concept(通用) + Analogy(相似桥)，RRF 融合
- `app/services/ranker.py` — RRF (Reciprocal Rank Fusion) 算法，支持多样性约束
- `app/services/generator.py` — 基于证据生成回答，输出引用和置信度

**Configuration:**

- `config/taxonomy.yaml` — 三级知识分类体系
- `config/facets.yaml` — Facet 枚举值（桥型、材料、年代、区域、功能）

**Data Model:**

- `chunks` — 核心检索单元，2048 维向量、taxonomy 标签（lvl1/lvl2/lvl3）、`contextual_text`/`search_text`/`tsv`
- `bridges` — 桥梁档案（bridge_type/material/era/location/function）
- `taxonomy_nodes` — 三级目录结构
- `sources` — 来源元信息

**API Endpoints:**

- `GET /health` — Health check
- `POST /api/v1/ask` — 问答端点，三通道混合检索，返回 `confidence` 和 `evidence_groups`
- `POST /api/v1/ingest` — 入库端点，接受 Markdown 格式文档

## Domain Context

知识体系采用三级目录：
- lvl1（四大主线）：形制与技术 / 地域与环境 / 功能与社会 / 历史与演变
- lvl2（主题桶）：结构体系、构造细部、水文地形等
- lvl3（具体知识点）：拱桥结构、桥墩设计、河流特征等

Chunk 可同时挂目录标签和 bridge_id，支持按知识点或按具体桥梁检索。

**三通道检索配额：** Anchor 6 条（本桥） + Concept 2 条（通用） + Analogy 2 条（类比） = 10 条

## Ingest Format

入库资料采用 Markdown 格式，支持 YAML front matter：

```markdown
---
bridge: 桥梁名称
source_type: document
title: 资料标题
---

# 章节标题

正文内容...
```

## Worktrees

项目使用 `.worktrees/` 存放 git worktrees，已在 .gitignore 中忽略。
