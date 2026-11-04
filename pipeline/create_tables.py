"""
Creates every table, index and constraint in the database.

Run this once on a fresh clone, before the import:
    python -m pipeline.create_tables

Safe to run again. create_all() skips anything that already exists.

IMPORTANT THING TO KNOW: it only CREATES missing tables, it never changes
existing ones. So if someone adds a column to models.py, running this will
not add that column to a database you already built. You have to delete
data/games.db and rebuild.

(The proper fix for that is a migration tool like Alembic. We have not set one
up because our database rebuilds from a CSV in about a minute, so deleting and
re-importing is simpler than maintaining migrations.)
"""
from backend.app.db import DB_PATH, engine
from backend.app.models import Base


def main() -> None:
    Base.metadata.create_all(engine)

    table_names = sorted(Base.metadata.tables)
    print(f"Database file: {DB_PATH}")
    print(f"{len(table_names)} tables ready:")
    for name in table_names:
        print(f"  - {name}")
    print("\nNext step: python -m pipeline.ingest")


if __name__ == "__main__":
    main()
