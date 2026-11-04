# Goon Squad: game database and import process

CSCI 150, Interactive Map of Video Games.

> **This is the `test/full-90k-database` branch.** It imports the entire Steam
> catalogue, all 89,618 games, instead of the 1,000-game map dataset, so we can
> see what the full data looks like. Do not merge it into `main`.
>
> How it differs from `main`:
>
> * `selection.mode` is `all`, `target_count` is `null`, and `min_genres` and
>   `min_tags` are `0`, so nothing is filtered out. The vocabulary and aliases
>   are the team's, the same as `main`.
> * `data/games.db` is not committed. The full build is about 330 MB, over
>   GitHub's 100 MB file limit. Build it yourself: `python -m pipeline.create_tables`
>   then `python -m pipeline.ingest`. It takes under two minutes and about 1 GB of
>   memory.
> * There is no published map in this database, and none can be built from it:
>   CON 3 caps a map at 1,100 games. `data/map.db` is still `main`'s v2 file, so
>   the website runs as before.
> * Three tests behave differently, each saying why: the DATA 1 gate skips
>   (its minimums are off here), the real-database map build skips (over the
>   CON 3 cap), and the vectorizer smoke test checks unit length only for games
>   that have tags, because about 17,000 games in the full catalogue have none.
>
> What the full build showed, worth reading before the next dataset decision:
>
> * 16,872 games (18.8%) have no Steam tags at all in this snapshot, including
>   very popular ones such as Overwatch 2, Marvel Rivals, THE FINALS and Metro
>   Exodus. `main`'s `min_tags: 3` rule drops them, so they are not on the map.
> * 87,301 games (97.4%) would pass DATA 1.
> * 890 normalised titles appear more than once, against 0 in the 1,000-game build.
> * Search stays fast: an indexed title lookup takes under 1 ms, a substring
>   search about 60 ms.

This file covers the database and the import process, which Ronnie owns. The ML
pipeline (coordinates, clusters, feature vectors and neighbors) belongs to Austin
and Kayne, and writes into the tables defined here through `pipeline/publish.py`.

---

## Setup

Use Python **3.14**, as recorded in `.python-version`. REL 2 requires identical
results across all four of our machines, so we all need the same Python and the
same package versions.

**Windows (PowerShell):**

```powershell
git clone https://github.com/Austinsucy/Video-game-recommendation-system.git
cd Video-game-recommendation-system

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

**macOS or Linux:**

```bash
git clone https://github.com/Austinsucy/Video-game-recommendation-system.git
cd Video-game-recommendation-system

