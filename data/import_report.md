# Import report

## Selection

| Stage | Games |
|---|---|
| Rows in source file | 89,618 |
| After genre exclusions | 89,618 |
| With a parsable release year | 89,618 |
| After year filter (`popular_recent`) | 66,756 |
| With at least the minimum genres | 64,259 |
| With at least the minimum tags | 48,062 |
| **Eligible pool** | **48,062** |
| **Selected** | **1,000** |

Snapshot: `C:\Users\rjpab\Video-game-recommendation-system\data\raw\games_march2025_cleaned.csv`  
SHA-256: `04d8df2778aaa8f8b575934b7072d55224d37a2ded23e8261583f0fcf668dfab`

## Missing values

| Field | Missing | % |
|---|---|---|
| `release_year` | 0 | 0.0% |
| `description` | 0 | 0.0% |
| `cover_image_url` | 0 | 0.0% |
| `store_url` | 0 | 0.0% |
| `playtime_hours` | 338 | 33.8% |
| `rating` | 0 | 0.0% |
| `rating_count` | 0 | 0.0% |
| `popularity` | 0 | 0.0% |

## Duplicate candidates

0 normalised titles appear more than once. These are reported for review and are **not** merged automatically.

## Feature-category coverage

`absent` means the source supplied the field and nothing matched the current vocabulary. `unknown` means the source gave us nothing to judge on.

| Category | Present | Absent | Unknown | Features defined |
|---|---|---|---|---|
| `genre` | 1,000 | 0 | 0 | 16 |
| `gameplay` | 737 | 263 | 0 | 10 |
| `mechanic` | 549 | 451 | 0 | 10 |
| `structure` | 612 | 388 | 0 | 8 |
| `theme` | 800 | 200 | 0 | 12 |
| `multiplayer` | 1,000 | 0 | 0 | 14 |
| `perspective` | 825 | 175 | 0 | 8 |
| `platform` | 1,000 | 0 | 0 | 3 |
| `tag` | 1,000 | 0 | 0 | 321 |

Total game-feature links: 21,997

## DATA 1 completeness

1,000 of 1,000 games (100.0%) have a title, a release year, at least one genre and at least three features. Requirement is 95%.

## Most common unmapped tags

These fell through to the display-only `tag` category. Austin and Kayne: add any of these to `aliases` in `config/map_config.yaml` to turn them into weighted features, then re-run the import.

| Tag | Games |
|---|---|
| Indie | 390 |
| Atmospheric | 359 |
| Early Access | 197 |
| Great Soundtrack | 192 |
| Violent | 178 |
| Realistic | 161 |
| Gore | 155 |
| Colorful | 135 |
| Pixel Graphics | 134 |
| Difficult | 131 |
| Action RPG | 130 |
| Cute | 125 |
| PvE | 122 |
| Female Protagonist | 121 |
| Sexual Content | 110 |
| Free to Play | 106 |
| Controller | 106 |
| Tactical | 98 |
| Family Friendly | 98 |
| Hack and Slash | 96 |
| Dark | 92 |
| Resource Management | 88 |
| Relaxing | 87 |
| Immersive Sim | 78 |
| Rogue-lite | 75 |
| Nudity | 70 |
| Replay Value | 68 |
| Medieval | 67 |
| Souls-like | 66 |
| Stylized | 64 |
