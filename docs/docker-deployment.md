# Docker 部署指南

本指南详细说明如何使用 Docker Compose 部署 Bridge RAG System。

## 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 已获取智谱 API Key

## 快速开始

### 1. 设置环境变量

```bash
# 必需
export ZHIPU_API_KEY="your_api_key_here"

# 可选（生产环境建议修改）
export POSTGRES_PASSWORD="bridge"
export WEB_PORT="80"  # 生产环境 Web 服务外部端口，默认 80
```

### 2. 启动服务

**开发环境：**
```bash
make dev
# 或
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

访问：
- Web UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Database: localhost:5433

**生产环境：**
```bash
make prod
# 或
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

访问：
- Web UI + API: http://localhost:80

### 3. 验证部署

```bash
# 查看服务状态
docker compose ps

# 查看日志
make logs
# 或
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

## 详细说明

### 环境变量配置

#### 方式一：直接导出（推荐用于开发）

```bash
export ZHIPU_API_KEY="your_api_key_here"
export POSTGRES_PASSWORD="bridge"
export WEB_PORT="80"  # 可选，自定义生产环境 Web 端口
```

#### 方式二：使用 .env 文件

创建项目根目录的 `.env` 文件：
```bash
ZHIPU_API_KEY=your_api_key_here
POSTGRES_PASSWORD=bridge
WEB_PORT=80  # 可选，自定义生产环境 Web 端口
```

然后加载：
```bash
source .env
# 或
export $(cat .env | xargs)
```

**注意：** `.env` 文件应添加到 `.gitignore`，避免泄露敏感信息。

#### 生产环境安全建议

- 使用强密码替换默认的 `POSTGRES_PASSWORD=bridge`
- 考虑使用 Docker Secrets 或外部密钥管理服务
- 定期轮换 API Key 和数据库密码

### 开发环境使用

#### 启动服务

```bash
make dev
```

等价于：
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

后台运行：
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

#### 热重载

开发环境已配置热重载：
- **API**: 修改 `app/` 下的 Python 文件会自动重启 uvicorn
- **Web**: 修改 `web/src/` 下的 React 文件会自动刷新浏览器

#### 访问服务

| 服务 | 地址 | 说明 |
|------|------|------|
| Web UI | http://localhost:3000 | Vite dev server |
| API | http://localhost:8000 | FastAPI 直接访问 |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Database | localhost:5433 | PostgreSQL + pgvector |

#### 数据库连接

使用 psql 命令行：
```bash
psql -h localhost -p 5433 -U bridge -d bridge_rag
# 密码: bridge (或你设置的 POSTGRES_PASSWORD)
```

使用 GUI 工具（如 DBeaver、pgAdmin）：
- Host: localhost
- Port: 5433
- Database: bridge_rag
- User: bridge
- Password: bridge

### 生产环境使用

#### 启动服务

```bash
make prod
```

等价于：
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

#### 访问服务

生产环境仅暴露一个端口：
- **Web UI + API**: http://localhost:80
- API 通过 `/api` 路径访问（nginx 反向代理）

#### nginx 配置

生产环境使用 nginx 作为：
1. **静态文件服务器** — 托管 React 构建产物
2. **反向代理** — 将 `/api` 请求转发到 API 服务
3. **性能优化** — gzip 压缩、缓存控制

nginx 配置文件位于 `nginx/nginx.conf`。

## 常用操作

### 查看日志

```bash
# 查看所有服务日志
make logs

# 查看特定服务日志
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f web
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f db
```

### 重启服务

```bash
# 重启所有服务
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart

# 重启特定服务
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart api
```

### 停止服务

```bash
make stop
# 或
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

### 清空数据

**警告：** 此操作会删除所有数据库数据，无法恢复！

```bash
make clean
# 或
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
```

### 重新构建镜像

代码或依赖变更后，需要重新构建镜像：

```bash
# 重新构建所有服务
docker compose -f docker-compose.yml -f docker-compose.dev.yml build

# 重新构建特定服务
docker compose -f docker-compose.yml -f docker-compose.dev.yml build api

# 强制重新构建（不使用缓存）
docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache
```

### 进入容器调试

```bash
# 进入 API 容器
docker exec -it bridge_rag_api bash

# 进入数据库容器
docker exec -it bridge_rag_db bash

# 直接连接数据库
docker exec -it bridge_rag_db psql -U bridge -d bridge_rag
```

### 查看容器状态

```bash
# 查看运行中的容器
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

# 查看容器资源占用
docker stats bridge_rag_api bridge_rag_web bridge_rag_db
```

## 故障排查

