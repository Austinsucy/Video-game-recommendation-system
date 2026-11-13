# Map pipeline decisions

What has been decided about how games become a map, why, and what is still
open. Each entry says whether it is **decided**, **proposed** (needs team
sign-off) or **open**, and where the evidence lives.

Requirement references are to the System Requirements document (10/9/2026).

## Summary

| # | Topic | Status | Current choice |
|---|---|---|---|
| 1 | Similarity measure | Decided | Cosine similarity, 15 neighbours per game |
| 2 | Clusters | Decided (count open) | K-Means on the full vectors, 12 clusters |
| 3 | 2D layout | Decided | t-SNE |
| 4 | Vectorization method | Decided; published as map v2 | `votes_max`; map v1 used `votes_log_idf` |
| 5 | Feature vocabulary | Decided | 15 new features, 64 new aliases |
| 6 | "Tactical" tag | Decided | Display-only |
| 7 | Similar-pairs list | Decided (33) + Proposed (67) | 33 approved pairs (20 sequels, 13 cross-studio); 67 more proposed 2026-11-04 (20 sequels, 47 cross-studio), pending team approval. Map v2 has 89 of 100 as mutual top-15 |
| 8 | Reproducible builds | Proposed | Build published maps with the pinned `requirements.txt` only |
| 9 | Map rendering | Proposed | Custom WebGL dot layer + Canvas 2D labels instead of Cytoscape (CON 1 deviation); dot and label size by Steam reviews |

## 1. Similarity measure: cosine, 15 neighbours (decided)

GM 1 specifies cosine similarity and 10 to 15 ranked neighbours. The pipeline
L2-normalises every vector and stores each game's 15 most similar games, ties
broken by game id (`pipeline/vectorize.py`, `neighbor_indices`).

## 2. Clusters: K-Means on the full vectors (decided; count open)

GM 1 specifies K-Means on the full weighted vectors, not the 2D points.
`cluster_count: 12` is still marked as a placeholder in
`config/map_config.yaml`. Cluster names are `Cluster 0` to `Cluster 11` until
the team names them (CL 1).

## 3. 2D layout: t-SNE instead of PCA (decided)

- **Choice:** `layout.method: tsne`, perplexity 30, PCA initialisation, seed 42.
- **Why:** with `votes_log_idf`, t-SNE keeps 47.5% of each game's 15 nearest
  games among its 15 nearest dots on the map; PCA keeps 11.5%. Similar games
  sit together on a t-SNE map far more often.
- **Cost:** distances between separate islands mean little; any change to the
  data or weights rearranges the whole map; it is slower than PCA.
- **Evidence:** commit `dc78a3f` (Kayne, 2026-10-28) and the Tag Vector Lab
  comparison page.
- **Requirements:** GM 1 and UDR 1 still say PCA. On 2026-11-02 the team chose
  not to update the requirements document; this entry records the deviation.

## 4. Vectorization method: `votes_max` for map v2 (decided 2026-11-02)

- **Choice:** `vectorization.method: votes_max`, with `map_version: v2`. Map v1
  was published with the placeholder `votes_log_idf`; v2 replaces it.
- **Why `votes_max` over `votes_rank`**, the other finalist:
  - It finds one more pair: 31 of 33 (11 of 13 cross-studio) against 30 (10).
    With 13 cross-studio pairs that gap is small.
  - It has no exact distance ties, so its t-SNE map rebuilds the same on any
    machine. `votes_rank` ties for every game and its map rearranged between
    builds (decision 8).
- **Known weakness:** it does not down-weight tags most games share, so a broad
  tag such as "Indie" counts fully when it is a game's top tag. The pair scores
  do not show this hurting. `votes_max_idf` (10 of 13, no ties) is the fallback.
- **Dry run of v2** (`python -m pipeline.build_map`, nothing written to the
  database): 1,000 games, 15 neighbours each, validation passed, 51% of
  neighbours kept on the t-SNE map (v1: 48%), cluster sizes 28 to 136,
  12 overlapping games moved apart. A second build gave identical positions
  and clusters.
- **Change from v1:** on average 6 of each game's 10 nearest games stay the
  same. 78% of games keep at least 5; 3% keep 2 or fewer. Every position on
  the map changes, since this is a new layout.
