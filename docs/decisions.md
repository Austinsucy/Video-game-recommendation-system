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
| 3 | 2D layout | Decided by implementation; requirements not updated | t-SNE |
| 4 | Vectorization method | **Open** | `votes_log_idf` (placeholder used for map v1) |
| 5 | Feature vocabulary | Decided | 15 new features, 64 new aliases |
| 6 | "Tactical" tag | Decided | Display-only |
| 7 | Similar-pairs list | Proposed | 33 pairs (20 sequels, 13 cross-studio) |
| 8 | Reproducible builds | Proposed | Build published maps with the pinned `requirements.txt` only |

## 1. Similarity measure: cosine, 15 neighbours (decided)

GM 1 specifies cosine similarity and 10 to 15 ranked neighbours. The pipeline
L2-normalises every vector and stores each game's 15 most similar games, ties
broken by game id (`pipeline/vectorize.py`, `neighbor_indices`).

## 2. Clusters: K-Means on the full vectors (decided; count open)

GM 1 specifies K-Means on the full weighted vectors, not the 2D points.
`cluster_count: 12` is still marked as a placeholder in
`config/map_config.yaml`. Cluster names are `Cluster 0` to `Cluster 11` until
the team names them (CL 1).

## 3. 2D layout: t-SNE instead of PCA (decided by implementation)

- **Choice:** `layout.method: tsne`, perplexity 30, PCA initialisation, seed 42.
- **Why:** with `votes_log_idf`, t-SNE keeps 47.5% of each game's 15 nearest
  games among its 15 nearest dots on the map; PCA keeps 11.5%. Similar games
  sit together on a t-SNE map far more often.
- **Cost:** distances between separate islands mean little; any change to the
  data or weights rearranges the whole map; it is slower than PCA.
- **Evidence:** commit `dc78a3f` (Kayne, 2026-10-28) and the Tag Vector Lab
  comparison page.
- **Gap:** GM 1 and UDR 1 still say PCA. Either update the requirements or
  decide how UDR 1 personalised maps will be laid out.

## 4. Vectorization method (open)

Map v1 was published with `votes_log_idf`, which the config labels a
placeholder. No method has been formally chosen.

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

Options for the team:

- **A.** Keep `votes_log_idf` (or switch to `votes_max`) for the default map,
  and treat UDR 1 personalisation as a separate problem.
- **B.** Tune the `category_weighted` weights until it matches the tag-vote
  methods on cross-studio pairs, then use one method for both the default map
  and UDR 1.

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

## 7. Similar-pairs list (proposed)

`config/similar_pairs.yaml` holds 33 pairs: 20 sequel pairs and 13 pairs of
similar games from different studios (commit `aa9808a`). The cross-studio
pairs are the ones that separate methods. Map v1 has 30 of the 33 pairs
(0.91) in each other's top 15.

Still to do: the list is pending approval from Kayne and Austin, and DATA 2
asks for 10 approved pairs with at least 8 passing.

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

Proposal: build every published map version from a clean environment with the
pinned `requirements.txt`, and prefer methods without distance ties (REL 2).
