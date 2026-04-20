"""DB migration script.

Supports incremental migrations from v1 onward.
Use `python scripts/reset_db.py --force` to recreate from scratch.
"""
import sys

import click
from sqlalchemy import text

from app.core.database import (
    LATEST_SCHEMA_VERSION,
    engine,
    get_current_schema_version,
    set_schema_version,
)


def migrate_v1_to_v2(conn) -> None:
    """Add knowledge_points + knowledge_point_key_points tables."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            taxonomy_node_id UUID REFERENCES taxonomy_nodes(id),
            name VARCHAR(200) NOT NULL,
            aliases TEXT,
            difficulty VARCHAR(20),
            summary TEXT,
            l2_content JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kp_taxonomy ON knowledge_points(taxonomy_node_id)"
    ))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_point_key_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_point_id UUID NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            explanation TEXT,
            order_index INTEGER NOT NULL,
            chunk_ids UUID[],
            illustration_urls TEXT[],
            related_term_ids UUID[],
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kpkp_kp ON knowledge_point_key_points(knowledge_point_id)"
    ))
    # Defensive: if table was created by an earlier code version without this column
    conn.execute(text(
        "ALTER TABLE knowledge_point_key_points "
        "ADD COLUMN IF NOT EXISTS related_term_ids UUID[]"
    ))
    set_schema_version(engine, 2, "Add knowledge_points + knowledge_point_key_points", conn=conn)


def migrate_v2_to_v3(conn) -> None:
    """Add flashcards + device tables."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_point_id UUID NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
            card_type VARCHAR(20) NOT NULL CHECK (card_type IN ('concept', 'identification')),
            front_title TEXT NOT NULL,
            front_hint TEXT,
            back_answer TEXT NOT NULL,
            back_key_features TEXT[],
            back_example_bridge_id UUID REFERENCES bridges(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_flashcards_kp ON flashcards(knowledge_point_id)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS device_favorites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id UUID NOT NULL,
            target_type VARCHAR(20) NOT NULL CHECK (target_type IN ('bridge', 'knowledge_point', 'flashcard')),
            target_id UUID NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_device_fav UNIQUE (device_id, target_type, target_id)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_device_favorites_device ON device_favorites(device_id)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS device_review_progress (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id UUID NOT NULL,
            flashcard_id UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            mastery VARCHAR(20) NOT NULL DEFAULT 'needs_review' CHECK (mastery IN ('mastered', 'needs_review')),
            last_reviewed_at TIMESTAMPTZ,
            interval INTEGER NOT NULL DEFAULT 1,
            ease_factor REAL NOT NULL DEFAULT 2.5,
            CONSTRAINT uq_device_review UNIQUE (device_id, flashcard_id)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS device_view_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id UUID NOT NULL,
            target_type VARCHAR(20) NOT NULL CHECK (target_type IN ('bridge', 'knowledge_point')),
            target_id UUID NOT NULL,
            viewed_at TIMESTAMPTZ DEFAULT now() NOT NULL
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_device_view_history_device ON device_view_history(device_id)"
    ))

    set_schema_version(engine, 3, "Add flashcards + device tables", conn=conn)


def migrate_v3_to_v4(conn) -> None:
    """Add password_changed_at column to users table."""
    conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ"
    ))
    set_schema_version(engine, 4, "Add users.password_changed_at for JWT invalidation", conn=conn)


def migrate_v4_to_v5(conn) -> None:
    """Add bridge_images + knowledge_point_bridges tables + bridges.geocode_source."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bridge_images (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bridge_id UUID NOT NULL REFERENCES bridges(id) ON DELETE CASCADE,
            r2_key VARCHAR(500) NOT NULL,
            caption TEXT,
            type VARCHAR(20),
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_bridge_images_bridge_id ON bridge_images(bridge_id)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_point_bridges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_point_id UUID NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
            bridge_id UUID NOT NULL REFERENCES bridges(id) ON DELETE CASCADE,
            relevance_note TEXT,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_kp_bridge UNIQUE (knowledge_point_id, bridge_id)
        )
    """))

    conn.execute(text(
        "ALTER TABLE bridges ADD COLUMN IF NOT EXISTS geocode_source VARCHAR(20)"
    ))

    set_schema_version(engine, 5, "Add bridge_images + knowledge_point_bridges + geocode_source", conn=conn)


