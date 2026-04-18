# api-spec.md — 筑脉-ArchTrail 移动端 API 规范（v1.1）

> 对应 design.md v1.1 | RESTful JSON API | 问答接口使用 SSE 流式返回  
> MVP 不设用户体系，使用客户端生成的设备 ID 关联个人数据（收藏/复习进度）。  
> 本规范定义移动端公开 API。现有 `/api/v1/*` 为管理后台 API，继续保留；移动端 API 使用 `/v1/*` 前缀，无需 JWT 认证。  
> **所有实体主键统一使用 UUID v4。**

---

## 0. 通用约定

### 0.1 Base URL
```
https://{host}/v1
```

### 0.2 请求头
| Header | 必选 | 说明 |
|--------|------|------|
| `Content-Type` | 是 | `application/json`（除识景上传用 `multipart/form-data`） |
| `Accept-Language` | 否 | `zh-CN`（默认）/ `en` |
| `X-Device-Id` | 条件必选 | 客户端首次启动时生成的 UUID v4，持久存储在本地。仅 `/favorites`、`/review`、`/history` 端点必选，其余端点不要求 |

> **安全注意：** 生产环境必须使用 HTTPS。`X-Device-Id` 不应出现在 URL path 或服务端日志中。UUID v4 的 122 bit 熵足以防止猜测攻击，但需防范 HTTP 明文传输导致的泄露。

### 0.3 统一响应格式

**成功（2xx）：**
```jsonc
{
  "data": { /* 业务数据 */ },
  "meta": {           // 可选，仅列表接口返回
    "total": 120,
    "page": 1,
    "page_size": 20,
    "has_more": true
  }
}
```

**错误（4xx/5xx）：**
```jsonc
{
  "error": {
    "code": "NOT_FOUND",           // 机器可读错误码
    "message": "桥梁不存在",        // 用户可读文案（跟随 Accept-Language）
    "details": {}                  // 可选，附加调试信息（仅开发环境返回）
  }
}
```

### 0.4 错误码枚举
| HTTP Status | code | 说明 |
|-------------|------|------|
| 400 | `BAD_REQUEST` | 请求参数不合法 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 422 | `UNPROCESSABLE` | 参数合法但无法处理（如识景无法识别） |
| 429 | `RATE_LIMITED` | 请求过于频繁 |
| 500 | `INTERNAL_ERROR` | 服务端内部错误 |
| 503 | `SERVICE_UNAVAILABLE` | 服务暂时不可用（如 RAG 过载） |

### 0.5 分页约定
列表接口统一使用 `page` + `page_size` 分页：
- `page`：从 1 开始，默认 1
- `page_size`：默认 20，最大 100

### 0.6 与现有管理后台 API 的关系

现有管理后台 API（`/api/v1/*`）继续保留，需 JWT 认证，用于内容管理。移动端 API（`/v1/*`）是只读的公开 API（除收藏/复习外），不需要 JWT。两套 API 共享同一数据库，但 schema 和响应格式不同。

| 维度 | 管理后台 `/api/v1/*` | 移动端 `/v1/*` |
|------|---------------------|--------------------------|
| 认证 | JWT Bearer Token | X-Device-Id（仅收藏/复习） |
| 读写 | 读写 | 只读 + 收藏/复习写入 |
| 数据粒度 | chunks 级别 | 知识点/桥梁 聚合级别 |
| 问答 | 同步 JSON | SSE 流式 |

---

## 1. 应用配置

### 1.1 获取应用配置
```
GET /config
```

客户端启动时拉取一次，获取枚举值、地图配置等。可缓存，通过 `ETag` / `If-None-Match` 控制更新。

**响应：**
```jsonc
{
  "data": {
    "eras": ["先秦", "秦汉", "魏晋南北朝", "隋唐", "宋元", "明清"],
    "bridge_types": ["石拱桥", "木拱桥", "梁桥", "浮桥", "索桥", "铁桥", "悬索桥", "斜拉桥"],
    "regions": ["华北", "华东", "华南", "华中", "西南", "西北", "东北"],
    "map": {
      "provider": "______",       // 地图来源（配置化）
      "approval_number": "______" // 审图号（配置化）
    }
  }
}
```

