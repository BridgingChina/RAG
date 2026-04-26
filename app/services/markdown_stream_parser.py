"""Streaming markdown parser for QA real-time SSE responses.

State machine:
  preamble → outline → detail* → end

- Outline yielded once when first '## ' heading is seen (after the '# 要点' block).
- Each detail yielded when next '## ' heading is seen, OR on flush().
- A heading line with no body before stream ends is dropped (avoids "stranded heading").
- Raises ParseDegradedError on flush if no '## ' heading was ever seen — the caller
  should yield exc.fallback_payload as a single detail with a degraded marker.

Public API:
  - MarkdownStreamParser()
  - parser.feed(token: str) -> Iterator[tuple[str, dict]]
  - parser.flush() -> Iterator[tuple[str, dict]]
  - parser.full_text() -> str   (raw accumulated text; for en-US summary extraction)
  - ParseDegradedError(fallback_payload: dict)
"""
import re
import uuid
from typing import Iterator


_OUTLINE_BULLET_RE = re.compile(r"^\s*-\s*(.+?)(?:\s*\[([0-9,\s]+)\])?\s*$")
_DETAIL_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_CITATION_RE = re.compile(r"\[(?:证据\s*)?([0-9,\s]+)\]")
_FENCE_RE = re.compile(r"^```[a-z]*\s*$", re.IGNORECASE)


class ParseDegradedError(Exception):
    """Raised when stream ended without any '## ' heading. Carries fallback payload."""

    def __init__(self, fallback_payload: dict):
        super().__init__("markdown stream ended with no recognizable structure")
        self.fallback_payload = fallback_payload


class MarkdownStreamParser:
    def __init__(self) -> None:
        self._buf = ""
        self._raw_full = ""
        self._mode = "preamble"  # preamble | outline | detail
        self._outline_items: list[dict] = []
        self._outline_yielded = False
        self._current_detail_id: str | None = None
        self._current_detail_buffer: list[str] = []
        self._saw_any_heading = False
        self._emitted_count = 0

    def feed(self, token: str) -> Iterator[tuple[str, dict]]:
        self._raw_full += token
        self._buf += token
        while "\n" in self._buf:
            line, _, self._buf = self._buf.partition("\n")
            yield from self._consume_line(line.rstrip("\r"))

    def flush(self) -> Iterator[tuple[str, dict]]:
        if self._buf:
            line = self._buf
            self._buf = ""
            yield from self._consume_line(line)
        # Emit final detail body if any.
        if self._current_detail_id is not None and self._current_detail_buffer:
            yield self._emit_current_detail()
        if not self._saw_any_heading:
            raw = self._raw_full.strip()
            raise ParseDegradedError({
                "key_point_id": str(uuid.uuid4()),
                "explanation": raw if raw else "(空响应)",
                "citations": [],
            })

    def full_text(self) -> str:
        return self._raw_full

    def _consume_line(self, line: str) -> Iterator[tuple[str, dict]]:
        if _FENCE_RE.match(line):
            return
        stripped = line.strip()

        if stripped.startswith("# ") and not stripped.startswith("## "):
            self._mode = "outline"
            return

        m_h2 = _DETAIL_HEADING_RE.match(stripped)
        if m_h2:
            self._saw_any_heading = True
            if not self._outline_yielded:
                if self._outline_items:
                    yield (
                        "outline",
                        {"key_points": [
                            {
                                "id": item["id"],
                                "summary": item["summary"],
                                "order": item["order"],
                                "citations": item["citations"],
                            }
                            for item in self._outline_items
                        ]},
                    )
                self._outline_yielded = True
            # Close prior detail.
            if self._current_detail_id is not None and self._current_detail_buffer:
                yield self._emit_current_detail()
            # Open next detail.
            next_idx = self._emitted_count
            if next_idx < len(self._outline_items):
                self._current_detail_id = self._outline_items[next_idx]["id"]
            else:
                self._current_detail_id = str(uuid.uuid4())
            self._current_detail_buffer = []
            self._mode = "detail"
            return

        if self._mode == "outline":
            m_b = _OUTLINE_BULLET_RE.match(line)
            if m_b:
                self._outline_items.append({
                    "id": str(uuid.uuid4()),
                    "summary": m_b.group(1).strip(),
                    "order": len(self._outline_items) + 1,
                    "citations": _parse_citations(m_b.group(2) or ""),
                })
            return

        if self._mode == "detail" and self._current_detail_id is not None:
            self._current_detail_buffer.append(line)

    def _emit_current_detail(self) -> tuple[str, dict]:
        explanation = "\n".join(self._current_detail_buffer).strip()
        cits: list[int] = []
        for m in _CITATION_RE.finditer(explanation):
            cits.extend(_parse_citations(m.group(1)))
        payload = {
            "key_point_id": self._current_detail_id,
            "explanation": explanation,
            "citations": sorted(set(cits)),
        }
        self._current_detail_id = None
        self._current_detail_buffer = []
        self._emitted_count += 1
        return ("detail", payload)


def _parse_citations(raw: str) -> list[int]:
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            out.append(int(piece))
    return out
