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
| `release_date` | 0 | 0.0% |
| `release_year` | 0 | 0.0% |
| `description` | 120 | 0.1% |
| `long_description` | 197 | 0.2% |
| `developers` | 221 | 0.2% |
| `publishers` | 553 | 0.6% |
| `cover_image_url` | 0 | 0.0% |
| `store_url` | 0 | 0.0% |
| `playtime_hours` | 81,608 | 91.1% |
| `rating` | 0 | 0.0% |
| `rating_count` | 0 | 0.0% |
| `popularity` | 0 | 0.0% |

### Description sizes

| Column | Average | Longest |
|---|---|---|
| `description` | 195 chars | 342 chars |
| `long_description` | 1,283 chars | 67,520 chars |

This is why `/map` does not send `long_description`. At about 1,283 characters each, 89,618 of them would be roughly 115.0 MB in one response. It loads from `/games/{id}` when someone clicks a game instead.

## Possible duplicate titles

890 normalised titles show up more than once. These are listed for a human to look at and are **never** merged automatically, because remasters and regional releases are legitimately different games with the same name.

| Normalised title | Actual titles |
|---|---|
| `1` | +1% / ➕1️⃣ |
| `10 seconds` | 10 Seconds / 10 seconds |
| `100` | 100$ / €100 |
| `12 hours` | 12 HOURS / 12 Hours |
| `50 years` | 50 years / 50 Years |
| `a walk in the woods` | A Walk in the Woods / A Walk in the Woods |
| `abyss` | Abyss / Abyss / Abyss |
| `achievement clicker` | Achievement Clicker / Achievement Clicker |
| `achromatic` | Achromatic / Achromatic |
| `across` | Across / Across |
| `after` | AFTER / After |
| `after school` | After School / After School |
| `afterlife` | Afterlife / AFTERLIFE / Afterlife / Afterlife |
| `aftermath` | Aftermath / Aftermath |
| `again` | Again / Again? |
| `against all odds` | Against All Odds / Against All Odds / Against All Odds |
| `air` | AIR / Air |
| `air attack` | Air Attack / Air Attack |
| `airborne` | Airborne / AIRBORNE |
| `aleph` | Aleph / ALEPH |
| `alien` | Alien / Alien |
| `alien defense` | Alien Defense / Alien Defense |
| `alive` | Alive / ALIVE |
| `alma` | Alma / Alma |
| `alone` | ALONE / ALONE? / Alone / Alone / Alone / Alone / Alone / Alone |

## Feature coverage by category

`present` means we found at least one feature in that category. `absent` means the source gave us the data but nothing matched our current vocabulary. `unknown` means the source gave us nothing to go on.

A high `absent` count is not a bug, it means the alias list in `config/map_config.yaml` has room to grow.

| Category | Present | Absent | Unknown | Features defined |
|---|---|---|---|---|
| `genre` | 87,306 | 2,177 | 135 | 16 |
| `gameplay` | 37,135 | 35,611 | 16,872 | 16 |
| `mechanic` | 29,258 | 43,488 | 16,872 | 13 |
| `structure` | 26,530 | 46,216 | 16,872 | 9 |
| `theme` | 43,454 | 29,292 | 16,872 | 16 |
| `multiplayer` | 88,177 | 627 | 814 | 15 |
| `perspective` | 49,488 | 23,258 | 16,872 | 8 |
| `platform` | 89,618 | 0 | 0 | 3 |
| `tag` | 84,037 | 1,907 | 3,674 | 300 |

Total game-to-feature links: 1,207,429

## DATA 1 completeness

87,301 of 89,618 games (97.4%) have a title, a release year, at least one genre and at least three features. Our requirement is 95%.

## Most common unmapped tags

These tags had no alias, so they became display-only `tag` features with weight 0.0. Nothing was lost, the ML just does not use them.

**Austin and Kayne:** this is the to-do list. Add any of these to `aliases` in `config/map_config.yaml`, then re-run the import to turn them into weighted features.

| Tag | Games with it |
|---|---|
| Indie | 43,408 |
| Atmospheric | 13,780 |
| Colorful | 11,833 |
| Pixel Graphics | 11,815 |
| Cute | 10,607 |
| Early Access | 9,187 |
| Retro | 7,940 |
| Relaxing | 7,646 |
| Family Friendly | 7,589 |
| Female Protagonist | 6,474 |
| Controller | 6,191 |
| Stylized | 5,997 |
| Difficult | 5,580 |
| Cartoony | 5,127 |
| Realistic | 5,118 |
| Dark | 5,106 |
| Minimalist | 4,725 |
| Violent | 4,346 |
| Free to Play | 4,115 |
| Great Soundtrack | 3,897 |
| Hidden Object | 3,777 |
| Gore | 3,738 |
| Old School | 3,716 |
| Hand-drawn | 3,702 |
| Logic | 3,574 |
| Tactical | 3,422 |
| Shoot 'Em Up | 3,126 |
| Cartoon | 3,076 |
| Sexual Content | 2,938 |
| Drama | 2,773 |
