"""Pure-logic tests for the streaming markdown parser state machine."""
import pytest
from app.services.markdown_stream_parser import (
    MarkdownStreamParser,
    ParseDegradedError,
)


def _feed_all(parser, full_text, chunk_size=5):
    """Feed text in small slices to simulate streaming."""
    events = []
    for i in range(0, len(full_text), chunk_size):
        for ev in parser.feed(full_text[i:i + chunk_size]):
            events.append(ev)
    for ev in parser.flush():
        events.append(ev)
    return events


def test_parses_outline_and_details():
    text = (
        "# 要点\n"
        "- 要点A摘要 [1,3]\n"
        "- 要点B摘要 [2]\n"
        "## 要点 1\n"
        "段落A正文 [证据 1]\n"
        "## 要点 2\n"
        "段落B正文 [证据 2]\n"
    )
    parser = MarkdownStreamParser()
    events = _feed_all(parser, text)

    types = [e[0] for e in events]
    assert types == ["outline", "detail", "detail"]

    outline_payload = events[0][1]
    assert len(outline_payload["key_points"]) == 2
    assert outline_payload["key_points"][0]["summary"] == "要点A摘要"
    assert outline_payload["key_points"][0]["citations"] == [1, 3]
    assert outline_payload["key_points"][0]["order"] == 1

    detail_a = events[1][1]
    assert detail_a["key_point_id"] == outline_payload["key_points"][0]["id"]
    assert "段落A正文" in detail_a["explanation"]
    assert detail_a["citations"] == [1]


def test_raw_text_without_headings_raises_parse_degraded():
    parser = MarkdownStreamParser()
    text = "这是一整段没有任何 markdown 标题的内容。"
    with pytest.raises(ParseDegradedError) as exc:
        events = _feed_all(parser, text)
    # the raw payload travels with the exception so qa.py can yield a fallback detail
    assert hasattr(exc.value, "fallback_payload")
    assert text in exc.value.fallback_payload["explanation"]


def test_partial_heading_at_stream_end_is_dropped():
    parser = MarkdownStreamParser()
    text = (
        "# 要点\n"
        "- A [1]\n"
        "## 要点 1\n"
        "正文\n"
        "## 要点 2\n"  # heading started but no body before stream ended
    )
    events = _feed_all(parser, text)
    detail_events = [e for e in events if e[0] == "detail"]
    # only the body-less heading is dropped; the previous one is yielded
    assert len(detail_events) == 1
    assert "正文" in detail_events[0][1]["explanation"]


def test_handles_markdown_fence_wrap():
    """Some GLM versions wrap output in ```markdown ... ``` — parser should strip."""
    text = (
        "```markdown\n"
        "# 要点\n"
        "- A [1]\n"
        "## 要点 1\n"
        "正文 [证据 1]\n"
        "```\n"
    )
    parser = MarkdownStreamParser()
    events = _feed_all(parser, text)
    types = [e[0] for e in events]
    assert "outline" in types
    assert "detail" in types
