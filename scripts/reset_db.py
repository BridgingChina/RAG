#!/usr/bin/env python
"""Database reset script.

Drops all tables and recreates them with a clean schema.
Use --seed to populate initial test data after reset.
"""
import sys
from argparse import ArgumentParser

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.models import Base


def reset_db(seed: bool = False, force: bool = False) -> None:
    """Drop all tables and recreate schema.

    Args:
        seed: If True, seed test data after reset
        force: If True, skip confirmation prompt
    """
    engine = create_engine(settings.database_url)

    if not force:
        confirm = input(
            "This will DELETE ALL DATA in the database. "
            "Type 'yes' to confirm: "
        )
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(1)

    print("Dropping all tables...")
    with engine.connect() as conn:
        # Drop tables in correct order (respecting foreign keys)
        conn.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS ingest_tasks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS chunk_bridge_links CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS chunks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS sources CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS bridges CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS taxonomy_nodes CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS schema_version CASCADE"))
        conn.commit()
    print("Tables dropped.")

    print("Creating pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    print("Creating tables...")
    Base.metadata.create_all(engine)
    print("Tables created.")

    print("Stamping schema version...")
    from app.core.database import LATEST_SCHEMA_VERSION, set_schema_version
    with engine.connect() as conn:
        set_schema_version(engine, LATEST_SCHEMA_VERSION, "Clean rebuild via reset_db.py", conn=conn)
        conn.commit()
    print(f"Schema version set to {LATEST_SCHEMA_VERSION}.")

    if seed:
        print("\nSeeding test data...")
        from scripts.seed_test_data import seed as seed_data
        seed_data()
    else:
        print("\nDatabase reset complete (no data seeded).")
        print("Run with --seed to populate test data.")


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed test data after reset",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()
    reset_db(seed=args.seed, force=args.force)


if __name__ == "__main__":
    main()
