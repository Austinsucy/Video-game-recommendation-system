# Goon Squad — game database and import process

CSCI 150, Interactive Map of Video Games.

This covers the **database and the import process** (Ronnie). The ML pipeline —
coordinates, clusters, feature vectors and neighbours — is Austin and Kayne's and
writes into the tables defined here via `pipeline/publish.py`.

---

## Setup

Python **3.12** (see `.python-version`). The data libraries have the best wheel
coverage there, and REL 2 needs all four of us on the same versions.

```bash
git clone <repo-url>
cd <repo>

python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Get the dataset

The snapshot is **447 MB** and is gitignored. Download it yourself:

- Source: <https://www.kaggle.com/datasets/artermiloff/steam-games-dataset>
- Save as: `data/raw/games_march2025_cleaned.csv`

The path is set in `config/map_config.yaml` under `dataset.csv_path`.

> **Licence (CON 4):** confirm the Kaggle licence permits redistributing derived
> data before committing a built `data/games.db`.

### Build the database

```bash
python -m pipeline.create_tables     # 9 tables, indexes, constraints
python -m pipeline.ingest            # import per config/map_config.yaml
python -m pipeline.ingest --reset    # rebuild, preserving existing game_ids
python -m pipeline.ingest --limit 40 # small run for the 30-50 game milestone
python -m pytest -q                  # all tests
```

Every import writes `data/import_report.md`. Read it — it is how we meet the
"report missing values, duplicate candidates and feature-category coverage after
every import" rule.

---

## Everything tunable is in one file

`config/map_config.yaml` holds the map version, random seed, cluster count,
category weights, feature vocabulary, tag aliases and the selection rule
(MAINT 2). **Changing a weight or adding a tag mapping never requires a code
change.** Re-run the import afterwards.

### For Austin and Kayne

The `vocabulary` and `aliases` sections are a **starter stub**. They exist so the
import could be built and tested, not because they are the right vocabulary.
Please take them over.

- A raw string in `aliases` becomes a weighted feature in its category.
- Anything **not** in `aliases` falls through to the display-only `tag`
  category, so nothing is lost — it just is not weighted.
- A string mapped to a weighted category does **not** also become a `tag`
  feature. That enforces "avoid counting the same concept twice."
- `category_weights.tag` is `0.0` on purpose.
- The report's "most common unmapped tags" section is your to-do list.

Duplicate YAML keys are rejected rather than silently overwriting each other.

---

## Schema

Nine tables, following the scrum doc. Two are additions, both flagged for review.

| Table | Purpose |
|---|---|
| `games` | One row per game |
| `game_sources` | External ids and provenance, PK `(source_name, external_id)` |
| `features` | Approved vocabulary, unique on `(category, name)` |
| `game_features` | Game ↔ feature links |
| `game_feature_coverage` | **ADDITION** — see below |
| `map_versions` | One row per generated map |
| `clusters` | Per-version cluster labels and colours |
| `map_games` | Per-version coordinates and cluster membership |
| `map_neighbors` | Per-version similarity recommendations |

### Additions for team review

1. **`games.raw_tags_json`** — the rules say "preserve the original dataset
   export and raw tags", but no column held them. Stores the source
   tag→vote-count object verbatim.
2. **`game_feature_coverage`** — the rules require distinguishing missing source
   information from a confirmed absence. `game_features` can only record
   presence. One row per game per category, status `present` / `absent` /
   `unknown`.
3. **`UNIQUE(map_version_id, game_id, rank)`** on `map_neighbors` — "rank is
   unique within each game's versioned list" is not enforceable by the stated
   primary key alone.
4. **Finite coordinates are validated in Python**, not by a CHECK. SQLite stores
   NaN as NULL and accepts infinity, so a constraint would not catch it.

### Rules enforced in the schema itself

- `PRAGMA foreign_keys=ON` on every connection
- Indexes on `games.title_search` and `game_features.feature_id`
- At most one `map_versions` row with `is_active = 1` (partial unique index)
- An active version must have status `published` (CHECK)
- A mapped game's cluster must belong to the same map version (composite FK)
- Both ends of a neighbour pair must exist in `map_games` for that version
- A game cannot recommend itself (CHECK)

---

## Import decisions worth knowing

| Decision | Why |
|---|---|
| `rating` from `pct_pos_total`, scale `0-100` | Metacritic is missing for 96% of games and `user_score` for 99.96% |
| `rating_count` and `popularity` from `num_reviews_total` | Fully populated and numeric |
| Zeros converted to NULL for metacritic, user score and playtime | Steam writes 0 to mean "no data" |
| `playtime_hours` = `average_playtime_forever` / 60 | Source is in minutes |
| `game_id` is ours, not the Steam appid | The appid lives in `game_sources`; ids are preserved across re-imports |
| `title_search` is Unicode-aware | Stripping to `[a-z0-9]` would blank every CJK title |
| Duplicate titles are reported, never merged | Stated rule |

---

## Requirement → test map (MAINT 1)

| Requirement | Test |
|---|---|
| DATA 1 completeness ≥ 95% | `tests/test_data_quality.py::test_data1_completeness_at_least_95_percent` |
| No game appears twice | `tests/test_data_quality.py::test_no_game_appears_twice` |
| CON 3 size cap | `tests/test_data_quality.py::test_game_count_within_cap` |
| Foreign-key enforcement | `tests/test_schema.py::test_foreign_keys_are_enforced` |
| Required indexes | `tests/test_schema.py::test_required_indexes_exist` |
| One active map version | `tests/test_schema.py::test_only_one_active_map_version` |
| Active version is published | `tests/test_schema.py::test_active_version_must_be_published` |
| Cluster belongs to same version | `tests/test_schema.py::test_map_game_cluster_must_belong_to_same_version` |
| No self-recommendation | `tests/test_schema.py::test_game_cannot_recommend_itself` |
| Neighbour rank unique per game | `tests/test_schema.py::test_neighbor_rank_is_unique_per_game` |
| Neighbours exist in the same map | `tests/test_schema.py::test_neighbor_must_be_in_the_same_map_version` |
| REL 4 failed build leaves previous active | `tests/test_publish.py::test_failed_build_leaves_previous_version_active` |
| 10–15 neighbours per game | `tests/test_publish.py` (parametrised) |
| MAINT 2 single config file | `tests/test_config.py` |

---

## For the ML pipeline

```python
from pipeline.publish import publish_map

