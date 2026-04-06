# Generate Test Documents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standalone Python script that calls an OpenAI-compatible API to generate 20-50 real Chinese bridge technical documents in mixed Markdown/PDF format.

**Architecture:** Two-phase pipeline — Phase 1 generates a bridge manifest via single LLM call, Phase 2 generates per-bridge documents concurrently. Output randomly split between `.md` and `.pdf` based on `--pdf-ratio`. Uses `httpx` for API calls, `fpdf2` for PDF generation.

**Tech Stack:** Python 3.11+, httpx, fpdf2, asyncio, argparse

---

### Task 1: Add fpdf2 dependency

**Files:**
- Modify: `pyproject.toml:26-31` (add to optional-dependencies)

**Step 1: Add fpdf2 to dev extras**

In `pyproject.toml`, add `fpdf2` to `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "fpdf2>=2.7.0",
]
```

**Step 2: Install**

Run: `pip install -e ".[dev]"`
Expected: fpdf2 installs successfully

**Step 3: Verify import**

Run: `python3 -c "import fpdf; print(fpdf.__version__)"`
Expected: prints version >= 2.7

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fpdf2 dependency for test doc generation"
```

---

### Task 2: Add LLM env vars to .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Append LLM configuration section**

Add to the end of `.env.example`:

```
# LLM for test doc generation (OpenAI-compatible)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_key_here
LLM_MODEL=deepseek-chat
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add LLM env vars to .env.example"
```

---

### Task 3: Create script skeleton with CLI parsing

**Files:**
- Create: `scripts/generate_test_docs.py`

**Step 1: Write the script skeleton**

```python
"""Generate test bridge documents using an OpenAI-compatible LLM API.

Usage:
    python3 scripts/generate_test_docs.py --count 30 --output-dir data/generated

Requires LLM_BASE_URL, LLM_API_KEY in .env (LLM_MODEL defaults to gpt-4o-mini).
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path

import httpx

# Load .env manually (no dependency on python-dotenv or pydantic-settings)
def load_dotenv(path: Path = Path(__file__).resolve().parent.parent / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate test bridge documents via LLM")
    p.add_argument("--count", type=int, default=30, help="Number of bridges (default: 30)")
    p.add_argument("--output-dir", type=str, default="data/generated", help="Output directory")
    p.add_argument("--pdf-ratio", type=float, default=0.5, help="Fraction output as PDF (0-1)")
    p.add_argument("--concurrency", type=int, default=5, help="Max concurrent API requests")
    return p.parse_args()


async def main():
    load_dotenv()
    args = parse_args()

    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not base_url or not api_key:
        print("ERROR: LLM_BASE_URL and LLM_API_KEY must be set in .env", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Config: model={model}, count={args.count}, pdf_ratio={args.pdf_ratio}")
    print(f"Output: {out.resolve()}")

    # Phase 1: generate manifest
    # Phase 2: generate documents
    # (implemented in subsequent tasks)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Verify it runs**

Run: `python3 scripts/generate_test_docs.py --count 5`
Expected: prints config + output path, then exits (no LLM calls yet). If `LLM_BASE_URL`/`LLM_API_KEY` not in `.env`, prints error and exits 1.

**Step 3: Commit**

```bash
git add scripts/generate_test_docs.py
git commit -m "feat: add generate_test_docs script skeleton with CLI"
```

---

### Task 4: Implement Phase 1 — bridge manifest generation

**Files:**
- Modify: `scripts/generate_test_docs.py`

**Step 1: Add the LLM chat helper function**

Add after `load_dotenv`:

```python
async def chat(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    json_mode: bool = False,
) -> str:
    """Call OpenAI-compatible chat completions endpoint."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = await client.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
