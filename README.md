# Interactive Map of Video Games

A web application for exploring approximately 1,000 video games on a zoomable, two-dimensional map. Games are positioned using their genres, mechanics, themes, and other characteristics.

Users will be able to search for games, view game information, filter by genre, and explore similar games. Personalized feature weighting is planned after the default map works.

## Project Status

We are beginning our first scrum cycle. Current work focuses on:

- Building the initial landing page.
- Selecting and cleaning the dataset.
- Creating the game database and import process.
- Developing the initial similarity and map-generation pipeline.

The structure below is the proposed organization. Some files and features have not been implemented yet.

## Tentative Repository Structure

```text
.
├── frontend/
│   ├── src/
│   │   ├── components/        # Map, search, panels, and controls
│   │   ├── pages/             # Landing page and page layouts
│   │   ├── services/          # Backend requests and browser storage
│   │   └── types/             # Shared frontend data definitions
│   ├── public/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI application
│   │   ├── database.py        # Database connections
│   │   ├── models.py          # SQLAlchemy database tables
│   │   ├── schemas.py         # Request and response definitions
│   │   └── routes/            # Map, game, and genre endpoints
│   ├── scripts/
│   │   └── import_games.py    # Imports the cleaned dataset
│   └── storage/               # Generated SQLite database; ignored
│
├── pipeline/
│   ├── clean.py               # Cleaning and duplicate handling
│   ├── features.py            # Feature encoding and normalization
│   ├── similarity.py          # Similarity scores and ranked neighbors
│   ├── map.py                 # PCA coordinates and K-Means clusters
│   ├── validate.py            # Dataset and generated-map checks
│   └── run.py                 # Runs the complete pipeline
│
├── config/
│   └── pipeline.yaml          # Vocabulary, aliases, weights, cluster
│                             # count, seed, and map-version identifier
│
├── data/
│   ├── README.md              # Sources, licenses, fields, and collection steps
│   ├── sample/                # Small shared sample allowed for redistribution
│   ├── raw/                   # Original downloaded data; ignored by default
│   └── processed/             # Cleaned data; ignored by default
│
├── artifacts/                 # Versioned map outputs and feature matrices
├── notebooks/                 # Exploration and experiments
├── tests/
│   ├── backend/
│   └── pipeline/
├── docs/
│   ├── database-schema.md
│   ├── api-contract.md
│   └── requirement-tests.md   # Requirements mapped to test files
├── requirements.txt          # Pinned Python dependencies
├── .env.example              # Environment variable names; no credentials
├── .gitignore
└── README.md
```

Frontend tests will stay alongside their components. Reusable processing code belongs in `pipeline/`; notebooks are for exploration.

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
6. Generate PCA coordinates and K-Means clusters.
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
- Feature categories and approved labels come from `config/pipeline.yaml`.
- `docs/database-schema.md` defines stored tables and relationships.
- `docs/api-contract.md` defines map and game-detail responses.
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

Setup commands will be added as each component becomes runnable.

The setup instructions must eventually cover:

- Installing frontend and Python dependencies.
- Obtaining the dataset.
- Importing game records.
- Generating the map.
- Starting the backend and frontend.
- Running tests.
