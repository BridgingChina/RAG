import pytest

from app.core.constants import get_taxonomy_lvl1
from app.providers import ChatMessage, ChatResponse
from app.services.tagger import MetadataTagger, TagResult


class MockProvider:
    def __init__(self, response_content: str):
        self.response_content = response_content

    async def embed(self, texts):
        return [[0.1] * 2048 for _ in texts]

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content=self.response_content, usage={})


@pytest.mark.asyncio
async def test_tag_with_valid_response():
    provider = MockProvider('{"lvl1": "形制与技术", "lvl2": "结构体系", "bridge_name": "赵州桥"}')
    tagger = MetadataTagger(provider)

    result = await tagger.tag("赵州桥是一座石拱桥，采用敞肩式结构。")

    assert result.lvl1 == "形制与技术"
    assert result.lvl2 == "结构体系"
    assert result.bridge_id == "赵州桥"


@pytest.mark.asyncio
async def test_tag_with_invalid_lvl1():
    provider = MockProvider('{"lvl1": "无效分类", "lvl2": null, "bridge_name": null}')
    tagger = MetadataTagger(provider)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None


@pytest.mark.asyncio
async def test_tag_with_malformed_response():
    provider = MockProvider("这不是JSON格式")
    tagger = MetadataTagger(provider)

    result = await tagger.tag("一些文本")

    assert result.lvl1 is None
    assert result.lvl2 is None


def test_taxonomy_lvl1_values():
    taxonomy_lvl1 = get_taxonomy_lvl1()
    assert "形制与技术" in taxonomy_lvl1
    assert "地域与环境" in taxonomy_lvl1
    assert "功能与社会" in taxonomy_lvl1
    assert "历史与演变" in taxonomy_lvl1
