# Portainer 部署指南

本指南详细说明如何在 Portainer Business Edition 2.33.6 LTS 上部署 Bridge RAG System 私有 GitHub 仓库。

## 前置要求

- Portainer BE 2.33.6 LTS 已安装并运行
- 对目标环境（Environment）有管理权限
- GitHub 账户，对本仓库有访问权限
- 已获取智谱 API Key

## 认证方式选择

Portainer 支持两种方式访问私有 GitHub 仓库：

| 方式 | 优点 | 缺点 | 推荐场景 |
|------|------|------|----------|
| **HTTPS + Personal Access Token** | 配置简单，快速上手 | Token 泄露风险较高 | 开发测试环境 |
| **SSH + 密钥对** | 更安全，密钥可轮换 | 配置稍复杂 | 生产环境 |

## 方式一：HTTPS + Personal Access Token

### 步骤 1: 创建 GitHub Personal Access Token

1. 登录 GitHub，访问 **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. 点击 **Generate new token (classic)**
3. 配置 Token：
   - **Note**: `Portainer Bridge RAG Access`
   - **Expiration**: 根据需求选择（建议 90 days）
   - **Scopes**: 勾选 `repo`（完整仓库访问权限）
4. 点击 **Generate token**
5. **重要：** 立即复制 Token（格式：`ghp_xxxxxxxxxxxx`），关闭页面后无法再查看

### 步骤 2: 在 Portainer 中部署 Stack

1. 登录 Portainer，进入目标 **Environment**
2. 导航到 **Stacks → Add stack**
3. 配置 Stack 基本信息：
   - **Name**: `bridge-rag-dev`（开发环境）或 `bridge-rag-prod`（生产环境）
   - **Build method**: 选择 **Repository**

4. 配置 Git 仓库：
   - **Repository URL**: `https://github.com/EchoBridgeCQU/RAG.git`
   - **Reference**: `refs/heads/main`（或其他分支）
   - **Authentication**: 开启（勾选）
   - **Username**: 你的 GitHub 用户名
   - **Personal Access Token**: 粘贴步骤 1 创建的 Token

5. 配置 Compose 文件路径：

   **开发环境：**
   - **Compose path**: `docker-compose.yml`
   - **Additional paths**: `docker-compose.dev.yml`

   **生产环境：**
   - **Compose path**: `docker-compose.yml`
   - **Additional paths**: `docker-compose.prod.yml`

6. 配置环境变量（Environment variables）：

   **开发环境必需：**
   ```
   ZHIPU_API_KEY=your_api_key_here
   POSTGRES_PASSWORD=bridge
   ```

   **生产环境必需：**
   ```
   ZHIPU_API_KEY=your_api_key_here
   POSTGRES_PASSWORD=your_strong_password_here
   WEB_PORT=80
   ```

7. 点击 **Deploy the stack**

### 步骤 3: 验证部署

1. 等待容器启动（通常 1-2 分钟）
2. 在 **Stacks → bridge-rag-xxx** 中查看容器状态，所有服务应为 **running**
3. 访问服务：
   - **开发环境**:
     - Web UI: `http://<host>:3000`
     - API Docs: `http://<host>:8000/docs`
   - **生产环境**:
     - Web UI + API: `http://<host>:80`

## 方式二：SSH + 密钥对

### 步骤 1: 生成 SSH 密钥对

在本地机器或 Portainer 服务器上执行：

```bash
ssh-keygen -t ed25519 -C "portainer-bridge-rag" -f ~/.ssh/portainer_bridge_rag
```

- 不设置 passphrase（直接回车），便于 Portainer 自动认证
- 生成两个文件：
  - `portainer_bridge_rag`（私钥）
  - `portainer_bridge_rag.pub`（公钥）

### 步骤 2: 添加公钥到 GitHub

1. 复制公钥内容：
   ```bash
   cat ~/.ssh/portainer_bridge_rag.pub
   ```

