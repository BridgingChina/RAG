"""Hard-coded description map for the 7 Phase B/C task keys.

The admin UI (Phase E) pulls from this to annotate each task row in the
routing table so operators know what they're re-routing before they click.
Keys here must stay in sync with migration v13's ``llm_task_routes`` seed.

This is deliberately a flat dict (not a DB table) — task keys are defined in
code call-sites (``chat_for_task("qa_generation", ...)``), so adding a new
task already requires a code change. One more dict entry in the same PR is
cheaper than a join + migration.
"""
from __future__ import annotations


TASK_DESCRIPTIONS: dict[str, str] = {
    "qa_generation": "用户 RAG 问答生成最终回答（质量敏感，建议好档模型）",
    "qa_facet_extraction": "从用户问题抽取 facet 维度（轻量高频，建议便宜档）",
    "ingest_tagger": "入库时 chunk 自动打 lvl1/lvl2/lvl3 标签",
    "ingest_context_enricher": "入库时为 chunk 生成上下文描述",
    "ingest_bridge_linker": "入库时判断 chunk 归属哪座桥",
    "content_generation": "管理端生成闪卡 / 知识点要点（质量敏感但非实时）",
    "translation": "i18n 翻译 — 桥梁/知识点等 zh→en",
}
