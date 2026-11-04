# Import report

## Where each column came from

Generated from `fields.column_sources` in `config/map_config.yaml`, so it always matches what the import actually did.

| Database column | Source CSV column | Conversion | Notes |
|---|---|---|---|
| `title` | `name` | `clean_text` | Shown on screen exactly as Steam spells it. |
| `title_search` | `name` | `normalise_title` | Lowercased, punctuation stripped. What we actually search on. |
| `release_date` | `release_date` | `iso_date` | Full date as YYYY-MM-DD, for the info panel. Always present in our data. |
| `release_year` | `release_date` | `year_from_date` | Same source as release_date, kept separately so filtering by year does not mean parsing 89,618 strings every import. |
| `description` | `short_description` | `clean_text` | Steam's one or two sentence blurb. Max ~342 characters. |
| `long_description` | `about_the_game` (falls back to `detailed_description`) | `clean_text` | Full 'About This Game' text, ~1,400 chars average. Detail view only. |
| `developers` | `developers` | `join_list` | Studio name(s), comma-joined. Missing for a small number of games. |
| `publishers` | `publishers` | `join_list` | Publisher name(s), comma-joined. Missing more often than developers. |
| `cover_image_url` | `header_image` | none | Steam's banner image. Always present in our data. |
| `store_url` | `appid` | `store_url_template` | Built from the app id, not stored in the CSV directly. |
| `playtime_hours` | `average_playtime_forever` | `minutes_to_hours` | Steam's lifetime average playtime, in MINUTES in the source. This is an average over players Steam has data for, not a how-long-to-beat figure. Missing for about a third of games. |
| `rating` | `pct_pos_total` | none | Percentage of reviews that are positive, 0 to 100. We use this instead of metacritic_score (missing for 96% of games) or user_score (missing for 99.96%). |
| `rating_count` | `num_reviews_total` | none | How many reviews that percentage is based on. |
| `popularity` | `num_reviews_total` | none | Deliberately the same source as rating_count. Review count was the only fully populated numeric signal. Swap to peak_ccu if we want popularity to mean something different from review volume. |
| `raw_tags_json` | `tags` | `json_dump` | The untouched tag object from Steam, including vote counts. Kept because game_features loses the counts, and our import rules say to preserve the raw tags. |

`game_id` is ours, counted from 1. The Steam app id is kept in `game_sources.external_id`.

Features come from four places: the `genres` column, the `categories` column, the three platform booleans, and the `tags` object. All four end up in `game_features`.

## How we got from 89,618 games to the final set

| Stage | Games left |
|---|---|
| Rows in the source file | 89,618 |
| After dropping excluded genres | 89,618 |
| With a readable release year | 89,618 |
| After the year filter (`popular_recent`) | 66,756 |
| With at least the minimum genres | 64,259 |
| With at least the minimum tags | 48,062 |
| **Eligible to pick from** | **48,062** |
| **Actually imported** | **1,000** |

Source file: `data/raw/games_march2025_cleaned.csv`  
SHA-256: `04d8df2778aaa8f8b575934b7072d55224d37a2ded23e8261583f0fcf668dfab`

The hash is how we prove two people imported the exact same file.

## Missing values

How many games have nothing in each optional column.

| Column | Missing | % |
|---|---|---|
| `release_date` | 0 | 0.0% |
| `release_year` | 0 | 0.0% |
| `description` | 0 | 0.0% |
| `long_description` | 4 | 0.4% |
| `developers` | 0 | 0.0% |
| `publishers` | 3 | 0.3% |
| `cover_image_url` | 0 | 0.0% |
| `store_url` | 0 | 0.0% |
| `playtime_hours` | 338 | 33.8% |
| `rating` | 0 | 0.0% |
| `rating_count` | 0 | 0.0% |
| `popularity` | 0 | 0.0% |

### Description sizes

| Column | Average | Longest |
|---|---|---|
| `description` | 221 chars | 339 chars |
| `long_description` | 1,962 chars | 10,520 chars |

This is why `/map` does not send `long_description`. At about 1,962 characters each, 1,000 of them would be roughly 2.0 MB in one response. It loads from `/games/{id}` when someone clicks a game instead.

## Possible duplicate titles

0 normalised titles show up more than once. These are listed for a human to look at and are **never** merged automatically, because remasters and regional releases are legitimately different games with the same name.

## Feature coverage by category

`present` means we found at least one feature in that category. `absent` means the source gave us the data but nothing matched our current vocabulary. `unknown` means the source gave us nothing to go on.

A high `absent` count is not a bug, it means the alias list in `config/map_config.yaml` has room to grow.

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

Total game-to-feature links: 20,707

## DATA 1 completeness

1,000 of 1,000 games (100.0%) have a title, a release year, at least one genre and at least three features. Our requirement is 95%.

## Most common unmapped tags

These tags had no alias, so they became display-only `tag` features with weight 0.0. Nothing was lost, the ML just does not use them.

**Austin and Kayne:** this is the to-do list. Add any of these to `aliases` in `config/map_config.yaml`, then re-run the import to turn them into weighted features.

| Tag | Games with it |
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
