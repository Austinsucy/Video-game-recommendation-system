# Goon Squad: game database and import process

CSCI 150, Interactive Map of Video Games.

> **This is the `test/steam-plus-igdb` branch.** It merges the IGDB dataset
> (232,595 games) into the full Steam catalogue (89,618 games). Do not merge it
> into `main` until the team has reviewed the drafted aliases and the hand-offs
> at the end of the "Steam + IGDB merge" section below.
>
> * `data/games.db` is not committed (about 750 MB). Map v3 and `data/map.db`
>   are untouched: this branch builds `games.db` with no map in it.
> * Put both CSVs in `data/raw/`: `games_march2025_cleaned.csv` (Steam) and
>   `game_dataset_cleaned.csv` (IGDB). Then `python -m pipeline.create_tables`
>   and `python -m pipeline.ingest`. `--steam-only` imports Steam alone, like main.
> * The import writes `data/import_report.md`, `data/merge_report.md`,
>   `data/match_review.csv` (pairs a person should check) and `data/non_games.csv`.

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

---

## Steam + IGDB merge (test/steam-plus-igdb)

### Measured build

| | |
|---|---|
| Games | 252,030 (89,586 Steam + 162,444 IGDB-only) |
| Run time | about 290 s (two runs: 286 s, 289 s) |
| Peak memory | about 2.6 GB |
| `data/games.db` | about 750 MB |
| Second build from scratch | identical tables (row-by-row hash of all 9 tables) |
| Steam SHA-256 | `04d8df2778aaa8f8b575934b7072d55224d37a2ded23e8261583f0fcf668dfab` |
| IGDB SHA-256 | `1e2e5b3d4e4857a044bbaaffaf088e0a056ca19c0e416e80d2c4551c71915a28` |

Measured on Python 3.14 with the pinned requirements, on a Linux machine.

### What happens, in order

1. **Steam**, read exactly like main. Every app gets main's id (1, 2, 3, ... in
   selection order), so every Steam game keeps its id.
2. **Fold Steam's own duplicate apps.** Same strict title key, same release
   date, a shared company and the same short description = one game. 26 groups,
   58 apps (EA SPORTS FC 25 x4, Shadow of the Tomb Raider x5, Metro Exodus and
   its Enhanced Edition app, ...). The app with the most reviews is the game;
   the others become extra steam rows in `game_sources` (`match_method =
   'steam_fold'`) and keep their numbers as gaps. The kept game takes the union
   of the group's features; `raw_tags_json` (votes) comes from the kept app only.
3. **Read IGDB and clean it.** Drop the 6 nameless rows and the 1,543
   `expanded_game` entries (bundles). Re-join list items split at commas
   ("4X (explore, expand, ...)"), dedupe, `Missing` becomes NULL.
4. **Check alias coverage.** The import stops if fewer than 95% of IGDB genres,
   perspectives or game modes reach a weighted feature.
5. **Match each IGDB game to at most one Steam game** (`pipeline/matching.py`):
   strict key, then roman numerals, then no spaces, then edition words removed.
   The first key that finds a Steam title decides.
   * MERGE: strict key + same year + no company conflict, or a shared company
     (the roman and compact keys also need the years within one).
   * NEW: companies conflict, IGDB lists no PC-family platform (explicit list,
     "PC Engine" is a console), descriptions differ (TF-IDF cosine < 0.1), or
     only the edition key matches.
   * MERGE ON TEXT: years differ, no company info, descriptions >= 0.5.
   * REVIEW (kept separate, listed): 0.1 to 0.5, no description to compare, or
     several Steam games with the title.
   * One Steam game gets at most one merge: same year first, then company,
     then main game over remaster, then lowest IGDB id.
   * `config/match_overrides.yaml` is applied last and always wins.
6. **Write.** One transaction. Merged games keep the Steam id and every Steam
   value; IGDB only fills empty columns (142 publishers, 69 long descriptions,
   29 developers, 7 descriptions) and adds features with `source = 'igdb'`.
   New IGDB games get ids after the last Steam id, in IGDB id order (REL 2).

Result: 68,602 merged, 1,946 review, 160,498 new.

### New columns

