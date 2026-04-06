"""Generate synthetic bridge documents for ingest testing.

Standalone script — does NOT import from app/ or use existing providers.
Uses any OpenAI-compatible chat API to generate realistic Chinese bridge documents.

Usage:
    python3 scripts/generate_test_docs.py --count 30 --output-dir data/generated

Environment variables (loaded from .env if present):
    LLM_BASE_URL   — OpenAI-compatible API base (e.g. https://open.bigmodel.cn/api/paas/v4)
    LLM_API_KEY    — API key
    LLM_MODEL      — Model name (e.g. glm-4-flash)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# .env loader (no python-dotenv dependency)
# ---------------------------------------------------------------------------

def load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def get_env(name: str, dotenv: dict[str, str], default: str | None = None) -> str:
    """Return env var from os.environ, falling back to dotenv, then default."""
    import os
    val = os.environ.get(name) or dotenv.get(name) or default
    if val is None:
        print(f"Error: {name} not set. Set it in .env or environment.")
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# OpenAI-compatible chat helper
# ---------------------------------------------------------------------------

async def chat(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    json_mode: bool = False,
) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint. Returns content string."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = await client.post(
        url,
        json=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Phase 1 — bridge manifest generation
# ---------------------------------------------------------------------------

MANIFEST_PROMPT = """\
你是一位中国桥梁专家。请生成一个包含 {count} 座真实中国桥梁的 JSON 数组。

要求:
- 每座桥梁都必须是真实存在的
- 类型多样: 包含梁桥、拱桥、悬索桥、斜拉桥、廊桥、浮桥等
- 年代跨度大: 从古代到现代
- 地域分布广: 覆盖不同省份
- 材料多样: 石、木、铁、钢、混凝土等

每个条目的格式:
{{
  "name": "桥梁名称",
  "bridge_type": "桥型(梁桥/拱桥/悬索桥/斜拉桥/廊桥/浮桥/其他)",
  "material": "主要材料",
  "era": "建造年代或朝代",
  "region": "所在省份或地区",
  "function": "功能(公路/铁路/人行/公铁两用/其他)",
  "summary": "一句话简介(30字以内)"
}}

只返回 JSON 数组，不要其他文字。"""


async def generate_manifest(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    count: int,
) -> list[dict[str, str]]:
    """Generate bridge manifest via a single LLM call. Retries once on parse failure."""
    prompt = MANIFEST_PROMPT.format(count=count)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(2):
        temp = 0.7 if attempt == 0 else 0.3
        raw = await chat(client, base_url, api_key, model, messages, temperature=temp, json_mode=True)
        try:
            # Try to extract JSON array — LLM may wrap in markdown or extra text
            raw = raw.strip()
            # If wrapped in ```json ... ```, extract
            m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1)
            result = json.loads(raw)
            if isinstance(result, dict) and len(result) == 1:
                # Some models wrap in {"bridges": [...]}
                result = list(result.values())[0]
            if not isinstance(result, list):
                raise ValueError("Expected JSON array")
            return result
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                print(f"  JSON parse failed ({e}), retrying with higher temperature...")
            else:
                print(f"  JSON parse failed on retry: {e}")
                print(f"  Raw response:\n{raw[:500]}")
                sys.exit(1)

    return []  # unreachable


# ---------------------------------------------------------------------------
# Phase 2 — per-bridge document generation
# ---------------------------------------------------------------------------

DOC_PROMPT = """\
你是一位桥梁工程专家。请撰写一篇关于"{name}"（{region}，{era}，{bridge_type}）的详细技术文档。