def migrate_v5_to_v6(conn) -> None:
    """Add UNIQUE(chunk_id, bridge_id) constraint to chunk_bridge_links."""
    # Remove duplicate rows first, keeping the one with the highest confidence
    conn.execute(text("""
        DELETE FROM chunk_bridge_links
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY chunk_id, bridge_id
                           ORDER BY confidence DESC, created_at ASC
                       ) AS rn
                FROM chunk_bridge_links
            ) ranked
            WHERE rn > 1
        )
    """))
    conn.execute(text(
        "ALTER TABLE chunk_bridge_links "
        "ADD CONSTRAINT uq_chunk_bridge_link UNIQUE (chunk_id, bridge_id)"
    ))
    set_schema_version(engine, 6, "Add UNIQUE(chunk_id, bridge_id) to chunk_bridge_links", conn=conn)


def migrate_v6_to_v7(conn) -> None:
    """Add missing indexes for needs_reindex, ingest_tasks.status, audit_logs composite."""
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_chunks_needs_reindex "
        "ON chunks (source_id) WHERE needs_reindex = true"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_ingest_tasks_status ON ingest_tasks (status)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action_resource "
        "ON audit_logs (action, resource_type)"
    ))
    set_schema_version(engine, 7, "Add missing indexes: needs_reindex, ingest_tasks.status, audit_logs composite", conn=conn)


def migrate_v7_to_v8(conn) -> None:
    """Add updated_at column to sources table."""
    conn.execute(text(
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()"
    ))
    set_schema_version(engine, 8, "Add sources.updated_at column", conn=conn)


def migrate_v8_to_v9(conn) -> None:
    """Add chunks.knowledge_point_id FK (ON DELETE SET NULL) + backfill from lvl3 strings.

    First step of the lvl3-KP merge refactor. chunks.lvl1/lvl2/lvl3 stay in place
    during this double-write phase; reads still flow through the string columns.
    """
    conn.execute(text(
        "ALTER TABLE chunks "
        "ADD COLUMN IF NOT EXISTS knowledge_point_id UUID "
        "REFERENCES knowledge_points(id) ON DELETE SET NULL"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_chunks_knowledge_point_id "
        "ON chunks(knowledge_point_id)"
    ))
    conn.execute(text("""
        UPDATE chunks c
           SET knowledge_point_id = kp.id
          FROM knowledge_points kp
          JOIN taxonomy_nodes tn ON tn.id = kp.taxonomy_node_id
         WHERE c.lvl1 = tn.lvl1
           AND c.lvl2 = tn.lvl2
           AND c.lvl3 = tn.lvl3
           AND c.knowledge_point_id IS NULL
    """))
    set_schema_version(
        engine,
        9,
        "Add chunks.knowledge_point_id FK (ON DELETE SET NULL) with backfill from lvl3 strings",
        conn=conn,
    )


