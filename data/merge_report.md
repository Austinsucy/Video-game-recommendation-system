# Steam + IGDB merge report

Written by `python -m pipeline.ingest --reset` on the test/steam-plus-igdb branch.
The rules are in DATABASE.md and config/map_config.yaml (sources).

## Source files

| source | file | SHA-256 |
|---|---|---|
| steam | data/raw/games_march2025_cleaned.csv | 04d8df2778aaa8f8b575934b7072d55224d37a2ded23e8261583f0fcf668dfab |
| igdb | data/raw/game_dataset_cleaned.csv | 1e2e5b3d4e4857a044bbaaffaf088e0a056ca19c0e416e80d2c4551c71915a28 |

## Funnel per source

| step | steam | igdb |
|---|---|---|
| rows in file | 89,618 | 232,595 |
| dropped: no usable name |  | 6 |
| dropped: category (expanded_game) |  | expanded_game 1,543 |
| selected / cleaned | 89,618 | 231,046 |
| folded into another app of the same game | 32 |  |
| merged into a Steam game |  | 68,602 |
| kept separate: review (a person should look) |  | 1,946 |
| kept separate: new game |  | 160,498 |
| games written | 89,586 | 162,444 |

**Total games: 252,030.**

## Steam duplicate apps folded

26 groups, 58 apps. The app with the most reviews is the game; the others are extra steam rows in game_sources.

| game | kept app | other apps |
|---|---|---|
| Mahjong Quest Collection | 38010 | 38020 |
| Call of Duty®: Black Ops | 42700 | 42710 |
| Medal of Honor™ | 47790 | 47830 |
| Darksiders™ | 50620 | 50640 |
| Crysis 2 - Maximum Edition | 99830 | 108800 |
| Call of Duty®: Modern Warfare® 3 (2011) | 115300 | 42680 |
| Call of Duty®: Black Ops II | 202970 | 202990 |
| Call of Duty®: Ghosts | 209160 | 209170 |
| Call of Duty®: Advanced Warfare - Gold Edition | 209650 | 209660 |
| Gear Up | 214420 | 234040, 300600 |
| Ys I & II Chronicles+ | 223810 | 223870 |
| System Shock® 2 (Classic) | 238210 | 915100 |
| Wasteland 2: Director's Cut | 240760 | 404730 |
| Goodbye Deponia | 241910 | 371040 |
| In Verbis Virtus | 242840 | 307860 |
| Men of War: Assault Squad 2 | 244450 | 562040 |
| Ethan: Meteor Hunter | 266330 | 323950 |
| Meadowland | 320120 | 349890 |
| Krosmaster Arena | 329790 | 413730 |
| Call of Duty®: Black Ops III | 388520 | 311210 |
| Metro Exodus | 412020 | 1449560 |
| Call of Duty®: WWII | 476600 | 476620 |
| Oats Studios - Volume 1 Assets | 652150 | 652930 |
| Shadow of the Tomb Raider: Definitive Edition | 750920 | 849160, 849200, 890030, 905320 |
| Nautical Dispute | 2377910 | 2186000 |
| EA SPORTS FC™ 25 | 2669320 | 2898330, 2898350, 2898360 |

Same title but NOT folded (different date, company or description): 857 groups. First 25:

| title | app ids |
|---|---|
| 10 seconds | 852190, 3418430 |
| 100$ | 1016250, 1036910 |
| 12 HOURS | 1063560, 3218080 |
| 50 years | 502740, 516460 |
| A Walk in the Woods | 557900, 842420 |
| Abyss | 1633770, 2493960, 2786120 |
| Achievement Clicker | 743640, 1229730 |
| Achromatic | 926170, 1990210 |
| Across | 547740, 1518870 |
| After | 1589790, 1657210 |
| After School | 1604790, 2455940 |
| Afterlife | 557240, 1012370, 1619590, 2536750 |
| Aftermath | 1916830, 2621140 |
| Again? | 906850, 1009240 |
| Against All Odds | 1465560, 2016470, 2218890 |
| Air | 1144520, 2983250 |
| Air Attack | 1424900, 2227380 |
| AIRBORNE | 1949480, 2338070 |
| Aleph | 2387410, 2665180 |
| Alien | 2203780, 2588740 |
| Alien Defense | 981480, 1868840 |
| Aliens&Asteroids | 661030, 2909650 |
| ALIVE | 1269080, 2258350 |
| Alma | 749320, 1602190 |
| ALONE? | 514240, 837930, 871870, 1544540, 1640090, 1789460, 1975890, 2639140 |

