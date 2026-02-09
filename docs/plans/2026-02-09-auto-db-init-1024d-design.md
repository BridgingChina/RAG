# 自动数据库初始化 + 1024维向量支持设计

**日期：** 2026-02-09
**状态：** 已批准

## 背景

### 问题

1. **pgvector 维度限制**：IVFFLAT 和 HNSW 索引最多支持 2000 维，但智谱 embedding-3 默认产生 2048 维向量，导致索引创建失败
2. **数据库未初始化**：开发环境首次启动时数据库为空，入库功能报错 `relation "sources" does not exist`
3. **手动初始化繁琐**：需要手动运行 `scripts/reset_db.py`，容易遗忘

### 目标

- 支持 1024 维向量（智谱 API 可配置维度）
- 应用启动时自动检测并初始化数据库
- 使用 schema 版本管理支持未来迁移
- 开发和生产环境统一初始化逻辑

## 架构设计

### 核心变更

```
应用启动 → lifespan 钩子 → 检查 schema_version
    ├─ 不存在/版本过旧 → 运行初始化/迁移 → 创建表 + 插入版本记录
    └─ 版本匹配 → 跳过初始化 → 正常启动

入库流程 → embed(text, dimensions=1024) → 1024维向量 → 存入 Vector(1024) 列
```

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 向量维度 | 1024 | 在 pgvector 限制内，保留足够语义信息 |
| 版本管理 | schema_version 表 | 支持未来增量迁移，而非简单的表存在检查 |
| 初始化时机 | FastAPI lifespan | 所有启动路径（dev/prod/test）统一执行 |
| 失败策略 | 阻止启动 | 避免带着损坏的数据库状态运行 |

## 详细设计

### 1. Embedding 维度变更

#### 1.1 Provider 层修改

**文件：** `app/providers/zhipu.py`

```python
def embed(self, text: str) -> list[float]:
    response = self.client.embeddings.create(
        model="embedding-3",
        input=text,
        dimensions=1024,  # 新增：指定 1024 维输出
    )
    return response.data[0].embedding
```

**验证：** 返回向量长度为 1024

#### 1.2 数据库 Model 修改

**文件：** `app/models/chunk.py`

```python
# 修改 embedding 列定义
embedding: Mapped[Vector] = mapped_column(Vector(1024))  # 从 2048 改为 1024

# 恢复 IVFFLAT 索引（之前被注释掉）
__table_args__ = (
    # ... 其他索引 ...
    Index(
        "ix_chunks_embedding_ivfflat",
        "embedding",
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    ),
)
```

**验证：** 索引创建成功，不再报 `column cannot have more than 2000 dimensions` 错误

### 2. Schema 版本管理系统

#### 2.1 新增 Model

**文件：** `app/models/schema_version.py`

```python
"""Database schema version tracking."""
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class SchemaVersion(Base):
    """Tracks applied database schema versions."""

    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(default=func.now())
    description: Mapped[str] = mapped_column()
```

**更新：** `app/models/__init__.py` 添加导入

```python
from app.models.schema_version import SchemaVersion
```

#### 2.2 版本号规则

- **版本 1**：当前 schema（初始版本）
- **未来版本**：递增（2, 3, ...），对应增量迁移

### 3. 自动初始化逻辑

#### 3.1 核心函数

**文件：** `app/core/database.py`

```python
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
import logging

logger = logging.getLogger(__name__)

LATEST_SCHEMA_VERSION = 1  # 当前最新版本


def get_current_schema_version(engine) -> int | None:
    """Get current database schema version.

    Returns:
        Version number if schema_version table exists, None otherwise
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT MAX(version) FROM schema_version")
            )
            return result.scalar()
    except (OperationalError, ProgrammingError):
        # Table doesn't exist
        return None


def set_schema_version(engine, version: int, description: str):
    """Record a schema version."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_version (version, description) "
                "VALUES (:version, :description)"
            ),
            {"version": version, "description": description}
        )


def init_database():
    """Check and initialize database schema if needed.

    Raises:
        OperationalError: Cannot connect to database
        Exception: Schema creation failed
    """
    from app.models import Base
    from app.core.config import settings

    logger.info("Checking database initialization...")

    try:
        engine = create_engine(settings.database_url)
    except OperationalError as e:
        logger.error(f"Cannot connect to database: {e}")
        logger.error("Ensure PostgreSQL is running and credentials are correct")
        raise

    # Check current version
    current_version = get_current_schema_version(engine)

    if current_version is None:
        # First-time initialization
        logger.info("No schema found, initializing database...")

        try:
            # Create pgvector extension
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Create all tables
            Base.metadata.create_all(engine)

            # Record initial version
            set_schema_version(
                engine,
                version=1,
                description="Initial schema with 1024-dim vectors"
            )

            logger.info("Database initialized successfully (schema v1)")

        except ProgrammingError as e:
            logger.error(f"pgvector extension not available: {e}")
            logger.error("Ensure pgvector is installed in PostgreSQL")
            raise
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    elif current_version < LATEST_SCHEMA_VERSION:
        # Future: run migrations
        logger.info(f"Schema upgrade needed: v{current_version} → v{LATEST_SCHEMA_VERSION}")
        # run_migrations(engine, current_version, LATEST_SCHEMA_VERSION)
        logger.warning("Migration not implemented yet, manual intervention required")

    else:
        logger.info(f"Database schema up to date (v{current_version})")
```

#### 3.2 集成到应用启动

**文件：** `app/main.py`