> 数据来源：`config/facets.yaml` 中的枚举值 + 新增 map 配置字段。

---

## 2. 知识图谱

### 2.1 获取知识架构树
```
GET /knowledge/tree
```

返回四大主线及其子分类的完整树结构。

> 数据来源：现有 `taxonomy_nodes` 表 + 新增的 `knowledge_points` 表。

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `depth` | integer | 否 | 返回深度，默认全部。`1` = 仅一级主线，`2` = 含二级子类 |

**响应：**
```jsonc
{
  "data": {
    "lines": [
      {
        "id": "b1a2c3d4-...",
        "name": "形制与技术",
        "icon_url": null,
        "children": [
          {
            "id": "e5f6a7b8-...",
            "name": "结构体系",
            "children": [
              {
                "id": "c9d0e1f2-...",
                "name": "拱桥结构",
                "type": "knowledge_point",
                "tags": ["基础概念"],
                "summary": "以拱圈为主要承重构件的桥梁形式…"
              }
            ]
          }
        ]
      }
      // 共 4 个主线
    ]
  }
}
```

### 2.2 获取知识点详情
```
GET /knowledge/points/{id}
```

返回知识点完整内容，含 L0/L1/L2 各层级。

> 数据来源：新增 `knowledge_points` 表，L1 引用从 `chunks` 表聚合。

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `level` | string | 否 | `"L0"` / `"L1"` / `"L2"` / `"all"`（默认 `"all"`）|

**响应：**
```jsonc
{
  "data": {
    "id": "c9d0e1f2-...",
    "name": "拱桥结构",
    "aliases": ["拱券桥"],
    "line": { "id": "b1a2c3d4-...", "name": "形制与技术" },
    "category": { "id": "e5f6a7b8-...", "name": "结构体系" },
    "tags": ["基础概念", "桥型"],
    "difficulty": "beginner",

    "l0": {
      "key_points": [
        { "id": "a1b2c3d4-...", "summary": "拱桥以拱圈为主要承重构件，将荷载转化为轴向压力", "order": 1 },
        { "id": "e5f6a7b8-...", "summary": "按拱圈形式分为圆弧拱、尖拱、抛物线拱等", "order": 2 }
        // 3~7 条
      ],
      "typical_bridges_count": 15
    },

    "l1": {
      "key_points": [
        {
          "id": "a1b2c3d4-...",
          "summary": "拱桥以拱圈为主要承重构件，将荷载转化为轴向压力",
          "explanation": "拱桥利用拱形结构将竖向荷载转化为沿拱轴的压力……",
          "illustrations": [
            { "url": "https://...", "caption": "典型圆弧拱受力示意" }
          ],
          "related_terms": [
            { "id": "d4e5f6a7-...", "name": "拱圈" },
            { "id": "b8c9d0e1-...", "name": "拱脚" }
          ],
          "citations": [1, 3]
        }
      ]
    },

    "l2": {
      "comparisons": [
        {
          "title": "敞肩拱 vs 实腹拱",
          "content": "敞肩拱在拱肩开设小拱洞……",
          "citations": [2, 5]
        }
      ],
      "evolution": "从简单石拱发展到敞肩拱……",
      "controversies": [
        {
          "title": "中国拱桥起源年代",
          "description": "关于中国最早拱桥的确切年代存在争议……",
          "confidence": "disputed",
          "views": [
            { "position": "始于东汉", "citations": [4] },
            { "position": "始于西晋", "citations": [6] }
          ]
        }
      ],
      "further_reading": [
        { "title": "《中国古桥技术史》第三章", "source_id": "f2a3b4c5-..." }
      ]
    },

    "sources": [
      {
        "id": 1,
        "title": "中国古代桥梁",
        "author": "唐寰澄",
        "type": "book",
        "excerpt": "拱桥以拱圈承重，是中国古代桥梁最重要的结构形式……",
        "location": "第三章 第1节"
      }
    ]
  }
}
```

