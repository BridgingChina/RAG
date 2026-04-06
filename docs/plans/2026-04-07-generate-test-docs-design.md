# Generate Test Documents Design

## Goal

独立 Python 脚本，调用 OpenAI 兼容 API，利用 LLM 内置知识生成 20-50 篇真实桥梁技术文档（Markdown + PDF 混合），用于检验入库流水线的切块能力。与现有项目代码解耦。

## CLI Interface

```bash
python3 scripts/generate_test_docs.py \
  --count 30 \
  --output-dir data/generated \
  --pdf-ratio 0.5 \
  --concurrency 5
```

| Parameter | Source | Default | Description |
|-----------|--------|---------|-------------|
| `LLM_BASE_URL` | `.env` | required | OpenAI-compatible API base URL |
| `LLM_API_KEY` | `.env` | required | API key |
| `LLM_MODEL` | `.env` | `gpt-4o-mini` | Model name |
| `--count` | CLI | 30 | Number of bridges to generate |
| `--output-dir` | CLI | `data/generated` | Output directory |
| `--pdf-ratio` | CLI | 0.5 | Fraction of docs output as PDF (0-1) |
| `--concurrency` | CLI | 5 | Max concurrent API requests |

## Architecture: Two-Phase Pipeline

### Phase 1: Bridge Manifest Generation

Single LLM call to generate a JSON array of real Chinese bridges:

```json
[
  {
    "name": "赵州桥",
    "bridge_type": "石拱桥",
    "material": "石",
    "era": "隋代",
    "region": "河北省赵县",
    "function": "交通",
    "summary": "世界现存最古老的敞肩石拱桥"
  }
]
```

Prompt strategy:
- Require only real, existing Chinese bridges (leverage model knowledge)
- Require diversity: bridge types (arch, beam, suspension, cable-stayed, pontoon, covered), eras (ancient/modern/contemporary), regions
- Use `response_format: {"type": "json_object"}` for structured output
- Retry once on JSON parse failure with different temperature

### Phase 2: Per-Bridge Document Generation

One LLM call per bridge. Prompt provides bridge metadata but **no chapter outline** — LLM freely organizes structure. This intentionally produces varied document structures to stress-test the chunker.

Prompt:
```
你是一位桥梁工程专家。请撰写一篇关于"{name}"（{region}，{era}，{bridge_type}）的详细技术文档。

要求：
- 基于真实信息，内容 1000-2000 字
- 自由组织章节结构，使用 Markdown 标题层级
- 不限定章节数量和主题，按你认为最合适的方式组织
```

Concurrency: `asyncio.Semaphore(concurrency)` to respect API rate limits.

### Output Routing

Each document randomly assigned to Markdown or PDF based on `--pdf-ratio`:
- Markdown: write directly to `{output_dir}/{name}.md`
- PDF: parse Markdown headings → `fpdf2` with Chinese font support

### PDF Generation

Tool: `fpdf2` (pure Python, no system dependencies).

Chinese font: check for system CJK font (e.g. NotoSansCN, PingFang). If unavailable, fall back to all-Markdown output with a warning.

Simple Markdown-to-PDF mapping:
- `#` → 18pt bold
- `##` → 15pt bold
- `###` → 13pt bold
- Body → 11pt regular, `multi_cell` layout

Goal is valid, text-extractable PDFs — not beautiful typesetting.

### Output Structure

```
data/generated/
├── 赵州桥.md
├── 卢沟桥.pdf
├── 广济桥.md
├── 港珠澳大桥.pdf
├── ...
└── manifest.json    # Phase 1 bridge list + output format per entry
```

## Dependencies

- `httpx` (existing)
- `fpdf2` (new, add to pyproject.toml extras or install separately)
- `python-dotenv` (existing)

## Non-Goals

- No integration with existing `seed_test_data.py` or ingest API
- No YAML front matter required
- No embedding or database operations