- **Published 2026-11-02** with `python -m pipeline.build_map --publish`. v2 is
  the active map version in `data/games.db`, which now also holds each game's
  15 ranked neighbours (15,000 rows) for the info panel and DATA 2. `data/map.db`
  was re-exported and matches the build exactly. v1 was never stored in the
  shared `games.db`; its file is in git history (commit `c9092e0`).
- **Re-importing now needs care:** `python -m pipeline.ingest` refuses to run
  while `map_versions` has rows, so a future re-import means deliberately
  clearing the published map first.

The comparison and tuning below are the evidence for this choice.

Comparison on 2026-11-02 (all 13 methods, vocabulary from decision 5, pairs
from decision 7, top-15 neighbours):

| Method | Sequel pairs (20) | Cross-studio pairs (13) | Kept on t-SNE map |
|---|---|---|---|
| votes_max | 1.00 | **0.85** | 0.51 |
| votes_log_idf (v1) | 1.00 | 0.77 | 0.48 |
| votes_rank, binary_idf, votes_max_idf | 1.00 | 0.77 | 0.46 to 0.54 |
| hybrid_tfidf, hybrid_embed, votes_rank_idf | 0.95 to 1.00 | 0.69 | 0.46 to 0.54 |
| binary, votes_log | 1.00 | 0.62 | 0.43 to 0.46 |
| desc_tfidf, desc_embed | 0.95 | 0.54 | 0.45 to 0.46 |
| category_weighted | 0.90 | **0.46** | 0.51 |

What the results show:

- Sequel pairs cannot separate the methods; nearly all score 1.00. Only the
  cross-studio pairs do.
- With 13 cross-studio pairs, one pair moves a score by about 0.08, so
  `votes_max` and `votes_log_idf` differ by a single pair.
- The description and embedding methods do not beat plain tag votes.
- `category_weighted` is the only method that uses the curated categories and
  their weights, which GM 1 and UDR 1 depend on, and it currently scores worst.
  Giving the display-only tags weight (0.5, 1, 2) did not help.

### Weight tuning for `category_weighted` (2026-11-02)

`python -m pipeline.tune_weights` searches each category weight over
0 to 3 against the 33 approved pairs, then checks for overfitting by tuning
without each pair and testing on the one left out. Report:
`data/artifacts/weight_tuning.md` (not committed).

| Vectors | Sequel (20) | Cross-studio (13) | All (33) |
|---|---|---|---|
| category_weighted, config weights | 18 | 6 | 24 |
| category_weighted, tuned weights | 20 | 7 | 27 |
| category_weighted, held-out estimate | 19 | 5 | 24 |
| votes_log_idf, no tuning | 20 | 10 | 30 |

Tuning finds weights that score 27 of 33, but on pairs it did not see it
scores 24, the same as the untuned config. The gain is fitting to these
pairs, not a better method. Setting every weight to 1 also scores 24. The
limit is the method's structure, not its weights: it squeezes 410 tags into
96 curated features and gives each category an equal block, while
`votes_log_idf` keeps every tag at full resolution. The config weights were
left unchanged.

This is why the default map uses a tag-vote method rather than
`category_weighted`. UDR 1 personalisation is still open. One untested idea:
keep the default map's tag vectors but scale each tag by the user's weight for
the category its alias belongs to. With equal weights this is exactly the
default map, so personalisation would start from the best-scoring vectors.

Avoid `binary` and `votes_rank` for a published map: see decision 8.

## 5. Feature vocabulary expansion (decided)

- **Choice:** 15 new curated features and 64 new aliases in
  `config/map_config.yaml`, then a re-import of `data/games.db` from the same
  snapshot (SHA-256 `04d8df27…dfab`). Commit `a242fd6`.
- **Rules applied:**
  - Merge synonyms into one feature so a concept counts once (RPG subgenres
    become RPG; "Rogue-lite", "Roguelite" and "Rogue-like" become Roguelike).
  - Add a feature only for a gameplay, mechanic, structure, theme or
    multiplayer concept that many games share (Souls-like, Melee Combat,
    Automation, PvE, Medieval, and others).
  - Keep art style, mood, content warnings and business tags display-only
    (Indie, Atmospheric, Pixel Graphics, Violent, Free to Play).
- **Effect:** tag-derived coverage rose for gameplay (737 to 815 games),
  mechanic (549 to 632), structure (612 to 638) and theme (800 to 854). Genre
  labels changed too (Platformer 68 to 98, RPG 376 to 394), which reaches the
  genre filter and info panel at the next `map.db` export. Feature ids were
  renumbered.
