# Multi-Provider + Task-Level Model Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give Bridge RAG a multi-LLM-provider adapter layer with per-task (provider, model) routing that admins can reconfigure from the web console — without ever exposing API keys to the database, HTTP responses, or frontend.

**Architecture:** Thin provider abstraction (3 subclasses) + DB-backed routing table (v12, 3 new tables) + admin REST API + React UI. Keys stay in env vars only. See design doc: `docs/plans/2026-04-21-multi-provider-model-routing-design.md` (commit `7b027e2`).

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy + PostgreSQL + pgvector (backend); Vite + React 19 + TanStack Query + shadcn/ui (admin console); pytest + vitest (tests).

**Phase boundaries = PR boundaries.** Each phase ships independently.

---

## Phase Overview

| Phase | Scope | Risk | Ships | PR depends on |
|---|---|---|---|---|
| **A** | Provider ABC + 3 concrete providers + sanitizer + config | 0 user impact (pure additions) | A-only | — |
| **B** | DB schema v12 + migration + seed | Schema change; zero behavior change | B-only | A |
| **C** | Router + registry + migrate 8 call sites + remove qa.py monkey-patch | Touches every LLM call; needs careful review | C-only | B |
| **D** | Admin REST API (11 endpoints) | New endpoints only | D-only | C |
| **E** | Admin UI (LLMSettingsPage + tabs + dialogs) | Frontend only | E-only | D |
| **F** | Structured logging + CLAUDE.md sync + E2E | Doc + observability | F-only | E |

---

# Phase A — Provider Layer Foundation

**Goal:** New code that nothing calls yet. Existing system untouched.

## Task A1: Provider error classes

**Files:**
- Create: `app/providers/errors.py`
- Create: `tests/test_provider_errors.py`

**Step 1: Write the failing test**

```python
# tests/test_provider_errors.py
import pytest
from app.providers.errors import (
    ProviderError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    ModelNotFoundError,
    TaskRouteNotFoundError,
)


def test_all_errors_subclass_provider_error():
    assert issubclass(ProviderConfigurationError, ProviderError)
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(ModelNotFoundError, ProviderError)
    assert issubclass(TaskRouteNotFoundError, ProviderError)


def test_provider_error_carries_message():
    exc = ProviderConfigurationError("env var missing")
    assert "env var missing" in str(exc)
```

**Step 2: Run test — expect fail**
```
pytest tests/test_provider_errors.py -v
# → ImportError: app.providers.errors
```

**Step 3: Implement**
```python
# app/providers/errors.py
class ProviderError(Exception):
    """Base class for all provider-layer exceptions."""


class ProviderConfigurationError(ProviderError):
    """Missing env var, invalid base_url, unknown kind. → HTTP 400."""


class ProviderUnavailableError(ProviderError):
    """Upstream 429/5xx/network failure. → HTTP 502, message sanitized."""


class ModelNotFoundError(ProviderError):
    """Routed model_id no longer present in list_models(). → HTTP 409."""


class TaskRouteNotFoundError(ProviderError):
    """task_key has no row in llm_task_routes. → HTTP 500 (bug)."""
```

**Step 4: Run — expect pass**
```
pytest tests/test_provider_errors.py -v
# → 2 passed
```

**Step 5: Commit**
```bash
git add app/providers/errors.py tests/test_provider_errors.py
git commit -m "feat(llm): provider error class hierarchy"
```

---

## Task A2: `sanitize_error()` — zero-key-leak sanitizer

**Files:**
- Create: `app/providers/_sanitize.py`
- Create: `tests/test_provider_sanitize.py`

**Step 1: Write failing tests**
```python
# tests/test_provider_sanitize.py
import httpx
import pytest
from app.providers._sanitize import register_sensitive_key, sanitize_error, _reset


@pytest.fixture(autouse=True)
def reset():
    _reset()
    yield
    _reset()


def test_strips_registered_key(monkeypatch):
    monkeypatch.setenv("FAKE_KEY", "sk-abc123def456ghi789jkl012")
    register_sensitive_key("FAKE_KEY")
    exc = RuntimeError("401 Bearer sk-abc123def456ghi789jkl012 invalid")
    out = sanitize_error(exc)
    assert "sk-abc123def456ghi789jkl012" not in out
    assert "***KEY***" in out


def test_regex_fallback_strips_bearer_token():
    exc = RuntimeError("got Bearer qwertyuiopasdfghjkl1234567 back")
    out = sanitize_error(exc)
    assert "qwertyuiopasdfghjkl" not in out
    assert "***KEY***" in out


def test_regex_fallback_strips_sk_prefix():
    exc = RuntimeError("api_key=sk-abcdefghijklmnopqrstuvwx expired")
    out = sanitize_error(exc)
    assert "sk-abcdefghijklmnopqrstuvwx" not in out


def test_truncates_to_300_chars():
    exc = RuntimeError("x" * 1000)
    assert len(sanitize_error(exc)) <= 300


def test_includes_cause_chain():
    cause = ValueError("underlying")
    exc = RuntimeError("wrapper")
    exc.__cause__ = cause
    out = sanitize_error(exc)
    assert "underlying" in out
    assert "wrapper" in out


def test_short_env_values_not_registered(monkeypatch):
    # values < 16 chars aren't treated as keys (false-positive guard)
    monkeypatch.setenv("SHORT", "dev")
    register_sensitive_key("SHORT")
    exc = RuntimeError("running in dev mode")
    assert "dev" in sanitize_error(exc)
```

**Step 2: Run — expect fail**
```
pytest tests/test_provider_sanitize.py -v
```

