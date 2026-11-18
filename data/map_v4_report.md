# Map v4 build report

Built by `python -m pipeline.build_map_v4`. Map v3 is kept as published; the reasons for every step are in docs/map-v4.md.

| | |
|---|---|
| v3 games kept (same x, y, cluster) | 72,722 |
| v3 games dropped (folded duplicate apps, no games row) | 24 |
| Steam games with votes not on v3 | 0 |
| translator training games | 57,563 (2,263 feature columns) |
| games without votes | 179,308 |
| ... nothing to translate | 106 |
| ... on the map (gate) | 147,340 (IGDB 130,708, Steam 16,632) |
| ... left off: not a game / under 3 features / no description | 114 / 31,530 / 510 |
| total map games | 220,062 |
| neighbour rows | 3,300,930 |
| confidence of map games (10th / median / 90th pct) | {10: 0.738, 50: 0.822, 90: 0.888} |
| busiest v3 game as a #1 recommendation | 455 new games |
| v3 games used as a recommendation | 89.6% |
| colour matches the 15 v3 points around it | 84.9% (v3 games: 77.0%) |
| stranded more than 50 units from any v3 game | 0.00% |
| within 0.2 units of another point | 5.28% |
| top-5 recommendations within 25 units | 55.3% |
| build time | 731 s |
| fingerprint (two builds must match) | `1048cab09541506a` |

Dropped v3 game ids (each was a duplicate Steam app, now folded into another game): 121, 307, 308, 309, 310, 581, 782, 822, 1107, 1261, 1366, 1529, 1598, 1599, 1653, 2015, 2061, 3698, 4353, 5030, 25173, 25321, 69278, 73622
