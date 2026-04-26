# 识景端点设计 · `/v1/recognition`

**Status:** approved · **Date:** 2026-04-26 · **Owner:** RAG backend
**Issue:** RAG#170（推荐方案 A → 本设计调整为 OpenRouter + 国产 VL 旗舰）

## 1 · 背景

C 端 `web/` 已上线识景页（`web/src/app/[locale]/recognize/page.tsx` + `UploadZone` + `CandidateList`），通过 `useRecognition` hook 发起 `POST /v1/recognition`（multipart）。后端 `RAG/app/api/public/v1/` 下无对应路由，前端调用 100% 404，识景功能用户不可用。

## 2 · 目标

新增 `/v1/recognition` 公开端点：用户上传桥梁照片（可选附经纬度）→ 返回候选桥梁列表（命中库内桥）或 fallback 搜索建议（库外/非桥）。匿名可访问，对齐 C 端"只有 `/me/*` 与收藏/复习/历史要登录"的守卫策略。

## 3 · 模型选型

**`qwen/qwen3-vl-235b-a22b-instruct`（OpenRouter）** —— 主路径
**`qwen/qwen3-vl-30b-a3b-instruct`（OpenRouter）** —— 限流降级备选

| 维度 | 选定理由 |
|---|---|
| 准确率 | 2025-09 发布的 Qwen3-VL 旗舰，在 VQA / 文档解析 / OCR 全面超越 Qwen2.5-VL-72B |
| 速度 | MoE 架构 A22B 激活，等效 22B 稠密推理，比 72B 稠密快 ~3× |
| Context | 262K，足以容纳全量桥梁名录（500 条 ≈ 15K tokens, 占比 5.7%）+ 图片 base64 |
| 成本 | $0.20 / $1M 输入，$0.88 / $1M 输出（用户已松绑成本约束，但价格反而比 2.5-VL-72B 便宜） |
| OpenRouter | 与现有 `OpenAICompatProvider` 协议同构，复用 httpx + retry + secret 管理基建，零新增 SDK 依赖 |

## 4 · 顶层设计

```
client (multipart: image, lat?, lng?)
        │
        ▼
┌──────────────────────────────────────────────┐
│ POST /v1/recognition (FastAPI)               │
│  · 文件大小校验 ≤ 5 MB → 413                 │
│  · MIME 校验 image/jpeg|png → 415            │
│  · 转 base64 data URL                        │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ vision_recognition.py (service)              │
│  ① 从 bridges 表拉名录 → CSV 拼装            │
│  ② 组 system + user message（含图片）        │
│  ③ 调 OpenRouter Qwen3-VL（json_object 模式）│
│  ④ 解析 JSON：{matched_name, free_form}     │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ 三分支召回（颗粒度清晰）                     │
│  分支①: matched_name 非空                    │
│    → bridges.name = $1 OR name_en = $1       │
│    → 唯一首位 candidate                      │
│  分支②: matched_name 空 & free_form 非空     │
│    → ILIKE '%bridge_name%' top 3-5           │
│    → confidence_hints = free_form.hints      │
│  分支③: 全空（不是桥）                       │
│    → candidates=[], fallback_suggestions      │
└──────────────────────────────────────────────┘
        │
        ▼
{ data: { candidates: [...], fallback_suggestions? }, meta: {...} }
```

## 5 · 数据契约

### 5.1 请求

```
POST /v1/recognition
Content-Type: multipart/form-data
Fields:
  image     File (jpeg|png, ≤5MB)         必选
  latitude  float                          可选
  longitude float                          可选
```

### 5.2 响应（C 端 `/v1/*` 外层包 `{data, meta}`）

```ts
{
  data: {
    candidates: Array<{
      bridge_id: string;          // bridges.id
      name: string;               // bridges.name
      bridge_type: string;        // bridges.bridge_type ?? ""
      era: string;                // bridges.era ?? ""
      region: string;             // bridges.region ?? ""
      thumbnail: string | null;   // 取 bridge_image 表首图 URL；无则 null
      confidence_hints: string[]; // ["分支①来自 LLM 命中确认", "分支②来自 free_form.hints"]
    }>;
    fallback_suggestions?: {
      search_hint: string | null; // free_form.bridge_name
      region_hint: string | null; // free_form.region
    };
  },
  meta: {
    model: "qwen/qwen3-vl-235b-a22b-instruct" | "qwen/qwen3-vl-30b-a3b-instruct";
    latency_ms: number;
    branch: "exact" | "fuzzy" | "fallback";
  }
}
```