- **Not affected:** map v1 positions. `votes_log_idf` reads raw tag votes, so
  only `category_weighted` uses the vocabulary for similarity.

## 6. "Tactical" stays display-only (decided)

Of the 98 games tagged "Tactical", 36 are strategy or tactics games, 29 are
tactical shooters, 28 have both kinds of tags and 5 have neither. Mapping it
to either side would pull the other kind of game toward the wrong
neighbours. The games already carry more specific mapped tags ("Turn-Based
Tactics", "Tactical RPG", "RTS", "Shooter", "FPS").

## 7. Similar-pairs list (decided)

`config/similar_pairs.yaml` holds 33 pairs: 20 sequel pairs and 13 pairs of
similar games from different studios (commit `aa9808a`). The team approved
the list on 2026-11-02. The cross-studio pairs are the ones that separate
methods. Map v1 had 30 of the 33 pairs (0.91) in each other's top 15; map
v2 has 31 (0.94), above DATA 2's 80% bar (8 of 10).
`tests/test_data_quality.py::test_data2_similar_pairs_are_in_each_others_top_15`
checks the published map's stored neighbour lists against that bar.

## 8. Build published maps with the pinned versions (proposed)

On 2026-11-02, rebuilding map v1 from `data/games.db` with the current config
and `requirements.txt` (Python 3.14) reproduced `data/map.db` exactly.

The same check showed a risk. Methods with coarse weights (`binary`,
`votes_rank`) produce exact ties in game-to-game distances for every game.
t-SNE then breaks those ties based on small software differences, and five
methods' t-SNE maps came out arranged differently from the earlier Tag Vector
Lab page despite identical input. Reruns on one machine are identical, and
the CPU thread count makes no difference. `votes_log_idf` has no ties and
matched exactly.

K-Means is different: with several threads its labels can change between runs
on the same vectors (seen on 89,500 games in the full-catalogue experiment,
`docs/full-90k-findings.md`). `assign_clusters` therefore runs K-Means on one
OpenMP thread.

Proposal: build every published map version from a clean environment with the
pinned `requirements.txt`, and prefer methods without distance ties (REL 2).

## 9. Map rendering: custom canvas instead of Cytoscape (proposed)

CON 1 lists Cytoscape.js for the map, and GM 2 asks for a Cytoscape preset
layout. With map v3 (72,746 games), Cytoscape could not reach PERF 3 (30 fps
pan and zoom). Measured on 2026-11-09 in the desktop app's built-in browser
(Intel Arc 140T, 1.5× display scale):

| Renderer | Pan | Zoom |
|---|---|---|
| Cytoscape 3.34, canvas | ~0.9 fps (1.2 s per frame) | ~0.6 fps |
| Cytoscape 3.34, WebGL (`webgl: true`) | ~3.7 fps (~200 ms per frame) | ~1 fps |
| Custom WebGL dots + 2D labels | 0.5 ms median, 4.3 ms worst JS per redraw | same |

Cytoscape's WebGL mode still visits every node in JavaScript on each frame
(~200 ms for 72,746 nodes), and the old constant-size styling restyled every
node on zoom (~2.5–3.8 s each time).

`frontend/src/components/map/` now draws the dots with WebGL: positions,
sizes and colours are uploaded once, and a pan or zoom only changes a few
shader uniforms. Labels, hover and the selected game are drawn on a 2D canvas
on top. Browsers without WebGL fall back to drawing the dots in 2D. Hover,
click to select, search focus, zoom buttons, keyboard pan and zoom, and the
pan limits work as before.

The look follows the Tag Vector Lab's "By Steam reviews" view:

- popularity `t = (log(1 + reviews) / log(1 + most reviews))^2.5`, using
  `games.popularity` in `map.db` (unknown counts, stored as -1, count as 0);
- dot radius = base × (0.35 + 6.25·t) × 1.8, drawn at 55% opacity, least
  reviewed first (the lab's size scale is 3; the app uses 2.5, a little smaller);
- labels only for the 25 (zoomed out) or 40 (zoomed in) most reviewed games on
  screen, at `10 + 11.25·t` px, skipping any that would overlap.

Cytoscape is still in `package.json` but no longer used. Needs team sign-off:
either accept the deviation from CON 1 / GM 2 and update the requirements doc,
or cap the map at a size Cytoscape can draw at 30 fps.
