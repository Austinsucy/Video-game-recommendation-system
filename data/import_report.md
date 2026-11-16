# Import report

## Where each column came from

Generated from `fields.column_sources` in `config/map_config.yaml`, so it always matches what the import actually did.

| Database column | Source CSV column | Conversion | Notes |
|---|---|---|---|
| `title` | `name` | `clean_display_title` | Shown on screen as Steam spells it, minus the trademark signs (TM, R, C, SM) and doubled spaces. The untouched name is kept in game_sources.title_in_source. |
| `title_search` | `name` | `normalise_title` | Lowercased, punctuation stripped. What we actually search on. |
| `release_date` | `release_date` | `iso_date` | Full date as YYYY-MM-DD, for the info panel. Always present in our data. |
| `release_year` | `release_date` | `year_from_date` | Same source as release_date, kept separately so filtering by year does not mean parsing 89,618 strings every import. |
| `description` | `short_description` | `clean_html_text` | Steam's one or two sentence blurb. Max ~342 characters. |
| `long_description` | `about_the_game` (falls back to `detailed_description`) | `clean_html_text` | Full 'About This Game' text, ~1,400 chars average. Detail view only. |
| `developers` | `developers` | `join_list` | Studio name(s), comma-joined. Missing for a small number of games. |
| `publishers` | `publishers` | `join_list` | Publisher name(s), comma-joined. Missing more often than developers. |
| `cover_image_url` | `header_image` | none | Steam's banner image. Always present in our data. |
| `header_image_url` | `header_image` | none | The wide banner image. For Steam it is the same picture as cover_image_url. It is its own column because IGDB's cover is a tall box-art picture, so IGDB games need a different image here. |
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
| After the year filter (`all`) | 89,618 |
| With at least the minimum genres | 89,618 |
| With at least the minimum tags | 89,618 |
| **Eligible to pick from** | **89,618** |
| **Actually imported** | **89,618** |

Source file: `data/raw/games_march2025_cleaned.csv`  
SHA-256: `04d8df2778aaa8f8b575934b7072d55224d37a2ded23e8261583f0fcf668dfab`

The hash is how we prove two people imported the exact same file.

## Missing values

How many games have nothing in each optional column.

| Column | Missing | % |
|---|---|---|
| `release_date` | 49,430 | 19.6% |
| `release_year` | 49,430 | 19.6% |
| `description` | 628 | 0.2% |
| `long_description` | 643 | 0.3% |
| `developers` | 88,927 | 35.3% |
| `publishers` | 91,533 | 36.3% |
| `cover_image_url` | 21,318 | 8.5% |
| `store_url` | 162,444 | 64.5% |
| `playtime_hours` | 244,026 | 96.8% |
| `rating` | 147,760 | 58.6% |
| `rating_count` | 162,444 | 64.5% |
| `popularity` | 162,444 | 64.5% |

### Description sizes

| Column | Average | Longest |
|---|---|---|
| `description` | 197 chars | 352 chars |
| `long_description` | 641 chars | 67,520 chars |

This is why `/map` does not send `long_description`. At about 641 characters each, 252,030 of them would be roughly 161.6 MB in one response. It loads from `/games/{id}` when someone clicks a game instead.

## Possible duplicate titles

10186 normalised titles show up more than once. These are listed for a human to look at and are **never** merged automatically, because remasters and regional releases are legitimately different games with the same name.