**Step 3: Implement**
```python
# app/providers/_sanitize.py
import os
import re

_SENSITIVE_KEYS: set[str] = set()


def _reset() -> None:  # test helper
    _SENSITIVE_KEYS.clear()


def register_sensitive_key(env_name: str) -> None:
    """Add current env value to the sanitize blacklist. Idempotent."""
    v = os.environ.get(env_name)
    if v and len(v) >= 16:
        _SENSITIVE_KEYS.add(v)


def sanitize_error(exc: BaseException) -> str:
    raw = f"{type(exc).__name__}: {exc}"
    if exc.__cause__:
        raw += f" (cause: {type(exc.__cause__).__name__}: {exc.__cause__})"

    for k in _SENSITIVE_KEYS:
        raw = raw.replace(k, "***KEY***")

    raw = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}", "Bearer ***KEY***", raw)
    raw = re.sub(r"sk-[A-Za-z0-9_\-]{20,}", "sk-***KEY***", raw)
    raw = re.sub(
        r"(api[_-]?key|token)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}[\"']?",
        r"\1=***KEY***",
        raw,
        flags=re.IGNORECASE,
    )
    return raw[:300]
```

**Step 4: Run — expect pass**
```
pytest tests/test_provider_sanitize.py -v  # 6 passed
```

**Step 5: Commit**
```bash
git add app/providers/_sanitize.py tests/test_provider_sanitize.py
git commit -m "feat(llm): add sanitize_error() — zero-key-leak third-line guard"
```

---

## Task A3: `ProviderConfig` + `resolve_api_key()`

**Files:**
- Create: `app/providers/config.py`
- Create: `app/providers/_secret.py`
- Create: `tests/test_provider_config.py`

**Step 1: Failing tests**
```python
# tests/test_provider_config.py
import pytest
from app.providers.config import ProviderConfig
from app.providers._secret import resolve_api_key
from app.providers.errors import ProviderConfigurationError


def test_config_is_frozen():
    c = ProviderConfig(
        provider_id="pid", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        c.base_url = "https://y"  # type: ignore


def test_config_default_extras():
    c = ProviderConfig(
        provider_id="pid", kind="zhipu",
        base_url="https://x", api_key_env="FAKE",
    )
    assert c.extra_headers == {}
    assert c.timeout_read == 90.0


def test_resolve_api_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_api_key("MISSING_KEY")
    assert "MISSING_KEY" in str(exc_info.value)


def test_resolve_api_key_returns_value(monkeypatch):
    monkeypatch.setenv("REAL_KEY", "sk-thisisalongenoughkey1234")
    assert resolve_api_key("REAL_KEY") == "sk-thisisalongenoughkey1234"
```

**Step 2: Run — expect fail**

**Step 3: Implement**
```python
# app/providers/config.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    kind: str
    base_url: str
    api_key_env: str
    extra_headers: dict = field(default_factory=dict)
    timeout_read: float = 90.0
```

```python
# app/providers/_secret.py
import os
from app.providers.errors import ProviderConfigurationError


def resolve_api_key(env_name: str) -> str:
    key = os.environ.get(env_name)
    if not key:
        raise ProviderConfigurationError(
            f"env var {env_name} not set; refusing to call provider with empty key"
        )
    return key
```

**Step 4: Run — expect pass**

**Step 5: Commit**
```bash
git add app/providers/config.py app/providers/_secret.py tests/test_provider_config.py
git commit -m "feat(llm): ProviderConfig frozen dataclass + resolve_api_key() single entry"
```

---

## Task A4: `ModelInfo` + ABC extension

**Files:**
- Modify: `app/providers/base.py` (add `ModelInfo`, `list_models`, `chat`/`embed` signature change)
- Modify: `tests/test_providers.py` (update existing tests if any break)
- Create: `tests/test_providers_contract.py`

**Step 1: Failing test — ABC contract**
```python
# tests/test_providers_contract.py
import inspect
import pytest
from app.providers.base import LLMProvider, ChatMessage, ModelInfo


def test_modelinfo_required_fields():
    m = ModelInfo(id="x", display_name="X", kind="chat")
    assert m.id == "x"
    assert m.context_window is None
    assert m.extra == {}


def test_list_models_is_abstract():
    assert "list_models" in LLMProvider.__abstractmethods__


def test_chat_has_model_keyword_only():
    sig = inspect.signature(LLMProvider.chat)
    assert "model" in sig.parameters


def test_embed_has_model_keyword_only():
    sig = inspect.signature(LLMProvider.embed)
    assert "model" in sig.parameters
```

**Step 2: Run — expect fail** (`ModelInfo` not exported)

**Step 3: Implement — modify `app/providers/base.py`**
```python
# app/providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatResponse:
    content: str
    usage: dict
    model: str = ""  # NEW: actual model used; default "" for back-compat


@dataclass
class ModelInfo:
    id: str
    display_name: str
    kind: str
    context_window: int | None = None
    extra: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float]]:
        """model: None → provider fallback (self.embedding_model). Phase C flips to required."""

    @abstractmethod
    async def chat(
        self, messages: list[ChatMessage], *, model: str | None = None
    ) -> ChatResponse:
        """model: None → provider fallback (self.chat_model). Phase C flips to required."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Fetch upstream model list. Raise ProviderUnavailableError on HTTP failures."""
```

**Note on signature**: `model: str | None = None` during Phase A–B so existing callers still work. Phase C finale: tighten to `model: str` required + remove default.

**Step 4: Run — expect pass** for `tests/test_providers_contract.py`. Existing `tests/test_providers.py` will start failing because `ZhipuProvider` doesn't yet implement `list_models`. Fix in A5.

**Step 5: Commit**
```bash
git add app/providers/base.py tests/test_providers_contract.py
git commit -m "feat(llm): extend LLMProvider ABC with ModelInfo + list_models + model= kwarg"
```

---

## Task A5: `ZhipuProvider` — `list_models` + `model=` kwarg fallback