要求：
- 基于真实信息，内容 1000-2000 字
- 自由组织章节结构，使用 Markdown 标题层级
- 不限定章节数量和主题，按你认为最合适的方式组织"""


async def generate_document(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    bridge: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> str | None:
    """Generate a Markdown document for one bridge. Returns content or None on failure."""
    prompt = DOC_PROMPT.format(
        name=bridge.get("name", ""),
        region=bridge.get("region", ""),
        era=bridge.get("era", ""),
        bridge_type=bridge.get("bridge_type", ""),
    )
    messages = [{"role": "user", "content": prompt}]

    async with semaphore:
        try:
            content = await chat(client, base_url, api_key, model, messages, temperature=0.7)
            return content.strip()
        except Exception as e:
            print(f"  Error generating doc for {bridge['name']}: {e}")
            return None


# ---------------------------------------------------------------------------
# PDF generation with fpdf2
# ---------------------------------------------------------------------------

CJK_FONT_PATHS = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    # Linux common locations
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf",
]


def find_cjk_font() -> str | None:
    """Search common paths for a CJK-capable font. Returns path or None."""
    for p in CJK_FONT_PATHS:
        if Path(p).exists():
            return p
    return None


def save_pdf(markdown_content: str, path: Path, font_path: str) -> None:
    """Convert Markdown content to a simple PDF with CJK support.

    Handles headings (#/##/###) and body text. Not a full Markdown renderer.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Register CJK font
    font_name = "CJK"
    pdf.add_font(font_name, "", font_path, uni=True)
    pdf.add_font(font_name, "B", font_path, uni=True)

    for line in markdown_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(4)
            continue

        # Detect heading level
        heading_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            sizes = {1: 18, 2: 15, 3: 13}
            size = sizes.get(level, 13)
            pdf.set_font(font_name, "B", size)
            pdf.ln(4)
            pdf.multi_cell(0, size * 0.6, text)
            pdf.ln(2)
        else:
            pdf.set_font(font_name, "", 11)
            pdf.multi_cell(0, 6, stripped)

    pdf.output(str(path))


def save_markdown(content: str, path: Path) -> None:
    """Save content as a Markdown file."""
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    dotenv = load_dotenv(Path(".env"))
    base_url = get_env("LLM_BASE_URL", dotenv)
    api_key = get_env("LLM_API_KEY", dotenv)
    model = get_env("LLM_MODEL", dotenv, default="gpt-4o-mini")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check CJK font for PDF generation
    font_path: str | None = None
    if args.pdf_ratio > 0:
        font_path = find_cjk_font()
        if font_path is None:
            print("Warning: No CJK font found. All files will be saved as .md instead.")
            args.pdf_ratio = 0.0

    print(f"Config: {args.count} docs, pdf_ratio={args.pdf_ratio}, "
          f"concurrency={args.concurrency}, output={output_dir}")
    print(f"LLM: {model} @ {base_url}")
    print()

    async with httpx.AsyncClient() as client:
        # Phase 1: Generate manifest
        print("Phase 1: Generating bridge manifest...")
        bridges = await generate_manifest(client, base_url, api_key, model, args.count)
        print(f"  Generated {len(bridges)} bridge entries")

        # Randomly assign format to each bridge
        for bridge in bridges:
            bridge["format"] = "pdf" if random.random() < args.pdf_ratio else "md"

        # Save manifest
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(bridges, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Saved manifest to {manifest_path}")
        print()

        # Phase 2: Generate documents
        print("Phase 2: Generating documents...")
        semaphore = asyncio.Semaphore(args.concurrency)

        async def generate_and_save(i: int, bridge: dict[str, str]) -> bool:
            fmt = bridge.get("format", "md")
            content = await generate_document(
                client, base_url, api_key, model, bridge, semaphore,
            )
            if content is None:
                print(f"  [{i+1}/{len(bridges)}] {bridge['name']} -> FAILED")
                return False

            # Sanitize filename
            safe_name = re.sub(r'[\\/:*?"<>|]', "_", bridge["name"])

            if fmt == "pdf" and font_path:
                path = output_dir / f"{safe_name}.pdf"
                try:
                    save_pdf(content, path, font_path)
                except Exception as e:
                    print(f"  [{i+1}/{len(bridges)}] {bridge['name']} -> PDF failed ({e}), saving as .md")
                    path = output_dir / f"{safe_name}.md"
                    save_markdown(content, path)
            else:
                path = output_dir / f"{safe_name}.md"
                save_markdown(content, path)

            print(f"  [{i+1}/{len(bridges)}] {bridge['name']} -> {path.suffix}")
            return True

        tasks = [generate_and_save(i, b) for i, b in enumerate(bridges)]
        results = await asyncio.gather(*tasks)

        success = sum(1 for r in results if r)
        failed = len(results) - success
        print()
        print(f"Done: {success} generated, {failed} failed. Output: {output_dir}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic bridge documents for ingest testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Environment variables (from .env or shell):
  LLM_BASE_URL    OpenAI-compatible API base URL
  LLM_API_KEY     API key
  LLM_MODEL       Model name (e.g. glm-4-flash)

Examples:
  python3 scripts/generate_test_docs.py --count 10
  python3 scripts/generate_test_docs.py --count 30 --pdf-ratio 0.3 --concurrency 3
""",
    )
    parser.add_argument(
        "--count", type=int, default=30,
        help="Number of documents to generate (default: 30)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="data/generated",
        help="Output directory (default: data/generated)",
    )
    parser.add_argument(
        "--pdf-ratio", type=float, default=0.5,
        help="Fraction of documents saved as PDF (default: 0.5)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Max concurrent LLM requests (default: 5)",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if not 0.0 <= args.pdf_ratio <= 1.0:
        parser.error("--pdf-ratio must be between 0.0 and 1.0")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
