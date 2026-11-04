"""
Sets up the connection to our SQLite database file.

Everything that touches the database imports `SessionLocal` from here, so
there is exactly one place that decides where the file lives and how the
connection is configured.

Why SQLite at all? Our CON 1 requirement picked it, and it suits us: the whole
database is a single file we can commit to the repo, so teammates get the data
by running `git pull` instead of each setting up a database server.
"""
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Work out the repo root by walking up from this file:
#   backend/app/db.py  ->  backend/app  ->  backend  ->  repo root
# Doing it this way instead of hardcoding a path means the project works
# wherever someone clones it, on any OS.
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "games.db"

# Create data/ if it is missing, so a fresh clone does not fail here.
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# The engine manages connections to the file. SessionLocal() hands us a
# session, which is how we actually run queries.
engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(engine)


@event.listens_for(engine, "connect")
def _turn_on_foreign_keys(dbapi_conn, _record):
    """Switch on foreign key checking, every single time we connect.

    This is a genuine SQLite gotcha. Unlike most databases, SQLite ignores
    foreign keys by default, and it forgets the setting when the connection
    closes. So it has to be set per connection, which is what this event
    listener does for us automatically.

    Without it you could insert a game_features row pointing at game_id 99999
    and SQLite would cheerfully accept it. Our import rules require foreign
    key enforcement, and tests/test_schema.py checks that this actually works.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
