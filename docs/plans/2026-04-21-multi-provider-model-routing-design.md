# 多 AI 供应商接入 + 任务级模型路由 + Web UI 配置 — 设计文档

- **日期**：2026-04-21
- **作者**：Bridge RAG team（brainstorming 协作产出）
- **状态**：Draft（待进入 writing-plans 出实施计划）
- **关联仓库**：`RAG/`（FastAPI 后端 + `RAG/web/` 管理后台）
- **Schema 版本**：v12 → v13

---

## 0 · TL;DR

给 Bridge RAG 增加：
1. **多 LLM 供应商适配** —— 预置智谱 / DeepSeek / Moonshot / 阿里百炼 / MiniMax，并开放 OpenAI 兼容自定义端点（OpenRouter 一等公民）。
2. **任务级模型路由** —— 7 个业务任务（QA 生成、facet 抽取、入库三件套、内容生成、翻译）各自独立指定"供应商 + 模型"。
3. **管理后台 Web UI 配置** —— 非工程师可视化修改，30 秒内热生效。
4. **零密钥暴露硬约束** —— 密钥永不入库、永不进响应、永不进日志。

**放弃**（v2+）：自动 fallback 链、A/B 灰度、密钥 UI 托管、任务调用审计专表。

---

## 1 · 背景与动机

### 1.1 现状痛点

| 痛点 | 证据 | 影响 |
|---|---|---|
| 供应商单一 | `app/providers/__init__.py::get_provider()` 只在 `ZhipuProvider` / `ZhipuCodingProvider` 二选一 | 智谱被 429 打死时全系统挂 |
| 任务级路由用野路子 | `app/api/public/v1/qa.py:180` 直接 `provider.chat_model = settings.qa_chat_model` 在单例上赋值 | **线程不安全**，并发请求互相污染模型字段 |
| 配置靠发版 | 所有模型名走 `app/core/config.py` env var | 运营改模型 = 找工程师 + 发版 |
| 成本浪费 | tagger / enricher / translation 等流水线任务也用 `glm-4.7` | 便宜模型（flash / deepseek-chat）足够但用不上 |

### 1.2 顶层动机（已对齐）

**ABF 组合 —— "运营省钱型"**：
- **A** 成本优化（便宜任务用便宜模型）
- **B** 质量优化（关键任务用好模型）
- **F** 前台可配（非工程师自助）

**放弃**：C 韧性 / D 合规 / E A/B 实验 → v2+。

---

## 2 · 范围冻结

| 维度 | 决策 |
|---|---|
| 预置供应商 | 智谱（保留）· DeepSeek · Moonshot(Kimi) · 阿里百炼 · MiniMax |
| 自定义供应商 | OpenAI 兼容 base_url（OpenRouter 作为典型用例，一等公民） |
| 模型列表 | **全动态**，零硬编码；每个 Provider 必须实现 `list_models()` |
| Embedding | **锁死 Zhipu embedding-3（1024d）**；v2 再议多供应商 |
| 任务颗粒度 | **7 个任务**（见 §5.4） |
| 密钥存储 | **永远只在后端 env var / 1Password**，DB/响应/前端/日志零暴露 |
| 实施风格 | 薄抽象 + DB 路由（方案 ①） |

---

## 3 · 架构与分层

### 3.1 运行时调用链

```
调用方（tagger.py / generator.py / translation_service.py / ...）
  │ from app.llm import chat_for_task, embed
  │ await chat_for_task("ingest_tagger", messages)
  ▼
app/llm/router.py  (new)
  1. 读 llm_task_routes 表 → (provider_id, model_id)
  2. 读 llm_providers 表   → (kind, base_url, api_key_env, extra_headers, timeout_read)
  3. ProviderRegistry.get(provider_id) → Provider 实例
  4. 返回 (provider, model_id) → 调用方做 provider.chat(messages, model=model_id)
  · 30s TTL threading.Lock 缓存（router 层 + registry 层两级）
  ▼
app/providers/  (existing, extended)
  LLMProvider (ABC) ── embed / chat / list_models
  ├─ ZhipuProvider         (保留；embedding 永锁；chat 兼容老路径)
  ├─ OpenAICompatProvider  (new；覆盖 DeepSeek/Moonshot/阿里/OpenRouter/自定义)
  └─ MiniMaxProvider       (new；特殊响应格式)
  ▼
HTTPS → 供应商 API（密钥仅在 _headers() 闭包内从 os.environ[api_key_env] 读出即用即丢）
```

