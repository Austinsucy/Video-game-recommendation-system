"""
Unit tests for the Steam + IGDB matching rules (pipeline/cleaning.py and
pipeline/matching.py).

Every case here is a real pair from the two datasets that a simpler rule got
wrong, or that is easy to get wrong. They run on tiny made-up tables, so they
need no download and take well under a second.
"""
import pandas as pd
import pytest

from pipeline.cleaning import (
    clean_display_title,
    clean_html_text,
    clean_list,
    company_keys,
    company_pattern,
    edition_pattern,
    key_compact,
    key_edition,
    key_roman,
    key_strict,
    non_game_match,
    compile_patterns,
    short_summary,
)
from pipeline.config import load_config
from pipeline.matching import MatchSettings, fold_steam_duplicates, match_igdb

CFG = load_config()
IGDB_CFG = CFG["sources"]["igdb"]
COMPANIES = company_pattern(IGDB_CFG["matching"]["company_suffixes"])
EDITIONS = edition_pattern(IGDB_CFG["matching"]["edition_words"])
SETTINGS = MatchSettings.from_config(IGDB_CFG)


def _keys(frame):
    frame["k_strict"] = frame["title"].map(key_strict)
    frame["k_roman"] = frame["title"].map(key_roman)
    frame["k_compact"] = frame["title"].map(key_compact)
    frame["k_edition"] = frame["title"].map(lambda t: key_edition(t, EDITIONS))
    return frame


def steam(*games):
    """games: (appid, title, year, [companies], description)"""
    frame = pd.DataFrame([{
        "game_id": g[0], "appid": g[0], "title": g[1], "year": g[2],
        "companies": company_keys(g[3], COMPANIES), "desc": g[4] if len(g) > 4 else None,
    } for g in games])
    return _keys(frame)


def igdb(*games):
    """games: (igdb_id, title, year, [companies], [platforms], description, category)"""
    frame = pd.DataFrame([{
        "igdb_id": g[0], "title": g[1], "year": g[2],
        "companies": company_keys(g[3], COMPANIES),
        "platforms": frozenset(g[4] if len(g) > 4 else ["PC (Microsoft Windows)"]),
        "desc": g[5] if len(g) > 5 else None,
        "category": g[6] if len(g) > 6 else "main_game",
    } for g in games])
    return _keys(frame)


def decide(steam_frame, igdb_frame, overrides=None, appid_to_game=None):
    out = match_igdb(steam_frame, igdb_frame, SETTINGS, overrides, appid_to_game)
    return {row.igdb_id: (row.decision, row.game_id) for row in out.itertuples()}


# ---------------------------------------------------------------------------
# Matching keys
# ---------------------------------------------------------------------------

def test_accents_do_not_split_a_game():
    assert key_strict("Brütal Legend") == key_strict("Brutal Legend")


def test_curly_apostrophes_and_trademarks_do_not_split_a_game():
    assert key_strict("Assassin’s Creed® II") == key_strict("Assassin's Creed II")


def test_compact_key_joins_mdk2_and_mdk_2():
    assert key_strict("MDK2") != key_strict("MDK 2")
    assert key_compact("MDK2") == key_compact("MDK 2")


def test_roman_numerals_become_digits_but_not_i_or_v():
    assert key_roman("Assassin's Creed II") == key_roman("Assassin's Creed 2")
    assert key_roman("V Rising") == "v rising"
    assert key_roman("I Am Bread") == "i am bread"


def test_the_is_kept_in_the_strict_key():
    """SiN (1998) and The Sin are different games."""
    assert key_strict("SiN") != key_strict("The Sin")
    assert key_compact("SiN") != key_compact("The Sin")


def test_edition_key_drops_edition_words():
    assert key_edition("Mafia II: Definitive Edition", EDITIONS) == key_edition("Mafia II", EDITIONS)


def test_company_suffixes_are_ignored():
    a = company_keys(["Bethesda Game Studios"], COMPANIES)
    b = company_keys(["Bethesda Softworks LLC"], COMPANIES)
    from pipeline.cleaning import companies_overlap
    assert companies_overlap(a, b) is True
    assert companies_overlap(a, frozenset()) is None


# ---------------------------------------------------------------------------
# Cleaning values we store
# ---------------------------------------------------------------------------

def test_display_title_loses_only_trademark_signs():
    assert clean_display_title("EA SPORTS FC™  25") == "EA SPORTS FC 25"
    assert clean_display_title("Brütal Legend") == "Brütal Legend"


