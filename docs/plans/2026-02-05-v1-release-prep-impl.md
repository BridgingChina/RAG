# V1.0.0 发布准备实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Bridge RAG System 从开发版本重构为 V1.0.0 正式版本，包括 API 版本化、常量配置化、代码清理和文档完善。

**Architecture:** 将常量从代码迁移到 YAML 配置文件，API 路由重构为 `/api/v1/` 前缀，移除 V0 废弃代码，添加 Markdown 入库解析器，创建完整测试数据集。

**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL + pgvector, PyYAML, jieba

---

## Task 1: 添加 PyYAML 依赖

**Files:**
- Modify: `pyproject.toml:6-17`

**Step 1: 修改 pyproject.toml 添加 pyyaml 依赖**

在 `dependencies` 列表中添加 `pyyaml>=6.0`：

```toml
dependencies = [
    "click>=8.0.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "psycopg>=3.1.0",
    "pgvector>=0.2.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.26.0",
    "jieba>=0.42.1",
    "pyyaml>=6.0",
]
```

**Step 2: 重新安装依赖**

Run: `pip install -e ".[dev]"`
Expected: 成功安装，输出包含 pyyaml

**Step 3: 验证安装**

Run: `python -c "import yaml; print(yaml.__version__)"`
Expected: 输出版本号如 `6.0.1`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyyaml dependency for config loading"
```

---

## Task 2: 创建 YAML 配置文件

**Files:**
- Create: `config/taxonomy.yaml`
- Create: `config/facets.yaml`

**Step 1: 创建 config 目录**

Run: `mkdir -p config`

**Step 2: 创建 taxonomy.yaml**

```yaml
# 三级知识分类体系
# lvl1 -> lvl2 -> lvl3

taxonomy:
  形制与技术:
    结构体系:
      - 拱桥结构
      - 梁桥结构
      - 悬索结构
      - 斜拉结构
      - 组合结构
    构造细部:
      - 桥墩设计
      - 桥台构造
      - 栏杆装饰
      - 桥面铺装
      - 伸缩缝节点
    材料工艺:
      - 石材加工
      - 木材处理
      - 铁件锻造
      - 混凝土浇筑
    建造技术:
      - 施工方法
      - 测量定位
      - 脚手架搭设
      - 吊装技术

  地域与环境:
    水文地形:
      - 河流特征
      - 峡谷地形
      - 平原水网
      - 山区溪流
    气候特征:
      - 季节洪水
      - 冻融循环
      - 台风影响
      - 干旱环境
    地质条件:
      - 地基处理
      - 岩土特性
      - 地震设防
      - 软土加固

  功能与社会:
    交通功能:
      - 公路通行
      - 铁路运输
      - 人行通道
      - 综合交通
    军事防御:
      - 关隘要塞
      - 战略要道
      - 防御工事
    景观价值:
      - 风景名胜
      - 文化地标
      - 园林景观
      - 城市名片

  历史与演变:
    建造年代:
      - 始建时间
      - 建造背景
      - 工匠记载
    修缮记录:
      - 历代维修
      - 重建改造
      - 现代修复
    变迁历史:
      - 功能变化
      - 名称演变
      - 归属变更
```

**Step 3: 创建 facets.yaml**

```yaml
# Facet 枚举值定义
# 用于 FacetExtractor 约束和 Bridge 属性校验

bridge_types:
  - 石拱桥
  - 木拱桥
  - 铁桥
  - 悬索桥
  - 斜拉桥
  - 梁桥
  - 浮桥
  - 索桥

materials:
  - 石
  - 木
  - 铁
  - 钢
  - 钢筋混凝土
  - 竹
  - 砖

eras:
  - 先秦
  - 秦汉
  - 魏晋南北朝
  - 隋唐
  - 宋元
  - 明清
  - 近现代
  - 当代

regions:
  - 华北
  - 华东
  - 华南
  - 华中
  - 西南
  - 西北
  - 东北
  - 港澳台

functions:
  - 交通
  - 军事
  - 景观
  - 水利
  - 铁路
  - 公路
  - 人行
```

**Step 4: 验证 YAML 格式**

Run: `python -c "import yaml; yaml.safe_load(open('config/taxonomy.yaml')); yaml.safe_load(open('config/facets.yaml')); print('YAML valid')"`
Expected: `YAML valid`

**Step 5: Commit**

```bash
git add config/
git commit -m "feat: add YAML config files for taxonomy and facets"
```

---

## Task 3: 创建常量加载模块

**Files:**
- Create: `app/core/constants.py`
- Create: `tests/test_constants.py`

**Step 1: 创建 tests/test_constants.py 测试文件**

```python
"""Tests for constants loading module."""
import pytest


