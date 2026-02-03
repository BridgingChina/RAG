# V1 检索增强设计方案

> 日期：2026-02-04
> 状态：待实现
> 依赖：V0 核心功能已完成

## 概述

本方案为 Bridge RAG 系统的 V1 检索增强，包含三个核心功能：

1. **Contextual Text（上下文增强索引）**：为每个 chunk 生成富含上下文的描述，改善 embedding 质量
2. **PostgreSQL FTS（全文检索）**：添加关键词检索能力，补充向量检索盲区
3. **双通道检索（本桥为主 + 类比拓展）**：先找本桥证据，再找相似桥证据做类比

---

## 技术决策总结

| 决策点 | 选定方案 |
|--------|----------|
| 设计范围 | 完整方案（三个功能一起实现） |
| Contextual Text 生成时机 | Ingest 时同步生成 |
| 中文分词 | jieba（Python 端预处理） |
| Analogy 候选桥选择 | LLM 从 Query 抽取 Facet，动态匹配 |
| Facet 抽取方式 | 轻量 LLM 调用 + 枚举约束 |
| Concept/General 识别 | `bridge_id = NULL` |
| 双路召回融合 | RRF (k=60) |
| 配额分配 | Anchor 6 + Concept 2 + Analogy 2 = 10 条 |
| 可信度判断 | LLM 直接输出 confidence |

---

## 一、数据模型变更

### Chunk 表新增字段

```sql
ALTER TABLE chunks ADD COLUMN contextual_text TEXT;
ALTER TABLE chunks ADD COLUMN search_text TEXT;
ALTER TABLE chunks ADD COLUMN tsv tsvector;

CREATE INDEX idx_chunks_tsv ON chunks USING GIN(tsv);
```

| 字段 | 类型 | 用途 |
|------|------|------|
| `contextual_text` | TEXT | 80-160 字的上下文描述，含来源、主题、实体、指代消歧 |
| `search_text` | TEXT | `contextual_text + "\n\n" + content`，作为 embedding 输入 |
| `tsv` | tsvector | jieba 分词后的全文检索向量 |

### 迁移策略

- 新字段允许 NULL，兼容已有数据
- 提供迁移脚本为旧 chunk 补充生成 contextual_text

---

## 二、Contextual Text 生成服务

### 新增服务 `app/services/context_enricher.py`

```python
class ContextEnricher:
    """为 chunk 生成上下文增强描述"""

    async def enrich(
        self,
        content: str,
        source_title: str,
        section_title: str | None,
        page_range: str | None,
        surrounding_chunks: list[str] | None = None
    ) -> ContextResult:
        """
        返回:
        - contextual_text: 80-160 字的上下文描述
        - entities: 抽取的实体列表（桥名、术语等）
        """
```

### LLM Prompt 设计

```
你是桥梁知识整理助手。请为以下文本片段生成一段上下文描述（80-160字）。

【来源】{source_title}
【章节】{section_title}
【页码】{page_range}
【前文摘要】{prev_chunk_summary}
【文本片段】
{content}

请输出 JSON：
{
  "contextual_text": "该片段来自《xxx》第x章，主要介绍...",
  "entities": ["赵州桥", "敞肩式", "石拱桥"],
  "resolved_references": {"该桥": "赵州桥", "它": "赵州桥"}
}

要求：
1. contextual_text 需包含：来源位置、主题概述、关键术语
2. 如有「该桥/它/此结构」等指代，明确写出指代对象
3. 如无法确定指代对象，写 "unknown"
```

---

## 三、FTS 全文检索实现

### 分词工具 `app/services/tokenizer.py`

```python
import jieba

class Tokenizer:
    """中文分词器，支持自定义桥梁术语词典"""

    def __init__(self, user_dict_path: str | None = None):
        if user_dict_path:
            jieba.load_userdict(user_dict_path)

    def tokenize(self, text: str) -> list[str]:
        """分词，返回词列表"""
        return list(jieba.cut_for_search(text))

    def to_tsquery(self, text: str) -> str:
        """转换为 PostgreSQL tsquery 格式"""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        return " & ".join(words)

    def to_tsvector_text(self, text: str) -> str:
        """转换为空格分隔的词序列，用于存入 tsvector"""
        words = [w.strip() for w in self.tokenize(text) if len(w.strip()) > 1]
        return " ".join(words)
```

### 自定义词典 `data/bridge_terms.txt`

```
敞肩式 n
实腹式 n
系杆拱 n
斜拉桥 n
悬索桥 n
赵州桥 nr
卢沟桥 nr
广济桥 nr
```

### 查询时的 FTS 检索

