# Multi-Provider + Task-Level Model Routing — Deploy Checklist

Use this before merging Phase A→F to production.

## Pre-deploy

- [ ] `ZHIPU_API_KEY` still set in 1Password "app" env — the v13 migration seeds the default route to it; missing key will make every LLM task fail with `ProviderConfigurationError`.
- [ ] If introducing a new provider at deploy time (DeepSeek / OpenRouter / Moonshot / MiniMax): add the corresponding env var (`DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, etc.) to 1Password BEFORE the admin UI PATCH adds the provider row. Otherwise the first `/test` call returns "env var not set".
- [ ] Confirm `scripts/migrate_db.py` runs cleanly on staging: `PYTHONPATH=. python3 scripts/migrate_db.py` → should report "v12 → v13" migration success OR "Schema v13 matches code. No migrations needed." if already migrated.

## Post-deploy smoke (run inside container)

```bash
ssh netcup "docker exec bridge_rag_api python3 -c '
from app.core.database import engine
from sqlalchemy import text
with engine.connect() as c:
    print(c.execute(text(\"SELECT version FROM schema_version ORDER BY created_at DESC LIMIT 1\")).scalar())
    print(c.execute(text(\"SELECT COUNT(*) FROM llm_task_routes\")).scalar())
'"
```

Expected: `13` and `7`.

Then exercise one real code path:

```bash
ssh netcup "docker exec bridge_rag_api python3 -c '
import asyncio
from app.llm import chat_for_task
from app.providers.base import ChatMessage
resp = asyncio.run(chat_for_task(\"qa_facet_extraction\", [ChatMessage(role=\"user\", content=\"赵州桥\")]))
print(resp.model, len(resp.content))
'"
```

Expected: prints `glm-4-flash <some positive int>` (or whatever task_key's model is configured).

## Rollback plan

If anything is wrong post-deploy:

1. Roll back code via git revert of Phase A-F PRs (main — in reverse order F→A).
2. DB rollback (if needed):
   ```sql
   DROP TABLE IF EXISTS llm_task_routes;
   DROP TABLE IF EXISTS llm_provider_models;
   DROP TABLE IF EXISTS llm_providers;
   UPDATE schema_version SET version = 12 WHERE version = 13;
   ```
3. Re-deploy. Phase D-era code (still on `main` pre-revert) depends on these tables — do NOT roll back DB while Phase D code is live.

## Observability checks

After first 10 minutes of traffic, verify the structured log:

```bash
ssh netcup "docker logs bridge_rag_api 2>&1 | grep '\"event\":\"llm_call\"' | head -20"
```

Each line is JSON with: `task_key`, `provider_class`, `model_id`, `status`, `latency_ms`. Failures also have `failure_reason` (sanitized).

## Known flakies (pre-existing, NOT caused by Phase A-F)

- `test_kp_bridge_service::TestSyncFromChunks::test_raises_when_no_taxonomy_node`
- `test_api_v1_ingest::test_ingest_v1_e2e_writes_chunks_and_tsv`

These are documented in CLAUDE.md — ignore them in CI.
