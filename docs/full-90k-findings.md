# Full-catalogue experiment: 1,000 games vs 89,618

What happened when the ML pipeline ran on every game in the March 2025 Steam
snapshot instead of the 1,000-game map dataset, using the long "About this
game" text. This is a test build, not a map: CON 3 caps a published map at
1,100 games, and nothing here was published or written to `data/map.db`.

Interactive results (both builds, every method, zoomable maps):
<https://claude.ai/artifact/RZsaERXeM7NfmWU5Qj6J4F>

Run on 2026-11-04 by Kayne. Requirement references are to the System
Requirements document (10/9/2026).

## Summary

* Going from 1,000 to 89,618 games replaces most neighbours. A game in the 1k
  set keeps only 5 to 15% of its top 10, and about 85% of the new top 10 are
  games the 1k set never had.
* Known-similar pairs (DATA 2) drop for every method, from about 0.89 to about
  0.53 for `votes_max`. Small games that copy a hit's tag list crowd out the
  hit's real peers.
* `hybrid_embed` suffers most because it is built on `votes_log`. A
  `votes_max`-based hybrid (`hybrid_max`) recovers about 10 of the 100 pairs.
* IDF does not help (decision 4 stands).
* The best method at 90k is `hybrid_semantic` (tags plus the description
  embedding), and it is the only strong method that places the 16,872 games
  with no Steam tags.
* The visible lines on the 90k maps are groups of near-identical tag vectors,
  not anything about titles.

## How to reproduce the database

