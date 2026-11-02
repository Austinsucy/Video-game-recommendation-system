# map.db: the browser's map data

`data/map.db` is the small SQLite file the frontend loads to draw the map
(CON 1). It holds the published map and the game fields the map needs before
anyone clicks. Everything else (descriptions, images, tags, ratings, similar
games) stays in the backend database `data/games.db` and loads when a game is
selected (GM 2).

The file is about 225 KB. The ML pipeline writes it, and the frontend only
reads it.

## Tables

### `map_info`

One row that identifies the map.

| Column | Type | Meaning |
|---|---|---|
| `map_version` | TEXT | Map version id, for example `v1`. Each new map gets a new id. |
| `created_at` | TEXT | When the map was published, ISO 8601 UTC. |

### `clusters`

One row per cluster, 12 in `v2`.

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | INTEGER | Cluster id, from 0. |
| `name` | TEXT | Display name for the legend. In `v2` these are placeholders (`Cluster 0`, `Cluster 1`, ...) until the clusters are named (CL 1). |
| `color` | TEXT | Hex colour such as `#E69F00`, from a colour-blind-friendly palette. Some colours look alike, so always label clusters by name, not by colour alone (ACC 3). |

### `games`

One row per game on the map, 1,000 in `v2`.

| Column | Type | Meaning |
|---|---|---|
| `game_id` | INTEGER | The same id as `games.game_id` in `games.db`. Use it to request the game's details from the backend. |
| `title` | TEXT | Title for tooltips and labels. |
| `x`, `y` | REAL | Fixed map position. Values run from about -1000 to 1000. Use them as-is with Cytoscape's preset layout and never recompute them (REL 1). |
| `cluster_id` | INTEGER | The game's cluster in `clusters`. |
| `popularity` | REAL | Total Steam review count. Use it to decide which titles to label when zoomed out. Larger means more popular. |

### `game_genres`

One row per game and genre. A game can have several genres. Every game in
`v2` has at least one.

| Column | Type | Meaning |
|---|---|---|
| `game_id` | INTEGER | The game in `games`. |
| `genre` | TEXT | Genre display name, for example `RPG`. `v2` has 16 genres. |

## Example queries

All games with their cluster colour:

```sql
SELECT g.game_id, g.title, g.x, g.y, c.name, c.color
FROM games g JOIN clusters c USING (cluster_id);
```

The genre list for the filter (GV 1):

```sql
SELECT DISTINCT genre FROM game_genres ORDER BY genre;
```

The games in one genre:

```sql
SELECT game_id FROM game_genres WHERE genre = 'RPG';
```

## Updating the file

The pipeline replaces `map.db` whenever a new map version is published:

```
python -m pipeline.build_map --publish --version-id v3
```

If the database already has a published map, this re-exports it:

```
python -m pipeline.export_map
```

Check `map_info.map_version` to tell which map a copy of the file holds.