## IGDB matching: what was decided and why

| decision | rule | IGDB games |
|---|---|---|
| merge | k_strict+same_year | 35,243 |
| merge | k_strict+same_year+company | 23,922 |
| merge | text_match | 4,747 |
| merge | k_strict+company | 4,568 |
| merge | k_compact+same_year+company | 84 |
| merge | k_roman+same_year+company | 28 |
| merge | k_compact+company | 8 |
| merge | k_roman+company | 2 |
| new | igdb_new | 152,079 |
| new | company_differs | 2,792 |
| new | not_on_pc | 2,260 |
| new | edition_key_only | 1,936 |
| new | descriptions_differ | 1,163 |
| new | lost_one_to_one | 268 |
| review | text | 1,306 |
| review | several_steam_games | 640 |

Low-confidence merges (description score under the separate_below threshold): **2,235**. All are in data/match_review.csv; first 20:

| IGDB title | year | Steam title | Steam year | score |
|---|---|---|---|---|
| Vampire: The Masquerade - Redemption | 2000 | Vampire: The Masquerade - Redemption | 2017 | 0.09 |
| Fallout: A Post Nuclear Role Playing Game | 1997 | Fallout: A Post Nuclear Role Playing Game | 2015 | 0.02 |
| Need for Speed: Hot Pursuit | 2010 | Need For Speed: Hot Pursuit | 2010 | 0.00 |
| L.A. Noire | 2011 | L.A. Noire | 2011 | 0.09 |
| Maniac Mansion | 1987 | Maniac Mansion | 2017 | 0.00 |
| Myst | 1993 | Myst | 2021 | 0.03 |
| Stonekeep | 1995 | Stonekeep | 2017 | 0.01 |
| Police Quest: SWAT 2 | 1998 | Police Quest: SWAT 2 | 2017 | 0.00 |
| Ragnarok Online | 2002 | Ragnarok Online | 2013 | 0.01 |
| The 7th Guest | 1993 | The 7th Guest | 2013 | 0.01 |
| Final Fantasy XIII-2 | 2011 | FINAL FANTASY® XIII-2 | 2014 | 0.02 |
| Heavy Rain | 2010 | Heavy Rain | 2020 | 0.07 |
| F.E.A.R. | 2005 | F.E.A.R. | 2010 | 0.04 |
| Far Cry 3 | 2012 | Far Cry 3 | 2012 | 0.06 |
| BioShock Infinite | 2013 | BioShock Infinite | 2013 | 0.00 |
| Marvel: Ultimate Alliance 2 | 2009 | Marvel: Ultimate Alliance 2 | 2016 | 0.08 |
| Close Combat | 1996 | Close Combat | 2024 | 0.06 |
| Company of Heroes | 2006 | Company of Heroes | 2006 | 0.06 |
| Ground Control II: Operation Exodus | 2004 | Ground Control II: Operation Exodus | 2015 | 0.02 |
| Mission Critical | 1995 | Mission Critical | 2019 | 0.06 |

data/match_review.csv lists **6,117** pairs (reviews, low-confidence merges and edition-key-only pairs). To settle one, add it to config/match_overrides.yaml.

Overrides applied: 0.

### What IGDB filled on merged Steam games (only empty columns)

| column | games |
|---|---|
| tags | 9906 |
| publishers | 142 |
| long_description | 69 |
| developers | 29 |
| description | 7 |

## Not games (is_non_game = 1, stay in the database, off the map)

188 titles: igdb 45, steam 143. The full list is in data/non_games.csv.

| pattern | titles |
|---|---|
| \bdemo\b | 81 |
| \b(open/closed/public/private)\s+(beta/alpha)\b | 25 |
| [\(\[]\s*(beta/alpha)\s*[\)\]] | 25 |
| [-:]\s*(beta/alpha)\s*$ | 20 |
| \bbenchmark\b | 11 |
| \b(beta/alpha)\s+(test/testing/build/version/branch/client/weekend)\b | 9 |
| (?-i:\bSDK\b) | 4 |
| friend'?s pass | 3 |
| \bsoundtracks?\b | 3 |
| \bart ?book\b | 2 |
| \btest server\b | 2 |
| \bstress test\b | 1 |
| \bearly access weekend\b | 1 |
| (?-i:\bOST\b) | 1 |

