# Interactive Map of Video Games

A web application for exploring approximately 1,000 video games on a zoomable, two-dimensional map. Games are positioned using their genres, mechanics, themes, and other characteristics.

Users will be able to search for games, view game information, filter by genre, and explore similar games. Personalized feature weighting is planned after the default map works.

## Project Status

We are beginning our first scrum cycle. Current work focuses on:

- Building the initial landing page.
- Selecting and cleaning the dataset.
- Creating the game database and import process.
- Developing the initial similarity and map-generation pipeline.

## Repository Layout

```text
.
├── frontend/                  # React + Vite website
│   ├── src/
│   │   ├── components/        # Map and other interface components
│   │   └── services/          # Loads data/map.db in the browser
│   ├── vite.config.ts
│   └── package.json
│
├── backend/app/
│   ├── db.py                  # SQLite connection for data/games.db
│   └── models.py              # SQLAlchemy tables (see DATABASE.md)
│
├── pipeline/
│   ├── create_tables.py       # Creates the database schema
│   ├── ingest.py, report.py   # Imports 1,000 games and writes the import report
│   ├── vectorize.py           # Turns each game's tags into a vector
│   ├── compare_vectors.py     # Compares vectorization methods
│   ├── tune_weights.py        # Searches category weights for category_weighted
│   ├── build_map.py           # Neighbours, t-SNE layout, K-Means clusters
│   ├── publish.py             # Saves a map version safely
│   └── export_map.py          # Writes data/map.db for the website
│
├── config/
│   ├── map_config.yaml        # Every tunable setting (MAINT 2)
│   └── similar_pairs.yaml     # Approved similar-game pairs (DATA 2)
│
├── data/
│   ├── games.db               # Full game data and published map versions
│   ├── map.db                 # The published map the website loads
│   ├── import_report.md       # Report from the last import
│   ├── raw/                   # Downloaded dataset; ignored by Git
│   └── artifacts/             # Pipeline reports and build outputs; ignored by Git
│
├── docs/
│   ├── decisions.md           # Why the pipeline works the way it does
│   └── map-db.md              # Tables in data/map.db
├── tests/                     # pytest tests
├── DATABASE.md                # Database schema, import process, requirement-to-test map
├── requirements.txt           # Pinned Python dependencies
└── requirements-embeddings.txt  # Optional, for the two embedding methods
```

The FastAPI backend (`backend/app/main.py` and its routes) has not been started yet.

## Technology

- **Frontend:** React, TypeScript, Vite, Material UI, Cytoscape.js.
- **Backend:** FastAPI, SQLite, SQLAlchemy.
- **Data pipeline:** pandas, NumPy, scikit-learn.
- **Testing:** pytest, Vitest, React Testing Library.

## Data Flow

1. Obtain a dataset and preserve its original export.
2. Clean records, standardize labels, and review duplicates.
3. Import the cleaned records and feature relationships into SQLite.
4. Encode features, normalize numerical values, and apply category weights.
5. Calculate cosine similarity and save 10–15 neighbors per game.
6. Generate t-SNE coordinates and K-Means clusters (see `docs/decisions.md`).
7. Validate and publish a complete map version.
8. Load the saved map in the frontend and request full game details when needed.

Published maps are generated offline. Their coordinates remain fixed for that version. Personalized maps use separate session results.

## First Scrum Cycle Responsibilities

| Team member | Focus |
|---|---|
| AJ | Landing page and interface components using sample responses. |
| Ronnie | Database schema, relationships, import process, and database validation. |
| Austin | Dataset selection, cleaning, feature definitions, and feature preparation. |
| Kayne | Similarity, map generation, clustering, and pipeline reproducibility. |

Austin and Kayne will coordinate the feature format before developing their pipeline stages independently.

## Shared Data Contract

Start with the same 1000 sample games across the database, pipeline, and frontend.

- Game IDs must remain consistent across all components.
- Feature categories and approved labels come from `config/map_config.yaml`.
- `DATABASE.md` defines stored tables and relationships.
- `docs/map-db.md` defines the map data the website reads.
- Changes to shared fields must be coordinated with the people using them.

## Branch Workflow

