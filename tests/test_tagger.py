import pytest

from app.core.constants import EMBEDDING_DIM, get_taxonomy_lvl1
from app.providers import ChatMessage, ChatResponse
from app.services.tagger import MetadataTagger, TagResult

# A minimal taxonomy snapshot mirroring the seed YAML. Using a fixed local
# constant (not a constants.py import) so these tests still pass after the
# YAML fallback in tagger.py has been removed — the point of the fix.
_TAXONOMY = {
    "形制与技术": {
        "结构体系": ["拱桥结构", "梁桥结构"],
        "构造细部": ["桥墩设计"],
    },
    "地域与环境": {
        "水文地形": ["河流特征"],
    },
    "功能与社会": {},
    "历史与演变": {},
}


class MockProvider:
    def __init__(self, response_content: str):
        self.response_content = response_content

    async def embed(self, texts):
        return [[0.1] * EMBEDDING_DIM for _ in texts]

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content=self.response_content, usage={})


@pytest.mark.asyncio
async def test_tag_with_valid_response():
    provider = MockProvider('{"lvl1": "形制与技术", "lvl2": "结构体系", "bridge_name": "赵州桥"}')
    tagger = MetadataTagger(provider, taxonomy=_TAXONOMY)

    result = await tagger.tag("赵州桥是一座石拱桥，采用敞肩式结构。")

    assert result.lvl1 == "形制与技术"
    assert result.lvl2 == "结构体系"
    assert result.bridge_id == "赵州桥"


@pytest.mark.asyncio
async def test_tag_with_invalid_lvl1():
    provider = MockProvider('{"lvl1": "无效分类", "lvl2": null, "bridge_name": null}')
    tagger = MetadataTagger(provider, taxonomy=_TAXONOMY)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None


@pytest.mark.asyncio
async def test_tag_with_malformed_response():
    provider = MockProvider("这不是JSON格式")
    tagger = MetadataTagger(provider, taxonomy=_TAXONOMY)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None
    assert result.lvl2 is None


def test_taxonomy_lvl1_values():
    taxonomy_lvl1 = get_taxonomy_lvl1()
    assert "形制与技术" in taxonomy_lvl1
    assert "地域与环境" in taxonomy_lvl1
    assert "功能与社会" in taxonomy_lvl1
    assert "历史与演变" in taxonomy_lvl1


# --- Regression tests for "admin adds new taxonomy node → new ingest picks
# it up without a process restart" (2026-04-19 fix). If a future PR sneaks
# the tagger back onto config/taxonomy.yaml or a cached loader, these tests
# go red.


@pytest.mark.asyncio
async def test_tagger_accepts_runtime_added_lvl1():
    """A lvl1 added via admin UI after boot must be usable by the tagger.

    Simulates: admin creates a brand-new lvl1 via POST /taxonomy/nodes →
    next ingest task constructs a tagger with the fresh snapshot →
    LLM returns this new lvl1 → it must NOT be nulled by the whitelist.
    """
    runtime_taxonomy = {
        **_TAXONOMY,
        "方案2回归测试用新分类": {
            "新二级分类": ["新三级分类"],
        },
    }
    provider = MockProvider(
        '{"lvl1": "方案2回归测试用新分类", "lvl2": "新二级分类", "lvl3": "新三级分类", "bridge_name": null}'
    )
    tagger = MetadataTagger(provider, taxonomy=runtime_taxonomy)

    result = await tagger.tag("一些属于新分类的文本")

    assert result.lvl1 == "方案2回归测试用新分类"
    assert result.lvl2 == "新二级分类"
    assert result.lvl3 == "新三级分类"


@pytest.mark.asyncio
async def test_tagger_rejects_runtime_deleted_lvl1():
    """A lvl1 removed via admin UI must stop appearing on new ingests.

    If the LLM hallucinates a now-deleted lvl1, the tagger's whitelist
    (sourced from the DB snapshot) must null it out rather than let
    zombie chunks reference a non-existent taxonomy row.
    """
    deleted_lvl1 = "已被管理员删除的旧分类"
    # Deleted lvl1 is deliberately absent from runtime_taxonomy.
    runtime_taxonomy = _TAXONOMY
    provider = MockProvider(
        f'{{"lvl1": "{deleted_lvl1}", "lvl2": "任何二级", "bridge_name": null}}'
    )
    tagger = MetadataTagger(provider, taxonomy=runtime_taxonomy)

    result = await tagger.tag("一些可能属于旧分类的文本")

    assert result.lvl1 is None
    assert result.lvl2 is None
    assert result.lvl3 is None


@pytest.mark.asyncio
async def test_tagger_prompt_lists_only_snapshot_categories():
    """The prompt sent to the LLM must enumerate exactly the snapshot's
    lvl1 keys — not anything from constants.py / taxonomy.yaml."""
    only_one_lvl1 = {"只有这一个分类": {"唯一二级": []}}
    provider = MockProvider('{"lvl1": null, "lvl2": null, "bridge_name": null}')
    tagger = MetadataTagger(provider, taxonomy=only_one_lvl1)

    prompt = tagger._build_taxonomy_prompt()

    assert "只有这一个分类" in prompt
    assert "唯一二级" in prompt
    # YAML-seeded categories must NOT leak into the prompt when they
    # aren't in the snapshot.
    assert "形制与技术" not in prompt
    assert "地域与环境" not in prompt