## Steam games with no tags: the rescue

16,872 Steam apps had no tags. Rescued games got IGDB features with source 'igdb', tag_source 'igdb' and raw_tags_kind 'presence'. raw_tags_json stays NULL: no vote counts were invented.

| group | games | most reviewed |
|---|---|---|
| duplicate app of another Steam game (folded) | 8 | Metro Exodus (app 1449560) (102,923); EA SPORTS FC 25 (app 2898330) (52,457); EA SPORTS FC 25 (app 2898360) (52,457); EA SPORTS FC 25 (app 2898350) (52,457); Men of War: Assault Squad 2 (app 562040) (33,595) |
| not a game, by name | 69 | It Takes Two Friend's Pass (173,876); Monster Hunter Wilds Beta test (95,095); Delta Force Alpha Test (89,868); Warhammer: Vermintide Versus - Open Beta (84,602); Age of Empires IV Technical Stress Test (58,146) |
| matched IGDB, 3+ IGDB tags | 4,548 | Overwatch 2 (333,200); Marvel Rivals (243,123); THE FINALS (221,252); Muck (173,736); Crab Game (152,589) |
| matched IGDB, 0 to 2 IGDB tags | 6,489 | Banana (87,399); VPet-Simulator (45,250); Trigger of Time (33,600); One-armed cook (27,374); College Kings - The Complete Season (9,216) |
| no IGDB match, has Steam genres and a description | 5,671 | eFootball (88,415); War of the Three Kingdoms (65,647); Combat Master: Season 3 (43,467); HoloCure - Save the Fans! (37,057); Pixel Gun 3D: PC Edition (36,589) |
| almost nothing to go on | 87 | Maid Coser Airi-chan (33,605); BlazBlue Entropy Effect Beta (24,412); Undisputed Online Beta (16,070); Riichi City × "Akagi: The Genius Who Descended into the Darkness" & "Ten: The Nice Guy on the Path of Tenhou" (3,189); VAIL Alpha (2,652) |

derived_text step: off (0 games got derived_text features).

## The finished database, per source

| primary_source | games |
|---|---|
| igdb | 162,444 |
| steam | 89,586 |

| tag_source | games |
|---|---|
| igdb | 144,962 |
| none | 34,346 |
| steam_votes | 72,722 |

| primary_source | is_non_game | is_adult | is_upcoming |
|---|---|---|---|
| igdb | 45 | 3,814 | 307 |
| steam | 143 | 5,726 | 0 |

| game_features.source | rows |
|---|---|
| igdb | 1,299,518 |
| steam | 1,206,788 |

| steam rows per game | games |
|---|---|
| 1 | 89,560 |
| 2 | 23 |
| 3 | 1 |
| 4 | 1 |
| 5 | 1 |

### DATA 1 (title, year, 1+ genre, 3+ features), split by source

| primary_source | tag_source | games | pass DATA 1 | % |
|---|---|---|---|---|
| igdb | igdb | 135,056 | 94,914 | 70.3 |
| igdb | none | 27,388 | 3,683 | 13.4 |
| steam | igdb | 9,906 | 9,687 | 97.8 |
| steam | none | 6,958 | 6,319 | 90.8 |
| steam | steam_votes | 72,722 | 71,530 | 98.4 |

### Missing values per source

| column | igdb missing | steam missing |
|---|---|---|
| release_date | 49,430 (30%) | 0 (0%) |
| description | 514 (0%) | 114 (0%) |
| long_description | 514 (0%) | 129 (0%) |
| developers | 88,736 (55%) | 191 (0%) |
| publishers | 91,122 (56%) | 411 (0%) |
| cover_image_url | 21,318 (13%) | 0 (0%) |
| header_image_url | 8,162 (5%) | 0 (0%) |
| store_url | 162,444 (100%) | 0 (0%) |
| playtime_hours | 162,444 (100%) | 81,582 (91%) |
| rating | 147,760 (91%) | 0 (0%) |
| rating_count | 162,444 (100%) | 0 (0%) |
| popularity | 162,444 (100%) | 0 (0%) |
| raw_tags_json | 162,444 (100%) | 16,864 (19%) |
| raw_igdb_json | 0 (0%) | 20,984 (23%) |
| platforms_raw | 35,475 (22%) | 0 (0%) |

