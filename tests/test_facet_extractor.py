"""Tests for FacetExtractor — Phase C routed via chat_for_task."""
import pytest

from app.providers import ChatResponse
from app.services import facet_extractor as extractor_module
from app.services.facet_extractor import Facet, FacetExtractor


def _patch_chat(monkeypatch, content: str):
    async def _fake(task_key, messages):
        return ChatResponse(content=content, usage={"total_tokens": 50}, model="stub-model")

    monkeypatch.setattr(extractor_module, "chat_for_task", _fake)


@pytest.mark.asyncio
async def test_extract_facet_basic(monkeypatch):
    _patch_chat(
        monkeypatch,
        '{"bridge_type": "石拱桥", "material": "石", "era": ["隋唐", "宋元"], "region": null, "function": null}',
    )
    extractor = FacetExtractor()
    facet = await extractor.extract("古代石拱桥有什么特点")
    assert facet.bridge_type == "石拱桥" or facet.bridge_type == ["石拱桥"]
    assert facet.material == "石" or facet.material == ["石"]


@pytest.mark.asyncio
async def test_extract_facet_multi_era(monkeypatch):
    _patch_chat(
        monkeypatch,
        '{"bridge_type": "石拱桥", "material": "石", "era": ["隋唐", "宋元"], "region": null, "function": null}',
    )
    extractor = FacetExtractor()
    facet = await extractor.extract("古桥的建造工艺")
    assert facet.era is not None
    if isinstance(facet.era, list):
        assert len(facet.era) >= 1


def test_facet_to_lists():
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