python3.14 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
```

Your prompt should now start with `(.venv)`. Activation does not persist, so
re-run the activate line in every new terminal. Check with:

```
python -c "import sqlalchemy, pandas, yaml, pytest; print('ok')"
```

Install from `requirements.txt` rather than using packages you already have.
The pinned versions are the point.

### Get the dataset

The snapshot is 447 MB and is gitignored, so download it yourself:

* Source: https://www.kaggle.com/datasets/artermiloff/steam-games-dataset
* Save it as `data/raw/games_march2025_cleaned.csv`

The path is set in `config/map_config.yaml` under `dataset.csv_path`.

> **License (CON 4):** confirm the Kaggle license permits redistributing derived
> data before committing a built `data/games.db`.

### Build the database

```
python -m pipeline.create_tables     # 9 tables, indexes, constraints
python -m pipeline.ingest            # import per config/map_config.yaml
python -m pytest -q                  # all tests, expect 38 passed
```

Two extra options on the import:

```
python -m pipeline.ingest --reset    # rebuild, keeping existing game_ids
python -m pipeline.ingest --limit 40 # small run for the 30 to 50 game milestone
```

Every import writes `data/import_report.md`. That report is how we meet the rule
about reporting missing values, duplicate candidates and feature-category
coverage after every import, so read it.

It opens with a table listing every database column and the exact CSV column it
came from. That table is generated from the config, so it can never drift out of
date the way a hand-written one would.

---

### Adding a column without re-importing

Once a map is published, `python -m pipeline.ingest` refuses to run, because
rebuilding the games could change ids or features under the live map. To add a
display column that the map does not use, follow these steps instead:

1. Add the column to `Game` in `backend/app/models.py`.
2. Add a matching entry to `fields.column_sources` in `config/map_config.yaml`,
   saying which CSV column it comes from.
3. Run `python -m pipeline.add_columns --check` to see what it will do, then
   `python -m pipeline.add_columns`.

It adds only the columns the database is missing, fills only those, and matches
each game by Steam app id. It never changes an existing value, a game id, the
features tables or any map table, so the published map and its fingerprint stay
the same. It refuses to run if the CSV is a different snapshot from the one the
games were imported from. Running it twice is harmless.

This is how `release_date`, `long_description`, `developers` and `publishers`
were added on top of map v2. Afterwards, the map's `corpus_hash` still matched
the one v2 recorded, and every pre-existing table was byte-for-byte unchanged. A
fresh import with the same code produced identical tables.

## Everything tunable lives in one file

`config/map_config.yaml` holds the map version, random seed, cluster count,
category weights, feature vocabulary, tag aliases, the selection rule, and the
full mapping of which CSV column becomes which database column (MAINT 2).
Changing a weight, adding a tag mapping or pointing a column at a different
source never requires a code change. Re-run the import afterwards.

### For Austin and Kayne

The `vocabulary` and `aliases` sections are a starter stub. They exist so the
import could be built and tested, not because they are the right vocabulary.
Please take them over.

* A raw string listed in `aliases` becomes a weighted feature in its category.
* Anything not in `aliases` falls through to the display-only `tag` category.
  Nothing is lost, it just is not weighted.
* A string mapped to a weighted category does not also become a `tag` feature.
  That is how the "avoid counting the same concept twice" rule is enforced.
* `category_weights.tag` is set to `0.0` on purpose.
* The import report's "most common unmapped tags" section is your to-do list.

Duplicate YAML keys are rejected instead of silently overwriting each other, so
a mapping cannot disappear without an error.

---

## Schema

Nine tables, following the scrum doc. Two are additions, both flagged for review.

| Table | Purpose |
|---|---|
| `games` | One row per game, including both the short and long descriptions |
| `game_sources` | External ids and provenance, PK `(source_name, external_id)` |
| `features` | Approved vocabulary, unique on `(category, name)` |
| `game_features` | Links games to features |
| `game_feature_coverage` | Addition, see below |
| `map_versions` | One row per generated map |
| `clusters` | Per-version cluster labels and colors |
| `map_games` | Per-version coordinates and cluster membership |
| `map_neighbors` | Per-version similarity recommendations |

### Additions for team review

1. **`games.raw_tags_json`.** The rules say to preserve the original dataset
   export and raw tags, but no column held them. This stores the source object
   of tag to vote count verbatim.
2. **`game_feature_coverage`.** The rules require distinguishing missing source
   information from a confirmed absence, and `game_features` can only record
   presence. One row per game per category, with status `present`, `absent` or
   `unknown`.
3. **`UNIQUE(map_version_id, game_id, rank)` on `map_neighbors`.** The rule that
   rank is unique within each game's versioned list is not enforceable by the
   stated primary key alone.
4. **Finite coordinates are validated in Python**, not by a CHECK constraint.
   SQLite stores NaN as NULL and accepts infinity, so a constraint would miss it.

### Rules enforced by the schema itself

* `PRAGMA foreign_keys=ON` on every connection
* Indexes on `games.title_search` and `game_features.feature_id`
* At most one `map_versions` row with `is_active = 1`, via a partial unique index
* An active version must have status `published`, via a CHECK constraint
* A mapped game's cluster must belong to the same map version, via a composite
  foreign key
* Both ends of a neighbor pair must exist in `map_games` for that version
* A game cannot recommend itself, via a CHECK constraint

---

## Import decisions worth knowing

| Decision | Reason |
|---|---|
| `rating` comes from `pct_pos_total`, scale `0-100` | Metacritic is missing for 96% of games and `user_score` for 99.96% |
| `rating_count` and `popularity` come from `num_reviews_total` | Fully populated and numeric |
| Zeros become NULL for metacritic, user score and playtime | Steam writes 0 to mean "no data" |
| `playtime_hours` is `average_playtime_forever` divided by 60 | The source value is in minutes |
| `game_id` is ours, not the Steam appid | The appid lives in `game_sources`, and ids are preserved across re-imports |
| `developers` and `publishers` are plural, comma-joined text | About 8% of games have more than one developer and one has 41, so a singular column would be wrong. Joined rather than given their own table because we only display them. |
| `release_date` and `release_year` both exist | The date is for the info panel, the year is for filtering. Storing the year separately avoids parsing 89,618 strings on every import. |
| `long_description` comes from `about_the_game` | It matches `detailed_description` 84% of the time, but when they differ, `detailed_description` opens with store sales copy. Falls back to it when missing. |
| `title_search` is Unicode-aware | Stripping down to `[a-z0-9]` would blank every CJK title |
| Duplicate titles are reported, never merged | Stated rule in the scrum doc |

---

## Requirement to test map (MAINT 1)

| Requirement | Test |
|---|---|
| DATA 1 completeness of at least 95% | `tests/test_data_quality.py::test_data1_completeness_at_least_95_percent` |
| No game appears twice | `tests/test_data_quality.py::test_no_game_appears_twice` |
| DATA 2 similar pairs, at least 80% mutual top-15 | `tests/test_data_quality.py::test_data2_similar_pairs_are_in_each_others_top_15` |
| CON 3 size cap | `tests/test_data_quality.py::test_game_count_within_cap` |
| Foreign-key enforcement | `tests/test_schema.py::test_foreign_keys_are_enforced` |
| Required indexes | `tests/test_schema.py::test_required_indexes_exist` |
| One active map version | `tests/test_schema.py::test_only_one_active_map_version` |
| Active version is published | `tests/test_schema.py::test_active_version_must_be_published` |
| Cluster belongs to the same version | `tests/test_schema.py::test_map_game_cluster_must_belong_to_same_version` |
| No self-recommendation | `tests/test_schema.py::test_game_cannot_recommend_itself` |
| Neighbor rank unique per game | `tests/test_schema.py::test_neighbor_rank_is_unique_per_game` |
| Neighbors exist in the same map | `tests/test_schema.py::test_neighbor_must_be_in_the_same_map_version` |
| REL 4, a failed build leaves the previous version active | `tests/test_publish.py::test_failed_build_leaves_previous_version_active` |
| 10 to 15 neighbors per game | `tests/test_publish.py`, parametrised cases |
| MAINT 2, single config file | `tests/test_config.py` |
| Every column documents its source | `tests/test_config.py::test_every_games_column_has_a_documented_source` |
| Long description imported correctly | `tests/test_data_quality.py::test_long_description_is_longer_than_the_short_one` |
| Raw tags keep their vote counts | `tests/test_data_quality.py::test_raw_tags_are_valid_json_with_vote_counts` |
| Dates stored so they sort correctly | `tests/test_data_quality.py::test_release_date_is_iso_format` |
| Date and year never disagree | `tests/test_data_quality.py::test_release_year_matches_release_date` |
| Multiple developers are all kept | `tests/test_config.py::test_developers_and_publishers_are_joined_not_truncated` |
| Adding a column never changes existing data | `tests/test_add_columns.py::test_never_changes_existing_values` |
| Adding a column refuses a mismatched CSV | `tests/test_add_columns.py::test_refuses_a_csv_from_a_different_snapshot` |

---

## For the ML pipeline

```python
from pipeline.config import load_config
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

