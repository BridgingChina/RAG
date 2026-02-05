# 快速开始

本指南帮助你在本地环境快速运行 Bridge RAG 系统。

## 环境要求

- Python 3.11+
- Docker & Docker Compose
- 智谱 AI API Key（用于 embedding 和生成）

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/bridge-rag.git
cd bridge-rag
```

### 2. 启动数据库

```bash
docker compose up -d db
```

这会启动 PostgreSQL + pgvector，端口 5433。

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 ZHIPU_API_KEY
```

### 4. 安装依赖

```bash
pip install -e ".[dev]"
```

### 5. 初始化数据库

```bash
python scripts/reset_db.py --force --seed
```

### 6. 启动服务

```bash
uvicorn app.main:app --reload
```

服务运行在 http://localhost:8000

## 验证安装

### 健康检查

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 测试问答

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "石拱桥的结构特点是什么？"}'
```

## 下一步

- [API 文档](api/v1.md) - 了解完整 API
- [入库指南](ingest-guide.md) - 导入自己的数据
- [架构文档](architecture.md) - 理解系统设计

