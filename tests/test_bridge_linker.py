"""Tests for BridgeLinker.

Phase C: BridgeLinker no longer takes an injected provider; the LLM call is
routed via :func:`app.llm.chat_for_task`. Tests monkey-patch the module-level
``chat_for_task`` symbol and use a call-recorder helper so assertions about
"was the LLM called" stay intact.
"""
import json

import pytest

from app.models import Bridge
from app.providers import ChatResponse
from app.services import bridge_linker as linker_module
from app.services.bridge_linker import BridgeLinker


class _LLMRecorder:
    """Stand-in for the old MockProvider — records chat_for_task calls and
    returns a canned ChatResponse built from the configured payload."""

    def __init__(self, response_payload: dict | None = None):
        self.response_payload = response_payload or {
            "primary_bridge": None,
            "primary_confidence": 0.0,
            "secondary_bridges": [],
            "candidate_bridges": [],
        }
        self.chat_calls = 0

    async def __call__(self, task_key, messages):
        self.chat_calls += 1
        return ChatResponse(
            content=json.dumps(self.response_payload, ensure_ascii=False),
            usage={},
            model="stub-model",
        )


def _install(monkeypatch, recorder: _LLMRecorder):
    monkeypatch.setattr(linker_module, "chat_for_task", recorder)


@pytest.mark.asyncio
async def test_rule_single_hit_promotes_to_primary(db_session, monkeypatch):
    db_session.add(Bridge(name="赵州桥"))
    db_session.flush()
    _install(monkeypatch, _LLMRecorder())

    linker = BridgeLinker()
    result = await linker.link_chunk(db_session, "赵州桥是著名石拱桥")

    assert result.binding_status == "primary"
    assert result.primary_bridge_name == "赵州桥"
    assert any(link.role == "primary" for link in result.links)


@pytest.mark.asyncio
async def test_conflicting_rule_hits_triggers_llm(db_session, monkeypatch):
    db_session.add_all([Bridge(name="赵州桥"), Bridge(name="卢沟桥")])
    db_session.flush()

    recorder = _LLMRecorder(
        {
            "primary_bridge": "卢沟桥",
            "primary_confidence": 0.9,
            "secondary_bridges": ["赵州桥"],
            "candidate_bridges": [],
        }
    )
    _install(monkeypatch, recorder)
    linker = BridgeLinker()
    result = await linker.link_chunk(db_session, "赵州桥与卢沟桥都很有名")

    assert recorder.chat_calls == 1
    assert result.binding_status == "primary"
    assert result.primary_bridge_name == "卢沟桥"
    assert "赵州桥" in result.secondary_bridge_names


@pytest.mark.asyncio
async def test_low_confidence_primary_becomes_ambiguous_candidate(db_session, monkeypatch):
    db_session.add_all([Bridge(name="赵州桥"), Bridge(name="卢沟桥")])
    db_session.flush()

    _install(
        monkeypatch,
        _LLMRecorder(
            {
                "primary_bridge": "赵州桥",
                "primary_confidence": 0.4,
                "secondary_bridges": [],
                "candidate_bridges": ["卢沟桥"],
            }
        ),
    )
    linker = BridgeLinker(min_primary_confidence=0.75)
    result = await linker.link_chunk(db_session, "这里讨论古桥")

    assert result.binding_status == "ambiguous"
    assert result.primary_bridge_name is None
    assert "赵州桥" in result.candidate_bridge_names
    assert any(link.role == "candidate" for link in result.links)


@pytest.mark.asyncio
async def test_unknown_bridge_auto_created(db_session, monkeypatch):
    _install(
        monkeypatch,
        _LLMRecorder(
            {
                "primary_bridge": "新桥一号",
                "primary_confidence": 0.9,
                "secondary_bridges": [],
                "candidate_bridges": [],
            }
        ),
    )
    linker = BridgeLinker()
    result = await linker.link_chunk(db_session, "新桥一号采用现代结构")

    assert result.primary_bridge_name == "新桥一号"
    assert "新桥一号" in result.auto_created_bridge_names
    assert db_session.query(Bridge).filter(Bridge.name == "新桥一号").first() is not None


@pytest.mark.asyncio
async def test_hints_do_not_force_first_bridge_as_primary(db_session, monkeypatch):
    db_session.add_all([Bridge(name="赵州桥"), Bridge(name="卢沟桥")])
    db_session.flush()

    _install(monkeypatch, _LLMRecorder())
    linker = BridgeLinker()
    result = await linker.link_chunk(
        db_session,
        "卢沟桥采用联拱结构。",
        hint_bridge_names=["赵州桥", "卢沟桥"],
    )

    assert result.binding_status == "primary"
    assert result.primary_bridge_name == "卢沟桥"
    assert result.primary_bridge_name != "赵州桥"


@pytest.mark.asyncio
async def test_no_auto_create_when_auto_detection_disabled(db_session, monkeypatch):
    _install(monkeypatch, _LLMRecorder())
    linker = BridgeLinker()
    result = await linker.link_chunk(
        db_session,
        "这是一段没有已知桥名的文本",
        bridge_candidates=["拼写错误桥名"],
        enable_auto_bridge_detection=False,
    )

    assert result.auto_created_bridge_names == []
    assert db_session.query(Bridge).filter(Bridge.name == "拼写错误桥名").first() is None


@pytest.mark.asyncio
async def test_llm_primary_alias_resolves_to_existing_bridge(db_session, monkeypatch):
    db_session.add(Bridge(name="赵州桥", aliases="安济桥"))
    db_session.flush()

    _install(
        monkeypatch,
        _LLMRecorder(
            {
                "primary_bridge": "安济桥",
                "primary_confidence": 0.92,
                "secondary_bridges": [],
                "candidate_bridges": [],
            }
        ),
    )
    linker = BridgeLinker()
    result = await linker.link_chunk(db_session, "该桥采用敞肩拱结构")

    assert result.binding_status == "primary"
    assert result.primary_bridge_name == "赵州桥"
    assert result.auto_created_bridge_names == []


@pytest.mark.asyncio
async def test_promotes_highest_confidence_candidate_to_primary(db_session, monkeypatch):
    db_session.add_all([Bridge(name="提示桥"), Bridge(name="赵州桥")])
    db_session.flush()

    _install(monkeypatch, _LLMRecorder())
    linker = BridgeLinker()
    result = await linker.link_chunk(
        db_session,
        "赵州桥采用敞肩拱结构",
        hint_bridge_names=["提示桥"],
        min_primary_confidence=0.6,
        enable_auto_bridge_detection=False,
    )

    assert result.binding_status == "primary"
    assert result.primary_bridge_name == "赵州桥"


@pytest.mark.asyncio
async def test_short_alias_embedded_in_word_not_counted(db_session, monkeypatch):
    db_session.add(Bridge(name="测试桥", aliases="州桥"))
    db_session.flush()

    _install(monkeypatch, _LLMRecorder())
    linker = BridgeLinker()
    result = await linker.link_chunk(
        db_session,
        "这段文本讨论苏州桥梁史，不特指某座桥",
        enable_auto_bridge_detection=False,
    )

    assert result.binding_status == "none"
    assert result.primary_bridge_name is None
    assert result.candidate_bridge_names == []