### 问题 1: 服务启动失败

**症状：** 容器反复重启或退出

**排查步骤：**
1. 查看日志找出错误信息
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml logs api
   ```

2. 常见原因：
   - 环境变量未设置（`ZHIPU_API_KEY`）
   - 端口被占用（5433, 8000, 3000）
   - 依赖服务未就绪（数据库未启动）

### 问题 2: 数据库连接失败

**症状：** API 日志显示 `connection refused` 或 `database does not exist`

**解决方案：**
1. 确认数据库容器运行中
   ```bash
   docker ps | grep bridge_rag_db
   ```

2. 检查数据库健康状态
   ```bash
   docker inspect bridge_rag_db | grep -A 5 Health
   ```

3. 手动测试连接
   ```bash
   docker exec -it bridge_rag_db pg_isready -U bridge -d bridge_rag
   ```

4. 如果数据库损坏，重置：
   ```bash
   make clean
   make dev
   ```

### 问题 3: Web 热重载不工作

**症状：** 修改代码后浏览器不自动刷新

**解决方案：**
1. 确认 volume 挂载正确
   ```bash
   docker inspect bridge_rag_web | grep -A 10 Mounts
   ```

2. 检查 Vite 配置中的 `--host 0.0.0.0`

3. 某些操作系统（如 Windows）可能需要 polling：
   ```dockerfile
   # web/Dockerfile.dev
   CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--force"]
   ```

### 问题 4: nginx 502 Bad Gateway

**症状：** 生产环境访问 `/api` 返回 502

**排查步骤：**
1. 确认 API 容器运行中
   ```bash
   docker ps | grep bridge_rag_api
   ```

2. 检查容器间网络连通性
   ```bash
   docker exec -it bridge_rag_web ping api
   ```

3. 查看 nginx 日志
   ```bash
   docker logs bridge_rag_web
   ```

### 问题 5: 端口冲突

**症状：** `Error: bind: address already in use`

**解决方案：**
1. 查找占用端口的进程
   ```bash
   # macOS/Linux
   lsof -i :5433
   lsof -i :8000
   lsof -i :3000

   # 或使用 netstat
   netstat -tuln | grep 5433
   ```

2. 停止占用端口的进程，或修改 docker-compose 中的端口映射

## 最佳实践

### 开发环境

1. **使用 Makefile** — `make dev` / `make stop` / `make logs` 简化命令
2. **定期清理** — `docker system prune` 清理未使用的镜像和容器
3. **保留数据卷** — 避免频繁 `down -v`，开发数据很宝贵
4. **监控日志** — 后台运行时用 `make logs` 监控异常

### 生产环境

1. **使用强密码** — 修改 `POSTGRES_PASSWORD` 默认值
2. **配置 HTTPS** — 在 nginx 前加 Caddy 或使用 Let's Encrypt
3. **资源限制** — 在 docker-compose 中设置 `mem_limit` 和 `cpus`
4. **监控告警** — 集成 Prometheus + Grafana 或其他 APM
5. **备份数据** — 定期备份 `pgdata` volume
   ```bash
   docker exec bridge_rag_db pg_dump -U bridge bridge_rag > backup.sql
   ```

### 性能优化

1. **镜像缓存** — 合理利用 Docker layer cache
2. **多阶段构建** — 生产镜像仅包含运行时必需文件
3. **并行构建** — `docker compose build --parallel`
4. **清理构建缓存** — `docker builder prune` 释放空间

## Makefile 参考

项目根目录的 `Makefile` 提供了便捷命令：

| 命令 | 说明 |
|------|------|
| `make dev` | 启动开发环境（前台运行） |
| `make prod` | 启动生产环境（后台运行） |
| `make stop` | 停止服务 |
| `make clean` | 停止并删除数据卷 |
| `make logs` | 查看实时日志 |

## 附录

### 服务端口映射

| 环境 | 服务 | 容器端口 | 宿主机端口 | 说明 |
|------|------|----------|------------|------|
| 开发 | db | 5432 | 5433 | PostgreSQL |
| 开发 | api | 8000 | 8000 | FastAPI |
| 开发 | web | 5173 | 3000 | Vite dev server |
| 生产 | db | 5432 | - | 仅容器内访问 |
| 生产 | api | 8000 | - | 通过 nginx 代理 |
| 生产 | web | 80 | 80 | nginx |

### 相关文档

- [架构设计文档](./plans/2026-02-08-docker-deployment-design.md) — 完整的架构设计和决策过程
- [入库指南](./ingest-guide.md) — 如何导入桥梁知识数据
- [架构文档](./architecture.md) — 系统整体架构说明
