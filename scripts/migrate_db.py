"""DB migration script (placeholder).

After the UUID clean rebuild (Batch 0), all legacy migrations were removed.
Use `python scripts/reset_db.py --force` to recreate the database from scratch.
"""
import sys

import click

from app.core.database import LATEST_SCHEMA_VERSION, engine, get_current_schema_version


@click.command()
def main() -> None:
    current = get_current_schema_version(engine)
    if current is None:
        click.echo("No schema_version table found — init_database() will create it on startup.")
        return
    if current != LATEST_SCHEMA_VERSION:
        click.echo(
            f"ERROR: DB schema v{current} does not match code v{LATEST_SCHEMA_VERSION}. "
            f"Run `python scripts/reset_db.py --force` to recreate.",
            err=True,
        )
        sys.exit(1)
    click.echo(f"Schema v{current} matches code. No migrations needed.")


if __name__ == "__main__":
    main()