### 2.3 获取知识点的典型桥梁
```
GET /knowledge/points/{id}/bridges
```

**Query 参数：** `page`, `page_size`

**响应：**
```jsonc
{
  "data": {
    "bridges": [
      {
        "id": "f7a8b9c0-...",
        "name": "赵州桥",
        "aliases": "安济桥",
        "bridge_type": "石拱桥",
        "era": "隋唐",
        "region": "河北省 石家庄市 赵县",
        "latitude": 37.7652,
        "longitude": 114.7761,
        "thumbnail": null,
        "relevance_note": "敞肩拱的典型代表"
      }
    ]
  },
  "meta": { "total": 15, "page": 1, "page_size": 20, "has_more": false }
}
```

> 数据来源：`bridges` 表，通过新增的 `knowledge_point_bridges` 关联表 join，或通过 `chunk_bridge_links` + taxonomy 标签反查。

---

## 3. 桥梁

### 3.1 桥梁列表（地图 + 搜索共用）
```
GET /bridges
```

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `bridge_type` | string | 否 | 多选逗号分隔 |
| `era` | string | 否 | 多选逗号分隔 |
| `region` | string | 否 | 省级/市级名称 |
| `keyword` | string | 否 | 名称/别名模糊匹配 |
| `near_lat` | number | 否 | 附近搜索中心纬度 |
| `near_lng` | number | 否 | 附近搜索中心经度 |
| `near_radius` | integer | 否 | 搜索半径（米），默认 50000 |
| `sort` | string | 否 | `"relevance"` / `"distance"` / `"name"` |
| `page`, `page_size` | integer | 否 | 分页 |

> 数据来源：现有 `bridges` 表。需新增 `latitude` / `longitude` 字段。

**响应：**
```jsonc
{
  "data": {
    "bridges": [
      {
        "id": "f7a8b9c0-...",
        "name": "赵州桥",
        "aliases": "安济桥",
        "bridge_type": "石拱桥",
        "era": "隋唐",
        "region": "河北省 石家庄市 赵县",
        "latitude": 37.7652,
        "longitude": 114.7761,
        "thumbnail": null,
        "distance": null
      }
    ]
  },
  "meta": { "total": 85, "page": 1, "page_size": 20, "has_more": true }
}
```

### 3.2 地图聚类点位
```
GET /bridges/clusters
```

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `bounds_ne_lat`, `bounds_ne_lng` | number | 是 | 视野东北角 |
| `bounds_sw_lat`, `bounds_sw_lng` | number | 是 | 视野西南角 |
| `zoom` | integer | 是 | 缩放级别 |
| `bridge_type`, `era`, `region` | string | 否 | 筛选条件 |

**响应：**
```jsonc
{
  "data": {
    "clusters": [
      {
        "latitude": 30.25,
        "longitude": 120.16,
        "count": 15,
        "representative": { "id": "a1b2c3d4-...", "name": "广济桥" }
      }
    ],
    "points": [
      {
        "id": "f7a8b9c0-...",
        "name": "赵州桥",
        "bridge_type": "石拱桥",
        "latitude": 37.7652,
        "longitude": 114.7761
      }
    ]
  }
}
```

> 数据来源：`bridges` 表 + PostGIS 或应用层聚类。需要新增地理坐标字段。

### 3.3 桥梁详情
```
GET /bridges/{id}
```

> 数据来源：`bridges` 表基础信息 + 从 `chunks` 表按 taxonomy 标签聚合四大章节内容。  
> **注意：桥梁详情不设 L2。深挖类内容通过关联知识点进入。**