### 3.2 关键决策

- `chat_for_task(task_key: str)` 是**新唯一入口**。老 `get_provider()` 保留但 deprecated，仅 embedding 路径使用。
- `ProviderRegistry` 维护 `provider_id → 实例` 单例表，懒加载 + 配置变更时主动 `invalidate(id)`。参考 `bridge_resolver.py` 的 TTL 缓存模式（现役）。
- **路由表缓存 TTL = 30s**：UI 改完 30s 内生效；"强制清缓存"按钮可走 `POST /routes/invalidate-cache` 立刻全部失效。
- **密钥读取只在 Provider `_headers()` 闭包内**，不存实例属性，防止 repr / 序列化 / 日志意外泄露。

---

## 4 · Provider 抽象契约

### 4.1 `LLMProvider` ABC 扩展

```python
# app/providers/base.py

@dataclass
class ChatMessage:
    role: str    # "system" | "user" | "assistant"
    content: str

@dataclass
class ChatResponse:
    content: str
    usage: dict
    model: str   # 实际用的模型，给 audit/metrics

@dataclass
class ModelInfo:
    id: str
    display_name: str
    kind: str                        # "chat" | "embedding" | "multimodal"
    context_window: int | None = None
    extra: dict = field(default_factory=dict)

class LLMProvider(ABC):
    """无状态 HTTP 适配器。不持有'当前模型' —— 每次调用由 router 指定。"""
    @abstractmethod
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]: ...
    @abstractmethod
    async def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse: ...
    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...
```

**破坏性变更**：`chat()` / `embed()` 新增 `model` keyword-only 参数。所有调用点随迁移同步改。

### 4.2 Provider 实现矩阵

| 类 | kind | 覆盖 | list_models 端点 | 响应适配 |
|---|---|---|---|---|
| `ZhipuProvider` | `zhipu` | 智谱 | `GET /api/paas/v4/models` | 现有 embed/chat 改造加 model 参数 |
| `OpenAICompatProvider` | `openai_compat` | DeepSeek / Moonshot / 阿里百炼 / OpenRouter / 任意自定义 | `GET {base_url}/v1/models` | OpenAI 标准，零适配 |
| `MiniMaxProvider` | `minimax` | MiniMax | `GET /v1/models` | 响应需 unwrap `base_resp` |

### 4.3 `ProviderConfig` + 密钥取用唯一入口

```python
# app/providers/config.py
@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    kind: str
    base_url: str
    api_key_env: str           # 变量名，NOT 密钥本身
    extra_headers: dict = field(default_factory=dict)
    timeout_read: float = 90.0

# app/providers/_secret.py
def resolve_api_key(env_name: str) -> str:
    key = os.environ.get(env_name)
    if not key:
        raise ProviderConfigurationError(
            f"env var {env_name} not set; refusing to call provider with empty key"
        )
    return key
```

### 4.4 连通性测试复用 `list_models()`

不做专门的 `ping()` 方法 —— `POST /providers/{id}/test` 内部调 `list_models()`，成功时顺便刷新 `llm_provider_models` 缓存。

---

## 5 · DB Schema (v13)

### 5.1 三张新表

```sql
-- llm_providers: 供应商元信息。密钥永不入库 —— 只存 env 变量名。
CREATE TABLE llm_providers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(64)  NOT NULL UNIQUE,
    kind            VARCHAR(32)  NOT NULL,
    base_url        VARCHAR(512) NOT NULL,
    api_key_env     VARCHAR(64)  NOT NULL,
    extra_headers   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    timeout_read    REAL         NOT NULL DEFAULT 90.0,
    last_tested_at  TIMESTAMPTZ,
    last_test_ok    BOOLEAN,
    last_test_error TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CHECK (kind IN ('zhipu', 'openai_compat', 'minimax'))
);
CREATE INDEX idx_llm_providers_enabled ON llm_providers(enabled) WHERE enabled = TRUE;

-- llm_provider_models: list_models() 结果缓存。覆盖式同步（DELETE+INSERT）。
CREATE TABLE llm_provider_models (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id     UUID NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    model_id        VARCHAR(128) NOT NULL,
    display_name    VARCHAR(256) NOT NULL,
    kind            VARCHAR(32)  NOT NULL,
    context_window  INTEGER,
    extra           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    fetched_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (provider_id, model_id)
);
CREATE INDEX idx_llm_provider_models_provider ON llm_provider_models(provider_id);
CREATE INDEX idx_llm_provider_models_kind ON llm_provider_models(provider_id, kind);

-- llm_task_routes: task → (provider, model) 的运行时路由。唯一来源。
CREATE TABLE llm_task_routes (
    task_key        VARCHAR(64)  PRIMARY KEY,
    provider_id     UUID NOT NULL REFERENCES llm_providers(id) ON DELETE RESTRICT,
    model_id        VARCHAR(128) NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      UUID
);
```

