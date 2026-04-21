"""LLM routing config ORM models (schema v13, 2026-04-21).

Phase B of the Multi-Provider + Task-Level Model Routing refactor introduces
three tables that back the admin console's routing UI:

- ``llm_providers``       — provider metadata (1 row per upstream endpoint).
  API keys are NEVER stored here; ``api_key_env`` names the env var to read.
- ``llm_provider_models`` — cache of ``list_models()`` output, refreshed on
  the "test" button. CASCADE deletes with the provider.
- ``llm_task_routes``     — ``task_key → (provider, model)`` runtime routing
  table. RESTRICT FK on provider_id: a provider that is in use by any task
  cannot be deleted. There is deliberately no FK on ``model_id`` — the
  provider temporarily dropping a model from ``list_models()`` must not
  orphan-nuke the route config.

See ``docs/plans/2026-04-21-multi-provider-model-routing-design.md`` §5 for
the migration plan and §7 for the Phase C router (``chat_for_task``) that
will consume these tables.

The ORM class for ``llm_providers`` is named :class:`LLMProviderRow` to avoid
clashing with the :class:`app.providers.base.LLMProvider` ABC.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class LLMProviderRow(Base, UUIDMixin):
    """A registered upstream LLM provider (e.g. 智谱, DeepSeek, Moonshot).

    ``api_key`` is NEVER stored — the admin UI writes a row containing
    ``api_key_env`` naming an environment variable, and at call time
    :class:`ProviderRegistry` (Phase C) reads ``os.environ[api_key_env]``.
    """

    __tablename__ = "llm_providers"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_env: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_headers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"),
    )
    timeout_read: Mapped[float] = mapped_column(
        REAL, nullable=False, server_default=text("90.0"),
    )
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('zhipu', 'openai_compat', 'minimax')",
            name="ck_llm_providers_kind",
        ),
        Index(
            "idx_llm_providers_enabled",
            "enabled",
            postgresql_where=text("enabled = TRUE"),
        ),
    )


class LLMProviderModel(Base, UUIDMixin):
    """A single model exposed by a provider, mirrored from ``list_models()``.

    Refreshed on the admin UI's "test" button. CASCADE deletes with the
    provider — if the provider row goes, its model cache should go too.
    """

    __tablename__ = "llm_provider_models"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_llm_provider_models"),
        Index("idx_llm_provider_models_provider", "provider_id"),
        Index("idx_llm_provider_models_kind", "provider_id", "kind"),
    )


class LLMTaskRoute(Base):
    """``task_key → (provider, model)`` routing table.

    Primary key is ``task_key`` — one row per logical task (e.g. "qa_generation",
    "ingest_tagger", "translation"). The Phase C :func:`chat_for_task` router
    reads this table (with TTL cache) to pick the provider+model for each LLM
    call site.

    RESTRICT FK on ``provider_id``: a provider that is in use by any task
    cannot be deleted — the admin UI must first re-route the tasks elsewhere.
    No FK on ``model_id`` — the provider temporarily removing a model from
    ``list_models()`` must not orphan-cascade-kill the route config.
    """

    __tablename__ = "llm_task_routes"

    task_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Better Auth user.id is a base64url string (not UUID). See
    # audit_logs.user_id / translation_reviews.reviewed_by for the same
    # TEXT-typed identity column pattern post-Phase-2.
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