**响应：**
```jsonc
{
  "data": {
    "id": "f7a8b9c0-...",
    "name": "赵州桥",
    "aliases": "安济桥, 大石桥",
    "bridge_type": "石拱桥",
    "era": "隋唐",
    "region": "河北省 石家庄市 赵县",
    "latitude": 37.7652,
    "longitude": 114.7761,
    "tags": ["石拱", "敞肩拱", "全国重点文物保护单位"],
    "images": [
      { "url": "https://...", "caption": "赵州桥全景", "type": "photo" }
    ],

    "sections": {
      "structure": {
        "l0": [
          { "id": "d1e2f3a4-...", "summary": "单孔敞肩石拱桥，净跨 37.02 米", "order": 1 }
        ],
        "l1": [
          {
            "id": "d1e2f3a4-...",
            "summary": "单孔敞肩石拱桥，净跨 37.02 米",
            "detail": "赵州桥为单孔圆弧石拱桥，拱圈由 28 道独立拱券并列砌筑……",
            "citations": [1, 2]
          }
        ]
      },
      "geography": {
        "l0": [],
        "l1": []
      },
      "society": {
        "l0": [],
        "l1": []
      },
      "history": {
        "l0": [],
        "l1": []
      }
    },

    "related_knowledge_points": [
      { "id": "a3b4c5d6-...", "name": "敞肩拱", "relevance": "本桥核心结构特征" }
    ],

    "sources": [
      {
        "id": 1,
        "title": "中国古代桥梁",
        "author": "唐寰澄",
        "type": "book",
        "excerpt": "赵州桥为现存最古老的敞肩拱石桥……",
        "location": "第五章"
      }
    ],
    "sources_count": 8
  }
}
```

### 3.4 桥梁的关联知识点
```
GET /bridges/{id}/knowledge-points
```

**响应：**
```jsonc
{
  "data": {
    "knowledge_points": [
      { "id": "a3b4c5d6-...", "name": "敞肩拱", "line": "形制与技术", "relevance": "本桥核心结构特征" }
    ]
  }
}
```

---

## 4. 搜索

### 4.1 统一搜索
```
GET /search
```

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 搜索关键词 |
| `type` | string | 否 | `"all"` / `"knowledge_point"` / `"bridge"` |
| `bridge_type` | string | 否 | 仅 type=bridge 时生效 |
| `era` | string | 否 | 仅 type=bridge 时生效 |
| `region` | string | 否 | 仅 type=bridge 时生效 |
| `line` | string | 否 | 仅 type=knowledge_point 时生效，主线名称 |
| `category` | string | 否 | 仅 type=knowledge_point 时生效，二级分类名称 |
| `page`, `page_size` | integer | 否 | 分页 |

> 数据来源：`bridges` 表名称/别名搜索 + `knowledge_points` 表名称搜索。可复用现有 `Tokenizer` 做中文分词。

**响应：**
```jsonc
{
  "data": {
    "results": [
      {
        "type": "bridge",
        "id": "f7a8b9c0-...",
        "name": "赵州桥",
        "aliases": "安济桥",
        "highlight": "河北省赵县的<em>赵州桥</em>",
        "bridge_type": "石拱桥",
        "era": "隋唐",
        "region": "河北省 石家庄市 赵县",
        "latitude": 37.7652,
        "longitude": 114.7761,
        "line": null,
        "thumbnail": null
      },
      {
        "type": "knowledge_point",
        "id": "c9d0e1f2-...",
        "name": "拱桥结构",
        "aliases": null,
        "highlight": "<em>拱桥</em>以拱圈为主要承重构件",
        "bridge_type": null,
        "era": null,
        "region": null,
        "latitude": null,
        "longitude": null,
        "line": "形制与技术",
        "thumbnail": null
      }
    ],
    "suggestions": []
  },
  "meta": { "total": 5, "page": 1, "page_size": 20, "has_more": false }
}
```

---

## 5. 识景（拍照识桥）

### 5.1 图像识别
```
POST /recognition
Content-Type: multipart/form-data
```