错误响应沿用现有 `error_handlers.py` 风格（`{ error: { code, message } }`）。

## 6 · LLM Prompt 契约

### 6.1 system prompt 模板（前缀稳定，命中 prompt cache）

```
你是中国桥梁识别助手。下方是已知桥梁名录（CSV，每行一座桥）：
name,region,era,bridge_type
赵州桥,河北,隋唐,石拱桥
南京长江大桥,江苏,现代,公铁两用桁架桥
...（全量注入）

任务：识别用户上传的图片中的桥梁。
- 若能在名录里精确对应到某座桥，把 matched_name 填那一行的 name；
- 若无法对应名录（包括"图中的桥不在名录里"和"图中根本不是桥"），matched_name 设为 null；
- 当 matched_name=null 但确实是一座桥，给出 free_form 自由识别；
- 当根本不是桥，free_form 也设为 null。

只输出 JSON，不要其他文本：
{
  "matched_name": string | null,
  "free_form": {
    "bridge_name": string,
    "region": string,
    "bridge_type": string,
    "hints": string[]
  } | null
}
```

### 6.2 user message

```json
[
  {"type": "text", "text": "可选位置：纬度 X，经度 Y"},
  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
]
```

### 6.3 OpenAI 协议字段

```python
{
  "model": settings.openrouter_vision_model,
  "messages": [...],
  "response_format": {"type": "json_object"},
  "temperature": 0.1,
  "max_tokens": 512,
}
```

## 7 · 候选召回细节

### 分支①（exact）
```sql
SELECT id, name, name_en, region, era, bridge_type
FROM bridges
WHERE name = :matched OR name_en = :matched
LIMIT 1;
```

### 分支②（fuzzy）
```sql
SELECT id, name, name_en, region, era, bridge_type,
  CASE
    WHEN name ILIKE :exact THEN 100
    WHEN name ILIKE :prefix THEN 80
    WHEN name ILIKE :contains THEN 60
    ELSE 40
  END AS score
FROM bridges
WHERE name ILIKE :contains
   OR name_en ILIKE :contains
   OR (region IS NOT NULL AND region = :region)
ORDER BY score DESC, name
LIMIT 5;
```

参数：`:exact = $name$`、`:prefix = $name%`、`:contains = %name%`。

### 分支③（fallback）
直接构造 `fallback_suggestions = { search_hint: free_form.bridge_name, region_hint: free_form.region }`。

### thumbnail 取数
对每条候选 `JOIN bridge_images ON bridge_images.bridge_id = bridges.id ORDER BY display_order ASC LIMIT 1`，取 `image_url` 字段；无图返回 `null`。前端目前不渲染缩略图，可空。

## 8 · Provider 接入

### 选择：**新建 `app/services/vision_recognition.py` 直接走 httpx，不强扩 `ChatMessage` 协议**

**理由：**
- 现有 `ChatMessage.content: str` 是项目级稳定契约，所有 chat / qa / streaming 调用都依赖。为单个识景端点扩协议成 multimodal blocks 牵动面太大，违反 YAGNI。
- 视觉识别的语义（图片 in / 结构化 JSON out）与 chat completion 的语义差距足够大，独立 service 更清晰。
- 仍复用 `app/providers/_secret.py` 的密钥解析、`app/providers/errors.py` 的异常类、tenacity 重试模式（直接拷贝 `openai_compat.py` 里 `_is_retryable_http_error / _rate_limit_aware_wait` 两个 helper —— 这两 helper 本来就标了"待抽 `_retry.py` 的 TODO"，本次不顺手做以保持 scope 紧）。
- 未来若有第二个视觉端点（比如桥梁碑文 OCR），再考虑抽 `MultimodalProvider` 协议。

### 关键代码骨架