2. 登录 GitHub，访问 **Settings → SSH and GPG keys → New SSH key**
3. 配置：
   - **Title**: `Portainer Bridge RAG Deploy Key`
   - **Key type**: `Authentication Key`
   - **Key**: 粘贴公钥内容
4. 点击 **Add SSH key**

**或者使用 Deploy Key（推荐，权限更精细）：**

1. 进入仓库 **Settings → Deploy keys → Add deploy key**
2. 配置：
   - **Title**: `Portainer Production Deploy`
   - **Key**: 粘贴公钥内容
   - **Allow write access**: 不勾选（只读权限即可）
3. 点击 **Add key**

### 步骤 3: 在 Portainer 中部署 Stack

1. 登录 Portainer，进入目标 **Environment**
2. 导航到 **Stacks → Add stack**
3. 配置 Stack 基本信息：
   - **Name**: `bridge-rag-prod`
   - **Build method**: 选择 **Repository**

4. 配置 Git 仓库：
   - **Repository URL**: `git@github.com:EchoBridgeCQU/RAG.git`（注意使用 SSH 格式）
   - **Reference**: `refs/heads/main`
   - **Authentication**: 开启（勾选）
   - **Username**: `git`（SSH 固定使用此用户名）
   - **SSH Key**: 粘贴私钥内容（`cat ~/.ssh/portainer_bridge_rag`）

5. 配置 Compose 文件路径和环境变量（同方式一）

6. 点击 **Deploy the stack**

## 自动更新配置

### 启用 Git Pull

在 Stack 详情页面：

1. 进入 **Stack details → Editor**
2. 开启 **Enable GitOps updates**
3. 配置：
   - **Mechanism**: `Poll` 或 `Webhook`
   - **Polling interval**: `5m`（Poll 模式下生效）
   - **Webhook**: 复制 Webhook URL（Webhook 模式下）
4. 点击 **Update the stack**

### 配置 GitHub Webhook（推荐）

1. 复制 Portainer 生成的 Webhook URL
2. 进入 GitHub 仓库 **Settings → Webhooks → Add webhook**
3. 配置：
   - **Payload URL**: 粘贴 Webhook URL
   - **Content type**: `application/json`
   - **Which events**: `Just the push event`
4. 点击 **Add webhook**

**效果：** 每次 push 到 main 分支，Portainer 自动拉取最新代码并重新部署。

## 网络配置

### 端口映射

Portainer 会自动应用 Compose 文件中的端口映射：

| 环境 | 容器 | 宿主机端口 | 说明 |
|------|------|------------|------|
| 开发 | db | 5433 | PostgreSQL |
| 开发 | api | 8000 | FastAPI |
| 开发 | web | 3000 | Vite dev server |
| 生产 | web | 80（可自定义 WEB_PORT） | nginx + API 反向代理 |

### 自定义生产端口

如果宿主机 80 端口被占用，设置 `WEB_PORT` 环境变量：

```
WEB_PORT=8080
```

访问时使用 `http://<host>:8080`。

### 防火墙配置

确保宿主机防火墙允许对应端口：

```bash
# Ubuntu/Debian
sudo ufw allow 3000/tcp  # 开发环境 Web
sudo ufw allow 8000/tcp  # 开发环境 API
sudo ufw allow 80/tcp    # 生产环境

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --reload
```

## 数据持久化

### Volume 管理

Portainer 会自动创建 Docker volume 用于数据持久化：

- `bridge_rag_pgdata` — PostgreSQL 数据文件

**查看 Volume：**

1. 进入 **Volumes**
2. 找到 `bridge-rag-xxx_pgdata`（Stack 名称前缀）
3. 可查看大小、挂载点等信息

### 数据备份

**备份数据库：**

