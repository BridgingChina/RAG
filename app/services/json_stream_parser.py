"""Streaming JSON parser for QA real-time SSE responses.

Replaces MarkdownStreamParser as the primary `generate_streaming_v2` parser:
GLM-4.7-Flash via OpenRouter ignored the markdown prompt and emitted JSON
anyway, which made `MarkdownStreamParser.flush()` raise ParseDegradedError
on every production request. Asking the LLM for JSON directly removes that
fragility.

Schema (prompt-enforced, summaries-first):

    {
      "summaries": ["bullet 1 [1,3]", "bullet 2 [2]", ...],
      "details":   [
        {"explanation": "paragraph 1 ...", "citations": [1, 3]},
        {"explanation": "paragraph 2 ...", "citations": [2]}
      ]
    }

The `summaries` array is short strings emitted top-down by the LLM so its
closing `]` lands within the first few seconds of streaming — that's the
trigger to flush the `outline` event. Each object inside `details[]`
flushes a `detail` event the moment its `}` closes, recreating the
per-bullet streaming the old markdown `## Heading N` boundaries provided.

Fallback schema (best-effort): legacy `key_points` of
`{summary, explanation, citations}` objects. If the LLM emits this shape
instead of the new one, we cannot flush outline early — we wait for the
whole array to close, then yield outline plus all details at once. Better
than degrading.

Public API:
    parser = JSONStreamParser()
    for event in parser.feed(token):
        ...
    for event in parser.flush():
        ...
    parser.full_text()  # raw accumulated stream
    raise ParseDegradedError(fallback_payload)
"""
import json
import re
import uuid
from typing import Any, Iterator


_FENCE_OPEN_RE = re.compile(r"^\s*```(?:json)?\s*\n?", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"\n?\s*```\s*$", re.IGNORECASE)
_INLINE_CITATION_RE = re.compile(r"\[\s*((?:\d+\s*,\s*)*\d+)\s*\]\s*$")


