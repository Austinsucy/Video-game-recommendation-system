"""
Deciding which games are the same game.

Two jobs, both run during the import before anything is written:

  1. fold_steam_duplicates
     Steam sometimes sells one game under several app ids (EA SPORTS FC 25 has
     four, Shadow of the Tomb Raider five). We fold those into one game.

  2. match_igdb
     For every IGDB game, decide whether it is a Steam game we already have
     (MERGE), a game we do not have (NEW), or unclear (REVIEW, which is kept
     separate until a person decides in config/match_overrides.yaml).

The rules are written out in map_config.yaml (sources.igdb.matching) and in
DATABASE.md. In one sentence: a title match is not enough on its own, there
also has to be a second piece of evidence (the same year, a shared company,
or matching descriptions), and anything that contradicts the match (different
companies, not on PC) wins over it.

Everything here is deterministic. Ties are always broken by an id, never by
whatever order a dictionary happened to be in, so REL 2 holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from pipeline.cleaning import companies_overlap

# The keys we try, strongest first. The first key that finds any Steam game
# is the one we decide on; weaker keys are never tried after that. That is
# what keeps "Modern Warfare 2" (2009) from also grabbing "Modern Warfare II"
# (2022): the strict key already found the 2009 game.
KEYS = ("k_strict", "k_roman", "k_compact", "k_edition")


# ===========================================================================
# PART 1: Steam's own duplicate apps
# ===========================================================================

@dataclass
class FoldResult:
    kept_for: dict[int, int] = field(default_factory=dict)      # appid -> appid of the game it belongs to
    groups: dict[int, list[int]] = field(default_factory=dict)  # kept appid -> every appid in the group
    not_folded: list[list[int]] = field(default_factory=list)   # same title, but not the same game


def fold_steam_duplicates(steam: pd.DataFrame) -> FoldResult:
    """Find Steam apps that are really one game.

    `steam` needs: appid, k_strict, release_date, companies, desc, reviews.

    Two apps are the same game only when ALL FOUR agree: the strict title
    key, the exact release date, at least one company, and the exact same
    short description. That is strict on purpose. A same-title game with a
    different date or company is a different game (a remake, or an unrelated
    game with the same name), so it is listed instead of folded.
    """
    result = FoldResult()
    for _key, group in steam.groupby("k_strict", sort=True):
        if len(group) < 2:
            continue
        rows = group.sort_values("appid").to_dict("records")

        # Tiny union-find: link every pair that meets all four rules.
        parent = {r["appid"]: r["appid"] for r in rows}

        def root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if (
                    a["release_date"] and a["release_date"] == b["release_date"]
                    and a["desc"] and a["desc"] == b["desc"]
                    and companies_overlap(a["companies"], b["companies"]) is True
                ):
                    parent[root(b["appid"])] = root(a["appid"])

        clusters: dict[int, list[dict]] = {}
        for r in rows:
            clusters.setdefault(root(r["appid"]), []).append(r)

        for members in clusters.values():
            if len(members) < 2:
                continue
            # The app with the most reviews is the game; ties go to the lowest app id.
            kept = min(members, key=lambda r: (-r["reviews"], r["appid"]))["appid"]
            ids = sorted(r["appid"] for r in members)
            result.groups[kept] = ids
            for appid in ids:
                result.kept_for[appid] = kept

        # Anything that shares the title but did not fold goes on the list.
        leftovers = sorted({root(r["appid"]) for r in rows})
        if len(leftovers) > 1:
            result.not_folded.append(sorted(r["appid"] for r in rows))
    return result


# ===========================================================================
# PART 2: IGDB against Steam
# ===========================================================================

@dataclass
class MatchSettings:
    separate_below: float
    merge_at_or_above: float
    min_description_chars: int
    category_rank: dict[str, int]
    pc_platforms: frozenset[str]

    @classmethod
    def from_config(cls, igdb_cfg: dict) -> "MatchSettings":
        m = igdb_cfg["matching"]
        return cls(
            separate_below=float(m["separate_below"]),
            merge_at_or_above=float(m["merge_at_or_above"]),
            min_description_chars=int(m["min_description_chars"]),
            category_rank=dict(m["category_rank"]),
            pc_platforms=frozenset(igdb_cfg["pc_platforms"]),
        )


def description_similarity(pairs_a: list[str], pairs_b: list[str]) -> np.ndarray:
    """TF-IDF cosine similarity for each (a[i], b[i]) pair of descriptions.

    1.0 means the same words, 0.0 means no words in common (after dropping
    common English words like "the"). Fitted on the pair texts themselves, so
    the result only depends on the input, never on anything random.
    """
    if not pairs_a:
        return np.zeros(0)
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(stop_words="english", min_df=2, sublinear_tf=True)
    try:
        vectorizer.fit(list(pairs_a) + list(pairs_b))
    except ValueError:          # every word was a stop word, nothing to compare
        return np.zeros(len(pairs_a))
    a = vectorizer.transform(pairs_a)
    b = vectorizer.transform(pairs_b)
    return np.asarray(a.multiply(b).sum(axis=1)).ravel()


def load_overrides(path: Path) -> list[dict]:
    """Read config/match_overrides.yaml. A missing or empty file means no overrides."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rows = data.get("overrides") or []
    clean = []
    for row in rows:
        verdict = str(row.get("verdict", "")).strip().lower()
        if verdict not in ("same", "different"):
            raise ValueError(f"override {row} needs verdict: same or different")
        clean.append({"igdb_id": int(row["igdb_id"]), "steam_appid": int(row["steam_appid"]),
                      "verdict": verdict, "note": row.get("note")})
    return clean