> 数据来源：新增服务。可基于 bridge 图片库做向量匹配，或调用外部视觉模型。MVP 可简化为基于图片 embedding 与 bridge 图片库的相似度匹配。

**请求字段：**
| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `image` | file | 是 | JPEG/PNG，≤ 5MB |
| `latitude` | number | 否 | GPS 纬度 |
| `longitude` | number | 否 | GPS 经度 |

**响应（成功）：**
```jsonc
{
  "data": {
    "candidates": [
      {
        "bridge_id": "f7a8b9c0-...",
        "name": "赵州桥",
        "bridge_type": "石拱桥",
        "era": "隋唐",
        "region": "河北省 石家庄市 赵县",
        "thumbnail": null,
        "confidence_hints": ["拱形结构特征匹配", "敞肩拱造型吻合", "地理位置接近"]
      }
    ]
  }
}
```

**响应（无法识别）：**
```jsonc
{
  "data": {
    "candidates": [],
    "fallback_suggestions": {
      "search_hint": "石拱桥",    // 可为 null
      "region_hint": "河北省"      // 可为 null（无 GPS 且图像无法推断地区时）
    }
  }
}
```

---

## 6. 问答（RAG + SSE 流式）

### 6.1 发起提问
```
POST /qa/ask
Content-Type: application/json
Accept: text/event-stream
```

> 数据来源：复用现有 `HybridRetriever` + `Generator`，但需要改造为 SSE 流式输出。现有 `/api/v1/ask` 是同步 JSON 返回，移动端需要 SSE。

**请求体：**
```jsonc
{
  "question": "赵州桥的敞肩拱有什么结构优势？",
  "context": {
    "type": "bridge",          // "bridge" / "knowledge_point" / "search" / "map" / null
    "id": "f7a8b9c0-...",     // bridge 或 knowledge_point 的 UUID
    "filters": {}              // search/map 上下文时传筛选条件
  }
}
```

> `X-Device-Id` 在本端点为可选。MVP 不使用，但为后续"提问历史"、"个性化推荐"预留接口。

**SSE 事件流：**

```
event: started
data: {"qa_id": "a1b2c3d4-..."}

event: outline
data: {"key_points": [{"id": "e5f6a7b8-...", "summary": "...", "order": 1}, ...]}

event: detail
data: {"key_point_id": "e5f6a7b8-...", "explanation": "...", "citations": [1, 2]}

event: detail
data: {"key_point_id": "c9d0e1f2-...", "explanation": "...", "citations": [3]}

event: deep_dive
data: {"comparisons": [...], "controversies": [], "further_reading": []}

event: sources
data: {"sources": [{"id": 1, "title": "...", "author": "...", "type": "book", "excerpt": "...", "location": "..."}]}

event: done
data: {"qa_id": "a1b2c3d4-..."}
```

> **心跳与超时：** 服务端每 15 秒发送 `event: ping\ndata: {}\n\n` 心跳事件，客户端据此判断连接存活。总超时 60 秒，超时后发送 `event: error` 并关闭连接。
>
> **断线重连：** 本接口不支持 `Last-Event-Id` 断线续传。SSE 连接断开后，客户端应重新发起 `POST /qa/ask` 请求。

**错误事件（证据不足）：**
```
event: error
data: {
  "code": "INSUFFICIENT_EVIDENCE",
  "message": "未找到直接证据，建议换一种问法或缩小范围",
  "fallback_actions": [
    {"type": "switch_context", "label": "搜索全部知识库"},
    {"type": "related_knowledge", "label": "查看相关知识点", "ids": ["a3b4c5d6-..."]},
    {"type": "bridge_detail", "label": "查看桥梁详情", "id": "f7a8b9c0-..."}
  ]
}
```