```python
def fts_search(query: str, filters: dict, limit: int = 20) -> list[ChunkScore]:
    tsquery = tokenizer.to_tsquery(query)
    sql = """
        SELECT id, ts_rank(tsv, plainto_tsquery('simple', :tsquery)) as score
        FROM chunks
        WHERE tsv @@ plainto_tsquery('simple', :tsquery)
          AND (:bridge_id IS NULL OR bridge_id = :bridge_id)
        ORDER BY score DESC
        LIMIT :limit
    """
```

---

## 四、双通道检索架构

### 检索流程

```
┌─────────────────────────────────────────────────────────────┐
│                        用户问题                              │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
   ┌─────────────┐                 ┌─────────────┐
   │ Query 向量化 │                 │ Facet 抽取  │ (LLM)
   └──────┬──────┘                 └──────┬──────┘
          │                               │
          │         ┌─────────────────────┘
          │         ▼
          │   候选桥选择 (bridges 表匹配)
          │         │
          ▼         ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    三通道并行召回                          │
   │  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
   │  │  Anchor    │  │  Concept   │  │  Analogy   │         │
   │  │ bridge_id= │  │ bridge_id  │  │ bridge_id  │         │
   │  │ target     │  │ IS NULL    │  │ IN (...)   │         │
   │  │            │  │            │  │ 每桥限1条   │         │
   │  │ Vec + FTS  │  │ Vec + FTS  │  │ Vec + FTS  │         │
   │  │  ↓ RRF ↓   │  │  ↓ RRF ↓   │  │  ↓ RRF ↓   │         │
   │  │  Top 6     │  │  Top 2     │  │  Top 2     │         │
   │  └────────────┘  └────────────┘  └────────────┘         │
   └──────────────────────────────────────────────────────────┘
                          │
                          ▼
                ┌─────────────────┐
                │ 去重 + 按组打包   │
                └────────┬────────┘
                         ▼
                 HybridRetrievalResult
```

### 新增检索器 `app/services/hybrid_retriever.py`

```python
class HybridRetriever:
    """双通道混合检索：Anchor(本桥) + Concept(通用) + Analogy(类比)"""

    async def retrieve(
        self,
        query: str,
        target_bridge_id: int | None,
        context: RetrievalContext | None = None,
        quota: RetrievalQuota = (6, 2, 2)
    ) -> HybridRetrievalResult:
        """
        返回三组证据：
        - anchor_chunks: 本桥证据 (最多 6 条)
        - concept_chunks: 通用概念 (最多 2 条)
        - analogy_chunks: 类比桥证据 (最多 2 条)
        """
```

---

## 五、Facet 抽取与候选桥选择

### 预定义枚举值 `app/constants/facets.py`

```python
BRIDGE_TYPES = ["石拱桥", "木拱桥", "铁桥", "悬索桥", "斜拉桥", "梁桥", "浮桥", "索桥"]
MATERIALS = ["石", "木", "铁", "钢", "钢筋混凝土", "竹", "砖"]
ERAS = ["先秦", "秦汉", "魏晋南北朝", "隋唐", "宋元", "明清", "近现代", "当代"]
REGIONS = ["华北", "华东", "华南", "华中", "西南", "西北", "东北", "港澳台"]
FUNCTIONS = ["交通", "军事", "景观", "水利", "铁路", "公路", "人行"]
```

### Facet 抽取 Prompt（枚举约束版）

```
分析以下关于桥梁的问题，提取涉及的桥梁属性。

【问题】{query}

【枚举值约束 - 只能从以下选项中选择，可多选】
- bridge_type: {bridge_types}
- material: {materials}
- era: {eras}
- region: {regions}
- function: {functions}

输出 JSON（无关维度填 null，相关维度可以是单值或数组）：
{
  "bridge_type": "石拱桥" 或 ["石拱桥", "木拱桥"] 或 null,
  "material": ...,
  "era": ...,
  "region": ...,
  "function": ...
}
```

### 候选桥选择逻辑

```python
async def select_candidate_bridges(
    self,
    facet: Facet,
    target_bridge_id: int | None,
    limit: int = 5
) -> list[int]:
    """根据 facet 从 bridges 表中选择相似桥"""

    conditions = []
    if facet.bridge_type:
        conditions.append("bridge_type = ANY(:bridge_types)")
    if facet.material:
        conditions.append("material = ANY(:materials)")
    if facet.era:
        conditions.append("era = ANY(:eras)")

    if not conditions:
        return []

    sql = f"""
        SELECT id FROM bridges
        WHERE ({" OR ".join(conditions)})
          AND id != :target_bridge_id
        ORDER BY
          (CASE WHEN bridge_type = ANY(:bridge_types) THEN 1 ELSE 0 END +
           CASE WHEN material = ANY(:materials) THEN 1 ELSE 0 END +
           CASE WHEN era = ANY(:eras) THEN 1 ELSE 0 END) DESC
        LIMIT :limit
    """
```