**Files:**
- Modify: `app/providers/zhipu.py`
- Modify: `tests/test_providers.py`
- Modify: `app/providers/zhipu_coding.py` (inherits from Zhipu)

**Step 1: Failing tests**
```python
# tests/test_providers.py (add)
import pytest
import respx
import httpx
from app.providers.zhipu import ZhipuProvider
from app.providers.base import ChatMessage


@pytest.mark.asyncio
@respx.mock
async def test_list_models_parses_response(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-1234567890ab")
    respx.get("https://open.bigmodel.cn/api/paas/v4/models").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"id": "glm-4.7", "object": "model"},
                {"id": "glm-4-flash", "object": "model"},
            ]
        })
    )
    p = ZhipuProvider()
    models = await p.list_models()
    assert {m.id for m in models} == {"glm-4.7", "glm-4-flash"}
    assert all(m.kind == "chat" for m in models)  # Zhipu doesn't tag kind → default "chat"


@pytest.mark.asyncio
@respx.mock
async def test_chat_uses_passed_model(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-1234567890ab")
    captured = {}
    def _capture(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
    respx.post("https://open.bigmodel.cn/api/paas/v4/chat/completions").mock(side_effect=_capture)
    p = ZhipuProvider()
    resp = await p.chat([ChatMessage("user", "hello")], model="glm-4-custom")
    assert b'"model":"glm-4-custom"' in captured["body"]
    assert resp.model == "glm-4-custom"


@pytest.mark.asyncio
@respx.mock
async def test_chat_falls_back_to_self_chat_model_when_model_none(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-1234567890ab")
    captured = {}
    def _capture(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {},
        })
    respx.post("https://open.bigmodel.cn/api/paas/v4/chat/completions").mock(side_effect=_capture)
    p = ZhipuProvider()
    await p.chat([ChatMessage("user", "hello")])  # no model=
    # should fall back to settings.chat_model default (glm-4.7)
    assert b'"model":"glm-4.7"' in captured["body"]
```

**Step 2: Run — expect fail**

**Step 3: Implement — modify `app/providers/zhipu.py`**

Changes:
1. `chat(messages, *, model: str | None = None)` — use `model or self.chat_model`
2. `embed(texts, *, model: str | None = None)` — use `model or self.embedding_model`
3. Add `list_models()` → `GET {BASE_URL}/models`
4. Return `ChatResponse(..., model=actual_model_used)`

Key snippet:
```python
async def chat(self, messages, *, model: str | None = None) -> ChatResponse:
    actual_model = model or self.chat_model
    base = self.CHAT_BASE_URL or self.BASE_URL
    async with _zhipu_semaphore:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers=self._headers(),
                json={"model": actual_model, "messages": [...]},
                timeout=_chat_timeout(),
            )
    resp.raise_for_status()
    data = resp.json()
    # ... existing parsing ...
    return ChatResponse(content=content, usage=data.get("usage", {}), model=actual_model)


async def list_models(self) -> list[ModelInfo]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{self.BASE_URL}/models",
            headers=self._headers(),
            timeout=httpx.Timeout(connect=10, read=20, write=10, pool=10),
        )
    resp.raise_for_status()
    data = resp.json()
    return [
        ModelInfo(
            id=row["id"],
            display_name=row.get("id"),
            kind=row.get("kind", "chat"),
            context_window=row.get("context_window"),
        )
        for row in data.get("data", [])
    ]
```

Same for `embed`.

**Step 4: Run — expect pass**
```
pytest tests/test_providers.py -v
```

**Step 5: Commit**
```bash
git add app/providers/zhipu.py app/providers/zhipu_coding.py tests/test_providers.py
git commit -m "feat(llm): ZhipuProvider implements list_models + accepts model= kwarg"
```

---

## Task A6–A8: `OpenAICompatProvider` + `MiniMaxProvider`

Same pattern as A5 but for new classes. Break into 3 tasks:

### Task A6: `OpenAICompatProvider.chat + embed`

**Files:**
- Create: `app/providers/openai_compat.py`
- Create: `tests/test_openai_compat_provider.py`

TDD steps identical to A5. Key differences:
- Constructor: `__init__(self, config: ProviderConfig)` — takes config, not settings
- Uses `resolve_api_key(config.api_key_env)` in `_headers()`
- Includes `config.extra_headers` in `_headers()` output
- Endpoints: `POST {base_url}/v1/chat/completions`, `POST {base_url}/v1/embeddings`
- Reuses tenacity retry decorator (copy from ZhipuProvider)

Commit: `feat(llm): OpenAICompatProvider chat + embed for DeepSeek/Moonshot/OpenRouter/etc`

### Task A7: `OpenAICompatProvider.list_models`

**Files:**
- Modify: `app/providers/openai_compat.py`
- Modify: `tests/test_openai_compat_provider.py`

Endpoint: `GET {base_url}/v1/models` → parse `data: [{id, owned_by, ...}]`.

Commit: `feat(llm): OpenAICompatProvider.list_models`

### Task A8: `MiniMaxProvider`

**Files:**
- Create: `app/providers/minimax.py`
- Create: `tests/test_minimax_provider.py`

Differences from OpenAI-compat:
- Response body wraps in `base_resp` — need `if data.get("base_resp", {}).get("status_code") != 0: raise ProviderUnavailableError(...)`
- No `embed` → raise `NotImplementedError` inside MVP (MiniMax embedding not on our Y list)

Commit: `feat(llm): MiniMaxProvider with base_resp unwrap`

---

## Task A9: Wire `register_sensitive_key` at app startup

**Files:**
- Modify: `app/main.py` (add startup hook)
- Create/modify: `tests/test_main_startup.py`