```

**Step 2: Add the manifest generation function**

```python
async def generate_manifest(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    count: int,
) -> list[dict]:
    """Phase 1: Generate a list of real Chinese bridges via LLM."""
    prompt = f"""请列出 {count} 座真实存在的中国桥梁，返回 JSON 对象，格式为 {{"bridges": [...]}}。

每座桥包含以下字段：
- name: 桥梁名称
- bridge_type: 桥型（如石拱桥、梁桥、悬索桥、斜拉桥、浮桥、廊桥等）
- material: 主要材料（石、木、铁、钢、混凝土等）
- era: 建造年代（如隋代、明代、清代、民国、1950年代、2000年代等）
- region: 所在地区（省份+具体位置）
- function: 主要功能（交通、军事、商贸、景观等）
- summary: 一句话简介

要求：
1. 只列真实存在的桥梁，不要虚构
2. 桥型多样化：至少覆盖拱桥、梁桥、悬索桥、斜拉桥、廊桥
3. 年代多样化：古代（隋-清）和现当代都要有
4. 地域多样化：覆盖不同省份"""

    for attempt in range(2):
        temp = 0.7 if attempt == 0 else 0.3
        try:
            raw = await chat(client, base_url, api_key, model,
                           [{"role": "user", "content": prompt}],
                           temperature=temp, json_mode=True)
            data = json.loads(raw)
            bridges = data.get("bridges", data) if isinstance(data, dict) else data
            if isinstance(bridges, list) and len(bridges) > 0:
                print(f"Phase 1: got {len(bridges)} bridges")
                return bridges
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Phase 1 attempt {attempt+1} failed: {e}")
    print("ERROR: Failed to generate bridge manifest", file=sys.stderr)
    sys.exit(1)
```

**Step 3: Wire into main()**

In `main()`, replace the `# Phase 1` comment:

```python
    async with httpx.AsyncClient() as client:
        # Phase 1
        bridges = await generate_manifest(client, base_url, api_key, model, args.count)

        # Save manifest
        for i, b in enumerate(bridges):
            b["format"] = "pdf" if random.random() < args.pdf_ratio else "md"
        manifest_path = out / "manifest.json"
        manifest_path.write_text(json.dumps(bridges, ensure_ascii=False, indent=2))
        print(f"Manifest saved: {manifest_path}")
```

**Step 4: Test Phase 1 only**

Run: `python3 scripts/generate_test_docs.py --count 5`
Expected: prints "Phase 1: got 5 bridges", saves `data/generated/manifest.json` with 5 entries.

**Step 5: Commit**

```bash
git add scripts/generate_test_docs.py
git commit -m "feat: implement Phase 1 bridge manifest generation"
```

---

### Task 5: Implement Phase 2 — per-bridge document generation

**Files:**
- Modify: `scripts/generate_test_docs.py`

**Step 1: Add document generation function**

```python
async def generate_document(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    bridge: dict,
    sem: asyncio.Semaphore,
) -> str:
    """Phase 2: Generate a full technical document for one bridge."""
    name = bridge["name"]
    region = bridge.get("region", "")
    era = bridge.get("era", "")
    bridge_type = bridge.get("bridge_type", "")

    prompt = f"""你是一位桥梁工程专家。请撰写一篇关于"{name}"（{region}，{era}，{bridge_type}）的详细技术文档。

要求：
- 基于真实信息，内容 1000-2000 字
- 自由组织章节结构，使用 Markdown 标题层级
- 不限定章节数量和主题，按你认为最合适的方式组织"""

    async with sem:
        return await chat(client, base_url, api_key, model,
                         [{"role": "user", "content": prompt}],
                         temperature=0.8)
```

**Step 2: Add batch generation with progress in main()**

After the manifest save in `main()`:

```python
        # Phase 2
        sem = asyncio.Semaphore(args.concurrency)
        total = len(bridges)

        async def process_one(i: int, bridge: dict):
            name = bridge["name"]
            try:
                content = await generate_document(
                    client, base_url, api_key, model, bridge, sem
                )
                fmt = bridge.get("format", "md")
                if fmt == "pdf":
                    save_pdf(content, out / f"{name}.pdf")
                else:
                    (out / f"{name}.md").write_text(content, encoding="utf-8")
                print(f"[{i+1}/{total}] {name} -> .{fmt}")
            except Exception as e:
                print(f"[{i+1}/{total}] {name} FAILED: {e}", file=sys.stderr)

        tasks = [process_one(i, b) for i, b in enumerate(bridges)]
        await asyncio.gather(*tasks)
        print(f"\nDone! {total} documents in {out.resolve()}")
```

Note: `save_pdf` is a placeholder that will be implemented in Task 6. For now add a stub:

```python
def save_pdf(markdown_content: str, path: Path):
    """Stub — implemented in Task 6."""
    # Fallback: save as .md with .pdf extension warning
    path.with_suffix(".md").write_text(markdown_content, encoding="utf-8")
    print(f"  (PDF stub: saved as .md instead)")
```

**Step 3: Test with small count**