### 5.2 外键策略

| FK | 策略 | 理由 |
|---|---|---|
| `llm_provider_models.provider_id → llm_providers.id` | CASCADE | 供应商删了模型缓存跟着走 |
| `llm_task_routes.provider_id → llm_providers.id` | **RESTRICT** | 正被引用不能删 —— 强制先改路由 |
| `llm_task_routes.model_id` | **无外键** | 供应商临时下架模型时不能连带打爆路由配置 |

### 5.3 为什么 `kind` 用 VARCHAR + CHECK 而不是 ENUM

Postgres ENUM 加值要 `ALTER TYPE`，VARCHAR + CHECK 只要 `ALTER TABLE ... DROP/ADD CONSTRAINT`，迭代成本更低。

### 5.4 7 个任务 + v13 迁移 seed

```python
# app/scripts/migrations/v13_multi_provider.py
def migrate_v12_to_v13(conn):
    conn.execute(CREATE_LLM_PROVIDERS_SQL)
    conn.execute(CREATE_LLM_PROVIDER_MODELS_SQL)
    conn.execute(CREATE_LLM_TASK_ROUTES_SQL)

    zhipu_id = conn.execute("""
        INSERT INTO llm_providers (name, kind, base_url, api_key_env)
        VALUES ('智谱 AI（默认）', 'zhipu',
                'https://open.bigmodel.cn/api/paas/v4', 'ZHIPU_API_KEY')
        RETURNING id
    """).scalar()

    # 保持与迁移前行为等价
    seed = [
        ("qa_generation",           zhipu_id, "glm-4.7"),
        ("qa_facet_extraction",     zhipu_id, "glm-4-flash"),
        ("ingest_tagger",           zhipu_id, "glm-4.7"),
        ("ingest_context_enricher", zhipu_id, "glm-4.7"),
        ("ingest_bridge_linker",    zhipu_id, "glm-4.7"),
        ("content_generation",      zhipu_id, "glm-4.7"),
        ("translation",             zhipu_id, "glm-4.7"),
    ]
    for task_key, pid, model in seed:
        conn.execute(
            "INSERT INTO llm_task_routes (task_key, provider_id, model_id) VALUES (%s, %s, %s)",
            (task_key, pid, model),
        )
```

**迁移后行为等价性保证**：所有 LLM 调用仍走智谱 + 原模型名；UI 默认显示 7 条路由全部 "智谱 AI（默认）"。零停机、零回归、可 rollback。

### 5.5 `app/core/config.py` 处置

- `chat_model`、`qa_chat_model` —— 保留 deprecated 6 个月观察
- `use_coding_plan` —— 下个大版本删除；运营用时在 UI 新增 `kind=openai_compat` 的 "智谱 Coding Plan" provider
- `embedding_model` —— **永久保留**，embedding 锁定路径，不走 DB 路由

---

## 6 · API 契约（管理后台，`/api/v1/llm/*`，全部 admin JWT）

| # | 方法 | 路径 | 用途 |
|---|---|---|---|
| 1 | GET | `/api/v1/llm/providers` | 列表 |
| 2 | POST | `/api/v1/llm/providers` | 新增 |
| 3 | GET | `/api/v1/llm/providers/{id}` | 详情 |
| 4 | PATCH | `/api/v1/llm/providers/{id}` | 更新元信息 |
| 5 | DELETE | `/api/v1/llm/providers/{id}` | 删除（被引用返 409） |
| 6 | POST | `/api/v1/llm/providers/{id}/test` | 测试连通性 + 刷新模型列表 |
| 7 | GET | `/api/v1/llm/providers/{id}/models` | 读模型缓存 |
| 8 | GET | `/api/v1/llm/tasks` | 7 任务路由一览 |
| 9 | PUT | `/api/v1/llm/tasks/{task_key}` | 改单个路由 |
| 10 | POST | `/api/v1/llm/tasks/batch-update` | 批量保存 |
| 11 | POST | `/api/v1/llm/routes/invalidate-cache` | 强制清 router TTL 缓存 |

