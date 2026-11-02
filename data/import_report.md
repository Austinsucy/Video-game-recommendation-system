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

Snapshot: `C:\Users\austi\Documents\VS Code Projects\CSCI-150-Project---Goon-Squad\data\raw\games_march2025_cleaned.csv`  
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
| `gameplay` | 815 | 185 | 0 | 16 |
| `mechanic` | 632 | 368 | 0 | 13 |
| `structure` | 638 | 362 | 0 | 9 |
| `theme` | 854 | 146 | 0 | 16 |
| `multiplayer` | 1,000 | 0 | 0 | 15 |
| `perspective` | 825 | 175 | 0 | 8 |
| `platform` | 1,000 | 0 | 0 | 3 |
| `tag` | 996 | 4 | 0 | 257 |

Total game-feature links: 20,707

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
| Cute | 125 |
| Female Protagonist | 121 |
| Sexual Content | 110 |
| Free to Play | 106 |
| Controller | 106 |
| Tactical | 98 |
| Family Friendly | 98 |
| Dark | 92 |
| Relaxing | 87 |
| Nudity | 70 |
| Replay Value | 68 |
| Stylized | 64 |
| Moddable | 61 |
| Mature | 58 |
| Team-Based | 56 |
| Cinematic | 56 |
| Cartoony | 51 |
| Drama | 49 |
| Emotional | 48 |
| Retro | 47 |