def migrate_v10_to_v11(conn) -> None:
    """Phase 2 identity migration — users + device_* out, user_id TEXT in.

    1. DROP device_favorites / device_review_progress / device_view_history
       (per-device state is replaced by per-user state).
    2. DROP users CASCADE (identity moved to ``auth.bridgingchina.net``).
       CASCADE also drops the FKs ``audit_logs.user_id -> users(id)`` and
       ``ingest_tasks.created_by -> users(id)``.
    3. ALTER the now-dangling columns to TEXT so they can hold Better Auth
       base64url ``user.id`` strings.
    4. CREATE ``favorites`` / ``review_progress`` / ``view_history`` with
       ``user_id TEXT`` and the same functional surface as the dropped
       device_* tables, minus ``device_id``.
    """
    # 1. Drop device-scoped state tables
    conn.execute(text("DROP TABLE IF EXISTS device_favorites CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS device_review_progress CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS device_view_history CASCADE"))

    # 2. Drop users (cascades to FK holders audit_logs.user_id + ingest_tasks.created_by)
    conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))

    # 3. Flip dangling user_id / created_by columns to TEXT
    conn.execute(text(
        "ALTER TABLE audit_logs ALTER COLUMN user_id TYPE TEXT USING user_id::text"
    ))
    conn.execute(text(
        "ALTER TABLE ingest_tasks ALTER COLUMN created_by TYPE TEXT USING created_by::text"
    ))

    # 4. New user-scoped tables
    conn.execute(text("""
        CREATE TABLE favorites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            target_id UUID NOT NULL,
            target_type TEXT NOT NULL CHECK (
                target_type IN ('bridge','knowledge_point','flashcard')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_favorite UNIQUE (user_id, target_id, target_type)
        )
    """))
    conn.execute(text(
        "CREATE INDEX idx_favorites_user ON favorites (user_id)"
    ))

    conn.execute(text("""
        CREATE TABLE review_progress (
            user_id TEXT NOT NULL,
            flashcard_id UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            mastery SMALLINT NOT NULL DEFAULT 0,
            last_reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            next_review_at TIMESTAMPTZ,
            interval_days INTEGER NOT NULL DEFAULT 1,
            ease_factor NUMERIC(4,2) NOT NULL DEFAULT 2.5,
            CONSTRAINT pk_review_progress PRIMARY KEY (user_id, flashcard_id)
        )
    """))

    conn.execute(text("""
        CREATE TABLE view_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            target_id UUID NOT NULL,
            target_type TEXT NOT NULL CHECK (
                target_type IN ('bridge','knowledge_point')
            ),
            viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(text(
        "CREATE INDEX idx_view_history_user_time "
        "ON view_history (user_id, viewed_at DESC)"
    ))

    set_schema_version(
        engine, 11,
        "Phase 2 identity migration: drop users + device_*, create user_id-based tables",
        conn=conn,
    )


def migrate_v9_to_v10(conn) -> None:
    """Add knowledge_points.lvl1 / lvl2 + backfill from taxonomy_node join.

    Phase 3 of the lvl3-KP merge: knowledge_points becomes the authoritative
    holder of (lvl1, lvl2, name=lvl3). taxonomy_nodes retains only lvl1/lvl2
    rows after a separate cleanup step (scripts/cleanup_lvl3_taxonomy_rows.py)
    executes once the application code no longer reads lvl3 taxonomy rows.
    """
    conn.execute(text(
        "ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl1 VARCHAR(100)"
    ))
    conn.execute(text(
        "ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl2 VARCHAR(100)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kp_lvl1_lvl2 ON knowledge_points(lvl1, lvl2)"
    ))
    conn.execute(text("""
        UPDATE knowledge_points kp
           SET lvl1 = tn.lvl1,
               lvl2 = tn.lvl2
          FROM taxonomy_nodes tn
         WHERE kp.taxonomy_node_id = tn.id
           AND kp.lvl1 IS NULL
    """))
    set_schema_version(
        engine, 10,
        "Add knowledge_points.lvl1 / lvl2 with backfill (Phase 3 prep)",
        conn=conn,
    )


MIGRATIONS = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
    3: migrate_v3_to_v4,
    4: migrate_v4_to_v5,
    5: migrate_v5_to_v6,
    6: migrate_v6_to_v7,
    7: migrate_v7_to_v8,
    8: migrate_v8_to_v9,
    9: migrate_v9_to_v10,
    10: migrate_v10_to_v11,
}


@click.command()
def main() -> None:
    current = get_current_schema_version(engine)
    if current is None:
        click.echo("No schema_version table found — init_database() will create it on startup.")
        return
    if current == LATEST_SCHEMA_VERSION:
        click.echo(f"Schema v{current} matches code. No migrations needed.")
        return
    if current > LATEST_SCHEMA_VERSION:
        click.echo(
            f"ERROR: DB schema v{current} is ahead of code v{LATEST_SCHEMA_VERSION}.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Migrating from v{current} to v{LATEST_SCHEMA_VERSION}...")
    with engine.begin() as conn:
        # Acquire advisory lock to prevent concurrent migrations (same lock ID as init_database)
        conn.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": 606059278})

        # Re-check version after acquiring lock (another process may have just migrated)
        current = get_current_schema_version(engine, conn=conn) or current
        if current >= LATEST_SCHEMA_VERSION:
            click.echo(f"Schema already at v{current} after acquiring lock. No migration needed.")
            return

        for v in range(current, LATEST_SCHEMA_VERSION):
            migrate_fn = MIGRATIONS.get(v)
            if migrate_fn is None:
                click.echo(f"ERROR: No migration function for v{v} → v{v+1}.", err=True)
                sys.exit(1)
            click.echo(f"  Running v{v} → v{v+1}...")
            migrate_fn(conn)
    click.echo(f"Migration complete. Now at v{LATEST_SCHEMA_VERSION}.")


if __name__ == "__main__":
    main()