### Feature coverage per source

| source | category | present | absent | unknown |
|---|---|---|---|---|
| igdb | gameplay | 8,117 | 109,744 | 44,583 |
| igdb | genre | 145,168 | 3,938 | 13,338 |
| igdb | mechanic | 3,924 | 113,937 | 44,583 |
| igdb | multiplayer | 100,878 | 53 | 61,513 |
| igdb | perspective | 69,542 | 53,543 | 39,359 |
| igdb | platform | 125,665 | 1,304 | 35,475 |
| igdb | structure | 7,826 | 110,035 | 44,583 |
| igdb | tag | 107,450 | 23,531 | 31,463 |
| igdb | theme | 43,937 | 73,924 | 44,583 |
| steam | gameplay | 37,755 | 42,556 | 9,275 |
| steam | genre | 87,540 | 1,922 | 124 |
| steam | mechanic | 29,558 | 50,753 | 9,275 |
| steam | multiplayer | 88,179 | 599 | 808 |
| steam | perspective | 57,480 | 22,991 | 9,115 |
| steam | platform | 89,586 | 0 | 0 |
| steam | structure | 27,243 | 53,068 | 9,275 |
| steam | tag | 85,278 | 2,071 | 2,237 |
| steam | theme | 46,485 | 33,826 | 9,275 |

## Titles shared by several games after the merge

10,186 title_search values are shared by 24,013 games; 6,271 of those groups mix a Steam and an IGDB game. Shared titles are allowed (remakes, unrelated games with one name); the search box should show the year and platform next to them. Largest 40:

