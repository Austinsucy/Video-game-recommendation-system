"""Database engine and session factory.

Backend SQLite is the source of truth (CON 1). The browser-side copy, when it
exists, is a disposable cache of published map data only.
"""
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "games.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(engine)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """SQLite ignores foreign keys unless they are enabled on EVERY connection.

    Required by the import rules ("enable SQLite foreign-key enforcement").
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()
