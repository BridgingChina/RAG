# Heading-Aware Chunker Redesign

## Problem

Current `SemanticChunker` receives a flattened string (all sections concatenated), splits by sentence-ending punctuation (`。！？.!?`), then groups by embedding similarity. This causes three issues:

1. **Text loss / garbled output** — Markdown headings and bullet lists lack sentence-ending punctuation, so the sentence splitter merges them with adjacent paragraphs into giant "sentences". `"".join()` then drops all inter-sentence whitespace consumed by the split regex `\s*`.
2. **No newline after `[章节: ...]` prefix** — Format is `f"[章节: {title}] {text}"` (single space), breaking Markdown rendering.
3. **Ignores heading structure** — Only the first heading is extracted as `section_title`; all others become inline text within chunks.

Root cause: flattening structured `Section[]` into a string destroys the document hierarchy that the Markdown parser already extracted.

## Design

### Algorithm: Section-First Chunking

`SemanticChunker.chunk()` accepts `list[Section]` instead of `str`.

```
Input: Section[] (from markdown_parser)
  ↓
1. Build heading paths
   Maintain parent_stack by level to track ancestor titles.
   e.g., level=1 "结构特点" → level=2 "木拱构造" → path = "结构特点 > 木拱构造"
  ↓
2. Filter empty sections (parent headings with no body content)
  ↓
3. Classify each non-empty section:
   ├─ content_len >= min_chunk_size (200):
   │   ├─ <= max_chunk_size (500): single chunk
   │   └─ > max_chunk_size: semantic sub-split (reuse existing embedding similarity logic)
   │
   └─ content_len < min_chunk_size: push to merge buffer
       Accumulate with subsequent sibling/child short sections.
       Flush when accumulated length >= min_chunk_size
       or when a higher-level heading is encountered.
  ↓
4. Format each chunk:
   content = "[章节: {heading_path}]\n\n{original_markdown_content}"
   section_title = heading_path (e.g., "结构特点 > 木拱构造")
```

### Long Section Sub-Splitting

For sections exceeding `max_chunk_size`, reuse existing sentence-level semantic splitting:
- Split by sentence boundaries (improved: add `\n` as split point for bullet lists)
- Embed all sentences
- Group by cosine similarity threshold
- Each sub-chunk inherits the parent section's heading path

### Short Section Merging

Consecutive short sections are merged into one chunk when:
- They share the same parent heading (or are siblings at the same level)
- Combined length < `max_chunk_size`

Merging flushes when:
- Accumulated length >= `min_chunk_size` and next section would exceed `max_chunk_size`
- A higher-level heading is encountered (topic boundary)
- No more sections remain

The merged chunk's `section_title` uses the first section's heading path. The `content` preserves all original Markdown headings within.

### Interface Changes

```python
# chunker.py
class ChunkResult:
    content: str         # "[章节: path]\n\n{markdown content}"
    section_title: str | None  # "结构特点 > 木拱构造" (no # prefix)

class SemanticChunker:
    async def chunk(self, sections: list[Section]) -> list[ChunkResult]:
        ...
```

```python
# ingest.py — caller change
# Old: flatten + chunk string
text_parts = [...]
chunk_results = await chunker.chunk("\n\n".join(text_parts))

# New: pass sections directly
chunk_results = await chunker.chunk(doc.sections)
```

### Sentence Splitter Improvement

Current pattern `(?<=[。！？.!?])\s*` misses bullet lists and headings. Add `\n` as a split point:
- Split on sentence-ending punctuation OR newlines
- Preserve original formatting within each sentence segment

### Downstream Impact

No changes needed:
- `search_text` = `contextual_text + "\n\n" + content` — unchanged
- `embedding` based on `search_text` — unchanged
- `tsv` based on `search_text` — unchanged
- `context_enricher` receives `content` and `section_title` — unchanged, better quality `section_title`

## Edge Cases

| Scenario | Handling |
|----------|----------|
| No-heading document | Parser returns `Section(title="", level=0, content=...)`, enters semantic sub-split as one large section |
| Single section > max_chunk_size | Semantic sub-split with improved sentence splitter |
| Trailing short section < min | Output as-is (prefer short chunk over cross-topic merge) |
| Merge buffer hits higher-level heading | Flush buffer immediately, start new accumulation |
| Content is only bullet items (no periods) | Improved sentence splitter handles `\n` splits |
| Merged chunk with multiple sections | `section_title` = first section's path; content preserves all headings |

## Testing

- Update `test_chunker.py`: change call signature from `chunk(str)` to `chunk(sections)`
- Add test with 碧波廊桥.md: verify chunk count, content completeness, heading paths
- Completeness check: concatenated chunk text must contain all original section content (no lost text)