def _text(value) -> str:
    """A description as a string, with missing values as ''."""
    return value if isinstance(value, str) else ""


def _year_gap(a, b) -> float:
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return float("inf")
    return abs(int(a) - int(b))


def match_igdb(steam: pd.DataFrame, igdb: pd.DataFrame, settings: MatchSettings,
               overrides: list[dict] | None = None,
               appid_to_game: dict[int, int] | None = None) -> pd.DataFrame:
    """Decide, for every IGDB game, which Steam game it is (if any).

    `steam` holds ONE row per Steam game (after folding) with: game_id,
    appid, title, year, companies, desc and the four keys.
    `igdb` holds: igdb_id, title, year, category, companies, desc, platforms
    and the four keys.

    Returns one row per IGDB game with:
      decision     'merge', 'new' or 'review' (review is stored as new)
      game_id      the Steam game it merges into, or the candidate it was compared to
      method       the rule that decided, e.g. 'k_strict+same_year+company'
      score        description similarity, when it was measured
      reason       a plain-English reason, for the report
      low_confidence  merged, but the descriptions barely agree (< separate_below)
    """
    # Sorted by game_id, so every list of hits is in game_id order and "the
    # first hit" always means the same game.
    steam = steam.sort_values("game_id", kind="mergesort").reset_index(drop=True)
    igdb = igdb.reset_index(drop=True)
    index = {k: {} for k in KEYS}
    for k in KEYS:
        for i, value in enumerate(steam[k]):
            index[k].setdefault(value, []).append(i)

    s_year = steam["year"].tolist()
    s_comp = steam["companies"].tolist()
    s_desc = [_text(v) for v in steam["desc"]]
    i_desc = [_text(v) for v in igdb["desc"]]
    s_gid = steam["game_id"].tolist()

    decisions = []          # one dict per IGDB row
    text_pairs = []         # (decision index, steam row) that need a similarity score
    for row in igdb.itertuples(index=False):
        d = {"igdb_id": row.igdb_id, "decision": "new", "game_id": None, "method": "igdb_new",
             "reason": "no Steam game with this title", "score": None, "needs_text": False,
             "same_year": False, "company": False, "low_confidence": False,
             "category": row.category}
        platforms = set(row.platforms or ())
        not_on_pc = bool(platforms) and not (platforms & settings.pc_platforms)

        for tier, key in enumerate(KEYS):
            hits = index[key].get(getattr(row, key))
            if not hits:
                continue
            first = hits[0]
            d["game_id"] = s_gid[first]

            if key == "k_edition":
                d.update(decision="new", method="edition_key_only",
                         reason="only matches with edition words removed (remaster or edition): kept separate, listed")
                break
            if not_on_pc:
                d.update(decision="new", method="not_on_pc",
                         reason="same title but IGDB lists no PC platform, so it cannot be the Steam game")
                break

            scored = []
            for j in hits:
                gap = _year_gap(row.year, s_year[j])
                scored.append((j, gap == 0, gap, companies_overlap(row.companies, s_comp[j])))

            # Strong evidence: a shared company. For the roman and compact
            # keys we also want the years within one of each other, because
            # "Modern Warfare 2" (2009) and "Modern Warfare II" (2022) are by
            # the same company but are different games.
            strong = [s for s in scored if s[3] is True and (tier == 0 or s[2] <= 1)]
            exact = [s for s in scored if tier == 0 and s[1] and s[3] is not False]
            good = {s[0]: s for s in strong + exact}
            good = [good[j] for j in sorted(good, key=lambda j: s_gid[j])]

            if len(good) == 1:
                j, same_year, _gap, comp = good[0]
                method = key + ("+same_year" if same_year else "") + ("+company" if comp else "")
                d.update(decision="merge", game_id=s_gid[j], method=method, same_year=same_year,
                         company=bool(comp), reason="title match plus " +
                         ("same year and " if same_year else "") +
                         ("a shared company" if comp else "no company conflict"))
                text_pairs.append((len(decisions), j))
            elif len(good) > 1:
                d.update(decision="review", game_id=s_gid[good[0][0]], method="several_steam_games",
                         reason=f"{len(good)} Steam games share this title")
            elif all(s[3] is False for s in scored):
                d.update(decision="new", method="company_differs",
                         reason="same title, different company: a different game")
                text_pairs.append((len(decisions), first))
            elif len(hits) > 1:
                d.update(decision="review", method="several_steam_games",
                         reason=f"{len(hits)} Steam games share this title")
            else:
                # Title matches, years differ, nothing about companies settles
                # it. Let the descriptions decide.
                d.update(decision="review", method="text", needs_text=True,
                         reason="same title, years differ, no company evidence")
                text_pairs.append((len(decisions), first))
            break
        decisions.append(d)

    # --- description similarity, all pairs in one go ---
    min_chars = settings.min_description_chars
    usable = [(di, j) for di, j in text_pairs
              if len(i_desc[di]) >= min_chars and len(s_desc[j]) >= min_chars]
    scores = description_similarity([i_desc[di] for di, _ in usable],
                                    [s_desc[j] for _, j in usable])
    score_of = {di: float(round(s, 6)) for (di, _), s in zip(usable, scores)}

    for di, d in enumerate(decisions):
        if di in score_of:
            d["score"] = score_of[di]
        if d["needs_text"]:
            if d["score"] is None:
                d.update(decision="review", reason="same title, years differ, no description to compare")
            elif d["score"] >= settings.merge_at_or_above:
                d.update(decision="merge", method="text_match",
                         reason=f"same title, descriptions agree ({d['score']:.2f})")
            elif d["score"] < settings.separate_below:
                d.update(decision="new", method="descriptions_differ",
                         reason=f"same title, descriptions differ ({d['score']:.2f}): a different game")
            else:
                d.update(decision="review", method="text",
                         reason=f"same title, descriptions unclear ({d['score']:.2f})")
        if d["decision"] == "merge" and d["score"] is not None and d["score"] < settings.separate_below:
            d["low_confidence"] = True

    out = pd.DataFrame(decisions)
    out = _one_to_one(out, settings)
    if overrides:
        out = _apply_overrides(out, overrides, appid_to_game or {})
    return out.drop(columns=["needs_text"])