- `main` contains reviewed work that runs together.
- `ml` temporarily combines dataset and ML work for the current milestone.
- Austin and Kayne create individual branches from `ml` and submit pull requests into it.
- Once the combined work passes its checks, submit a pull request from `ml` into `main`.
- Frontend and database task branches normally start from `main`.
- Keep `ml` updated with relevant changes from `main`.

Pull requests require at least one reviewer and passing checks before merging.

## Data and Generated Files

Record dataset sources, collection dates, licenses, required attribution, and field definitions in `data/README.md`.

Keep credentials, local environments, downloaded datasets, generated databases, and temporary outputs out of Git. Share a small sample only when its license permits redistribution.

Preserve versioned input snapshots, configuration, feature order, and generated results in an agreed artifact location so published maps can be reproduced.

## Running Locally

A fresh clone already contains the game database and a published map, so you can run the website and the tests without downloading the dataset.

### What you need

- **Git**
- **Python 3.14** (the version in `.python-version`; the pinned packages are tested on it)
- **Node.js LTS** with npm (tested with Node 26)

### 1. Set up Python

Run these from the repository root.

Windows:

```bash
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

macOS or Linux:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The commands below call Python as `python`. Either activate the environment first (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on macOS or Linux), or replace `python` with `.venv\Scripts\python` or `.venv/bin/python`.

Optional: `pip install -r requirements-embeddings.txt` adds the two embedding-based vectorization methods to the comparison. It downloads PyTorch, which is large. Nothing else needs it.

### 2. Run the tests

```bash
python -m pytest -q
```

Every test should pass. Without the optional embedding packages, one test is skipped.

### 3. Run the website

```bash
cd frontend
npm install
npm run dev
```

Open the address it prints, usually http://localhost:5173. The page reloads when you save a file in `frontend/src/`. Press Ctrl+C in the terminal to stop the server.

- Run `npm install` again whenever a pull changes `frontend/package.json`.
- The website reads `data/map.db` directly. After a new map is published, refresh the page; nothing needs copying.
- `npm run build` makes a production build in `frontend/dist/`, and `npm run lint` checks the code.

### 4. Change the map (pipeline)

You only need this to build a new map version. Every setting lives in `config/map_config.yaml`, and `docs/decisions.md` explains the current choices.

| Command | What it does |
|---|---|
| `python -m pipeline.compare_vectors` | Compares the vectorization methods and writes `data/artifacts/vector_comparison.md` |
| `python -m pipeline.tune_weights` | Searches the category weights for `category_weighted` and writes `data/artifacts/weight_tuning.md` |
| `python -m pipeline.build_map` | Builds and validates a map without saving it (a dry run) |
| `python -m pipeline.build_map --publish --version-id v3` | Saves map version `v3` in `data/games.db` and rewrites `data/map.db` |
| `python -m pipeline.export_map` | Rewrites `data/map.db` from the active map version |

- Use a new version id for each published map. The pipeline refuses to reuse one, and a dry run prints a warning while `map_version` in the config names a published map (currently `v2`). Set it to the next id before building, or pass `--version-id`.
- Build published maps from a clean environment with the pinned `requirements.txt`, so the layout matches on every machine (REL 2).
- After publishing, commit `data/games.db` and `data/map.db` together.

### 5. Re-import the games (rare)

Re-importing is only needed after changing the dataset, the selection rule, or the tag vocabulary and aliases.

1. Download the [Steam games dataset](https://www.kaggle.com/datasets/artermiloff/steam-games-dataset) and save it as `data/raw/games_march2025_cleaned.csv` (about 447 MB; Git ignores it). Its SHA-256 should match the one in `data/import_report.md`.
2. Run `python -m pipeline.ingest --reset`. It rebuilds the games and keeps their ids.

While a published map exists, the import refuses to run so it cannot invalidate that map. Clearing the published map first is a deliberate team decision; see `DATABASE.md`.

### Troubleshooting

| Problem | Fix |
|---|---|
| PowerShell says "running scripts is disabled" for `npm` or `Activate.ps1` | Use `npm.cmd run dev`, or run the commands in Command Prompt, or call `.venv\Scripts\python` directly. |
| Vite says "Failed to resolve import" | Run `npm install` in `frontend/`. A pull probably added a package. |
| The page says "The map could not load" | Check that `data/map.db` exists. Pull from `main` if it is missing. |
| `py -3.14` is not found | Install Python 3.14 from python.org, then open a new terminal. |
