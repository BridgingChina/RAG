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


MIGRATIONS = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
    3: migrate_v3_to_v4,
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