**故意不做**：`GET /providers/{id}/api-key`（零暴露）、`POST /providers/import|export`（防密钥入备份）。

### 6.1 Pydantic Schema 白名单（零暴露第二道闸）

```python
# ProviderPublic 里 NO api_key, NO api_key_env, NO extra_headers
class ProviderPublic(BaseModel):
    id: UUID
    name: str
    kind: ProviderKind
    base_url: str
    enabled: bool
    timeout_read: float
    has_api_key_configured: bool     # 后端校验 os.environ.get(api_key_env) 是否有值
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None       # 已脱敏
    model_count: int
    created_at: datetime
    updated_at: datetime
```

### 6.2 删除保护

```python
in_use = db.query(LLMTaskRoute.task_key).filter(provider_id=id).all()
if in_use:
    raise HTTPException(409, detail={
        "error": "provider_in_use",
        "message": f"Provider 正被 {len(in_use)} 个任务使用，请先改路由",
        "task_keys": in_use,
    })
# savepoint + IntegrityError 兜底，防止将来加新 FK 不同步改 check
with db.begin_nested():
    db.delete(provider_row)
```

### 6.3 速率限制

- `/api/v1/llm/*` 全部 `@limiter.limit("30/minute")`
- `POST /providers/{id}/test` 额外 `@limiter.limit("10/minute")`（防点爆上游）

---

## 7 · UI 设计（`RAG/web/`）

### 7.1 路由 + 入口

- `/settings/llm` 新页面，默认 tab "任务路由"，另一 tab "供应商管理"
- `/settings` 增加入口卡片 "LLM 路由" → `/settings/llm`

### 7.2 页面 A：任务路由

- 7 行卡片，每行 `[供应商下拉] [模型下拉（异步加载）]`
- 模型下拉显示 `name · context_window`
- 未保存标记 `•` + 全页"保存全部"（batch-update 原子）
- "强制清缓存" 按钮

### 7.3 页面 B：供应商管理

- 卡片列表 `[name, kind, base_url, 测试状态, 模型数, 被引用计数]`
- `✓ Key 已配` / `✗ Key 未配` 视觉区分（后端返回 `has_api_key_configured`）
- "测试并刷新模型"单按钮（一次 RPC 完成连通性 + 同步模型）
- 删除前端先校验被引用计数，引导先改路由

### 7.4 新增 / 编辑 Dialog

- 字段：name / kind / base_url / api_key_env / extra_headers JSON / timeout_read / enabled
- **api_key_env 字段：提示"只填变量名，保存后前端不再展示"**
- "保存并测试"按钮：创建后立即调 `/test`
- 编辑时 api_key_env 可重写但不回显

### 7.5 组件布局

```
web/src/pages/settings/LLMSettingsPage.tsx        # 外壳 + Tab
web/src/components/settings/llm/
  ├─ TaskRoutesTab.tsx / TaskRouteCard.tsx
  ├─ ProvidersTab.tsx / ProviderCard.tsx
  ├─ ProviderFormDialog.tsx / ProviderDeleteDialog.tsx
  └─ ModelPicker.tsx                              # 下拉 + 异步加载
web/src/hooks/useLLMProviders.ts + useLLMTasks.ts + useLLMProviderModels.ts
web/src/lib/api/llm.ts
```

### 7.6 权限

所有页面 `session.user.role === 'admin'` gate；非 admin 复用现役 `ForbiddenPanel`。

---

## 8 · 错误处理 / 脱敏（零暴露第三道闸）

### 8.1 异常体系

```python
class ProviderError(Exception): ...
class ProviderConfigurationError(ProviderError):     # 400
class ProviderUnavailableError(ProviderError):       # 502 + 脱敏 reason
class ModelNotFoundError(ProviderError):             # 409
class TaskRouteNotFoundError(ProviderError):         # 500 (bug)
```

### 8.2 `sanitize_error()` 脱敏器

三层过滤：
1. 替换所有已注册的密钥值（启动时 + 每次 provider 变更时 `register_sensitive_key()`）
2. regex 兜底：`Bearer \w{16+}`、`sk-\w{20+}`、`api_key=\w{16+}` 统一替换为 `***KEY***`
3. 截断 300 字符