**Step 1: Test**
```python
async def test_startup_registers_known_env_keys(monkeypatch):
    from app.providers._sanitize import _SENSITIVE_KEYS, _reset
    _reset()
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-long-enough-zhipu-token-123")
    # Reuse or stub FastAPI startup event
    from app.main import on_startup_register_keys
    await on_startup_register_keys()
    assert "sk-long-enough-zhipu-token-123" in _SENSITIVE_KEYS
```

**Step 2: Run — expect fail**

**Step 3: Implement** — in `app/main.py`:
```python
@app.on_event("startup")
async def on_startup_register_keys():
    from app.providers._sanitize import register_sensitive_key
    # Seed with currently known envs (ZHIPU + anything already in .env).
    # Phase C router will re-register per DB row.
    for env in ("ZHIPU_API_KEY",):
        register_sensitive_key(env)
```

**Step 4: Run — expect pass**

**Step 5: Commit**
```bash
git add app/main.py tests/test_main_startup.py
git commit -m "feat(llm): register sensitive keys at app startup"
```

---

## Phase A exit criteria

- [ ] `pytest tests/test_provider_*.py tests/test_providers*.py tests/test_minimax_provider.py -v` → all pass
- [ ] `pytest tests/ -v` (full suite) → no regressions
- [ ] Open PR with title `feat(llm): Phase A — provider layer foundation (A1–A9)`
- [ ] Merge PR to main before starting Phase B

---

# Phase B — DB Schema v12

**Goal:** 3 new tables + migration + seed. Runtime behavior unchanged.

## Task B1: SQL migration file

**Files:**
- Create: `app/scripts/migrations/v12_multi_provider.py`

**Step 1: Write test file**
```python
# tests/integration/test_v12_migration.py
import pytest
from sqlalchemy import inspect as sa_inspect, text
from app.core.database import engine
from app.scripts.migrations.v12_multi_provider import migrate_v11_to_v12


@pytest.fixture
def v11_db(real_db):
    """Set schema to v11 and drop v12 tables if they exist."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS llm_task_routes"))
        conn.execute(text("DROP TABLE IF EXISTS llm_provider_models"))
        conn.execute(text("DROP TABLE IF EXISTS llm_providers"))
        conn.execute(text("UPDATE schema_version SET version = 11"))
    yield real_db


def test_v12_creates_three_tables(v11_db):
    with engine.begin() as conn:
        migrate_v11_to_v12(conn)
    insp = sa_inspect(engine)
    assert "llm_providers" in insp.get_table_names()
    assert "llm_provider_models" in insp.get_table_names()
    assert "llm_task_routes" in insp.get_table_names()


def test_v12_seeds_zhipu_provider(v11_db):
    with engine.begin() as conn:
        migrate_v11_to_v12(conn)
        rows = conn.execute(text(
            "SELECT name, kind, api_key_env FROM llm_providers"
        )).fetchall()
    assert len(rows) == 1
    assert rows[0].name == "智谱 AI（默认）"
    assert rows[0].kind == "zhipu"
    assert rows[0].api_key_env == "ZHIPU_API_KEY"


def test_v12_seeds_seven_task_routes(v11_db):
    with engine.begin() as conn:
        migrate_v11_to_v12(conn)
        rows = conn.execute(text(
            "SELECT task_key, model_id FROM llm_task_routes ORDER BY task_key"
        )).fetchall()
    keys = {r.task_key for r in rows}
    assert keys == {
        "qa_generation", "qa_facet_extraction",
        "ingest_tagger", "ingest_context_enricher", "ingest_bridge_linker",
        "content_generation", "translation",
    }
    assert all(r.model_id in {"glm-4.7", "glm-4-flash"} for r in rows)


def test_v12_is_idempotent_raises_on_rerun(v11_db):
    with engine.begin() as conn:
        migrate_v11_to_v12(conn)
    with engine.begin() as conn, pytest.raises(Exception):
        # UNIQUE(name) on llm_providers should prevent double seed
        migrate_v11_to_v12(conn)


def test_v12_fk_restrict_prevents_provider_delete_when_route_exists(v11_db):
    with engine.begin() as conn:
        migrate_v11_to_v12(conn)
    with engine.begin() as conn, pytest.raises(Exception):
        conn.execute(text(
            "DELETE FROM llm_providers WHERE name = '智谱 AI（默认）'"
        ))
```

**Step 2: Run — fail**

**Step 3: Implement `app/scripts/migrations/v12_multi_provider.py`** — full SQL + seed (see design §5.1 and §5.4). Register in `MIGRATIONS` dict in `migrate_db.py`:
```python
MIGRATIONS[(11, 12)] = migrate_v11_to_v12
```

**Step 4: Run — pass**

**Step 5: Commit**
```bash
git add app/scripts/migrations/v12_multi_provider.py tests/integration/test_v12_migration.py
git commit -m "feat(llm): v12 migration — 3 tables + seed Zhipu + 7 task routes"
```

---

## Task B2: SQLAlchemy models

**Files:**
- Create: `app/models/llm.py`
- Modify: `app/models/__init__.py`
- Create: `tests/test_models_llm.py`

**Step 1–5:** Define `LLMProvider` (rename Python class to avoid clash with ABC; use `LLMProviderRow`), `LLMProviderModel`, `LLMTaskRoute` ORM classes. All FK + UNIQUE constraints match B1 SQL.

Tests verify column presence, FK directions, CHECK constraint on `kind`.

Commit: `feat(llm): SQLAlchemy models for llm_providers / llm_provider_models / llm_task_routes`

---

## Task B3: `reset_db.py` / `init_database` path

**Files:**
- Modify: `scripts/reset_db.py`
- Modify: `app/core/database.py::init_database`

Ensure fresh-install path also creates v12 tables and seeds, so new developers get the same state as migrated ones.

**Step 1:** Test that `init_database()` on empty DB ends in schema_version=12 with 1 provider + 7 task_routes.