def test_html_entities_are_decoded():
    assert clean_html_text("Rock &amp; Roll <b>Racing</b>") == "Rock & Roll Racing"


def test_list_items_split_inside_brackets_are_glued_back():
    raw = "['Action', '4X (explore', 'expand', 'exploit', 'and exterminate)', 'Action']"
    assert clean_list(raw) == ["Action", "4X (explore, expand, exploit, and exterminate)"]


def test_lone_company_suffix_is_glued_back():
    assert clean_list("['Studio X', 'LLC', 'Missing']", ("LLC",)) == ["Studio X, LLC"]


def test_short_summary_cuts_at_a_sentence_end():
    text = ("This is the first sentence of a fairly long summary. " * 8).strip()
    short = short_summary(text, limit=350)
    assert len(short) <= 350 and short.endswith(".")


def test_tiny_summaries_become_null():
    assert short_summary("Fishing") is None


def test_non_game_patterns():
    patterns = compile_patterns(CFG["non_game_patterns"])
    assert non_game_match("Half-Life 2: Deathmatch Dedicated Server", patterns)
    assert non_game_match("Celeste Soundtrack", patterns)
    assert non_game_match("Marvel Rivals Playtest", patterns)
    assert non_game_match("Alpha Protocol", patterns) is None
    assert non_game_match("Sid Meier's Alpha Centauri", patterns) is None
    assert non_game_match("Demon's Souls", patterns) is None


# ---------------------------------------------------------------------------
# The match rules, on real cases
# ---------------------------------------------------------------------------

def test_brutal_legend_merges():
    s = steam((225260, "Brütal Legend", 2013, ["Double Fine Productions"]))
    i = igdb((1, "Brutal Legend", 2009, ["Double Fine Productions"]))
    assert decide(s, i)[1] == ("merge", 225260)


def test_mdk2_merges_with_mdk_2():
    s = steam((10, "MDK 2", 2000, ["BioWare"]))
    i = igdb((2, "MDK2", 2000, ["BioWare"]))
    assert decide(s, i)[2] == ("merge", 10)


def test_assassins_creed_ii_merges_with_2():
    s = steam((33230, "Assassin's Creed® 2", 2010, ["Ubisoft Montreal"]))
    i = igdb((3, "Assassin's Creed II", 2009, ["Ubisoft Montreal"]))
    assert decide(s, i)[3] == ("merge", 33230)


def test_fallout_1997_merges_with_its_2015_steam_release():
    """Same company, different year: a PC re-release, the same game."""
    s = steam((38400, "Fallout", 2015, ["Interplay Productions"]))
    i = igdb((4, "Fallout", 1997, ["Interplay Productions", "Black Isle Studios"]))
    assert decide(s, i)[4] == ("merge", 38400)


def test_system_shock_1994_is_not_the_2023_remake():
    s = steam((482400, "System Shock", 2023, ["Nightdive Studios", "Prime Matter"]))
    i = igdb((5, "System Shock", 1994, ["Looking Glass Technologies", "Origin Systems"]))
    assert decide(s, i)[5][0] == "new"


def test_modern_warfare_2_and_ii_stay_apart():
    s = steam(
        (10180, "Call of Duty: Modern Warfare 2", 2009, ["Infinity Ward", "Activision"]),
        (1938090, "Call of Duty: Modern Warfare II", 2022, ["Infinity Ward", "Activision"]),
    )
    i = igdb(
        (6, "Call of Duty: Modern Warfare 2", 2009, ["Infinity Ward", "Activision"]),
        (7, "Call of Duty: Modern Warfare II", 2022, ["Infinity Ward", "Activision"]),
    )
    got = decide(s, i)
    assert got[6] == ("merge", 10180)
    assert got[7] == ("merge", 1938090)

    # And with only the 2022 game on Steam, the 2009 game must NOT grab it,
    # even though the roman key and the company agree.
    only_new = s[s["appid"] == 1938090]
    assert decide(only_new, i.iloc[:1])[6][0] != "merge"


def test_sin_is_not_the_sin():
    s = steam((1300, "SiN", 1998, ["Ritual Entertainment"]))
    i = igdb((8, "The Sin", 2015, []))
    assert decide(s, i)[8][0] == "new"


def test_mafia_ii_is_not_its_definitive_edition():
    s = steam((1030830, "Mafia II: Definitive Edition", 2020, ["Hangar 13"]))
    i = igdb((9, "Mafia II", 2010, ["2K Czech"]))
    assert decide(s, i)[9][0] == "new"