**三个强制调用点**：`/test` 响应的 reason、`llm_providers.last_test_error` 写库前、所有 provider 日志。

### 8.3 全局异常处理器

挂到 `app/main.py` 的 `@app.exception_handler(ProviderError 子类)`，返回体经过 sanitize。

---

## 9 · 可观测性（MVP 只做结构化日志）

每次 `chat_for_task()` 完毕 emit：

```json
{
  "event": "llm_call",
  "task_key": "...",
  "provider_id": "...",
  "provider_name": "...",
  "model_id": "...",
  "status": "ok|fail",
  "latency_ms": 1234,
  "prompt_tokens": 100,
  "completion_tokens": 200,
  "retry_attempts": 0,
  "failure_reason": null
}
```

- 现役 `docker logs bridge_rag_api` 聚合
- 未来接 Grafana/Loki 直接 JSON parse
- **v2 再加 `llm_task_audit` 专表**，MVP 不预建

---

## 10 · 缓存失效 + 配置传播

| 事件 | 传播 |
|---|---|
| `PATCH /providers/{id}` | `ProviderRegistry.invalidate(id)` + `register_sensitive_key(new_env)` |
| `DELETE /providers/{id}` | `ProviderRegistry.invalidate(id)` |
| `POST /providers/{id}/test` | 刷新 `llm_provider_models`（不动 registry） |
| `PUT /tasks/{key}` | `router.invalidate(task_key)` |
| `POST /routes/invalidate-cache` | `ProviderRegistry.invalidate_all()` + `router.invalidate_all()` |

**多 worker 场景**：现役 `uvicorn` 单 worker 部署（login rate limiter 也有同限制，见 CLAUDE.md），MVP 不跨 worker 同步；v2 上 Redis pub/sub。

---

## 11 · 测试策略（按优先级）

1. **迁移测试**（最高 ROI）—— v12→v13 后 seed 正确、所有路由指向智谱、7 task_keys 齐全
2. **Provider ABC 契约测试** —— 所有 Provider 的 `chat()` 必须接 `model=` keyword-only
3. **`sanitize_error` 测试** —— 注册密钥后异常消息里看不见明文
4. **路由缓存 TTL 测试** —— 改 DB 后 30s 内命中旧缓存、31s 后命中新值
5. **11 个端点 smoke** —— 路由 + schema + 权限 gate
6. **E2E**（一个就够）—— 切换 qa_generation 到 DeepSeek 后实际 RPC 命中 DeepSeek 而非智谱

---

## 12 · 回归风险清单（部署前 checklist）

| 风险 | 缓解 |
|---|---|
| 迁移后 RAG / ingest 中断 | seed 全部指向智谱现役模型 + 迁移测试把关 |
| `qa.py:180` monkey-patch 清理后 facet 抽取变慢 | 该 task_key 默认模型 = `glm-4-flash`，行为等价 |
| Provider 实例化失败导致 boot 挂 | Registry 懒加载 + 坏 provider 不影响其他任务 |
| 密钥意外出现在 error / audit | sanitizer 三道闸 + 单测 |
| 部署后 env var 没加 | UI 供应商卡片 `✗ Key 未配` 直观可见 |
| 模型缓存过期 UI 假模型 | 显示 `fetched_at` + "测试并刷新"按钮 |

---

## 13 · 文档更新（DoD）

- `CLAUDE.md` Gotchas 新增：**禁止 `provider.chat_model = ...` 单例赋值 → 必须走 `chat_for_task(task_key)`**
- `CLAUDE.md` schema 版本升 v13 + 三表简述
- `docs/architecture.md` 加 §3.1 架构图

---

## 14 · 超出范围（v2+ 列入 backlog）

- 自动 fallback 链（动机 C）
- A/B 灰度百分比路由（动机 E）
- 密钥 UI 托管 + 加密入库（动机 F 的完整闭环）
- `llm_task_audit` 调用审计专表 + 成本面板
- Embedding 多供应商（触发全量 reindex 的大工程）
- 跨 worker 缓存失效（Redis pub/sub）

---

## 15 · 下一步

1. 本文档 commit 落盘 → `RAG/docs/plans/2026-04-21-multi-provider-model-routing-design.md`
2. 调用 `writing-plans` skill 产出实施计划（Phase/任务拆解 / 依赖 / 验收标准）
3. 实施计划评审通过后进入编码