**Step 2–5:** Add seed call after `Base.metadata.create_all`.

Commit: `feat(llm): init_database seeds v12 llm_* tables on fresh install`

---

## Phase B exit criteria

- [ ] `pytest tests/integration/test_v12_migration.py tests/test_models_llm.py -v` → pass
- [ ] Local DB migrates cleanly: `python scripts/migrate_db.py`
- [ ] Fresh-install path: `python scripts/reset_db.py --force` ends at schema v12 with seed
- [ ] PR `feat(llm): Phase B — DB schema v12`
- [ ] **Do not merge until Phase C ready** — leaving seeded tables + no reader causes no harm, but coordinated rollout is simpler

---

# Phase C — Router + Registry + Call-Site Migration

**Goal:** `chat_for_task(task_key)` becomes the new single entry. Fix `qa.py:180` race. Registry caches providers; router caches routes.

## Task C1: `ProviderRegistry`

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/registry.py`
- Create: `tests/test_provider_registry.py`

**Step 1: Tests**
```python
def test_registry_builds_zhipu_provider_from_config():
    cfg = ProviderConfig(provider_id="pid", kind="zhipu",
                         base_url="https://open.bigmodel.cn/api/paas/v4",
                         api_key_env="ZHIPU_API_KEY")
    reg = ProviderRegistry()
    p = reg.get_or_build(cfg)
    assert isinstance(p, ZhipuProvider)


def test_registry_caches_by_provider_id():
    cfg1 = ProviderConfig(provider_id="pid", kind="zhipu", base_url="https://x", api_key_env="K")
    reg = ProviderRegistry()
    p1 = reg.get_or_build(cfg1)
    p2 = reg.get_or_build(cfg1)
    assert p1 is p2


def test_registry_invalidate_rebuilds():
    cfg = ProviderConfig(provider_id="pid", kind="zhipu", base_url="https://x", api_key_env="K")
    reg = ProviderRegistry()
    p1 = reg.get_or_build(cfg)
    reg.invalidate("pid")
    p2 = reg.get_or_build(cfg)
    assert p1 is not p2


def test_registry_unknown_kind_raises():
    cfg = ProviderConfig(provider_id="pid", kind="gemini_native",
                         base_url="https://x", api_key_env="K")
    reg = ProviderRegistry()
    with pytest.raises(ProviderConfigurationError):
        reg.get_or_build(cfg)
```

**Step 3: Implement** with `threading.Lock`, mapping `kind → Provider class`.

Commit: `feat(llm): ProviderRegistry with threaded cache + invalidate`

---

## Task C2: `router.get_for_task` (TTL cache)

**Files:**
- Create: `app/llm/router.py`
- Create: `tests/test_llm_router.py`

**Step 1: Tests** (use `freezegun` or `time_machine`):
```python
def test_router_returns_seeded_route_for_task_key(real_db):
    from app.llm.router import get_for_task
    provider, model_id = get_for_task("qa_generation")
    assert model_id == "glm-4.7"
    assert isinstance(provider, ZhipuProvider)


def test_router_raises_on_unknown_task_key(real_db):
    with pytest.raises(TaskRouteNotFoundError):
        get_for_task("nonexistent_task")


def test_router_cache_ttl_30s(real_db, time_machine):
    # 1. get route → cached
    _, model_a = get_for_task("qa_generation")
    # 2. UPDATE llm_task_routes SET model_id = 'glm-4-flash' WHERE task_key = ...
    # 3. within 30s → still returns cached model_a
    time_machine.shift(timedelta(seconds=10))
    _, model_b = get_for_task("qa_generation")
    assert model_b == model_a  # still cached
    # 4. after 31s → returns new
    time_machine.shift(timedelta(seconds=21))
    _, model_c = get_for_task("qa_generation")
    assert model_c == "glm-4-flash"


def test_router_invalidate_task_forces_refetch(real_db):
    _, _ = get_for_task("qa_generation")
    # UPDATE DB to 'glm-4-flash'
    invalidate("qa_generation")
    _, m = get_for_task("qa_generation")
    assert m == "glm-4-flash"
```

**Step 3: Implement**. Schema:
```python
# app/llm/router.py
_CACHE: dict[str, tuple[float, Provider, str]] = {}  # task_key → (expiry_ts, provider, model_id)
_CACHE_LOCK = threading.Lock()
_TTL_SECONDS = 30.0

def get_for_task(task_key: str) -> tuple[LLMProvider, str]:
    # check cache; if stale, query DB through SessionLocal(), build ProviderConfig from row,
    # pass to registry.get_or_build(), cache
```

Commit: `feat(llm): router.get_for_task with 30s TTL cache + invalidate`

---

## Task C3: High-level `chat_for_task` / `embed` helpers

**Files:**
- Modify: `app/llm/__init__.py`
- Create: `tests/test_llm_helpers.py`

**Step 1: Tests**
```python
async def test_chat_for_task_calls_provider_chat_with_correct_model():
    # mock registry to return a mock provider
    # call chat_for_task("qa_generation", [ChatMessage(...)])
    # assert provider.chat called with model="glm-4.7"


async def test_embed_uses_locked_zhipu_embedding_model(monkeypatch):
    # embed() is *not* task-routed — stays on Zhipu embedding-3
    # assert Zhipu provider called with model=settings.embedding_model
```

**Step 3: Implement**
```python
# app/llm/__init__.py
async def chat_for_task(task_key: str, messages: list[ChatMessage]) -> ChatResponse:
    provider, model_id = get_for_task(task_key)
    return await provider.chat(messages, model=model_id)


async def embed(texts: list[str]) -> list[list[float]]:
    # Embedding is locked: always Zhipu. Future v2 may route per-kind.
    from app.providers import get_provider  # legacy, stays only here
    return await get_provider().embed(texts, model=settings.embedding_model)