**与现有 `/api/v1/ask` 的关系：**
- 现有端点：`POST /api/v1/ask` → 同步 JSON，含 `confidence` + `evidence_groups` + `debug`
- 新端点：`POST /v1/qa/ask` → SSE 流式，面向终端用户
- 底层共用 `HybridRetriever` + `Generator`
- Generator 新增 `generate_streaming()` 方法：单次 LLM 调用，输出结构化 JSON，收到完整响应后按结构拆分为多个 SSE 事件依次 yield。现有 `generate_v2()` 保持不变

---

## 7. Flash Cards

### 7.1 获取知识点的卡片列表
```
GET /knowledge/points/{id}/flashcards
```

> 数据来源：新增 `flashcards` 表。

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `card_type` | string | 否 | `"concept"` / `"identification"` / `"all"` |

**响应：**
```jsonc
{
  "data": {
    "cards": [
      {
        "id": "a1b2c3d4-...",
        "knowledge_point_id": "c9d0e1f2-...",
        "card_type": "concept",
        "front": {
          "title": "什么是拱桥？",
          "hint": "最重要的古代桥梁结构形式"
        },
        "back": {
          "answer": "以拱圈为主要承重构件的桥梁，将荷载转化为轴向压力传至拱脚。",
          "key_features": ["拱圈承重", "轴向压力", "拱脚传力"],
          "example_bridge": { "id": "f7a8b9c0-...", "name": "赵州桥" }
        }
      }
    ]
  }
}
```

---

## 8. 收藏与复习（基于 X-Device-Id）

### 8.1 获取收藏列表
```
GET /favorites
```

> 数据来源：新增 `device_favorites` 表，以 `device_id` + `target_type` + `target_id` 为唯一键。

**Query 参数：**
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 否 | `"all"` / `"bridge"` / `"knowledge_point"` / `"flashcard"` |
| `page`, `page_size` | integer | 否 | 分页 |

**响应：**
```jsonc
{
  "data": {
    "items": [
      {
        "id": "d4e5f6a7-...",
        "target_type": "bridge",
        "target_id": "f7a8b9c0-...",
        "target_name": "赵州桥",
        "target_summary": "河北赵县，隋代敞肩拱石桥",
        "thumbnail": null,
        "created_at": "2024-06-01T10:00:00Z"
      }
    ]
  },
  "meta": { "total": 15, "page": 1, "page_size": 20, "has_more": false }
}
```

### 8.2 添加收藏
```
POST /favorites
```

**请求体：**
```jsonc
{ "target_type": "bridge", "target_id": "f7a8b9c0-..." }
```

**响应：** `201`
```jsonc
{
  "data": {
    "id": "d4e5f6a7-...",
    "target_type": "bridge",
    "target_id": "f7a8b9c0-...",
    "created_at": "2024-06-01T10:00:00Z"
  }
}
```

### 8.3 取消收藏
```
DELETE /favorites/{favorite_id}
```

**响应：** `204 No Content`

### 8.4 批量检查收藏状态
```
POST /favorites/check
```

**请求体：**
```jsonc
{
  "targets": [
    { "type": "bridge", "id": "f7a8b9c0-..." },
    { "type": "knowledge_point", "id": "a3b4c5d6-..." }
  ]
}
```

**响应：**
```jsonc
{
  "data": {
    "results": {
      "f7a8b9c0-...": { "favorited": true, "favorite_id": "d4e5f6a7-..." },
      "a3b4c5d6-...": { "favorited": false, "favorite_id": null }
    }
  }
}
```

> UUID 全局唯一，无需 type 前缀。客户端直接用实体 UUID 做 key lookup。

### 8.5 获取今日复习队列
```
GET /review/today
```

> 数据来源：`device_favorites` 表中 target_type=flashcard 的记录 + `device_review_progress` 表。
>
> **MVP 复习规则：** 返回所有 `mastery = 'needs_review'` 的卡片，以及 `mastery = 'mastered'` 但 `last_reviewed_at` 距今超过 3 天的卡片。按 `last_reviewed_at ASC` 排序（最久未复习的排前面）。

