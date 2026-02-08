# Docker Compose 集成部署设计

> 日期: 2026-02-08
> 状态: 已验证

## 概述

为 Bridge RAG System 设计 Docker Compose 集成部署方案，统一管理数据库、API、Web 三个服务。采用 Base + Override 模式，同时支持开发和生产环境。

## 设计决策

| 维度 | 选择 | 理由 |
|------|------|------|
| **环境支持** | 开发 + 生产双环境 | 一套配置，开发验证，生产部署 |
| **前端部署** | 开发用 Vite dev，生产用 nginx | 开发保留热重载，生产高性能静态托管 |
| **环境变量** | docker-compose environment + 宿主机变量 | 明确控制，通过 `${VAR}` 引用 |
| **端口暴露** | 开发全暴露，生产仅 nginx | 开发便于调试，生产安全收敛 |
| **数据持久化** | 生产持久化，开发可选清空 | 灵活性，`down -v` 可快速重置 |

## 架构设计

### 文件结构

```
RAG/
├── docker-compose.yml           # 基础配置（三个服务共同部分）
├── docker-compose.dev.yml       # 开发环境覆盖
├── docker-compose.prod.yml      # 生产环境覆盖
├── Dockerfile                   # API 服务镜像
├── Makefile                     # 简化启动命令
├── web/
│   ├── Dockerfile.dev           # Web 开发镜像（Vite dev server）
│   └── Dockerfile.prod          # Web 生产镜像（多阶段构建 + nginx）
└── nginx/
    └── nginx.conf               # 生产环境 nginx 配置
```

### 服务拓扑

**docker-compose.yml (base)** 定义三个服务：
- `db` — PostgreSQL + pgvector，端口 5432（容器内）
- `api` — FastAPI 应用，端口 8000（容器内）
- `web` — React 前端，端口因环境而异

**docker-compose.dev.yml** 覆盖：
- `web` 使用 `Dockerfile.dev`，运行 Vite dev server（端口 5173）
- 暴露端口：`3000` (web)、`8000` (api)、`5433` (db)
- 挂载源码目录实现热重载

**docker-compose.prod.yml** 覆盖：
- `web` 使用 `Dockerfile.prod`，多阶段构建 + nginx
- 仅暴露端口：`80` (nginx)
- 不挂载源码，使用镜像内的构建产物

## 服务详细设计

### 1. 数据库服务 (db)

**docker-compose.yml:**
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: bridge_rag_db
    environment:
      POSTGRES_DB: bridge_rag
      POSTGRES_USER: bridge
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bridge}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - bridge_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bridge -d bridge_rag"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:

networks:
  bridge_net:
    driver: bridge
```

**关键点：**
- 使用 `${POSTGRES_PASSWORD:-bridge}` 读取宿主机环境变量，默认值 `bridge`
- `pgdata` volume 用于持久化（开发时可用 `down -v` 清空）
- healthcheck 确保后续服务等待数据库就绪

---

### 2. API 服务 (api)

**docker-compose.yml:**
```yaml
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: bridge_rag_api
    environment:
      DATABASE_URL: postgresql+psycopg://bridge:${POSTGRES_PASSWORD:-bridge}@db:5432/bridge_rag
      ZHIPU_API_KEY: ${ZHIPU_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - bridge_net
```

**关键点：**
- `depends_on` 带 `condition: service_healthy` 确保数据库就绪后才启动
- `DATABASE_URL` 使用容器内域名 `db:5432`（不是 localhost:5433）
- `ZHIPU_API_KEY` 必须从宿主机环境变量传入

---

### 3. Web 服务 (web) — Base 部分

**docker-compose.yml:**
```yaml
  web:
    container_name: bridge_rag_web
    depends_on:
      - api
    networks:
      - bridge_net
```

**关键点：**
- Base 配置只定义共同部分，`build` 和 `ports` 留给 dev/prod 覆盖
- 所有服务在同一 `bridge_net` 网络，可通过服务名互相访问

## 开发环境特性

### docker-compose.dev.yml

```yaml
services:
  db:
    ports:
      - "5433:5432"  # 暴露数据库便于 GUI 工具连接

  api:
    ports:
      - "8000:8000"  # 暴露 API 便于直接测试
    volumes:
      - ./app:/app/app              # 挂载源码
      - ./config:/app/config
      - ./data:/app/data
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build:
      context: ./web
      dockerfile: Dockerfile.dev
    ports:
      - "3000:5173"   # Vite dev server 端口映射
    volumes:
      - ./web/src:/app/src          # 挂载源码实现热重载
      - ./web/public:/app/public
      - /app/node_modules           # 避免覆盖容器内的 node_modules
    environment:
      - VITE_API_URL=http://localhost:8000
```

### web/Dockerfile.dev

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

**开发环境关键特性：**
- **热重载：** API 用 `--reload`，Web 挂载 `src/` 目录，代码变更立即生效
- **端口全暴露：** db (5433)、api (8000)、web (3000) 都可从宿主机访问
- **源码挂载：** 无需重新构建镜像，修改代码即可看到效果
- **快速启动：** Vite dev server 秒启动，无需构建步骤

## 生产环境特性

### docker-compose.prod.yml

```yaml
services:
  db:
    restart: always
    # 不暴露端口，仅容器内访问

  api:
    restart: always
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    # 不暴露端口，仅通过 nginx 访问

  web:
    build:
      context: ./web
      dockerfile: Dockerfile.prod
      args:
        VITE_API_URL: /api  # 生产环境下 API 通过 nginx 代理
    ports:
      - "80:80"
    restart: always
```

### web/Dockerfile.prod (多阶段构建)

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### nginx/nginx.conf

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # 前端静态文件
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

**生产环境关键特性：**
- **多阶段构建：** 第一阶段构建，第二阶段仅包含 nginx + 静态文件，镜像更小
- **单一入口：** 只暴露 80 端口，所有请求通过 nginx 路由
- **反向代理：** nginx 转发 `/api` 到 `api:8000`，前端无需关心后端地址
- **生产优化：** gzip 压缩、多 worker 进程、restart 策略

## 使用方式

### 环境变量设置

启动前需要在宿主机设置环境变量：

```bash
export ZHIPU_API_KEY="your_api_key_here"
export POSTGRES_PASSWORD="bridge"  # 开发环境，可选
```

### 启动命令

```bash
# 开发环境
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# 生产环境
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Makefile 简化

```makefile
.PHONY: dev prod stop logs clean

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

stop:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

clean:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v

logs:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

使用：`make dev` / `make prod` / `make stop` / `make clean` / `make logs`

## 优势总结

1. **环境一致性** — 开发和生产使用相同的容器化环境
2. **配置清晰** — Base + Override 模式避免重复，易于维护
3. **开发体验** — 热重载、端口暴露、快速启动
4. **生产级别** — nginx 反向代理、多阶段构建、安全收敛
5. **易于扩展** — 未来可添加 test/ci 环境的 override 文件