```python
# app/services/vision_recognition.py
async def recognize_bridge(
    image_bytes: bytes,
    mime: str,
    latitude: float | None,
    longitude: float | None,
    db: AsyncSession,
) -> RecognitionResult:
    catalog = await _fetch_bridge_catalog(db)         # CSV 字符串
    payload = _build_payload(image_bytes, mime, latitude, longitude, catalog)
    raw = await _call_openrouter(payload)             # 含降级 235B → 30B
    parsed = _parse_json(raw)
    return await _route_to_branches(parsed, db)
```

## 9 · 配置

`app/core/config.py` 新增字段（snake_case，对齐现有约定）：

```python
openrouter_api_key: str = ""
openrouter_base_url: str = "https://openrouter.ai/api/v1"
openrouter_vision_model: str = "qwen/qwen3-vl-235b-a22b-instruct"
openrouter_vision_fallback_model: str = "qwen/qwen3-vl-30b-a3b-instruct"
recognition_max_image_bytes: int = 5 * 1024 * 1024
recognition_request_timeout: float = 30.0
```

`.env.example` 同步追加 `OPENROUTER_API_KEY=` + `OPENROUTER_BASE_URL=` + 注释说明可换 `Z_AI_*` 或 `ARK_*` 不在本期。

OpenRouter 推荐发送 `HTTP-Referer` 和 `X-Title` 头以获得更好的 rate limit；本期注入 `https://bridgingchina.net` 与 `BridgingChina-Recognition`。

## 10 · 错误处理

| 场景 | HTTP | 行为 |
|---|---|---|
| 文件 > 5MB | 413 | `error.code = "file_too_large"` |
| MIME 非 jpeg/png | 415 | `error.code = "unsupported_media_type"` |
| OpenRouter 429（限流） | 主模型 → 退避重试 → 仍失败则切降级模型 | 仍失败再返 503 |
| OpenRouter 5xx | 退避重试 → 切降级 → 返 503 | `error.code = "vision_unavailable"` |
| LLM JSON 解析失败 | 200 | 视为分支③，返回空 candidates + fallback_suggestions=null（避免 5xx 让前端 toast 报错） |
| DB 异常 | 500 | 沿用现有 `error_handlers.py` |

## 11 · 测试矩阵

`tests/test_recognition.py`（mock OpenRouter）：

- `test_branch_exact` —— mock 返回 `matched_name=赵州桥`，断言 candidate 唯一且 bridge_id 命中
- `test_branch_fuzzy` —— mock 返回 `free_form.bridge_name=赵州`，断言 ILIKE 命中赵州桥
- `test_branch_fallback_not_a_bridge` —— mock 返回全空，断言 candidates=[] + fallback_suggestions=null
- `test_branch_fallback_unknown_bridge` —— mock 返回 `free_form.bridge_name=某个不在库的桥`，断言 fallback_suggestions 非空
- `test_413_oversize` / `test_415_wrong_mime`
- `test_openrouter_5xx_falls_back_to_smaller_model` —— mock 主模型 503，断言重试切到 30B-A3B
- `test_llm_returns_invalid_json` —— mock 返回乱码，断言降级到分支③而非 5xx

## 12 · 验收

- `pytest tests/test_recognition.py -v` 全绿
- 本地 `uvicorn app.main:app --reload` + `web/` 真实 e2e：上传赵州桥图片 → 返回 candidate；上传猫图 → fallback；上传 6MB 图 → 413
- `git diff main` 无前端代码改动（契约已 frozen）
- `OPENROUTER_API_KEY` 入 secrets，不入 git

## 13 · 显式 non-goals（YAGNI）

- 不做 pgvector 图像 embedding 召回（issue#170 P1，不在本期）
- 不做 `latitude/longitude` 地理半径过滤（库小于 1000 时无收益，靠 LLM 自己用经纬度文本提示推理就够）
- 不做 prompt 多语言 / 国际化（识景目前中文 only）
- 不抽 `MultimodalProvider` 通用协议（YAGNI，等第二个视觉端点出现）
- 不做请求级缓存（用户每次拍的图都不一样，缓存命中率近零）

## 14 · 部署清单

- `OPENROUTER_API_KEY` → 生产 env / secrets
- `CORS_ORIGINS` 无需追加（识景走 `/v1/*` 已全局开）
- 无 DB schema 变更，无 migration
