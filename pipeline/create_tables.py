"""Create every table, index and constraint. Safe to re-run."""
from backend.app.db import DB_PATH, engine
from backend.app.models import Base


def main() -> None:
    Base.metadata.create_all(engine)
    names = sorted(Base.metadata.tables)
    print(f"Database: {DB_PATH}")
    print(f"{len(names)} tables ready:")
    for n in names:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