1. 进入 **Containers → bridge_rag_db → Console**
2. 选择 **Command**: `/bin/bash`，点击 **Connect**
3. 执行备份：
   ```bash
   pg_dump -U bridge bridge_rag > /tmp/backup.sql
   ```
4. 退出容器，在宿主机复制备份文件：
   ```bash
   docker cp bridge_rag_db:/tmp/backup.sql ./backup-$(date +%Y%m%d).sql
   ```

**定期备份（推荐）：**

在宿主机配置 cron 任务：

```bash
# 每天凌晨 2 点备份
0 2 * * * docker exec bridge_rag_db pg_dump -U bridge bridge_rag | gzip > /backup/bridge-rag-$(date +\%Y\%m\%d).sql.gz
```

## 日志查看

### Portainer Web UI

1. 进入 **Stacks → bridge-rag-xxx**
2. 点击具体容器（如 `bridge_rag_api`）
3. 选择 **Logs** 标签
4. 可实时查看日志（**Auto-refresh logs** 勾选）

### CLI 方式

```bash
# 查看所有容器日志
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# 查看特定容器日志
docker logs -f bridge_rag_api
docker logs -f bridge_rag_db --tail 100
```

## 故障排查

### 问题 1: Stack 部署失败 - 认证错误

**症状：**
```
fatal: Authentication failed for 'https://github.com/EchoBridgeCQU/RAG.git/'
```

**解决方案：**

1. **HTTPS 方式：**
   - 确认 Personal Access Token 未过期
   - 确认 Token 拥有 `repo` 权限
   - 确认 Username 是 GitHub 用户名（不是邮箱）

2. **SSH 方式：**
   - 确认公钥已添加到 GitHub
   - 确认私钥格式正确（包含 `-----BEGIN OPENSSH PRIVATE KEY-----` 头尾）
   - 确认 Repository URL 使用 `git@github.com:` 格式

### 问题 2: 容器启动失败 - 环境变量缺失

**症状：**
```
app.core.config.SettingsError: ZHIPU_API_KEY is required
```

**解决方案：**

1. 在 Stack 详情页面点击 **Editor**
2. 检查 **Environment variables** 是否正确设置
3. 确认 `ZHIPU_API_KEY` 已填写
4. 点击 **Update the stack**

### 问题 3: 无法访问服务 - 端口冲突

**症状：** 容器日志显示 `address already in use`

**解决方案：**

1. 检查宿主机端口占用：
   ```bash
   sudo netstat -tuln | grep ':80'
   sudo netstat -tuln | grep ':8000'
   ```

2. 如果端口被占用：
   - **临时方案：** 停止占用进程
   - **永久方案：** 修改 Stack 环境变量 `WEB_PORT=8080`

### 问题 4: GitOps 自动更新不工作

**症状：** Push 代码后 Stack 未自动更新

**排查步骤：**

1. **Poll 模式：**
   - 确认 **Enable GitOps updates** 已开启
   - 检查 **Polling interval** 设置（最小 5 分钟）
   - 手动测试：点击 **Pull and redeploy**

2. **Webhook 模式：**
   - 在 GitHub 仓库 **Settings → Webhooks** 检查 Delivery 状态
   - 确认 Portainer Webhook URL 可从公网访问
   - 检查 Portainer 日志是否收到 Webhook 请求

### 问题 5: 数据库连接失败

**症状：** API 容器日志显示 `connection refused`

**解决方案：**

1. 确认数据库容器运行中：
   ```bash
   docker ps | grep bridge_rag_db
   ```

2. 检查健康状态：
   - 在 Portainer **Containers** 中查看 `bridge_rag_db` 状态
   - 应显示 **healthy**

3. 手动测试连接：
   ```bash
   docker exec -it bridge_rag_db pg_isready -U bridge -d bridge_rag
   ```

4. 如果数据库损坏，重置 Volume：
   - 在 Portainer 停止并删除 Stack
   - 删除对应的 Volume（**Volumes** 页面）
   - 重新部署 Stack

