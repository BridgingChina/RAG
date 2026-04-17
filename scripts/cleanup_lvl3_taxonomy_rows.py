"""Delete all lvl3 rows from taxonomy_nodes (Phase 3 cleanup).

Run AFTER the application code stops reading taxonomy_nodes.lvl3:
- migrate_v9_to_v10 has backfilled knowledge_points.lvl1 / lvl2
- resolve_knowledge_point_id queries KnowledgePoint directly
- tree builders (admin + mobile) skip TaxonomyNode.lvl3 rows
- POST /taxonomy/nodes rejects lvl3 creation

The knowledge_points rows keep pointing at taxonomy_node_id of the row
being deleted; the FK on knowledge_points is nullable without a
cascade, so we null the FK explicitly before deleting the taxonomy rows.

Usage:
    python3 scripts/cleanup_lvl3_taxonomy_rows.py              # dry-run
    python3 scripts/cleanup_lvl3_taxonomy_rows.py --execute    # commit
"""
import click
from sqlalchemy import create_engine, text

from app.core.config import settings


@click.command()
@click.option("--execute", is_flag=True, help="Actually delete; omit for dry-run")
def main(execute: bool) -> None:
    engine = create_engine(settings.database_url)
    banner = "=" * 60
    mode = "EXECUTE" if execute else "DRY-RUN"
    click.echo(f"\n{banner}\n  Cleanup lvl3 taxonomy rows [{mode}]")
    click.echo(f"  Database: {settings.database_url[:80]}\n{banner}\n")

    with engine.begin() as conn:
        lvl3_count = conn.execute(text(
            "SELECT COUNT(*) FROM taxonomy_nodes WHERE lvl3 IS NOT NULL"
        )).scalar_one()

        kp_orphan_count = conn.execute(text("""
            SELECT COUNT(*) FROM knowledge_points kp
            WHERE kp.taxonomy_node_id IN (
                SELECT id FROM taxonomy_nodes WHERE lvl3 IS NOT NULL
            )
        """)).scalar_one()

        click.echo(f"taxonomy_nodes rows with lvl3 IS NOT NULL: {lvl3_count}")
        click.echo(f"knowledge_points pointing at those rows: {kp_orphan_count}")

        if lvl3_count == 0:
            click.echo("\nNothing to do. Schema is already clean.")
            return

        if not execute:
            click.echo("\nDRY-RUN — re-run with --execute to:")
            click.echo(f"  1. NULL knowledge_points.taxonomy_node_id for {kp_orphan_count} rows")
            click.echo(f"  2. DELETE {lvl3_count} lvl3 rows from taxonomy_nodes")
            return

        conn.execute(text("""
            UPDATE knowledge_points
               SET taxonomy_node_id = NULL
             WHERE taxonomy_node_id IN (
                 SELECT id FROM taxonomy_nodes WHERE lvl3 IS NOT NULL
             )
        """))
        result = conn.execute(text(
            "DELETE FROM taxonomy_nodes WHERE lvl3 IS NOT NULL"
        ))
        click.echo(f"\nOK. Nulled {kp_orphan_count} KP FKs, deleted {result.rowcount} lvl3 rows.")


if __name__ == "__main__":
    main()