def _one_to_one(out: pd.DataFrame, settings: MatchSettings) -> pd.DataFrame:
    """One Steam game gets at most one IGDB merge. The best pair wins.

    Best means, in order: the same year, then a shared company, then the
    main game over a remaster, then the lowest IGDB id (so it is always the
    same answer). Every loser becomes its own game, which is usually right:
    the losers are remasters and re-releases with the same title.
    """
    merges = out[out["decision"] == "merge"].copy()
    if merges.empty:
        return out
    merges["_rank"] = list(zip(~merges["same_year"], ~merges["company"],
                               merges["category"].map(settings.category_rank).fillna(9),
                               merges["igdb_id"]))
    winners = merges.sort_values("_rank", kind="mergesort").drop_duplicates("game_id", keep="first")
    losers = merges.index.difference(winners.index)
    out.loc[losers, "decision"] = "new"
    out.loc[losers, "method"] = "lost_one_to_one"
    out.loc[losers, "reason"] = "the Steam game already matched a better IGDB entry"
    out.loc[losers, "low_confidence"] = False
    return out


def _apply_overrides(out: pd.DataFrame, overrides: list[dict], appid_to_game: dict[int, int]) -> pd.DataFrame:
    """config/match_overrides.yaml: a person's decision always wins, every run."""
    pos = {igdb_id: i for i, igdb_id in enumerate(out["igdb_id"])}
    for o in sorted(overrides, key=lambda o: (o["igdb_id"], o["steam_appid"])):
        i = pos.get(o["igdb_id"])
        game_id = appid_to_game.get(o["steam_appid"])
        if i is None or game_id is None:
            continue            # the report lists overrides that matched nothing
        idx = out.index[i]
        if o["verdict"] == "same":
            # Anything else merged into this Steam game is pushed out first,
            # so the one-to-one rule still holds.
            clash = out.index[(out["decision"] == "merge") & (out["game_id"] == game_id) & (out.index != idx)]
            out.loc[clash, ["decision", "method", "reason"]] = ["new", "displaced_by_override",
                                                                "a person matched this Steam game to another IGDB entry"]
            out.loc[idx, ["decision", "game_id", "method", "reason", "low_confidence"]] = [
                "merge", game_id, "override_same", "a person said these are the same game", False]
        else:
            if out.at[idx, "decision"] == "merge" and out.at[idx, "game_id"] == game_id:
                out.loc[idx, ["decision", "method", "reason", "low_confidence"]] = [
                    "new", "override_different", "a person said these are different games", False]
            elif out.at[idx, "game_id"] == game_id:
                out.loc[idx, ["decision", "method", "reason"]] = [
                    "new", "override_different", "a person said these are different games"]
    return out