def test_load_taxonomy_returns_dict():
    """Test that load_taxonomy returns a nested dict."""
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()

    assert isinstance(taxonomy, dict)
    assert "形制与技术" in taxonomy
    assert "地域与环境" in taxonomy
    assert "功能与社会" in taxonomy
    assert "历史与演变" in taxonomy


def test_load_taxonomy_has_three_levels():
    """Test that taxonomy has lvl1 -> lvl2 -> lvl3 structure."""
    from app.core.constants import load_taxonomy

    taxonomy = load_taxonomy()

    # lvl1 -> lvl2 -> [lvl3]
    assert "结构体系" in taxonomy["形制与技术"]
    assert isinstance(taxonomy["形制与技术"]["结构体系"], list)
    assert "拱桥结构" in taxonomy["形制与技术"]["结构体系"]


def test_load_facets_returns_dict():
    """Test that load_facets returns facet enums."""
    from app.core.constants import load_facets

    facets = load_facets()

    assert isinstance(facets, dict)
    assert "bridge_types" in facets
    assert "materials" in facets
    assert "eras" in facets
    assert "regions" in facets
    assert "functions" in facets


def test_load_facets_bridge_types():
    """Test bridge_types facet values."""
    from app.core.constants import load_facets

    facets = load_facets()

    assert "石拱桥" in facets["bridge_types"]
    assert "木拱桥" in facets["bridge_types"]
    assert "悬索桥" in facets["bridge_types"]


def test_get_taxonomy_lvl1():
    """Test helper to get lvl1 list."""
    from app.core.constants import get_taxonomy_lvl1

    lvl1_list = get_taxonomy_lvl1()

    assert lvl1_list == ["形制与技术", "地域与环境", "功能与社会", "历史与演变"]


def test_get_taxonomy_lvl2():
    """Test helper to get lvl2 list for a given lvl1."""
    from app.core.constants import get_taxonomy_lvl2

    lvl2_list = get_taxonomy_lvl2("形制与技术")

    assert "结构体系" in lvl2_list
    assert "构造细部" in lvl2_list


def test_get_taxonomy_lvl3():
    """Test helper to get lvl3 list for given lvl1 and lvl2."""
    from app.core.constants import get_taxonomy_lvl3

    lvl3_list = get_taxonomy_lvl3("形制与技术", "结构体系")

    assert "拱桥结构" in lvl3_list
    assert "梁桥结构" in lvl3_list
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/test_constants.py -v`
Expected: FAIL with "cannot import name 'load_taxonomy'"

**Step 3: 创建 app/core/constants.py**

```python
"""Constants loading from YAML configuration files."""
from functools import lru_cache
from pathlib import Path

import yaml

# Config directory is at project root
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