**响应：**
```jsonc
{
  "data": {
    "cards": [
      {
        "id": "a1b2c3d4-...",
        "card_type": "concept",
        "front": { "title": "什么是拱桥？", "hint": "..." },
        "back": { "answer": "...", "key_features": [...], "example_bridge": {...} },
        "last_reviewed_at": "2024-05-30T10:00:00Z",
        "mastery": "needs_review"      // "mastered" / "needs_review"
      }
    ],
    "total_due": 5
  }
}
```

### 8.6 更新复习进度
```
PUT /review/progress/{flashcard_id}
```

**请求体：**
```jsonc
{ "mastery": "mastered" }   // "mastered" / "needs_review"
```

**响应：** `200`
```jsonc
{ "data": { "flashcard_id": "a1b2c3d4-...", "mastery": "mastered", "reviewed_at": "2024-06-01T10:00:00Z" } }
```

### 8.7 获取所有已收藏卡片
```
GET /review/cards
```

> 返回当前设备收藏的所有 flashcard 的完整内容（front/back），支持分页。与 `/review/today`（只返回今日待复习子集）互补。

**Query 参数：** `page`, `page_size`

**响应：**
```jsonc
{
  "data": {
    "cards": [
      {
        "id": "a1b2c3d4-...",
        "card_type": "concept",
        "front": { "title": "什么是拱桥？", "hint": "..." },
        "back": { "answer": "...", "key_features": [...], "example_bridge": {...} },
        "last_reviewed_at": "2024-05-30T10:00:00Z",
        "mastery": "needs_review"
      }
    ]
  },
  "meta": { "total": 12, "page": 1, "page_size": 20, "has_more": false }
}
```

### 8.8 获取浏览历史
```
GET /history
```

> 数据来源：新增 `device_view_history` 表。

**Query 参数：** `page`, `page_size`

**响应：**
```jsonc
{
  "data": {
    "items": [
      {
        "target_type": "bridge",
        "target_id": "f7a8b9c0-...",
        "target_name": "赵州桥",
        "viewed_at": "2024-06-01T09:30:00Z"
      }
    ]
  },
  "meta": { "total": 30, "page": 1, "page_size": 20, "has_more": true }
}
```

### 8.9 记录浏览
```
POST /history
```

**请求体：**
```jsonc
{ "target_type": "bridge", "target_id": "f7a8b9c0-..." }
```

**响应：** `201`

---

## 9. 端点总表

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/config` | 应用配置 | 无 |
| GET | `/knowledge/tree` | 知识架构树 | 无 |
| GET | `/knowledge/points/{id}` | 知识点详情 | 无 |
| GET | `/knowledge/points/{id}/bridges` | 知识点典型桥梁 | 无 |
| GET | `/knowledge/points/{id}/flashcards` | 知识点卡片 | 无 |
| GET | `/bridges` | 桥梁列表 | 无 |
| GET | `/bridges/clusters` | 地图聚类 | 无 |
| GET | `/bridges/{id}` | 桥梁详情 | 无 |
| GET | `/bridges/{id}/knowledge-points` | 桥梁关联知识点 | 无 |
| GET | `/search` | 统一搜索 | 无 |
| POST | `/recognition` | 拍照识桥 | 无 |
| POST | `/qa/ask` | 问答（SSE） | 可选 X-Device-Id |
| GET | `/favorites` | 收藏列表 | X-Device-Id |
| POST | `/favorites` | 添加收藏 | X-Device-Id |
| DELETE | `/favorites/{id}` | 取消收藏 | X-Device-Id |
| POST | `/favorites/check` | 批量检查收藏 | X-Device-Id |
| GET | `/review/today` | 今日复习 | X-Device-Id |
| GET | `/review/cards` | 全部已收藏卡片 | X-Device-Id |
| PUT | `/review/progress/{id}` | 更新复习进度 | X-Device-Id |
| GET | `/history` | 浏览历史 | X-Device-Id |
| POST | `/history` | 记录浏览 | X-Device-Id |

---