```

Commit: `feat(llm): chat_for_task + embed high-level helpers`

---

## Task C4–C11: Migrate 8 call sites

**Pattern — identical per call site:**

1. Change import: `from app.providers import get_provider` → `from app.llm import chat_for_task`
2. Replace `await get_provider().chat(messages)` with `await chat_for_task("<task_key>", messages)`
3. Remove any `provider.chat_model = ...` assignment lines
4. Update tests to mock `app.llm.chat_for_task` instead of `app.providers.get_provider`
5. Run affected test files
6. Commit

### Call sites table

| # | Task key | Call site file | Old pattern | Notes |
|---|---|---|---|---|
| C4 | `ingest_tagger` | `app/services/tagger.py` | `self.provider.chat(messages)` | injected provider → switch to direct import of helper |
| C5 | `ingest_context_enricher` | `app/services/context_enricher.py` | same | |
| C6 | `ingest_bridge_linker` | `app/services/bridge_linker.py` | same | |
| C7 | `qa_generation` | `app/services/generator.py` | `await self.provider.chat(messages)` | |
| C8 | `qa_facet_extraction` | `app/services/facet_extractor.py` **+ `app/api/public/v1/qa.py:180`** | `provider.chat_model = settings.qa_chat_model; await provider.chat(...)` | **REMOVE monkey-patch** |
| C9 | `content_generation` | `app/services/flashcard_generator.py` | `await self.provider.chat(messages)` | |
| C10 | `content_generation` | `app/api/v1/knowledge_points.py::generate_key_points` | inline LLM call | reuse same task_key as C9 |
| C11 | `translation` | `app/services/translation_service.py` | `await provider.chat(messages)` | |

**Per-task commit message template:**
```
refactor(llm): migrate <service> to chat_for_task("<task_key>")
```

**Special step for C8 — destroy the race bug:**

```python
# BEFORE (app/api/public/v1/qa.py:180)
provider = get_provider()
provider.chat_model = settings.qa_chat_model   # <-- race bug
response = await provider.chat(messages)

# AFTER
response = await chat_for_task("qa_facet_extraction", messages)
```

Add a regression test that proves no global mutation happens:
```python
# tests/test_qa_no_monkey_patch.py
async def test_qa_ask_does_not_mutate_provider_chat_model(real_db, monkeypatch):
    provider_instance = get_provider()
    before = provider_instance.chat_model
    await client.post("/v1/qa/ask", json={"q": "..."})
    assert provider_instance.chat_model == before  # unchanged