| Normalised title | Actual titles |
|---|---|
| `1` | +1% / ➕1️⃣ / +1% |
| `1 vs 100` | 1 vs. 100 / 1 vs. 100 |
| `10` | =10 / 10 / 10 |
| `10 pin bowling` | 10-Pin Bowling / 10-Pin Bowling |
| `10 seconds` | 10 Seconds / 10 seconds |
| `100` | 100$ / €100 / %100 / 100! / 100$ |
| `100 in 1 game collection` | 100 in 1 Game Collection / 100-in-1 Game Collection |
| `100 trials` | 100 Trials / 100 Trials |
| `1000` | 1000 / 1000$ |
| `1000 words` | 1000 Words / 1000 Words / 1000 Words |
| `1010` | 1010 / 1010! |
| `11 45 a vivid life` | 11:45 A Vivid Life / 11.45 A Vivid Life |
| `12 hours` | 12 HOURS / 12 Hours |
| `15 in 1 solitaire` | 15 in 1 Solitaire / 15 in 1 Solitaire |
| `15 minutes` | 15 Minutes / 15 Minutes |
| `15 puzzle` | 15 puzzle / 15 Puzzle / 15 Puzzle / 15 Puzzle / 15 Puzzle |
| `16 shot shooting watch` | 16 Shot! Shooting Watch / 16 Shot! Shooting Watch |
| `16 tiles mahjong` | 16 Tiles Mahjong / 16 Tiles Mahjong |
| `180 darts` | 180 Darts / 180! Darts |
| `1990` | 1990 / 1990 |
| `1993 space machine` | 1993 Space Machine / 1993 Space Machine |
| `2 planets fire and ice` | 2 Planets Fire and Ice / 2 Planets Fire and Ice |
| `2048` | 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048 / 2048+# |
| `2089 space divided` | 2089 - Space Divided / 2089: Space Divided |
| `21` | 21+ / 21 |

## Feature coverage by category

`present` means we found at least one feature in that category. `absent` means the source gave us the data but nothing matched our current vocabulary. `unknown` means the source gave us nothing to go on.

A high `absent` count is not a bug, it means the alias list in `config/map_config.yaml` has room to grow.

| Category | Present | Absent | Unknown | Features defined |
|---|---|---|---|---|
| `genre` | 232,708 | 5,860 | 13,462 | 19 |
| `gameplay` | 45,872 | 152,300 | 53,858 | 16 |
| `mechanic` | 33,482 | 164,690 | 53,858 | 13 |
| `structure` | 35,069 | 163,103 | 53,858 | 9 |
| `theme` | 90,422 | 107,750 | 53,858 | 16 |
| `multiplayer` | 189,057 | 652 | 62,321 | 15 |
| `perspective` | 127,022 | 76,534 | 48,474 | 9 |
| `platform` | 215,251 | 1,304 | 35,475 | 15 |
| `tag` | 192,728 | 25,602 | 33,700 | 5,411 |

Total game-to-feature links: 2,506,306

## DATA 1 completeness

186,133 of 252,030 games (73.9%) have a title, a release year, at least one genre and at least three features. Our requirement is 95%.

## Most common unmapped tags

These tags had no alias, so they became display-only `tag` features with weight 0.0. Nothing was lost, the ML just does not use them.

**Austin and Kayne:** this is the to-do list. Add any of these to `aliases` in `config/map_config.yaml`, then re-run the import to turn them into weighted features.

| Tag | Games with it |
|---|---|
| Indie | 43,401 |
| Atmospheric | 13,770 |
| Colorful | 11,833 |
| Pixel Graphics | 11,813 |
| Cute | 10,607 |
| Early Access | 9,187 |
| Retro | 7,937 |
| Relaxing | 7,646 |
| Family Friendly | 7,588 |
| Female Protagonist | 6,469 |
| Controller | 6,185 |
| Stylized | 5,997 |
| Difficult | 5,577 |
| Cartoony | 5,127 |
| Realistic | 5,117 |
| Dark | 5,102 |
| Minimalist | 4,725 |
| Violent | 4,340 |
| Free to Play | 4,112 |
| Great Soundtrack | 3,886 |
| Hidden Object | 3,777 |
| Gore | 3,729 |
| Old School | 3,715 |
| Hand-drawn | 3,701 |
| Logic | 3,574 |
| Tactical | 3,420 |
| Shoot 'Em Up | 3,126 |
| Cartoon | 3,076 |
| Sexual Content | 2,938 |
| Drama | 2,773 |