def test_pc_engine_games_never_count_as_pc():
    s = steam((20, "Bonk's Adventure", 2015, []))
    i = igdb((10, "Bonk's Adventure", 2015, [], ["TurboGrafx-16/PC Engine"]))
    assert decide(s, i)[10][0] == "new"


def test_one_steam_game_never_gets_two_merges():
    s = steam((30, "Tomb Raider", 2013, ["Crystal Dynamics"]))
    i = igdb(
        (11, "Tomb Raider", 2013, ["Crystal Dynamics"], ["PC (Microsoft Windows)"], None, "main_game"),
        (12, "Tomb Raider", 2013, ["Crystal Dynamics"], ["PC (Microsoft Windows)"], None, "remaster"),
    )
    got = decide(s, i)
    merges = [k for k, v in got.items() if v[0] == "merge"]
    assert merges == [11]


def test_descriptions_decide_when_nothing_else_does():
    s = steam((40, "Echo", 2017, [], "A stealth game in a palace that learns from you and copies your moves."))
    same = igdb((13, "Echo", 2018, [], ["PC (Microsoft Windows)"],
                 "A stealth game set in a palace that learns from you and copies your moves."))
    other = igdb((14, "Echo", 2001, [], ["PC (Microsoft Windows)"],
                  "Racing cars through neon tunnels while dodging trucks at night."))
    # min_df=2 needs the shared words to appear twice, which these pairs do.
    assert decide(s, same)[13][0] == "merge"
    assert decide(s, other)[14][0] == "new"


def test_no_description_goes_to_review():
    s = steam((50, "Orbit", 2016, []))
    i = igdb((15, "Orbit", 2012, []))
    assert decide(s, i)[15][0] == "review"


def test_overrides_win():
    s = steam((60, "Lone Game", 2016, ["Studio"]),
              (61, "Something Else", 2016, ["Other"]))
    i = igdb((16, "Lone Game", 2016, ["Studio"]),
             (17, "Totally Different Name", 2001, []))
    overrides = [
        {"igdb_id": 16, "steam_appid": 60, "verdict": "different"},
        {"igdb_id": 17, "steam_appid": 61, "verdict": "same"},
    ]
    got = decide(s, i, overrides, {60: 60, 61: 61})
    assert got[16][0] == "new"
    assert got[17] == ("merge", 61)


def test_matching_is_deterministic():
    s = steam((70, "Twin", 2010, ["A"]), (71, "Twin", 2010, ["A"]))
    i = igdb((18, "Twin", 2010, ["A"]))
    assert decide(s, i) == decide(s.iloc[::-1].reset_index(drop=True), i)


# ---------------------------------------------------------------------------
# Folding Steam's own duplicate apps
# ---------------------------------------------------------------------------

def _fold_frame(rows):
    frame = pd.DataFrame([{
        "appid": r[0], "title": r[1], "release_date": r[2],
        "companies": company_keys(r[3], COMPANIES), "desc": r[4], "reviews": r[5],
    } for r in rows])
    frame["k_strict"] = frame["title"].map(key_strict)
    return frame


def test_fold_keeps_the_most_reviewed_app_and_lists_the_rest():
    frame = _fold_frame([
        (412020, "Metro Exodus", "2019-02-14", ["4A Games", "Deep Silver"], "Same blurb.", 100000),
        (1449560, "Metro Exodus", "2019-02-14", ["4A Games", "Deep Silver"], "Same blurb.", 50),
    ])
    fold = fold_steam_duplicates(frame)
    assert fold.groups == {412020: [412020, 1449560]}
    assert fold.kept_for[1449560] == 412020


def test_same_title_with_a_different_date_is_not_folded():
    frame = _fold_frame([
        (1, "Doom", "1993-12-10", ["id Software"], "Demons.", 10),
        (2, "Doom", "2016-05-12", ["id Software"], "Demons.", 20),
    ])
    fold = fold_steam_duplicates(frame)
    assert fold.groups == {}
    assert fold.not_folded == [[1, 2]]


def test_fold_ties_go_to_the_lowest_app_id():
    frame = _fold_frame([
        (9, "Twin", "2020-01-01", ["Twin Makers"], "Blurb.", 5),
        (3, "Twin", "2020-01-01", ["Twin Makers"], "Blurb.", 5),
    ])
    assert list(fold_steam_duplicates(frame).groups) == [3]


@pytest.mark.parametrize("platform", ["PC Engine SuperGrafx", "PC-FX", "Turbografx-16/PC Engine CD"])
def test_no_pc_engine_platform_is_in_the_pc_list(platform):
    assert platform not in IGDB_CFG["pc_platforms"]