| title_search | games | source:year |
|---|---|---|
| tetris | 30 | igdb:1989 igdb:2009 igdb:1985 igdb:1992 igdb:1994 igdb:1988 igdb:1985 igdb:2002 igdb:1988 igdb:1987 igdb:1988 igdb:1988 igdb:1988 igdb:1989 igdb:1991 igdb:1991 igdb:1990 igdb:2006 igdb:2014 igdb:? igdb:2004 igdb:1994 igdb:? igdb:2009 igdb:2008 igdb:2020 igdb:2003 igdb:2008 igdb:2008 igdb:2024 |
| escape | 26 | steam:2015 steam:2018 steam:2022 steam:2022 steam:2021 steam:2023 steam:2019 steam:2018 steam:2024 igdb:1978 igdb:2018 igdb:2018 igdb:1999 igdb:1982 igdb:1982 igdb:2013 igdb:? igdb:2015 igdb:2022 igdb:? igdb:2025 igdb:? igdb:2022 igdb:1982 igdb:? igdb:2025 |
| sudoku | 21 | steam:2025 igdb:2009 igdb:2010 igdb:2011 igdb:2008 igdb:? igdb:2008 igdb:2015 igdb:2008 igdb:2015 igdb:2006 igdb:? igdb:2007 igdb:2021 igdb:2019 igdb:2000 igdb:2006 igdb:2008 igdb:2023 igdb:2006 igdb:2008 |
| monopoly | 20 | igdb:1995 igdb:2008 igdb:2012 igdb:1993 igdb:2002 igdb:1997 igdb:1991 igdb:2017 igdb:1988 igdb:1993 igdb:1999 igdb:2010 igdb:1999 igdb:2019 igdb:2004 igdb:2009 igdb:2024 igdb:1984 igdb:2007 igdb:2010 |
| cube | 18 | steam:2024 steam:2024 steam:2019 steam:2020 steam:2021 steam:2022 igdb:2001 igdb:2007 igdb:? igdb:? igdb:2022 igdb:2022 igdb:2002 igdb:2023 igdb:1991 igdb:2024 igdb:2024 igdb:? |
| labyrinth | 17 | steam:2016 steam:2023 steam:2020 steam:2024 steam:2020 igdb:2016 igdb:2005 igdb:2020 igdb:1980 igdb:? igdb:2008 igdb:? igdb:? igdb:1982 igdb:2010 igdb:2024 igdb:2014 |
| pinball | 16 | steam:2017 steam:2020 igdb:2000 igdb:1981 igdb:2017 igdb:2017 igdb:1984 igdb:2000 igdb:1983 igdb:1983 igdb:1991 igdb:1999 igdb:1979 igdb:1983 igdb:1982 igdb:2005 |
| alone | 14 | steam:2021 steam:2016 steam:2018 steam:2018 steam:2021 steam:2021 steam:2023 steam:2022 igdb:2018 igdb:2021 igdb:? igdb:? igdb:2014 igdb:? |
| chess | 14 | steam:2023 steam:2024 steam:2017 steam:2020 igdb:2001 igdb:1981 igdb:1998 igdb:2020 igdb:1982 igdb:2021 igdb:1983 igdb:2001 igdb:? igdb:1992 |
| jeopardy | 14 | igdb:1998 igdb:2012 igdb:2003 igdb:2017 igdb:2010 igdb:1988 igdb:1998 igdb:1994 igdb:1997 igdb:2006 igdb:1991 igdb:1987 igdb:1993 igdb:1995 |
| solitaire | 14 | steam:2017 steam:2017 igdb:1992 igdb:2017 igdb:2009 igdb:? igdb:2013 igdb:1997 igdb:2009 igdb:? igdb:2004 igdb:2000 igdb:2022 igdb:2025 |
| 2048 | 13 | steam:2018 igdb:2014 igdb:2014 igdb:2014 igdb:2014 igdb:2021 igdb:2014 igdb:2021 igdb:2014 igdb:2021 igdb:2014 igdb:2014 igdb:2014 |
| hangman | 13 | steam:2024 steam:2019 steam:2024 igdb:1978 igdb:2017 igdb:1984 igdb:2018 igdb:1993 igdb:2018 igdb:? igdb:2010 igdb:2009 igdb:1978 |
| mahjong | 13 | steam:2017 steam:2017 steam:2024 igdb:2017 igdb:2017 igdb:2016 igdb:2010 igdb:2016 igdb:2009 igdb:2009 igdb:2011 igdb:? igdb:2023 |
| wheel of fortune | 13 | igdb:1989 igdb:2010 igdb:2003 igdb:1990 igdb:1988 igdb:2017 igdb:1987 igdb:1994 igdb:1997 igdb:1998 igdb:1997 igdb:2005 igdb:2010 |
| battleship | 12 | steam:2023 igdb:2012 igdb:2016 igdb:1991 igdb:2009 igdb:1997 igdb:2013 igdb:1999 igdb:1995 igdb:1993 igdb:? igdb:2024 |
| hide and seek | 12 | steam:2019 steam:2017 steam:2021 steam:2024 steam:2024 igdb:? igdb:2021 igdb:2024 igdb:2009 igdb:2024 igdb:2024 igdb:2020 |
| abyss | 11 | steam:2024 steam:2022 steam:2024 igdb:1984 igdb:1987 igdb:2012 igdb:? igdb:2023 igdb:2023 igdb:2024 igdb:2024 |
| baseball | 11 | igdb:1983 igdb:1977 igdb:1972 igdb:1971 igdb:1978 igdb:1981 igdb:1994 igdb:1982 igdb:1984 igdb:2011 igdb:2024 |
| invasion | 11 | steam:2016 steam:2023 steam:2018 steam:2020 steam:2019 igdb:1987 igdb:2015 igdb:2015 igdb:1972 igdb:2022 igdb:2024 |
| maze | 11 | steam:2021 steam:2024 steam:2020 steam:2019 steam:2023 igdb:1973 igdb:1984 igdb:2016 igdb:2022 igdb:2022 igdb:2023 |
| batman | 10 | igdb:1989 igdb:1986 igdb:1990 igdb:2013 igdb:1990 igdb:1989 igdb:1990 igdb:1990 igdb:? igdb:2010 |
| family feud | 10 | igdb:2010 igdb:1993 igdb:2020 igdb:1987 igdb:1991 igdb:2004 igdb:1994 igdb:1997 igdb:1999 igdb:2000 |
| gravity | 10 | steam:2020 steam:2024 steam:2023 steam:2023 igdb:1990 igdb:2016 igdb:2018 igdb:? igdb:? igdb:2023 |
| nightmare | 10 | steam:2022 igdb:1983 igdb:2016 igdb:? igdb:1983 igdb:2021 igdb:2021 igdb:2024 igdb:2020 igdb:2024 |
| othello | 10 | steam:2015 igdb:1986 igdb:2014 igdb:1981 igdb:1993 igdb:? igdb:1985 igdb:1985 igdb:1984 igdb:2022 |
| snake | 10 | steam:2020 igdb:1997 igdb:2008 igdb:2010 igdb:2021 igdb:2016 igdb:2023 igdb:2021 igdb:? igdb:1989 |
| the tower | 10 | steam:2022 steam:2018 steam:2025 igdb:2019 igdb:2018 igdb:? igdb:2021 igdb:2015 igdb:2022 igdb:2014 |
| asteroids | 9 | steam:2024 igdb:1979 igdb:1998 igdb:2020 igdb:? igdb:2013 igdb:2022 igdb:1982 igdb:1982 |
| aurora | 9 | steam:2020 steam:2020 steam:2023 steam:2018 steam:2018 igdb:2018 igdb:2020 igdb:? igdb:2020 |
| backgammon | 9 | steam:2017 igdb:1991 igdb:? igdb:1979 igdb:1999 igdb:2010 igdb:1982 igdb:1990 igdb:? |
| basketball | 9 | steam:2021 igdb:1980 igdb:1978 igdb:? igdb:1973 igdb:2018 igdb:1982 igdb:1982 igdb:1977 |
| echoes | 9 | steam:2015 steam:2021 steam:2023 steam:2024 steam:2024 steam:2024 igdb:2009 igdb:2024 igdb:2024 |
| equinox | 9 | steam:2021 steam:2022 steam:2022 igdb:1986 igdb:1993 igdb:2022 igdb:2022 igdb:? igdb:2025 |
| flappy bird | 9 | igdb:2013 igdb:2014 igdb:2019 igdb:2015 igdb:2014 igdb:2014 igdb:2022 igdb:2021 igdb:2024 |
| haunted house | 9 | steam:2024 steam:2023 igdb:1982 igdb:1972 igdb:2010 igdb:1980 igdb:2020 igdb:2006 igdb:? |
| jurassic park | 9 | igdb:1993 igdb:1993 igdb:1994 igdb:1993 igdb:1994 igdb:1993 igdb:1993 igdb:2010 igdb:1993 |
| pandora | 9 | steam:2023 steam:2023 steam:2023 steam:2023 igdb:1988 igdb:2023 igdb:2023 igdb:2023 igdb:2023 |
| popeye | 9 | igdb:1982 igdb:1994 igdb:? igdb:1981 igdb:2021 igdb:1983 igdb:? igdb:1985 igdb:1990 |
| sonic the hedgehog | 9 | igdb:1991 igdb:2008 igdb:2013 igdb:1991 igdb:2020 igdb:2021 igdb:2004 igdb:2023 igdb:? |

