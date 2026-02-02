# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bridge RAG System — 桥梁知识检索增强生成系统。云端 RAG 服务，支持带引用的问答。

## Commands

```bash
# Start database
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
```

## Architecture

**Tech Stack:** Python + FastAPI, PostgreSQL + pgvector, 智谱 API (embedding + GLM-4)

**Core Flow:**
```
入库: 资料 → 语义切块 → LLM标注metadata → embedding → PostgreSQL
问答: 问题 → metadata过滤 → 向量检索 → LLM生成(带引用)
```

**Key Abstractions:**

- `app/providers/` — LLM Provider 抽象层，封装智谱 API，便于替换模型
- `app/services/chunker.py` — 语义切块，按 embedding 相似度判断断点
- `app/services/tagger.py` — LLM 自动标注 lvl1/lvl2/bridge_id
- `app/services/retriever.py` — 向量检索 + metadata 过滤
- `app/services/generator.py` — 基于证据生成回答，输出引用

**Data Model:**

- `chunks` — 核心检索单元，带 1024 维向量、taxonomy 标签（lvl1/lvl2/lvl3）、bridge_id
- `bridges` — 桥梁档案
- `taxonomy_nodes` — 三级目录结构
- `sources` — 来源元信息（PDF/网页/笔记）

## Domain Context

知识体系采用三级目录：
- lvl1（四大主线）：形制与技术 / 地域与环境 / 功能与社会 / 历史与演变
- lvl2：主题桶（结构体系、构造细部、水文地形等）
- lvl3：具体知识点（V0 暂留空）

Chunk 可同时挂目录标签和 bridge_id，支持按知识点或按具体桥梁检索。

## Worktrees

项目使用 `.worktrees/` 存放 git worktrees，已在 .gitignore 中忽略。