@lru_cache
def load_taxonomy() -> dict[str, dict[str, list[str]]]:
    """Load taxonomy from YAML config.

    Returns:
        Nested dict: {lvl1: {lvl2: [lvl3, ...]}}
    """
    with open(CONFIG_DIR / "taxonomy.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["taxonomy"]


@lru_cache
def load_facets() -> dict[str, list[str]]:
    """Load facet enums from YAML config.

    Returns:
        Dict with keys: bridge_types, materials, eras, regions, functions
    """
    with open(CONFIG_DIR / "facets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy_lvl1() -> list[str]:
    """Get list of lvl1 taxonomy categories."""
    return list(load_taxonomy().keys())


def get_taxonomy_lvl2(lvl1: str) -> list[str]:
    """Get list of lvl2 categories for a given lvl1."""
    taxonomy = load_taxonomy()
    if lvl1 in taxonomy:
        return list(taxonomy[lvl1].keys())
    return []


def get_taxonomy_lvl3(lvl1: str, lvl2: str) -> list[str]:
    """Get list of lvl3 items for given lvl1 and lvl2."""
    taxonomy = load_taxonomy()
    if lvl1 in taxonomy and lvl2 in taxonomy[lvl1]:
        return taxonomy[lvl1][lvl2]
    return []
```

**Step 4: 运行测试验证通过**

Run: `pytest tests/test_constants.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add app/core/constants.py tests/test_constants.py
git commit -m "feat: add constants loading module with YAML support"
```

---

## Task 4: 更新 Tagger 使用配置常量

**Files:**
- Modify: `app/services/tagger.py`
- Modify: `tests/test_tagger.py`

**Step 1: 更新 tests/test_tagger.py 的导入**

将：
```python
from app.services.tagger import MetadataTagger, TagResult, TAXONOMY_LVL1
```

改为：
```python
from app.services.tagger import MetadataTagger, TagResult
from app.core.constants import get_taxonomy_lvl1
```

并更新测试：
```python
def test_taxonomy_lvl1_values():
    """Test that TAXONOMY_LVL1 contains expected values."""
    lvl1_list = get_taxonomy_lvl1()
    assert "形制与技术" in lvl1_list
    assert "地域与环境" in lvl1_list
    assert "功能与社会" in lvl1_list
    assert "历史与演变" in lvl1_list
```

**Step 2: 运行测试验证当前状态**

Run: `pytest tests/test_tagger.py -v`
Expected: 可能 FAIL（因为导入变了）

**Step 3: 更新 app/services/tagger.py**

将：
```python
# Fixed taxonomy for V0
TAXONOMY_LVL1 = ["形制与技术", "地域与环境", "功能与社会", "历史与演变"]
```

改为：
```python
from app.core.constants import get_taxonomy_lvl1, load_taxonomy
```

并更新 `_parse_response` 方法：
```python
def _parse_response(self, content: str) -> TagResult:
    """Parse LLM response to TagResult."""
    try:
        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            data = json.loads(json_match.group())
            lvl1 = data.get("lvl1")
            lvl2 = data.get("lvl2")
            lvl3 = data.get("lvl3")

            # Validate lvl1
            if lvl1 not in get_taxonomy_lvl1():
                lvl1 = None

            return TagResult(
                lvl1=lvl1,
                lvl2=lvl2,
                lvl3=lvl3,
                bridge_id=data.get("bridge_name"),
            )
    except (json.JSONDecodeError, AttributeError):
        pass

    return TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
```

同时更新 prompt 模板以包含三级分类提示（修改 `tag` 方法）。

**Step 4: 运行测试验证通过**

Run: `pytest tests/test_tagger.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/services/tagger.py tests/test_tagger.py
git commit -m "refactor: update tagger to use YAML config for taxonomy"
```

---

## Task 5: 更新 FacetExtractor 使用配置常量

**Files:**
- Modify: `app/services/facet_extractor.py`
- Modify: `tests/test_facet_extractor.py`
- Delete: `app/constants/facets.py`
- Delete: `app/constants/__init__.py`

**Step 1: 读取当前 facet_extractor.py 了解导入**

**Step 2: 更新 app/services/facet_extractor.py**

将：
```python
from app.constants.facets import BRIDGE_TYPES, ERAS, FUNCTIONS, MATERIALS, REGIONS
```

改为：
```python
from app.core.constants import load_facets
```

并在需要使用的地方调用：
```python
facets = load_facets()
bridge_types = facets["bridge_types"]
materials = facets["materials"]
# etc.
```

**Step 3: 更新 tests/test_facet_extractor.py**

更新任何直接引用 `app.constants.facets` 的地方。

**Step 4: 更新 tests/test_facets.py**

这个测试文件测试 facets 常量，需要改为测试从 YAML 加载的 facets：
```python
"""Tests for facet constants loaded from YAML."""
from app.core.constants import load_facets


def test_bridge_types_exist():
    """Test that bridge_types are loaded."""
    facets = load_facets()
    assert "石拱桥" in facets["bridge_types"]
    assert "木拱桥" in facets["bridge_types"]


def test_materials_exist():
    """Test that materials are loaded."""
    facets = load_facets()
    assert "石" in facets["materials"]
    assert "木" in facets["materials"]


def test_eras_exist():
    """Test that eras are loaded."""
    facets = load_facets()
    assert "隋唐" in facets["eras"]
    assert "明清" in facets["eras"]
```

**Step 5: 删除旧的 constants 目录**

Run: `rm -rf app/constants/`

**Step 6: 运行相关测试**

Run: `pytest tests/test_facet_extractor.py tests/test_facets.py -v`
Expected: all passed

**Step 7: 运行全部测试确认无破坏**

Run: `pytest tests/ -v`
Expected: all passed

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: migrate facets to YAML config, remove app/constants/"
```

---

## Task 6: 更新 ingest.py 使用配置常量

**Files:**
- Modify: `scripts/ingest.py`

**Step 1: 更新 scripts/ingest.py**

删除硬编码的 `TAXONOMY_LVL2`，改为从配置加载：

将：
```python
# Lvl2 taxonomy (optional, for better classification)
TAXONOMY_LVL2 = {
    "形制与技术": ["结构体系", "构造细部", "材料工艺", "建造技术"],
    "地域与环境": ["水文地形", "气候特征", "地质条件"],
    "功能与社会": ["交通功能", "军事防御", "景观价值"],
    "历史与演变": ["建造年代", "修缮记录", "变迁历史"],
}
```

改为：
```python
from app.core.constants import load_taxonomy

def get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}
```

并在 `ingest_text` 函数中使用：
```python
taxonomy_lvl2 = get_taxonomy_lvl2_map()
tagger = MetadataTagger(provider=provider, taxonomy_lvl2=taxonomy_lvl2)
```

**Step 2: 验证脚本可导入**

Run: `python -c "from scripts.ingest import ingest_text; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/ingest.py
git commit -m "refactor: update ingest script to use YAML taxonomy config"
```

---

## Task 7: 创建 API v1 路由结构

**Files:**
- Create: `app/api/v1/__init__.py`
- Create: `app/api/v1/ask.py`
- Create: `app/api/v1/schemas.py`

**Step 1: 创建 v1 目录**

Run: `mkdir -p app/api/v1`

**Step 2: 创建 app/api/v1/schemas.py**

从 `app/api/schemas.py` 复制，移除 V0 的 `AskResponse`，只保留 V1 相关的 schema，并将 `AskResponseV2` 重命名为 `AskResponse`：

```python
"""API v1 request/response schemas."""
from typing import Literal, TypeAlias

from pydantic import BaseModel


class AskContext(BaseModel):
    """Optional context for filtering retrieval."""
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    """Request body for /api/v1/ask endpoint."""
    question: str
    target_bridge_id: int | None = None
    context: AskContext | None = None


class CitationResponse(BaseModel):
    """Citation reference in response."""
    chunk_id: int
    source_title: str
    page_range: str | None


ConfidenceLevel: TypeAlias = Literal["high", "medium", "low"]


class ConfidenceResponse(BaseModel):
    """Confidence assessment for the answer."""
    level: ConfidenceLevel
    reason: str


class ChunkSummary(BaseModel):
    """Summary of a retrieved chunk."""
    chunk_id: int
    bridge_id: int | None = None
    bridge_name: str | None = None
    preview: str


class EvidenceGroupsResponse(BaseModel):
    """Evidence grouped by retrieval channel."""
    anchor: list[ChunkSummary]
    concept: list[ChunkSummary]
    analogy: list[ChunkSummary]


class AskResponse(BaseModel):
    """Response body for /api/v1/ask endpoint."""
    summary: str
    details: str
    analogy: str | None = None
    citations: list[CitationResponse]
    sources: list[str]
    confidence: ConfidenceResponse
    evidence_groups: EvidenceGroupsResponse | None = None
    degraded: list[str] | None = None
```

**Step 3: 创建 app/api/v1/ask.py**

从旧的 `app/api/ask.py` 迁移 V1 端点（`ask_v2`），重命名为 `ask`：

```python
"""V1 Ask API endpoint."""
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.schemas import (
    AskRequest,
    AskResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator
from app.services.facet_extractor import FacetExtractor
from app.services.hybrid_retriever import HybridRetriever, HybridRetrievalResult
from app.services.tokenizer import Tokenizer

router = APIRouter()

_provider_cache: dict[object, object] = {}
_tokenizer_cache: dict[str | None, Tokenizer] = {}


def _get_provider():
    key = ZhipuProvider
    provider = _provider_cache.get(key)
    if provider is None:
        provider = key()
        _provider_cache[key] = provider
    return provider


def _get_tokenizer() -> Tokenizer:
    key = "data/bridge_terms.txt"
    tokenizer = _tokenizer_cache.get(key)
    if tokenizer is None:
        tokenizer = Tokenizer(user_dict_path=key)
        _tokenizer_cache[key] = tokenizer
    return tokenizer


@router.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    db: Session = Depends(get_db),
    provider=Depends(_get_provider),
    tokenizer: Tokenizer = Depends(_get_tokenizer),
):
    """Ask a question and get an answer with citations.

    Uses hybrid retrieval (vector + FTS + facets) with three channels:
    - Anchor: chunks from the target bridge
    - Concept: general knowledge chunks
    - Analogy: chunks from similar bridges

    Returns confidence assessment and evidence groups.
    """
    retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
    generator = Generator(provider=provider)
    facet_extractor = FacetExtractor(provider=provider)

    async def _run():
        degraded: list[str] = []

        target_bridge_id = request.target_bridge_id
        if not target_bridge_id and request.context:
            target_bridge_id = request.context.bridge_id

        facet = None
        try:
            facet = await facet_extractor.extract(request.question)
        except Exception:
            degraded.append("facet")

        try:
            evidence = await retriever.retrieve(
                db,
                request.question,
                target_bridge_id=target_bridge_id,
                facet=facet,
            )
            degraded.extend(retriever.last_degraded)
        except Exception:
            evidence = HybridRetrievalResult(
                anchor_chunks=[], concept_chunks=[], analogy_chunks=[]
            )
            degraded.extend(retriever.last_degraded)
            degraded.append("retrieval")

        if not evidence.all_chunks():
            degraded.append("empty_evidence")

        degraded = list(dict.fromkeys(degraded))

        result = await generator.generate_v2(request.question, evidence)

        evidence_groups = EvidenceGroupsResponse(
            anchor=[
                ChunkSummary(
                    chunk_id=c.chunk_id,
                    bridge_id=c.bridge_id,
                    bridge_name=c.bridge_name,
                    preview=(
                        c.content[:100] + "..." if len(c.content) > 100 else c.content
                    ),
                )
                for c in evidence.anchor_chunks
            ],
            concept=[
                ChunkSummary(
                    chunk_id=c.chunk_id,
                    bridge_id=c.bridge_id,
                    bridge_name=c.bridge_name,
                    preview=(
                        c.content[:100] + "..." if len(c.content) > 100 else c.content
                    ),
                )
                for c in evidence.concept_chunks
            ],
            analogy=[
                ChunkSummary(
                    chunk_id=c.chunk_id,
                    bridge_id=c.bridge_id,
                    bridge_name=c.bridge_name,
                    preview=(
                        c.content[:100] + "..." if len(c.content) > 100 else c.content
                    ),
                )
                for c in evidence.analogy_chunks
            ],
        )

        return AskResponse(
            summary=result.summary,
            details=result.details,
            analogy=result.analogy,
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    source_title=c.source_title,
                    page_range=c.page_range,
                )
                for c in result.citations
            ],
            sources=result.sources,
            confidence=ConfidenceResponse(
                level=result.confidence.level,
                reason=result.confidence.reason,
            ),
            evidence_groups=evidence_groups,
            degraded=degraded if degraded else None,
        )

    return asyncio.run(_run())
```

**Step 4: 创建 app/api/v1/__init__.py**

```python
"""V1 API routes."""
from fastapi import APIRouter

from app.api.v1.ask import router as ask_router

router = APIRouter()
router.include_router(ask_router)

__all__ = ["router"]
```

**Step 5: 验证模块可导入**

Run: `python -c "from app.api.v1 import router; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add app/api/v1/
git commit -m "feat: create API v1 route structure with ask endpoint"
```

---

## Task 8: 更新 main.py 使用新路由

**Files:**
- Modify: `app/main.py`
- Modify: `pyproject.toml` (版本号)

**Step 1: 更新 app/main.py**

```python
from fastapi import FastAPI

from app.api.v1 import router as v1_router

app = FastAPI(title="Bridge RAG", version="1.0.0")

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])


@app.get("/health")
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
```

**Step 2: 更新 pyproject.toml 版本号**

将 `version = "0.1.0"` 改为 `version = "1.0.0"`

**Step 3: 验证服务可启动**

Run: `timeout 5 uvicorn app.main:app --port 8765 2>&1 || true`
Expected: 输出包含 "Uvicorn running"

**Step 4: Commit**

```bash
git add app/main.py pyproject.toml
git commit -m "feat: update main.py to v1.0.0 with /api/v1 prefix"
```

---

## Task 9: 更新测试适配新 API

**Files:**
- Modify: `tests/test_api_ask.py` -> 删除或重写
- Modify: `tests/test_api_ask_v2.py` -> 重命名并更新

**Step 1: 删除旧的 V0 API 测试**

Run: `rm tests/test_api_ask.py`

**Step 2: 更新 tests/test_api_ask_v2.py**

重命名为 `tests/test_api_v1_ask.py` 并更新路由路径：

```python
"""Tests for V1 Ask API endpoint."""
from fastapi.testclient import TestClient

from app.main import app


def test_ask_endpoint_exists():
    """Test that /api/v1/ask endpoint exists."""
    client = TestClient(app)
    # Just check it doesn't 404
    response = client.post("/api/v1/ask", json={"question": "test"})
    # May fail for other reasons (no DB, etc.) but should not be 404
    assert response.status_code != 404
```

**Step 3: 运行测试**

Run: `pytest tests/test_api_v1_ask.py -v`
Expected: passed

**Step 4: Commit**

```bash
git add -A
git commit -m "test: update API tests for v1 routes"
```

---

## Task 10: 清理废弃代码

**Files:**
- Delete: `app/api/ask.py`
- Delete: `app/api/schemas.py`
- Modify: `app/api/__init__.py`
- Modify: `app/services/__init__.py`
- Modify: `app/services/generator.py`
- Delete: `app/services/retriever.py` (审计后)
- Delete: `tests/test_retriever.py`
- Delete: `tests/test_integration.py` (V0 integration test)

**Step 1: 检查 retriever.py 的引用**

Run: `grep -r "from app.services.retriever" --include="*.py" | grep -v "docs/" | grep -v "__pycache__"`

确认引用情况：
- `app/services/__init__.py` - 导出
- `app/services/generator.py` - 使用 `RetrievalResult`
- `tests/test_retriever.py` - 测试
- `tests/test_integration.py` - V0 集成测试
- `tests/test_generator.py` - 使用 `RetrievalResult`

**Step 2: 更新 generator.py 移除 V0 依赖**

移除 `from app.services.retriever import RetrievalResult` 和 `generate` 方法，只保留 `generate_v2`。

**Step 3: 更新 tests/test_generator.py**

移除使用 `RetrievalResult` 的测试，只保留 V2 相关测试。

**Step 4: 更新 app/services/__init__.py**

移除 `Retriever`, `RetrievalContext`, `RetrievalResult` 的导出。

**Step 5: 删除废弃文件**

```bash
rm app/api/ask.py
rm app/api/schemas.py
rm app/services/retriever.py
rm tests/test_retriever.py
rm tests/test_integration.py
```

**Step 6: 更新 app/api/__init__.py**

```python
"""API module."""
from app.api.v1 import router as v1_router

__all__ = ["v1_router"]
```

**Step 7: 运行全部测试确认无破坏**

Run: `pytest tests/ -v`
Expected: all passed (数量会减少，因为删除了一些测试)

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove V0 code (retriever, old ask endpoint, schemas)"
```

---

## Task 11: 创建数据库重置脚本

**Files:**
- Create: `scripts/reset_db.py`

**Step 1: 创建 scripts/reset_db.py**

```python
"""Reset database - drop all tables and recreate schema.

WARNING: This will delete all data!

Usage:
    python scripts/reset_db.py
    python scripts/reset_db.py --yes  # Skip confirmation
"""
import sys

import click
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.models import Base


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def reset_db(yes: bool):
    """Reset database by dropping and recreating all tables."""
    if not yes:
        confirm = input("WARNING: This will delete all data! Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(1)

    engine = create_engine(settings.database_url)

    print("Dropping all tables...")
    Base.metadata.drop_all(engine)

    print("Creating pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    print("Creating tables...")
    Base.metadata.create_all(engine)

    print("Database reset complete!")


if __name__ == "__main__":
    reset_db()
```

**Step 2: 验证脚本可运行（不实际执行）**

Run: `python -c "from scripts.reset_db import reset_db; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/reset_db.py
git commit -m "feat: add database reset script"
```

---

## Task 12: 创建 Markdown 解析器

**Files:**
- Create: `app/services/markdown_parser.py`
- Create: `tests/test_markdown_parser.py`

**Step 1: 创建 tests/test_markdown_parser.py**

```python
"""Tests for Markdown parser."""
import pytest


def test_parse_front_matter():
    """Test extracting YAML front matter."""
    from app.services.markdown_parser import MarkdownParser

    content = """---
bridge: 赵州桥
source_type: document
title: 研究资料
---

# 内容
"""
    parser = MarkdownParser()
    result = parser.parse(content)

    assert result.front_matter["bridge"] == "赵州桥"
    assert result.front_matter["source_type"] == "document"
    assert result.front_matter["title"] == "研究资料"


def test_parse_sections():
    """Test extracting sections from headings."""
    from app.services.markdown_parser import MarkdownParser

    content = """# 结构特点

这是结构特点的内容。

## 主拱设计

主拱的详细说明。

# 历史背景

历史背景内容。
"""
    parser = MarkdownParser()
    result = parser.parse(content)

    assert len(result.sections) == 3
    assert result.sections[0].title == "结构特点"
    assert result.sections[1].title == "结构特点 > 主拱设计"
    assert result.sections[2].title == "历史背景"


def test_parse_no_front_matter():
    """Test parsing without front matter."""
    from app.services.markdown_parser import MarkdownParser

    content = """# 标题

内容
"""
    parser = MarkdownParser()
    result = parser.parse(content)

    assert result.front_matter == {}
    assert len(result.sections) == 1


def test_section_content():
    """Test section content extraction."""
    from app.services.markdown_parser import MarkdownParser

    content = """# 标题

第一段内容。

第二段内容。
"""
    parser = MarkdownParser()
    result = parser.parse(content)

    assert "第一段内容" in result.sections[0].content
    assert "第二段内容" in result.sections[0].content
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/test_markdown_parser.py -v`
Expected: FAIL with "cannot import name 'MarkdownParser'"

**Step 3: 创建 app/services/markdown_parser.py**

```python
"""Markdown parser for ingest documents."""
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class Section:
    """A section extracted from Markdown."""
    title: str
    content: str
    level: int  # Heading level (1 for #, 2 for ##, etc.)


@dataclass
class ParseResult:
    """Result of parsing a Markdown document."""
    front_matter: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    raw_content: str = ""


class MarkdownParser:
    """Parser for Markdown documents with YAML front matter."""

    def parse(self, content: str) -> ParseResult:
        """Parse Markdown content into structured data.

        Args:
            content: Raw Markdown string

        Returns:
            ParseResult with front_matter and sections
        """
        result = ParseResult(raw_content=content)

        # Extract front matter
        content = self._extract_front_matter(content, result)

        # Extract sections
        self._extract_sections(content, result)

        return result

    def _extract_front_matter(self, content: str, result: ParseResult) -> str:
        """Extract YAML front matter from content.

        Returns content without front matter.
        """
        pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(pattern, content, re.DOTALL)

        if match:
            yaml_content = match.group(1)
            try:
                result.front_matter = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError:
                result.front_matter = {}
            return content[match.end():]

        return content

    def _extract_sections(self, content: str, result: ParseResult) -> None:
        """Extract sections from Markdown headings."""
        # Pattern to match headings
        heading_pattern = r'^(#{1,6})\s+(.+)$'

        lines = content.split('\n')
        current_section: Section | None = None
        current_content_lines: list[str] = []
        heading_stack: list[tuple[int, str]] = []  # (level, title)

        for line in lines:
            match = re.match(heading_pattern, line)

            if match:
                # Save previous section
                if current_section is not None:
                    current_section.content = '\n'.join(current_content_lines).strip()
                    if current_section.content:  # Only add non-empty sections
                        result.sections.append(current_section)

                level = len(match.group(1))
                title = match.group(2).strip()

                # Update heading stack
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))

                # Build full title path
                full_title = ' > '.join(t for _, t in heading_stack)

                current_section = Section(title=full_title, content='', level=level)
                current_content_lines = []
            else:
                current_content_lines.append(line)

        # Save last section
        if current_section is not None:
            current_section.content = '\n'.join(current_content_lines).strip()
            if current_section.content:
                result.sections.append(current_section)
```

**Step 4: 运行测试验证通过**

Run: `pytest tests/test_markdown_parser.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/services/markdown_parser.py tests/test_markdown_parser.py
git commit -m "feat: add Markdown parser with front matter support"
```

---

## Task 13: 创建入库 API 端点

**Files:**
- Create: `app/api/v1/ingest.py`
- Modify: `app/api/v1/__init__.py`

**Step 1: 创建 app/api/v1/ingest.py**

```python
"""V1 Ingest API endpoint."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Bridge, Chunk, Source
from app.providers import ZhipuProvider
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import MarkdownParser
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer
from app.core.constants import load_taxonomy
from sqlalchemy import text as sql_text

router = APIRouter()

_provider_cache: dict[object, object] = {}


def _get_provider():
    key = ZhipuProvider
    provider = _provider_cache.get(key)
    if provider is None:
        provider = key()
        _provider_cache[key] = provider
    return provider


class IngestResponse(BaseModel):
    """Response for ingest endpoint."""
    source_id: int
    chunk_count: int
    bridge_id: int | None = None
    message: str


def get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    content: Annotated[str, Body(media_type="text/markdown")],
    db: Session = Depends(get_db),
    provider=Depends(_get_provider),
):
    """Ingest a Markdown document into the knowledge base.

    The document should be in Markdown format with optional YAML front matter:

    ```markdown
    ---
    bridge: 桥梁名称
    source_type: document
    title: 资料标题
    ---

    # 章节标题

    正文内容...
    ```

    Returns the source ID, chunk count, and bridge ID (if specified).
    """
    # Parse Markdown
    parser = MarkdownParser()
    parsed = parser.parse(content)

    # Extract metadata from front matter
    bridge_name = parsed.front_matter.get("bridge")
    source_type = parsed.front_matter.get("source_type", "document")
    source_title = parsed.front_matter.get("title", "导入资料")

    async def _run():
        # Initialize services
        tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")
        chunker = SemanticChunker(
            provider=provider,
            min_chunk_size=200,
            max_chunk_size=500,
            similarity_threshold=0.5,
        )
        context_enricher = ContextEnricher(provider=provider)
        taxonomy_lvl2 = get_taxonomy_lvl2_map()
        tagger = MetadataTagger(provider=provider, taxonomy_lvl2=taxonomy_lvl2)

        # Get or create bridge
        bridge_id = None
        if bridge_name:
            bridge = db.query(Bridge).filter(Bridge.name == bridge_name).first()
            if not bridge:
                bridge = Bridge(name=bridge_name)
                db.add(bridge)
                db.flush()
            bridge_id = bridge.id

        # Create source
        source = Source(type=source_type, title=source_title)
        db.add(source)
        db.flush()

        # Process each section
        all_chunks = []
        for section in parsed.sections:
            # Chunk the section content
            chunk_results = await chunker.chunk(section.content)

            for i, chunk_result in enumerate(chunk_results):
                # Context enrichment
                contextual_text = ""
                try:
                    surrounding = [chunk_results[i-1].content] if i > 0 else None
                    ctx = await context_enricher.enrich(
                        content=chunk_result.content,
                        source_title=source_title,
                        section_title=section.title,
                        page_range=None,
                        surrounding_chunks=surrounding,
                    )
                    contextual_text = (ctx.contextual_text or "").strip()
                except Exception:
                    pass

                # Build search text
                search_text = chunk_result.content
                if contextual_text:
                    search_text = f"{contextual_text}\n\n{chunk_result.content}"

                # Tag
                tag_result = await tagger.tag(chunk_result.content)

                # Embedding
                embeddings = await provider.embed([search_text])
                embedding = embeddings[0] if embeddings else []

                # Create chunk
                chunk = Chunk(
                    source_id=source.id,
                    content=chunk_result.content,
                    section_title=section.title,
                    contextual_text=contextual_text,
                    search_text=search_text,
                    lvl1=tag_result.lvl1,
                    lvl2=tag_result.lvl2,
                    lvl3=tag_result.lvl3,
                    bridge_id=bridge_id,
                    embedding=embedding,
                )
                db.add(chunk)
                all_chunks.append(chunk)

        db.flush()

        # Populate tsvector
        if all_chunks:
            mappings = [
                {
                    "id": chunk.id,
                    "tsv_text": tokenizer.to_tsvector_text(chunk.search_text or chunk.content),
                }
                for chunk in all_chunks
            ]
            db.execute(
                sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
                mappings,
            )

        db.commit()

        return IngestResponse(
            source_id=source.id,
            chunk_count=len(all_chunks),
            bridge_id=bridge_id,
            message=f"成功入库 {len(all_chunks)} 个知识块",
        )

    try:
        return asyncio.run(_run())
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")
```

**Step 2: 更新 app/api/v1/__init__.py**

```python
"""V1 API routes."""
from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.ingest import router as ingest_router

router = APIRouter()
router.include_router(ask_router)
router.include_router(ingest_router)

__all__ = ["router"]
```

**Step 3: 验证模块可导入**

Run: `python -c "from app.api.v1.ingest import router; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add app/api/v1/ingest.py app/api/v1/__init__.py
git commit -m "feat: add /api/v1/ingest endpoint for Markdown documents"
```

---

## Task 14: 运行完整测试并修复问题

**Step 1: 运行全部测试**

Run: `pytest tests/ -v`

**Step 2: 修复发现的问题**

根据测试结果修复任何失败的测试。

**Step 3: 验证所有测试通过**

Run: `pytest tests/ -v`
Expected: all passed

**Step 4: Commit（如有修复）**

```bash
git add -A
git commit -m "fix: resolve test failures after refactoring"
```

---

## Task 15-22: 创建测试数据集（后续任务）

这些任务将创建 12 座虚构桥梁的数据：

- Task 15: 创建 data/seed/ 目录结构和 bridges.yaml
- Task 16: 创建完整 taxonomy.yaml（seed 版本）
- Task 17-20: 创建 4 批桥梁文档（每批 3 座）
- Task 21: 创建 questions.yaml 测试问题集
- Task 22: 更新 seed_test_data.py 使用新数据

---

## Task 23-29: 创建文档（后续任务）

- Task 23: 创建 docs/README.md
- Task 24: 创建 docs/getting-started.md
- Task 25: 创建 docs/api/v1.md
- Task 26: 创建 docs/architecture.md
- Task 27: 创建 docs/deployment.md
- Task 28: 创建 docs/development.md
- Task 29: 创建 docs/ingest-guide.md

---

## Final Task: 验证与合并

**Step 1: 运行完整测试**

Run: `pytest tests/ -v`
Expected: all passed

**Step 2: 检查代码风格**

Run: `python -m py_compile app/**/*.py`

**Step 3: 启动服务验证**

Run: `uvicorn app.main:app --reload`

验证：
- `GET /health` 返回 `{"status": "ok"}`
- `POST /api/v1/ask` 端点可访问
- `POST /api/v1/ingest` 端点可访问

**Step 4: 创建 PR 或合并到主分支**
