"""DB migration script (placeholder).

After the UUID clean rebuild (Batch 0), all legacy migrations were removed.
Use `python scripts/reset_db.py --force` to recreate the database from scratch.
"""
import click


@click.command()
def main() -> None:
    click.echo("No incremental migrations available.")
    click.echo("This codebase uses clean rebuild (schema v1).")
    click.echo("To recreate the database: python scripts/reset_db.py --force")


if __name__ == "__main__":
    main()