publish_map(
    "v2",
    clusters=[{"cluster_id": 0, "display_name": "Co-op shooters",
               "color": "#4C7BD9", "description": ""}],
    positions=[{"game_id": 1, "x": 0.12, "y": -3.4, "cluster_id": 0}],
    neighbors=[{"game_id": 1, "neighbor_game_id": 7,
                "similarity_score": 0.91, "rank": 1}],
    dataset_snapshot_ref="data/raw/games_march2025_cleaned.csv",
    dataset_hash="<sha256 from the import report>",
    config_snapshot=load_config(),
    feature_artifact_ref="data/artifacts/v2/",
)
```

Validate-then-activate runs in **one transaction**. Any failure rolls back
completely and the previously published version stays active. Use `mark_failed()`
to record a build that did not make it.

---

## Open items

- **CON 3 conflict.** The NFR document says the published map is "approximately
  1,000 **mostly pre-2019** games". The current build uses
  `selection.mode: popular_recent` (2019 onward). Flip that one value to
  `popular_pre2019` to match CON 3. Needs a team decision.
- **Non-game software** (Utilities, Accounting, Audio Production) is currently
  kept. Add entries to `selection.exclude_genres` to drop it.
- **Adult content** is currently kept: 110 games carry `sexual_content`, 70
  `nudity`, 155 `gore`, 178 `violent`. The map shows cover images.
- **Repo README** lists PyTorch; CON 1 specifies scikit-learn.
- **SEC 5** says browser storage holds only the saved map configuration and guide
  status, but the scrum doc adds a browser SQLite cache of map data.
