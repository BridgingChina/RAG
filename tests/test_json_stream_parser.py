"""Pure-logic tests for the streaming JSON parser state machine."""
import json

import pytest

from app.services.json_stream_parser import (
    JSONStreamParser,
    ParseDegradedError,
)


def _feed_all(parser: JSONStreamParser, full_text: str, chunk_size: int = 5):
    """Feed text in small slices to simulate token streaming."""
    events: list[tuple[str, dict]] = []
    for i in range(0, len(full_text), chunk_size):
        for ev in parser.feed(full_text[i:i + chunk_size]):
            events.append(ev)
    for ev in parser.flush():
        events.append(ev)
    return events


def test_parses_outline_then_details_in_primary_schema():
    payload = {
        "summaries": ["要点A [1,3]", "要点B [2]"],
        "details": [
            {"explanation": "段落A正文。", "citations": [1, 3]},
            {"explanation": "段落B正文。", "citations": [2]},
        ],
    }
    text = json.dumps(payload, ensure_ascii=False)

    parser = JSONStreamParser()
    events = _feed_all(parser, text)

    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]

    outline = events[0][1]
    assert len(outline["key_points"]) == 2
    assert outline["key_points"][0]["summary"] == "要点A"
    assert outline["key_points"][0]["citations"] == [1, 3]
    assert outline["key_points"][0]["order"] == 1

    detail_a = events[1][1]
    assert detail_a["key_point_id"] == outline["key_points"][0]["id"]
    assert detail_a["explanation"] == "段落A正文。"
    assert detail_a["citations"] == [1, 3]


def test_outline_emits_before_details_complete_streaming_ux():
    """The summaries array closes early; outline must yield before any detail."""
    text = (
        '{"summaries":["A [1]","B [2]"],'
        '"details":[{"explanation":"long-A...","citations":[1]},'
        '{"explanation":"long-B...","citations":[2]}]}'
    )
    parser = JSONStreamParser()
    events: list[tuple[str, dict]] = []
    # Feed up to the closing ']' of summaries
    cutoff = text.index('"details"')
    for ev in parser.feed(text[:cutoff]):
        events.append(ev)
    # Outline should already have been yielded with no details yet.
    types = [e[0] for e in events]
    assert types == ["outline"]
    # Now feed the rest; details should arrive incrementally
    for ev in parser.feed(text[cutoff:]):
        events.append(ev)
    for ev in parser.flush():
        events.append(ev)
    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]


def test_strips_json_fence_wrap():
    payload = {
        "summaries": ["A [1]"],
        "details": [{"explanation": "exp", "citations": [1]}],
    }
    text = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    parser = JSONStreamParser()
    events = _feed_all(parser, text)
    types = [e[0] for e in events]
    assert types == ["outline", "detail"]


def test_legacy_key_points_schema_falls_back_at_flush():
    """If the LLM emits the old key_points schema, parser still returns events."""
    payload = {
        "key_points": [
            {"summary": "old A", "explanation": "exp A", "citations": [1]},
            {"summary": "old B", "explanation": "exp B", "citations": [2]},
        ],
        "deep_dive": None,
    }
    text = json.dumps(payload, ensure_ascii=False)

    parser = JSONStreamParser()
    events = _feed_all(parser, text)
    types = [e[0] for e in events]
    # Single-shot emission on flush — outline first, all details next.
    assert types == ["outline", "detail", "detail"]
    outline = events[0][1]
    assert outline["key_points"][0]["summary"] == "old A"
    assert outline["key_points"][0]["citations"] == [1]


def test_raw_text_raises_parse_degraded_with_truncation():
    parser = JSONStreamParser()
    text = "这是一整段没有任何 JSON 结构的文本。" * 30
    with pytest.raises(ParseDegradedError) as exc:
        _feed_all(parser, text)
    assert hasattr(exc.value, "fallback_payload")
    explanation = exc.value.fallback_payload["explanation"]
    assert len(explanation) <= 600
    assert "这是一整段" in explanation


def test_partial_details_at_stream_end_yields_only_complete_objects():
    """Stream cuts mid-explanation of detail #2 — only detail #1 should yield."""
    text = (
        '{"summaries":["A [1]","B [2]"],'
        '"details":[{"explanation":"complete-A","citations":[1]},'
        '{"explanation":"truncat'
    )
    parser = JSONStreamParser()
    events = _feed_all(parser, text)
    types = [e[0] for e in events]
    assert types == ["outline", "detail"]
    assert events[1][1]["explanation"] == "complete-A"


def test_handles_strings_with_brackets_and_braces_inside():
    """Detail explanations that legitimately contain `[` `{` must not confuse parser."""
    payload = {
        "summaries": ["A [1]"],
        "details": [{
            "explanation": "考虑函数 f(x) = {x | x in [0,1]}; reference [1].",
            "citations": [1],
        }],
    }
    text = json.dumps(payload, ensure_ascii=False)
    parser = JSONStreamParser()
    events = _feed_all(parser, text)
    detail_evs = [e for e in events if e[0] == "detail"]
    assert len(detail_evs) == 1
    assert "f(x)" in detail_evs[0][1]["explanation"]
    assert detail_evs[0][1]["citations"] == [1]


def test_handles_escaped_quotes_in_explanation():
    raw = (
        '{"summaries":["A [1]"],'
        '"details":[{"explanation":"He said \\"hello\\" then [1].","citations":[1]}]}'
    )
    parser = JSONStreamParser()
    events = _feed_all(parser, raw)
    detail_evs = [e for e in events if e[0] == "detail"]
    assert len(detail_evs) == 1
    assert detail_evs[0][1]["explanation"] == 'He said "hello" then [1].'