Run: `python3 scripts/generate_test_docs.py --count 3 --pdf-ratio 0`
Expected: generates 3 `.md` files in `data/generated/`, each 1000-2000 chars of bridge content.

**Step 4: Commit**

```bash
git add scripts/generate_test_docs.py
git commit -m "feat: implement Phase 2 per-bridge document generation"
```

---

### Task 6: Implement PDF generation with fpdf2

**Files:**
- Modify: `scripts/generate_test_docs.py` (replace `save_pdf` stub)

**Step 1: Find a usable Chinese font**

The script needs a TTF with CJK coverage. On macOS, PingFang is available at `/System/Library/Fonts/PingFang.ttc`. On Linux, look for NotoSansCJK. Add a helper:

```python
def find_cjk_font() -> str | None:
    """Find a CJK-capable TTF/TTC font on this system."""
    candidates = [
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None
```

**Step 2: Implement save_pdf**

Replace the stub with:

```python
def save_pdf(markdown_content: str, path: Path, font_path: str | None = None):
    """Convert Markdown text to a simple PDF with CJK support."""
    from fpdf import FPDF

    if not font_path:
        # Fallback: save as markdown
        fallback = path.with_suffix(".md")
        fallback.write_text(markdown_content, encoding="utf-8")
        print(f"  (no CJK font: saved as {fallback.name})")
        return

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("CJK", "", font_path, uni=True)
    pdf.add_font("CJK", "B", font_path, uni=True)

    for line in markdown_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            pdf.set_font("CJK", "B", 13)
            pdf.multi_cell(0, 8, stripped[4:])
            pdf.ln(2)
        elif stripped.startswith("## "):
            pdf.set_font("CJK", "B", 15)
            pdf.multi_cell(0, 9, stripped[3:])
            pdf.ln(3)
        elif stripped.startswith("# "):
            pdf.set_font("CJK", "B", 18)
            pdf.multi_cell(0, 10, stripped[2:])
            pdf.ln(4)
        elif stripped:
            pdf.set_font("CJK", "", 11)
            pdf.multi_cell(0, 7, stripped)
            pdf.ln(1)
        else:
            pdf.ln(4)

    pdf.output(str(path))
```

**Step 3: Wire font detection into main()**

Before Phase 2 in `main()`, add:

```python
        font_path = find_cjk_font()
        if font_path:
            print(f"CJK font: {font_path}")
        else:
            print("WARNING: No CJK font found, PDFs will fall back to Markdown")
```

Update `process_one` to pass `font_path`:

```python
                if fmt == "pdf":
                    save_pdf(content, out / f"{name}.pdf", font_path)
```

**Step 4: Test PDF output**

Run: `python3 scripts/generate_test_docs.py --count 2 --pdf-ratio 1.0`
Expected: generates 2 `.pdf` files in `data/generated/`. Open one to verify Chinese text renders.

**Step 5: Commit**

```bash
git add scripts/generate_test_docs.py
git commit -m "feat: implement PDF generation with fpdf2 and CJK font"
```

---

### Task 7: Add data/generated to .gitignore and do final test

**Files:**
- Modify: `.gitignore`

**Step 1: Add generated data directory to .gitignore**

Append to `.gitignore`:

```
# Generated test documents
data/generated/
```

**Step 2: Full end-to-end test**

Run: `python3 scripts/generate_test_docs.py --count 5 --pdf-ratio 0.5 --concurrency 3`
Expected:
- `data/generated/manifest.json` with 5 entries
- Mix of `.md` and `.pdf` files (~2-3 of each)
- Each `.md` is 1000-2000 chars of Markdown with headings
- Each `.pdf` opens and displays Chinese text
- Console shows `[1/5]` through `[5/5]` progress

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore generated test documents"
```

---

## Summary

| Task | What | Key files |
|------|------|-----------|
| 1 | Add fpdf2 dependency | `pyproject.toml` |
| 2 | Add LLM env vars to .env.example | `.env.example` |
| 3 | Script skeleton + CLI parsing | `scripts/generate_test_docs.py` |
| 4 | Phase 1: bridge manifest generation | `scripts/generate_test_docs.py` |
| 5 | Phase 2: per-bridge document generation | `scripts/generate_test_docs.py` |
| 6 | PDF generation with fpdf2 | `scripts/generate_test_docs.py` |
| 7 | Gitignore + final E2E test | `.gitignore` |
