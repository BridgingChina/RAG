# Bridge RAG System

桥梁知识检索增强生成系统 v1.0.0

## 特性

- **三通道混合检索** - Anchor（本桥）+ Concept（通用）+ Analogy（类比）
- **上下文增强索引** - 自动生成 chunk 上下文描述
- **Facet 智能过滤** - 按桥型、材料、年代、区域、功能过滤
- **置信度评估** - 基于证据来源评估回答可信度
- **Markdown 入库** - 支持 YAML front matter 的标准化格式

## 快速开始

```bash
# 启动数据库
docker compose up -d db

# 安装依赖
pip install -e ".[dev]"

# 初始化数据
python scripts/reset_db.py --force --seed

# 启动服务
uvicorn app.main:app --reload
```

详见 [快速开始指南](getting-started.md)

## API

| 端点 | 描述 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/v1/ask` | 问答 |
| `POST /api/v1/ingest` | 入库 |

详见 [API 文档](api/v1.md)

## 文档

- [快速开始](getting-started.md)
- [API 参考](api/v1.md)
- [入库指南](ingest-guide.md)
- [系统架构](architecture.md)

## 开发

```bash
# 运行测试
pytest tests/ -v

# 重置数据库
python scripts/reset_db.py --force --seed
```

## 技术栈

- Python 3.11+ / FastAPI
- PostgreSQL + pgvector
- 智谱 AI (embedding-3 + GLM-4)

## License

MIT

