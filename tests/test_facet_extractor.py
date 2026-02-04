import pytest


class MockProvider:
    async def chat(self, messages):
        from app.providers import ChatResponse
        return ChatResponse(
            content='{"bridge_type": "石拱桥", "material": "石", "era": ["隋唐", "宋元"], "region": null, "function": null}',
            usage={"total_tokens": 50},
        )


@pytest.mark.asyncio
async def test_extract_facet_basic():
    from app.services.facet_extractor import FacetExtractor
    extractor = FacetExtractor(provider=MockProvider())
    facet = await extractor.extract("古代石拱桥有什么特点")
    assert facet.bridge_type == "石拱桥" or facet.bridge_type == ["石拱桥"]
    assert facet.material == "石" or facet.material == ["石"]


@pytest.mark.asyncio
async def test_extract_facet_multi_era():
    from app.services.facet_extractor import FacetExtractor
    extractor = FacetExtractor(provider=MockProvider())
    facet = await extractor.extract("古桥的建造工艺")
    assert facet.era is not None
    if isinstance(facet.era, list):
        assert len(facet.era) >= 1


def test_facet_to_lists():
    from app.services.facet_extractor import Facet
    facet = Facet(
        bridge_type="石拱桥",
        material=["石", "木"],
        era=None,
        region="华东",
        function=None,
    )
    lists = facet.to_lists()
    assert lists["bridge_type"] == ["石拱桥"]
    assert lists["material"] == ["石", "木"]
    assert lists["era"] == []
    assert lists["region"] == ["华东"]