## 性能优化

### 资源限制（生产环境推荐）

在 Portainer Stack 编辑器中，为 `docker-compose.prod.yml` 添加资源限制：

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G

  db:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 镜像清理

定期清理未使用的镜像释放空间：

1. 进入 **Environments → <your-env> → Images**
2. 勾选 **Unused** 镜像
3. 点击 **Remove**

或使用 CLI：

```bash
docker system prune -a --volumes
```

## 安全建议

### 1. 使用强密码

生产环境必须修改默认密码：

```bash
# 生成强密码
openssl rand -base64 32
```

在 Portainer Stack 环境变量中设置：

```
POSTGRES_PASSWORD=<generated_password>
```

### 2. 限制网络访问

使用 Portainer **Networks** 功能隔离容器：

- 仅允许 API 容器访问数据库
- Web 容器仅通过 nginx 反向代理访问 API

### 3. 定期轮换 Token/密钥

- **Personal Access Token**: 每 90 天轮换一次
- **SSH 密钥**: 每年轮换一次
- 轮换后更新 Stack 认证配置

### 4. 启用 HTTPS（生产环境必需）

在 nginx 前添加 SSL 终止：

- **方案 1:** 使用 Caddy 作为反向代理（自动 Let's Encrypt 证书）
- **方案 2:** 配置 nginx SSL + Certbot
- **方案 3:** 使用云服务商的负载均衡器（自动 HTTPS）

## 监控告警

### 配置健康检查

Portainer 会自动识别 Compose 文件中的 `healthcheck` 配置。

检查容器健康状态：

1. 进入 **Containers**
2. 查看 **Status** 列，应显示 **healthy**
3. 不健康的容器会显示 **unhealthy** 并自动重启

### 集成外部监控

推荐集成以下监控方案：

- **Prometheus + Grafana**: 容器指标监控
- **Loki**: 日志聚合
- **Uptime Kuma**: 服务可用性监控

## 相关文档

- [Docker 部署指南](./docker-deployment.md) — 本地 Docker Compose 部署说明
- [架构设计文档](./plans/2026-02-08-docker-deployment-design.md) — 完整的架构设计和决策过程
- [入库指南](./ingest-guide.md) — 如何导入桥梁知识数据
- [Portainer 官方文档](https://docs.portainer.io/) — Portainer 完整使用说明

## 附录

### Portainer API 自动化部署

对于 CI/CD 集成，可使用 Portainer API：

```bash
# 获取 JWT Token
curl -X POST http://<portainer-host>:9000/api/auth \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'

# 创建 Stack
curl -X POST http://<portainer-host>:9000/api/stacks \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bridge-rag-prod",
    "type": 2,
    "endpointId": 1,
    "repositoryURL": "https://github.com/EchoBridgeCQU/RAG.git",
    "repositoryReferenceName": "refs/heads/main",
    "repositoryAuthentication": true,
    "repositoryUsername": "your_username",
    "repositoryPassword": "ghp_xxxx",
    "composeFile": "docker-compose.yml",
    "additionalFiles": ["docker-compose.prod.yml"],
    "env": [
      {"name": "ZHIPU_API_KEY", "value": "your_api_key"},
      {"name": "POSTGRES_PASSWORD", "value": "your_password"}
    ]
  }'
```

### 常见 Portainer 版本差异

| 功能 | CE (Community) | BE (Business) 2.33.6 LTS |
|------|----------------|--------------------------|
| Git 部署 | ✓ | ✓ |
| GitOps 自动更新 | ✓ | ✓ |
| RBAC 权限控制 | 基础 | 高级 |
| Git 认证方式 | HTTPS, SSH | HTTPS, SSH, Deploy Token |
| Webhook | ✓ | ✓ |
| 多环境管理 | ✓ | ✓ + 高级策略 |

本指南基于 BE 2.33.6 LTS 编写，CE 版本功能略有差异。