### Analogy 通道多样性约束

```python
def apply_diversity(chunks: list[ChunkScore], max_per_bridge: int = 1) -> list[ChunkScore]:
    """每座候选桥最多取 1 条 chunk"""
    seen_bridges = {}
    result = []
    for chunk in chunks:
        bid = chunk.bridge_id
        if bid not in seen_bridges or seen_bridges[bid] < max_per_bridge:
            result.append(chunk)
            seen_bridges[bid] = seen_bridges.get(bid, 0) + 1
    return result
```

---

## 六、RRF 融合与结果打包

### RRF 融合实现 `app/services/ranker.py`

```python
def rrf_merge(
    vec_results: list[int],
    fts_results: list[int],
    k: int = 60
) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion
    返回: [(chunk_id, rrf_score), ...] 按分数降序
    """
    scores = {}

    for rank, chunk_id in enumerate(vec_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)

    for rank, chunk_id in enumerate(fts_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)

    return sorted(scores.items(), key=lambda x: -x[1])
```

### 打包给 LLM 的格式

```python
def format_evidence_for_llm(result: HybridRetrievalResult) -> str:
    """按组打包，让 LLM 明确区分证据来源"""

    output = []

    output.append("## 本桥证据")
    for i, chunk in enumerate(result.anchor_chunks, 1):
        output.append(f"[{i}] {chunk.content[:200]}...")

    output.append("\n## 通用概念")
    for i, chunk in enumerate(result.concept_chunks, len(result.anchor_chunks)+1):
        output.append(f"[{i}] {chunk.content[:200]}...")

    output.append("\n## 类比参考（其他相似桥）")
    for i, chunk in enumerate(result.analogy_chunks, ...):
        bridge_name = get_bridge_name(chunk.bridge_id)
        output.append(f"[{i}] ({bridge_name}) {chunk.content[:200]}...")

    return "\n".join(output)
```

---

## 七、Generator 改造

### Generation Prompt

```
你是桥梁知识问答助手。请根据以下证据回答问题。

【问题】{question}

【证据】
{evidence}

【回答要求】
1. 先答本桥：优先使用「本桥证据」回答，引用格式 [1][2]
2. 再做类比：如有需要，使用「类比参考」补充说明其他桥的做法
3. 概念补充：如需解释术语，可引用「通用概念」
4. 如果本桥证据不足，明确告知「本桥相关资料有限」
5. 无证据支撑的内容标注为「常识性补充」

请按以下 JSON 格式输出：
{
  "summary": "要点（带引用）",
  "details": "详细说明",
  "analogy": "类比参考（如无则 null）",
  "confidence": {
    "level": "high | medium | low",
    "reason": "简要说明判断依据"
  }
}

confidence 判断标准：
- high: 本桥证据充分，能完整回答问题
- medium: 本桥证据部分覆盖，需借助类比或通用概念补充
- low: 本桥证据极少或无，主要依赖类比推断
```

### GenerationResult 数据结构

```python
@dataclass
class Confidence:
    level: str    # "high" | "medium" | "low"
    reason: str

@dataclass
class GenerationResult:
    summary: str
    details: str
    analogy: str | None
    citations: list[Citation]
    sources: list[str]
    confidence: Confidence
```

---

## 八、API 层变化

### `/ask` 接口调整

```python
class AskRequest(BaseModel):
    question: str
    context: RetrievalContext | None = None
    target_bridge_id: int | None = None  # 新增

class Confidence(BaseModel):
    level: str
    reason: str

class AskResponse(BaseModel):
    summary: str
    details: str
    analogy: str | None
    citations: list[Citation]
    sources: list[str]
    confidence: Confidence
    evidence_groups: EvidenceGroups | None = None
    degraded: list[str] | None = None
```

### 请求示例

```json
POST /ask
{
  "question": "这座桥的拱券结构有什么特点？",
  "target_bridge_id": 42,
  "context": {"lvl1": "形制与技术"}
}
```

### 响应示例

```json
{
  "summary": "- 赵州桥采用敞肩式拱券结构 [1][2]\n- 主拱跨度 37.02 米 [1]",
  "details": "赵州桥的拱券结构是其最显著的技术特征...",
  "analogy": "类似的敞肩式结构也见于永通桥 [8]，但跨度较小...",
  "citations": [...],
  "sources": ["《中国古桥》", "《赵州桥研究》"],
  "confidence": {
    "level": "high",
    "reason": "本桥有 4 条直接证据，涵盖结构特点"
  }
}
```

---

## 九、Ingest 流程改造