class ParseDegradedError(Exception):
    """Raised on flush() when no recognizable JSON structure was extracted."""

    def __init__(self, fallback_payload: dict):
        super().__init__("JSON stream ended with no recognizable structure")
        self.fallback_payload = fallback_payload


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` fence wrappers if the LLM added any."""
    stripped = _FENCE_OPEN_RE.sub("", text, count=1)
    stripped = _FENCE_CLOSE_RE.sub("", stripped, count=1)
    return stripped


def _split_inline_citations(summary: str) -> tuple[str, list[int]]:
    """Pull a trailing ``[1,3]`` marker off a summary string.

    Returns (clean_summary, citations). When no marker is present, citations
    is an empty list and the summary is returned verbatim.
    """
    if not isinstance(summary, str):
        return str(summary), []
    match = _INLINE_CITATION_RE.search(summary)
    if not match:
        return summary.strip(), []
    citations = []
    for part in match.group(1).split(","):
        part = part.strip()
        if part.isdigit():
            citations.append(int(part))
    clean = summary[: match.start()].rstrip()
    return clean, citations


def _coerce_citations(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            out.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            out.append(int(item.strip()))
    return out


class JSONStreamParser:
    """Incremental JSON parser for the QA streaming schema."""

    # Primary schema keys.
    KEY_SUMMARIES = "summaries"
    KEY_DETAILS = "details"
    # Fallback (legacy) schema key.
    KEY_LEGACY = "key_points"

    def __init__(self) -> None:
        self._raw = ""
        self._outline_ids: list[str] = []
        self._outline_yielded = False
        self._details_emitted = 0
        # Schema chosen on first successful extraction; sticky thereafter.
        self._schema: str | None = None  # "primary" | "legacy"

    # -- Public API ---------------------------------------------------------

    def feed(self, token: str) -> Iterator[tuple[str, dict]]:
        if not token:
            return
        self._raw += token
        yield from self._scan()

    def flush(self) -> Iterator[tuple[str, dict]]:
        # Final pass — buffer is complete; pick up any objects that closed
        # exactly on the last token, plus the legacy single-shot case.
        yield from self._scan(final=True)
        if not self._outline_yielded and self._details_emitted == 0:
            raw = self._raw.strip()
            raise ParseDegradedError({
                "key_point_id": str(uuid.uuid4()),
                "explanation": raw[:600] if raw else "(empty response)",
                "citations": [],
            })

    def full_text(self) -> str:
        return self._raw

    # -- Internals ----------------------------------------------------------

    def _stripped(self) -> str:
        return _strip_fences(self._raw)

    def _scan(self, *, final: bool = False) -> Iterator[tuple[str, dict]]:
        buf = self._stripped()

        # Schema selection — once chosen, never switch.
        if self._schema is None:
            # Try primary first (summaries closes faster than legacy
            # key_points so it gets first dibs).
            if not self._outline_yielded:
                summaries = self._try_parse_complete_array(buf, self.KEY_SUMMARIES)
                if summaries is not None:
                    self._schema = "primary"
                    yield from self._emit_outline_from_summaries(summaries)
            # Legacy schema only locks in on flush — if we're mid-stream we
            # may still see "summaries" appear later (unlikely but safe).
            if self._schema is None and final:
                full_legacy = self._try_parse_complete_array(buf, self.KEY_LEGACY)
                if full_legacy is not None:
                    self._schema = "legacy"
                    yield from self._emit_legacy(full_legacy)
                    return

        if self._schema == "primary":
            # Outline may have just been emitted above; emit any new
            # complete details objects.
            yield from self._emit_new_details(buf)

        if self._schema == "legacy" and final:
            # Already handled above on the schema-selection branch.
            return

    # ---- Primary schema emission -----------------------------------------

    def _emit_outline_from_summaries(
        self, summaries: list[Any],
    ) -> Iterator[tuple[str, dict]]:
        if not isinstance(summaries, list):
            return
        items = []
        self._outline_ids = []
        for i, raw in enumerate(summaries):
            text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            clean, citations = _split_inline_citations(text)
            kp_id = str(uuid.uuid4())
            self._outline_ids.append(kp_id)
            items.append({
                "id": kp_id,
                "summary": clean,
                "order": i + 1,
                "citations": citations,
            })
        self._outline_yielded = True
        yield ("outline", {"key_points": items})

    def _emit_new_details(self, buf: str) -> Iterator[tuple[str, dict]]:
        elements = self._extract_object_elements(buf, self.KEY_DETAILS)
        # `elements` may contain unparseable entries; only step the cursor
        # by entries we successfully parsed.
        for i in range(self._details_emitted, len(elements)):
            elem = elements[i]
            if not isinstance(elem, dict):
                # Skip but advance so we don't re-process garbage.
                self._details_emitted = i + 1
                continue
            kp_id = (
                self._outline_ids[i]
                if i < len(self._outline_ids)
                else str(uuid.uuid4())
            )
            yield ("detail", {
                "key_point_id": kp_id,
                "explanation": str(elem.get("explanation", "")),
                "citations": _coerce_citations(elem.get("citations")),
            })
            self._details_emitted = i + 1

    # ---- Legacy schema (single-shot) -------------------------------------

    def _emit_legacy(self, key_points: list[Any]) -> Iterator[tuple[str, dict]]:
        if not isinstance(key_points, list):
            return
        outline_items = []
        details = []
        for i, kp in enumerate(key_points):
            if not isinstance(kp, dict):
                continue
            kp_id = str(uuid.uuid4())
            self._outline_ids.append(kp_id)
            outline_items.append({
                "id": kp_id,
                "summary": str(kp.get("summary", "")),
                "order": i + 1,
                "citations": _coerce_citations(kp.get("citations")),
            })
            details.append({
                "key_point_id": kp_id,
                "explanation": str(kp.get("explanation", "")),
                "citations": _coerce_citations(kp.get("citations")),
            })
        if not outline_items:
            return
        self._outline_yielded = True
        yield ("outline", {"key_points": outline_items})
        for d in details:
            self._details_emitted += 1
            yield ("detail", d)

    # ---- Low-level scan helpers ------------------------------------------

    @staticmethod
    def _find_array_open(buf: str, key: str) -> int | None:
        """Return index of `[` opening the array value of `"key"`, or None."""
        needle = f'"{key}"'
        pos = buf.find(needle)
        if pos < 0:
            return None
        pos += len(needle)
        # Skip whitespace + ':' + whitespace
        while pos < len(buf) and buf[pos] in " \t\n\r":
            pos += 1
        if pos >= len(buf) or buf[pos] != ":":
            return None
        pos += 1
        while pos < len(buf) and buf[pos] in " \t\n\r":
            pos += 1
        if pos >= len(buf) or buf[pos] != "[":
            return None
        return pos

    @classmethod
    def _try_parse_complete_array(cls, buf: str, key: str) -> list[Any] | None:
        """Return the parsed list when the array value of `key` has fully closed.

        Returns None if the key is missing, the array hasn't closed yet, or
        the partial slice is unparseable.
        """
        open_pos = cls._find_array_open(buf, key)
        if open_pos is None:
            return None
        close_pos = cls._find_matching_close(buf, open_pos)
        if close_pos is None:
            return None
        try:
            value = json.loads(buf[open_pos:close_pos + 1])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, list) else None

    @classmethod
    def _extract_object_elements(cls, buf: str, key: str) -> list[Any]:
        """Return all `{...}` objects already closed inside the `key` array.

        Walks depth-1 elements; objects inside nested arrays/objects are
        consumed by the depth tracker, not emitted. The array itself can be
        unclosed — partial-but-valid objects still surface.
        """
        open_pos = cls._find_array_open(buf, key)
        if open_pos is None:
            return []
        elements: list[Any] = []
        depth = 0
        in_string = False
        escape = False
        elem_start: int | None = None
        pos = open_pos + 1  # skip the `[`
        while pos < len(buf):
            ch = buf[pos]
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    if depth == 0:
                        elem_start = pos
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and elem_start is not None:
                        raw = buf[elem_start:pos + 1]
                        try:
                            elements.append(json.loads(raw))
                        except json.JSONDecodeError:
                            elements.append(None)
                        elem_start = None
                elif ch == "]" and depth == 0:
                    return elements  # array fully closed
            pos += 1
        return elements

    @staticmethod
    def _find_matching_close(buf: str, open_pos: int) -> int | None:
        """Find the matching `]` (or `}`) for an opening bracket at open_pos.

        Returns the index of the close character, or None when the bracket is
        not yet balanced (stream still in flight).
        """
        if open_pos >= len(buf):
            return None
        opener = buf[open_pos]
        if opener not in "[{":
            return None
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_string = False
        escape = False
        pos = open_pos
        while pos < len(buf):
            ch = buf[pos]
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch in "[{":
                    depth += 1
                elif ch in "]}":
                    depth -= 1
                    if depth == 0:
                        return pos if ch == closer else None
            pos += 1
        return None


__all__ = ["JSONStreamParser", "ParseDegradedError"]