```python
from contextlib import asynccontextmanager
from app.core.database import init_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""

    # Startup: Initialize database
    try:
        init_database()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise  # Prevent app from starting with broken database

    yield  # Application runs

    # Shutdown: Cleanup if needed
    logger.info("Application shutting down")


app = FastAPI(
    title="Bridge RAG",
    lifespan=lifespan,  # 添加生命周期管理
)
```

## 错误处理

### 失败场景与处理

| 场景 | 错误类型 | 处理策略 | 日志级别 |
|------|----------|----------|----------|
| 数据库连接失败 | `OperationalError` | 记录错误，阻止启动 | ERROR |
| pgvector 扩展缺失 | `ProgrammingError` | 提示安装命令，阻止启动 | ERROR |
| 表创建失败 | `Exception` | 记录详细错误，阻止启动 | ERROR |
| 版本不匹配 | N/A | 未来：运行迁移；当前：警告 | WARNING |
| 已初始化（正常） | N/A | 跳过初始化 | INFO |

### 日志示例

**首次启动（成功）：**
```
INFO: Checking database initialization...
INFO: No schema found, initializing database...
INFO: Database initialized successfully (schema v1)
INFO: Application startup complete.
```

**已初始化（跳过）：**
```
INFO: Checking database initialization...
INFO: Database schema up to date (v1)
INFO: Application startup complete.
```

**连接失败：**
```
INFO: Checking database initialization...
ERROR: Cannot connect to database: connection refused
ERROR: Ensure PostgreSQL is running and credentials are correct
ERROR: Application startup failed
```

## 测试计划

### 单元测试

**文件：** `tests/test_database_init.py`

```python
def test_get_schema_version_none():
    """Empty database returns None"""

def test_get_schema_version_exists():
    """Existing schema returns version number"""

def test_init_fresh_database():
    """First-time initialization creates all tables and version record"""

def test_init_existing_database():
    """Already initialized database skips creation"""

def test_embedding_dimension():
    """Zhipu API returns 1024-dim vectors"""
```

### 集成测试

**手动验证步骤：**

```bash
# 1. 清空数据库
docker compose down -v
docker compose up -d db

# 2. 启动 API（观察自动初始化）
uvicorn app.main:app --reload

# 预期日志：
# INFO: Checking database initialization...
# INFO: No schema found, initializing database...
# INFO: Database initialized successfully (schema v1)

# 3. 验证表结构
docker exec -it bridge_rag_db psql -U bridge -d bridge_rag -c "\dt"

# 预期输出：
# schema_version | sources | bridges | taxonomy_nodes | chunks

# 4. 验证 schema_version 记录
docker exec -it bridge_rag_db psql -U bridge -d bridge_rag -c "SELECT * FROM schema_version"

# 预期输出：
# version | applied_at | description
# 1       | 2026-02-09 | Initial schema with 1024-dim vectors

# 5. 测试入库功能
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d @data/seed/documents/长江斜拉桥.md

# 预期：成功返回，无 500 错误

# 6. 验证向量维度
docker exec -it bridge_rag_db psql -U bridge -d bridge_rag -c \
  "SELECT array_length(embedding, 1) FROM chunks LIMIT 1"

# 预期输出：1024

# 7. 重启应用（验证跳过初始化）
# Ctrl+C 停止，重新启动
uvicorn app.main:app --reload

# 预期日志：
# INFO: Checking database initialization...
# INFO: Database schema up to date (v1)
```

### 验证清单

- [ ] 首次启动自动创建所有表（包括 schema_version）
- [ ] schema_version 表包含版本 1 记录
- [ ] IVFFLAT 索引成功创建（不再报 `ProgramLimitExceeded` 错误）
- [ ] embedding 列定义为 1024 维
- [ ] 智谱 API 返回 1024 维向量
- [ ] 入库功能正常工作
- [ ] 重启应用跳过初始化（日志显示 "schema up to date"）
- [ ] 开发环境（本地 Python）初始化正常
- [ ] 生产环境（Docker）初始化正常

## 实现顺序

1. **修改 embedding 维度**
   - [ ] `app/providers/zhipu.py` 添加 `dimensions=1024`
   - [ ] `app/models/chunk.py` 改为 `Vector(1024)`
   - [ ] 恢复 IVFFLAT 索引定义

2. **添加版本管理**
   - [ ] 创建 `app/models/schema_version.py`
   - [ ] 更新 `app/models/__init__.py` 导入

3. **实现初始化逻辑**
   - [ ] 在 `app/core/database.py` 添加初始化函数
   - [ ] 在 `app/main.py` 集成 lifespan 钩子

4. **测试验证**
   - [ ] 编写单元测试
   - [ ] 手动集成测试
   - [ ] 验证开发和生产环境

5. **文档更新**
   - [ ] 更新 `CLAUDE.md` 移除手动初始化说明
   - [ ] 更新 `docs/docker-deployment.md` 说明自动初始化

## 未来改进

- **增量迁移**：实现 `run_migrations()` 支持 schema 升级
- **回滚机制**：记录每个版本的回滚脚本
- **健康检查**：添加 `/health` 端点检查数据库状态
- **性能监控**：记录初始化耗时，优化启动速度

## 参考

- 智谱 API 文档：https://open.bigmodel.cn/dev/api#embeddings（支持 512/1024/2048 维）
- pgvector 限制：https://github.com/pgvector/pgvector#ivfflat（IVFFLAT 最大 2000 维）
- SQLAlchemy 事件：https://docs.sqlalchemy.org/en/20/core/event.html
- FastAPI Lifespan：https://fastapi.tiangolo.com/advanced/events/