On branch `test/full-90k-database` (Ronnie's), with the Kaggle CSV at
`data/raw/games_march2025_cleaned.csv`:

```
python -m pipeline.create_tables
python -m pipeline.ingest
```

This takes about 1.5 minutes and writes a 337 MB `data/games.db`, which is
gitignored because it is over GitHub's 100 MB limit. The 1k comparison
database is `data/games.db` from `main` at commit `d6160f0`.

## How to rebuild the lab

The pipeline builds the lab data itself. With the 1k database and the 90k
database from the step above:

```
python -m pipeline.vector_lab --small <1k games.db> --full <90k games.db> --device cuda
```

This writes `data/artifacts/vector_lab/`: `meta.json` with every score, one
compressed data file per build and method, and `shared.bin.gz.b64.txt` with the
game list. The viewer page is not in the repo. Pass it with `--page` to copy it
in as `index.html`, then serve the folder over HTTP to view it. On an RTX 5080 the full run takes about 40 minutes, most of it t-SNE on the 90k
maps. `--device` defaults to `vectorization.embedding_device` (`cpu`).

The export always runs the six methods below on both builds. Each build is
vectorised from its own database. The 90k database supplies the shared game
list and titles that the page uses to line the two builds up. It scores pairs against
`config/similar_pairs.yaml`.

## What was run

`pipeline.vector_lab` runs the normal map build (`build_map_from_vectors`)
for each build and method, with `config/map_config.yaml` unchanged except:

| Setting | Lab | Published map | Why |
|---|---|---|---|
| Text for embeddings | `long_description`, falling back to `description` per game (`--text-field`) | `description` | The richer text was the point of the test |
| Embedding device | GPU (`--device cuda`) | CPU | 89,618 descriptions in 49 s on an RTX 5080. `build_map --publish` refuses a non-CPU device for an embedding method (REL 2) |
| Collision spreading | 1k only | Yes | The minimum spacing cannot be met at 90k density, so maps over the CON 3 cap skip it |

Everything else is the pipeline's normal path. Neighbours are exact cosine
top 15, computed in blocks of 512 rows so 90k games fit in memory. The layout
is the pipeline's scikit-learn t-SNE (205 s and 3.9 GB for 72,746 games).
K-Means is `assign_clusters` with k = 12 and seed 42.

Two full runs gave byte-identical output for every build and method except
the 90k `semantic` clusters, which differed between runs (adjusted Rand index
0.999). Multithreaded K-Means can change its labels between runs on the same
vectors, so `assign_clusters` now runs on one thread. Two single-thread runs on
those vectors gave identical labels, and the 1k published build is unchanged.

The embedding model reads only the first 256 word pieces of each text. At 90k
the median description is 226 word pieces, 42% are longer than 256, and about
30% of all description text is never read.

GPU arithmetic differs slightly from the CPU, so these vectors do not match a
CPU build to the last bit. That is acceptable for an experiment, not for a
published map.

## Methods compared

All six are methods in `pipeline/vectorize.py`, so `vectorization.method` in the
config and `compare_vectors --methods` can use them too.

| Method | Weight of each tag the game has | Tagless games |
|---|---|---|
| `votes_max` (map v2) | votes / votes on the game's top tag | Left out |
| `desc_embed` | 0.4 + 0.6 x closeness of the tag to the description | Left out |
| `hybrid_embed` | 0.7 x `votes_log` + 0.3 x `desc_embed` | Left out |
| `hybrid_max` | 0.7 x `votes_max` + 0.3 x `desc_embed` | Left out |
| `semantic` | No tags: the 384-number description embedding | Included |
| `hybrid_semantic` | `votes_max` and `semantic` side by side, so similarity = 0.7 x tag cosine + 0.3 x text cosine | Included |

`votes_log` is log(1 + votes) / log(1 + top tag's votes). No method here uses
IDF.

## Results

Pairs use the 100 pairs in `config/similar_pairs.yaml` on Austin's branch
(commit `002ccc7`): mutual means each game is in the other's top 15; one-way
means at least one direction. With 100 pairs, a difference of 0.05 is 5 pairs.

| Method | 1k pairs (mutual / one-way) | 90k pairs (mutual / one-way) | 1k genre | 90k genre | 90k top 10 same as 1k |
|---|---|---|---|---|---|
| `votes_max` | 0.89 / 0.92 | 0.53 / 0.62 | 0.586 | 0.728 | 15% |
| `desc_embed` | 0.83 / 0.87 | 0.41 / 0.51 | 0.594 | 0.692 | 11% |
| `hybrid_embed` | 0.85 / 0.89 | 0.44 / 0.56 | 0.604 | 0.734 | 13% |
| `hybrid_max` | 0.88 / 0.92 | 0.53 / 0.62 | 0.596 | 0.740 | 14% |
| `semantic` | 0.56 / 0.62 | 0.25 / 0.33 | 0.400 | 0.367 | 5% |
| `hybrid_semantic` | 0.89 / 0.92 | 0.60 / 0.69 | 0.581 | 0.644 | 15% |

Genre is the mean Jaccard overlap of Steam genres with the top 10. It rises at
90k because there are more candidates to match, and it favours tag-only
methods because many genre names are also tags. Do not read it as quality.

The share of each game's 15 true neighbours that stay among its 15 closest
map points falls from 30 to 51% at 1k to 24 to 34% at 90k.

## Findings

### Clones outrank the games they copy

Factorio's 10 nearest neighbours under `hybrid_embed`:

* 1k: shapez, Satisfactory, Mindustry, Space Haven, Hydroneer, OpenTTD...
* 90k: Life is Feudal: Forest Village, Survival Vacancy, ReFactory, Planet
  Barren Objective, shapez...

Tag vectors cannot tell a hit from a small game with the same tag list. The
1k map avoids this because `popular_recent` selection only admits well-reviewed
games.

### `votes_log` is what hurts `hybrid_embed`

The log squashes vote counts, so a small game whose 20 tags each have about 30
votes looks like Factorio, whose tags have thousands of votes in a distinctive
shape. Under `votes_max` Factorio's 90k list starts shapez, Satisfactory,
Mindustry. `hybrid_max` (the same hybrid built on `votes_max`) scores 0.53
mutual at 90k against 0.44 for `hybrid_embed`, and ties `hybrid_embed` at 1k.

### IDF is neutral to harmful

Each `_idf` variant was scored against its base method:

| Method | 1k pairs, without / with IDF | 90k pairs, without / with IDF |
|---|---|---|
| `votes_max` | 0.94 / 0.91 | 0.59 / 0.53 |
| `votes_log` | 0.85 / 0.91 | 0.47 / 0.53 |
| `hybrid_semantic` | 0.91 / 0.91 | 0.61 / 0.58 |

All of these were scored on the earlier 33 pairs. Every change is 1 or 2
pairs, and genre drops by 0.05 to 0.10 because IDF downweights the common tags
that are also genre names. IDF cannot separate games with identical tag
profiles, and it makes clones look more alike by turning a shared rare tag
(Automation, for example) into the main signal.

### The lines on the map are near-duplicate tag vectors

On the 90k `hybrid_embed` map, 73 groups (3,759 games) have 10 or more
neighbours at cosine above 0.98. t-SNE strings such groups out into arcs: they
are about 10 times more elongated than an ordinary patch of the map. The
largest group is 302 hidden-object games that all share exactly Adventure,
Casual and Hidden Object. 97% of their titles contain a colon or dash because
that genre names its games "Series: Subtitle Collector's Edition". No method
reads titles. `semantic` has far fewer such groups (0.2% of games against
6.8%).

### Data problems found

* **Tagless games.** 16,872 games (18.8%) have no Steam tags, including
  Overwatch 2. Tag-only methods cannot place them. `main`'s `min_tags: 3` rule
  already excludes them.
* **Unknown review counts.** 36,419 games store `rating_count` as -1 for
  "unknown". Any code that casts it to an unsigned type turns it into
  4,294,967,295.
* **Duplicate titles.** 890 normalised titles appear more than once (store editions and
  bundles). `compare_vectors.resolve_pairs` used to keep the last row with a
  title, which matched the pair "EA SPORTS FC 25" to a tagless edition listing
  (game_id 366) instead of the base game (game_id 362). It now picks the
  listing with the most tag votes, then the lowest game_id. The 1k build has
  no duplicate titles, so its scores do not change.

### K-Means at 90k

With `votes_max` on the 72,746 tagged games, k = 12 gives clusters of 3,800
to 10,100 games that read at the genre level (shooters, RPGs, strategy, visual
novels, horror, platformers), plus a catch-all "Adventure, Indie, Action". The
silhouette score is flat at about 0.08 for every k from 8 to 120 (0.13 at 1k),
so the data has no natural cluster count. Clusters are more stable across
seeds than at 1k (ARI 0.71 to 0.88, against 0.59 to 0.81). At k = 40 the
clusters become specific: party RPGs, roguelites, atmospheric
puzzle-platformers, local-multiplayer party games.

These numbers come from a one-off script outside the repo that ran
`assign_clusters` and scikit-learn's `silhouette_score` and
`adjusted_rand_score` on the `votes_max` vectors.

## Open questions for the team

1. Make `hybrid_semantic` the map method? It is now in `vectorize.py`. On the
   1k build with the 100 pairs it ties `votes_max` (0.89 mutual), and at 90k it
   is the best method.
2. Store Steam app IDs in `similar_pairs.yaml` instead of titles, so
   duplicate titles cannot pick the wrong listing (Austin).
3. If the map ever grows past the 1,000 most-reviewed games: re-rank
   neighbours with a popularity term, or keep a review-count floor.
4. Decide what to do with the cluster that groups adult-content games at 1k
   (28 games in a K-Means run with map v2's settings: `votes_max`, k = 12,
   seed 42).