Validation and activation run in one transaction. Any failure rolls the whole
thing back, so the previously published version stays active and no partial
version is ever saved. Use `mark_failed()` to record a build that did not make it.

The validator rejects a map for any of these, so check them before calling:

* a non-finite x or y coordinate
* a game that appears twice
* a game that is not in the `games` table
* a cluster id that this version does not define
* a game recommending itself
* fewer than 10 or more than 15 neighbors for a game
* neighbor ranks that are duplicated, or that do not start at 1 and run
  consecutively
* more than 1100 games, per CON 3

---

## Open items

* **CON 3 conflict.** The NFR document says the published map is approximately
  1,000 mostly pre-2019 games. The current build uses
  `selection.mode: popular_recent`, meaning 2019 onward. Changing that one value
  to `popular_pre2019` switches it. This needs a team decision.
* **Non-game software** such as Utilities, Accounting and Audio Production is
  currently kept. Add entries to `selection.exclude_genres` to drop it.
* **Adult content** is currently kept. 110 games carry `sexual_content`, 70
  carry `nudity`, 155 carry `gore` and 178 carry `violent`. The map displays
  cover images.
* **The repo README** lists PyTorch, while CON 1 specifies scikit-learn.
* **SEC 5** says browser storage holds only the saved map configuration and
  guide-completion status, but the scrum doc adds a browser SQLite cache of map
  data. One of the two needs updating.