## Alias coverage of IGDB fields

Share of values that reach a weighted feature. 'Indie' is demoted to a tag on purpose and left out of the share. The import refuses to run below min_alias_coverage for the gated fields.

| field | values | demoted | mapped | share |
|---|---|---|---|---|
| genres | 422,222 | 99,322 | 320,027 | 99.1% |
| themes | 206,335 | 0 | 176,745 | 85.7% |
| player_perspectives | 104,546 | 0 | 103,681 | 99.2% |
| game_modes | 201,271 | 0 | 200,684 | 99.7% |
| keywords | 475,267 | 0 | 67,290 | 14.2% |

### Most common unmapped IGDB values (Austin's to-do list)

- **genres**: Tactical (2,679), MOBA (194)
- **themes**: Erotic (7,208), Kids (5,257), Educational (4,934), Drama (3,417), Party (3,222), Business (1,740), Thriller (1,661), Non-fiction (1,636), 4X (explore, expand, exploit, and exterminate) (515)
- **player_perspectives**: Auditory (865)
- **game_modes**: Battle Royale (587)
- **keywords**: digital distribution (8,146), nudity (4,607), sexual content (4,604), steam (3,890), female protagonist (3,816), licensed game (3,516), steam achievements (2,630), pixel art (2,469), free-to-play (2,437), fangame (2,425), polygonal 3d (2,390), achievements (2,210), adult (2,168), shoot 'em up (2,093), retro (1,953), male protagonist (1,911), high score (1,864), boss fight (1,863), unofficial (1,847), cute (1,825)