```

Commit with message: `fix(llm): remove qa.py monkey-patch race; route via chat_for_task`

---

## Task C12: Phase C full-suite smoke

**Files:**
- None new — just run the whole suite

```bash
pytest tests/ -v
# All green; no regressions.
```

If any test fails referencing `settings.chat_model` / `settings.qa_chat_model` directly, migrate it to `chat_for_task` or mock the helper.

Commit if any additional test fixtures changed: `test(llm): update test fixtures for chat_for_task helper`

---

## Phase C exit criteria

- [ ] `grep -rn "provider.chat_model" app/` returns 0 hits outside `zhipu.py` fallback impl
- [ ] `grep -rn "get_provider()" app/services app/api` returns 0 hits (only `app/llm/__init__.py::embed` left as legacy)
- [ ] `pytest tests/ -v` fully green
- [ ] Run a real ingest end-to-end locally: confirm tagger / enricher / bridge_linker each emit a log line with task_key matching their service
- [ ] PR `feat(llm): Phase C — router + migrate 8 call sites + remove qa.py race`

---

# Phase D — Admin REST API

**Goal:** 11 endpoints exposing `/api/v1/llm/*` for the console. All admin-JWT gated, audit-logged, rate-limited.

## Task D1: Pydantic schemas

**Files:**
- Create: `app/api/v1/schemas/llm.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Create: `tests/test_schemas_llm.py`

Schemas (verbatim from design §6.1): `ProviderCreate`, `ProviderUpdate`, `ProviderPublic`, `ModelInfoPublic`, `ProviderTestResult`, `TaskRouteUpdate`, `TaskRoutePublic`.

**Step 1: Tests** — assert `ProviderPublic` has NO `api_key` or `api_key_env` field via `ProviderPublic.model_fields`.

**Step 3: Implement**

**Step 5: Commit**
```bash
git add app/api/v1/schemas/llm.py tests/test_schemas_llm.py
git commit -m "feat(llm): Pydantic schemas for LLM admin API (whitelist — no api_key_env)"
```

---

## Task D2–D6: Endpoint implementations

**Pattern per endpoint task:**
1. Add route handler in `app/api/v1/llm.py`
2. Add admin-role dependency (reuse `require_admin` from `dependencies.py`)
3. Add `@limiter.limit("30/minute")`
4. Add audit log call where applicable
5. Write pytest smoke (route exists + returns expected shape)
6. Commit

### D2: `GET /providers`, `POST /providers`, `GET /providers/{id}`, `PATCH /providers/{id}`, `DELETE /providers/{id}` (CRUD)

- `GET` filters by `enabled` optional query param
- `POST` returns 201 + `ProviderPublic`; on create, calls `register_sensitive_key(api_key_env)`
- `PATCH` invalidates `ProviderRegistry` for that id + re-registers new env on change
- `DELETE` enforces in-use check per design §6.2 with task_keys enumerated

One commit per endpoint (5 commits).

### D3: `POST /providers/{id}/test`

- Builds Provider via registry, calls `list_models()`
- On success: DELETE + bulk_insert into `llm_provider_models`, write `last_tested_at/ok/error`, audit log success
- On fail: write `last_test_ok=False, last_test_error=sanitize_error(e)`, audit log fail
- Extra rate limit: `@limiter.limit("10/minute")`

Commit: `feat(llm): POST /providers/{id}/test — test connectivity + refresh model cache`

### D4: `GET /providers/{id}/models`

Read-only from `llm_provider_models`, no upstream call. Returns list ordered by `(kind, model_id)`.

Commit: `feat(llm): GET /providers/{id}/models — serve cached model list`

### D5: Tasks routes

- `GET /tasks` — join providers table, return 7 rows with `provider_name` populated; includes hardcoded i18n `description` per task_key (map stored in `app/core/llm_tasks.py`)
- `PUT /tasks/{task_key}` — validates provider exists + enabled + model_id valid (best-effort: check `llm_provider_models` cache, warn-not-error if missing)
- `POST /tasks/batch-update` — transactional; partial failure → rollback all

Commit per endpoint (3 commits).

### D6: `POST /routes/invalidate-cache`

One-liner: calls `ProviderRegistry.invalidate_all()` + `router.invalidate_all()`. Returns 204.

Commit: `feat(llm): POST /routes/invalidate-cache`

---

## Task D7: Global exception handlers

**Files:**
- Modify: `app/main.py`

Register 4 handlers (one per `Provider*Error` subclass) per design §8.3. Each handler passes `exc` through `sanitize_error` before serialization.

Commit: `feat(llm): FastAPI exception handlers for Provider* errors with sanitize`

---

## Task D8: Wire router into FastAPI app

**Files:**
- Modify: `app/main.py` (add `app.include_router(llm_router, prefix="/api/v1/llm")`)
- Modify: `app/api/v1/__init__.py`

Smoke test: `app.routes` contains expected paths.

Commit: `feat(llm): register /api/v1/llm/* router`

---

## Phase D exit criteria

- [ ] Curl against local API: `curl -H "Authorization: Bearer $ADMIN_JWT" http://localhost:8000/api/v1/llm/providers` returns 1-item list (seeded Zhipu)
- [ ] Curl test endpoint and verify `llm_provider_models` populated
- [ ] `pytest tests/test_api_v1_llm.py -v` → green
- [ ] PR `feat(llm): Phase D — admin REST API (11 endpoints)`

---

# Phase E — Admin Console UI (`RAG/web/`)

**Goal:** `LLMSettingsPage` with 2 tabs. Uses TanStack Query.

All work happens under `RAG/web/`. Pre-step: `cd RAG/web && npm install` if new dependencies.

## Task E1: API client + types

**Files:**
- Create: `web/src/lib/api/llm.ts`
- Create: `web/src/lib/types/llm.ts`

Types mirror backend Pydantic schemas exactly (D1). API client uses existing `get/post/put/patch/del` helpers from `web/src/lib/api.ts`.

Commit: `feat(llm-ui): API client + TS types`

## Task E2: `useLLMProviders` hook

**Files:**
- Create: `web/src/hooks/useLLMProviders.ts`
- Create: `web/src/hooks/useLLMProviders.test.ts` (optional vitest)

Uses TanStack Query. Query keys: `['llm','providers']`, `['llm','provider', id]`. Mutations invalidate `['llm']`.

Commit: `feat(llm-ui): useLLMProviders hook`

## Task E3: `useLLMTasks` hook

Same pattern. Keys: `['llm','tasks']`.

Commit: `feat(llm-ui): useLLMTasks hook`

## Task E4: `useLLMProviderModels` hook

Keys: `['llm','provider', id, 'models']`, `enabled: !!providerId`, `staleTime: 5min`.

Commit: `feat(llm-ui): useLLMProviderModels hook`

## Task E5: `ModelPicker` component

**Files:**
- Create: `web/src/components/settings/llm/ModelPicker.tsx`

Props: `providerId, value, onChange`. Renders shadcn `<Select>`. Shows `{display_name} · {context_window}K` when context_window known.

Commit: `feat(llm-ui): ModelPicker with async loading`

## Task E6: `TaskRouteCard` component

**Files:**
- Create: `web/src/components/settings/llm/TaskRouteCard.tsx`

Shows one task row: title, description, provider `<Select>`, `<ModelPicker>`. Emits `onChange(task_key, provider_id, model_id)` upward. Renders "•" badge when dirty.

Commit: `feat(llm-ui): TaskRouteCard`

## Task E7: `TaskRoutesTab`

**Files:**
- Create: `web/src/components/settings/llm/TaskRoutesTab.tsx`

Renders 7 `TaskRouteCard`s. Local dirty state map. "Save All" button calls `/tasks/batch-update`. "Force Invalidate Cache" button.

Commit: `feat(llm-ui): TaskRoutesTab with batch save`

## Task E8: `ProviderCard`

**Files:**
- Create: `web/src/components/settings/llm/ProviderCard.tsx`

Displays provider meta + status badges + 3 action buttons (Test & Refresh / Edit / Delete).

Commit: `feat(llm-ui): ProviderCard`

## Task E9: `ProvidersTab`

**Files:**
- Create: `web/src/components/settings/llm/ProvidersTab.tsx`

Renders list of `ProviderCard`. Top-right "+ Add Provider" opens `ProviderFormDialog`.

Commit: `feat(llm-ui): ProvidersTab`

## Task E10: `ProviderFormDialog`

**Files:**
- Create: `web/src/components/settings/llm/ProviderFormDialog.tsx`

Modal form for create/edit. Fields per design §7.4. `api_key_env` field shown with warning copy. "Save & Test" button.

Commit: `feat(llm-ui): ProviderFormDialog with create + edit modes`

## Task E11: `ProviderDeleteDialog`

**Files:**
- Create: `web/src/components/settings/llm/ProviderDeleteDialog.tsx`

Confirmation modal. If provider has `tasks_using_count > 0`, blocks delete and suggests changing routes first.

Commit: `feat(llm-ui): ProviderDeleteDialog with in-use guard`

## Task E12: `LLMSettingsPage` shell

**Files:**
- Create: `web/src/pages/settings/LLMSettingsPage.tsx`
- Modify: `web/src/App.tsx` (add route `/settings/llm`)
- Modify: `web/src/pages/SettingsPage.tsx` (add entry card linking to `/settings/llm`)

Shell with tabs (`TaskRoutesTab` | `ProvidersTab`). Admin-role guard using `ForbiddenPanel` fallback.

Commit: `feat(llm-ui): LLMSettingsPage shell + route wiring + Settings entry`

---

## Phase E exit criteria

- [ ] `cd web && npm run build` — succeeds
- [ ] `npm run lint && npx tsc --noEmit` — clean
- [ ] Manually: open `/settings/llm`, verify 7 task rows show "智谱 AI（默认）" / `glm-4.7`, click "Test & Refresh" on Zhipu card, verify model list populates
- [ ] Manually: add an OpenRouter provider (with `OPENROUTER_API_KEY` env set), test it, switch `qa_generation` to OpenRouter + `anthropic/claude-3.5-sonnet`, save
- [ ] Manually: run a QA query from the UI, verify it uses the new route
- [ ] PR `feat(llm-ui): Phase E — admin console UI`

---

# Phase F — Observability + Docs + E2E

## Task F1: `llm_call` structured logging

**Files:**
- Modify: `app/llm/__init__.py` (wrap `chat_for_task`)

Record `(task_key, provider_id, provider_name, model_id, status, latency_ms, prompt_tokens, completion_tokens, retry_attempts, failure_reason)` per call. Emit as single `logger.info("llm_call", extra={...})`.

**Step 1: Test**
```python
def test_chat_for_task_emits_llm_call_log(caplog, real_db):
    with caplog.at_level(logging.INFO):
        await chat_for_task("qa_generation", [ChatMessage("user", "hi")])
    records = [r for r in caplog.records if r.getMessage() == "llm_call"]
    assert len(records) == 1
    assert records[0].task_key == "qa_generation"
    assert records[0].status == "ok"
```

**Step 5: Commit**: `feat(llm): structured llm_call log with task_key + model + latency`

## Task F2: E2E test — switch provider

**Files:**
- Create: `tests/integration/test_llm_routing_e2e.py`

Full round-trip: seed a second provider (fake `OpenAICompatProvider` pointing at a mocked HTTP server), UI-equivalent PATCH of `qa_generation`'s route, trigger a real `/v1/qa/ask`, assert mock upstream was called (not Zhipu).

Commit: `test(llm): e2e — switch qa_generation route survives end-to-end`

## Task F3: Update `CLAUDE.md` gotchas

**Files:**
- Modify: `RAG/CLAUDE.md`
- Modify: `RAG/web/CLAUDE.md` (if exists)

Add:
- "Schema v12 — 3 LLM routing tables"
- New gotcha: **Don't write `provider.chat_model = ...` — use `chat_for_task(task_key)`**
- New gotcha: **`api_key_env` is the env variable NAME; real secret stays in env/1Password**
- New gotcha: **Adding a new task_key requires: (1) add constant in `app/core/llm_tasks.py`, (2) seed row in a new migration, (3) switch the call site to `chat_for_task("<new_key>", ...)`**

Commit: `docs(llm): CLAUDE.md gotchas + v12 schema notes`

## Task F4: `docs/architecture.md` update

Add the ASCII architecture diagram from design §3.1.

Commit: `docs(llm): architecture.md routing layer diagram`

## Task F5: Deployment checklist

**Files:**
- Create: `docs/plans/2026-04-21-multi-provider-deploy-checklist.md`

Checklist covering:
- Ensure `ZHIPU_API_KEY` still set (migration seeds route to it)
- If introducing DeepSeek/OpenRouter: add `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY` to 1Password envs
- Verify `migrate_db.py` runs cleanly on prod DB (v11 → v12)
- Post-deploy: `curl /api/v1/llm/providers` returns 1 row; `curl -X POST /api/v1/llm/providers/{id}/test` returns `ok`
- Run one real QA query and verify logs emit `llm_call` event with `status=ok`

Commit: `docs(llm): deployment checklist for v12 rollout`

---

## Phase F exit criteria

- [ ] `pytest tests/ -v` all green
- [ ] One real deployment to staging (if available) with all phases merged
- [ ] `grep 'event":"llm_call"' /var/log/...` shows entries for each service
- [ ] PR `feat(llm): Phase F — observability + CLAUDE.md + E2E`

---

# Global DoD (across all phases)

- [ ] All 6 phase PRs merged
- [ ] `git grep -n "provider\.chat_model\s*=" app/` returns 0 hits (race fully killed)
- [ ] `git grep -n "api_key" app/api/v1/schemas/llm.py` returns 0 hits (whitelist clean)
- [ ] Full `pytest tests/ -v` green on main
- [ ] `docker compose up` + browser smoke: add a new provider, test it, switch one task, verify route change in logs
- [ ] Rollback rehearsal: drop 3 v12 tables + `UPDATE schema_version SET version=11` — system still boots and runs (falls back to `ZhipuProvider` directly via legacy `get_provider()`)

---

# References

- Design doc: `docs/plans/2026-04-21-multi-provider-model-routing-design.md` (commit `7b027e2`)
- CLAUDE.md: `RAG/CLAUDE.md` — check 'Gotchas' section for existing conventions on migrations, FK policy, auth, audit
- Existing pattern: `app/services/bridge_resolver.py` — TTL cache + threading.Lock with `invalidate_*` helpers
- Existing pattern: `app/api/v1/taxonomy.py::delete_taxonomy_node` — 409 on in-use FK with savepoint defense-in-depth