| table | column | meaning |
|---|---|---|
| games | rating_kind | `steam_positive_pct` or `igdb_user_score` |
| games | popularity_source | `steam_review_count`, NULL for IGDB-only games (IGDB has no counts) |
| games | header_image_url | wide image: Steam header, IGDB first screenshot (else cover) |
| games | platforms_raw | JSON list of every platform the sources name |
| games | is_adult | config `adult_markers` matched (safe-mode, frontend hand-off) |
| games | primary_source | `steam` or `igdb` |
| games | is_non_game | name matches `non_game_patterns` (demos, playtests, servers); stays in the DB |
| games | is_upcoming | release date after `sources.igdb.upcoming_after` (fixed date, REL 2) |
| games | tag_source | `steam_votes`, `igdb` or `none` |
| games | raw_tags_kind | `votes` or `presence` |
| games | raw_igdb_json | the IGDB lists, untouched |
| game_sources | title_in_source, release_date_in_source | the source's own spelling |
| game_sources | match_method, match_score | which rule attached the row, description similarity |
| game_features | source | `steam`, `igdb` or `derived_text` |

`raw_tags_json` still means Steam tag -> votes and nothing else. The 9,906
untagged Steam games rescued by IGDB have `tag_source = 'igdb'`,
`raw_tags_kind = 'presence'` and `raw_tags_json` NULL: no votes were invented.
The optional `derived_text` step is off.

Untagged Steam games (16,872 apps): 8 duplicate apps (folded), 69 non-games,
4,548 got 3+ IGDB tags (Overwatch 2, Marvel Rivals, THE FINALS, Muck, Crab
Game), 6,489 got 0 to 2, 5,671 have no IGDB match but have Steam genres and a
description, 87 have almost nothing. DATA 1 pass rate: Steam games with Steam
votes 98.4%, rescued by IGDB 97.8%, still untagged 90.8%; IGDB-only games with
IGDB tags 70.3%, without 13.4%.

### Steam safety, checked against a main build

Compared with a database built from main on the same CSV: all 89,618 app ids
are present, 89,586 keep the same game id (the other 32 are the folded apps).
The only value changes are: 889 titles lose a TM / R / C sign or a doubled or
non-breaking space; 2,015 short and 8,263 long descriptions are HTML-unescaped
(`&amp;` to `&`); and empty Steam columns filled from IGDB. Three Steam tags now
reach a weighted feature through the drafted aliases ("Text-Based" 2,147 games,
"Music" 1,050, "Pinball" 136). `config/similar_pairs.yaml` titles lost their TM
signs too, to keep matching `games.title`.

### Drafted for Austin (marked DRAFT in map_config.yaml)

IGDB aliases, the platform families (`dos`, `pc_vr`, `standalone_vr`,
`playstation`, `xbox`, `nintendo`, `sega`, `mobile`, `web_browser`,
`arcade_cabinet`, `retro_computer`, `other_console`), the perspective
`text_based`, and the genres `music_rhythm`, `card_and_board`, `quiz_trivia`.
Coverage with them: genres 99.1% (Indie left as a tag on purpose),
perspectives 99.2%, modes 99.7%.

### Test changes on this branch

* New: `tests/test_matching.py` (keys, cleaning, every real-case rule),
  `tests/test_merge_database.py` (parity, folding, rescue, Steam safety).
* Steam-only checks in `test_data_quality.py` (long description, developers)
  now look at Steam games only; IGDB's numbers are in the merge report.
* The vectorizer smoke test and the real-database map build skip above a size
  limit instead of running out of memory (the corpus alone needs over 10 GB).

### Open items and hand-offs (not built)

* **CON 4:** the IGDB Kaggle link, license and snapshot date are still empty
  in `sources.igdb`. Credit both datasets on the Help page.
* **Kayne:** weighting for presence-only IGDB tags; placing untagged games by
  description plus Steam genres; which games go on the map (is_non_game,
  IGDB-only games); t-SNE memory at 252,000 games; a cross-source neighbour check.
  `build_map` does not filter `is_non_game` yet.
* **Frontend:** year and platform in search results (10,186 titles are shared),
  accent-insensitive search, source-aware rating and review labels, the wide
  image fallback, a platform filter, a safe-mode toggle, a "not on the map" note.
* **Everyone:** look through `data/match_review.csv` (6,117 pairs) and
  `data/non_games.csv`, and settle pairs in `config/match_overrides.yaml`.