### 完整入库流水线

```
原始文档
    │
    ▼
┌─────────────────┐
│ 1. Chunker      │  语义切块 (300-500 字)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Enricher     │  生成上下文描述 (LLM)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Tagger       │  分类标注 (LLM)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 组装字段      │  search_text, tsv_text
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Embedding    │  向量化 search_text (2048 维)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. 入库         │  INSERT 含 tsvector
└─────────────────┘
```

### Ingest 服务 `app/services/ingest.py`

```python
class IngestService:
    """文档入库服务，整合完整流水线"""

    async def ingest_document(
        self,
        content: str,
        source: Source,
    ) -> list[Chunk]:
        # 1. 切块
        raw_chunks = await self.chunker.chunk(content)

        chunks = []
        for i, raw in enumerate(raw_chunks):
            # 2. 上下文增强
            ctx = await self.enricher.enrich(...)

            # 3. 标注
            tag = await self.tagger.tag(raw.content)

            # 4. 组装
            search_text = f"{ctx.contextual_text}\n\n{raw.content}"
            tsv_text = self.tokenizer.to_tsvector_text(search_text)

            # 5. 向量化
            embedding = (await self.provider.embed([search_text]))[0]

            # 6. 构建 Chunk
            chunk = Chunk(...)
            chunks.append(chunk)

        self._bulk_insert(chunks)
        return chunks
```

---

## 十、错误处理与降级策略

| 环节 | 失败场景 | 降级策略 |
|------|----------|----------|
| **Enricher** | LLM 超时/格式错误 | `contextual_text = ""`，仅用原文 |
| **Tagger** | LLM 返回无效分类 | `lvl1 = None`，不影响入库 |
| **Facet 抽取** | LLM 超时 | 跳过 Analogy 通道 |
| **FTS 召回** | 分词异常 | 降级为纯向量召回 |
| **向量召回** | pgvector 失败 | 降级为纯 FTS 召回 |
| **Generator** | LLM 返回非 JSON | 正则兜底解析 |

### 响应中标记降级

```python
class AskResponse(BaseModel):
    ...
    degraded: list[str] | None = None  # 如 ["facet_extraction"]
```

---

## 十一、测试策略

### 新增测试文件

| 文件 | 测试内容 |
|------|----------|
| `test_context_enricher.py` | 上下文生成、指代消歧 |
| `test_tokenizer.py` | jieba 分词、自定义词典 |
| `test_facet_extractor.py` | Facet 抽取、枚举约束 |
| `test_hybrid_retriever.py` | 三通道召回、RRF、配额 |
| `test_ingest.py` | 完整入库流程 |
| `test_fts.py` | FTS 索引、中文检索 |

### 关键测试用例

```python
async def test_anchor_channel_prioritized():
    """本桥证据应占多数"""
    result = await retriever.retrieve(query="...", target_bridge_id=1)
    assert len(result.anchor_chunks) == 6
    assert all(c.bridge_id == 1 for c in result.anchor_chunks)

async def test_analogy_diversity():
    """类比证据每桥最多 1 条"""
    result = await retriever.retrieve(...)
    bridge_ids = [c.bridge_id for c in result.analogy_chunks]
    assert len(bridge_ids) == len(set(bridge_ids))

async def test_rrf_merge_correctness():
    """RRF 融合正确性"""
    vec = [1, 2, 3]
    fts = [2, 4, 1]
    merged = rrf_merge(vec, fts, k=60)
    assert merged[0][0] == 2  # chunk 2 两路都靠前
```

---

## 十二、新增/改动组件清单

```
app/
├── services/
│   ├── context_enricher.py   # 新增
│   ├── tokenizer.py          # 新增
│   ├── facet_extractor.py    # 新增
│   ├── hybrid_retriever.py   # 新增
│   ├── ranker.py             # 新增
│   ├── ingest.py             # 新增
│   ├── generator.py          # 改造
│   └── retriever.py          # 保留兼容
├── constants/
│   └── facets.py             # 新增
├── api/
│   └── schemas.py            # 改造
data/
└── bridge_terms.txt          # 新增
```

---

## 十三、实施顺序建议

1. **数据模型变更** — 添加字段和索引
2. **Tokenizer + FTS** — 分词和全文检索基础
3. **Context Enricher** — 上下文增强服务
4. **Ingest 流程改造** — 整合入库流水线
5. **Facet Extractor** — 查询维度抽取
6. **Hybrid Retriever** — 三通道混合检索
7. **Generator 改造** — 分组回答 + confidence
8. **API 层调整** — 新增字段和响应格式
9. **测试补充** — 各组件单测 + 集成测试
10. **数据迁移** — 为旧 chunk 补充生成 contextual_text
