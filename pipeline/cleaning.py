"""
Clean-up helpers for the Steam + IGDB merge.

Two kinds of thing live here:

  1. Clean-up of VALUES we store (titles, lists, descriptions). These change
     what the website shows, so they are careful: they only remove things
     that are clearly junk, like the trademark sign or "&amp;".

  2. MATCHING KEYS. These are never stored or shown. They are aggressive
     versions of a title, only used to ask "could these two titles be the
     same game?". For example "Brütal Legend" and "Brutal Legend" get the
     same key, and so do "MDK2" and "MDK 2".

Every function is small and has no side effects, so tests/test_matching.py
can check each one with real examples.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata

import pandas as pd

# ===========================================================================
# PART 1: cleaning values we store
# ===========================================================================

TRADEMARK_SIGNS = re.compile(r"[™®©℠]")

# Values that mean "nothing here". The IGDB file writes missing names as the
# word "Missing", and pandas turns some blanks into the text "nan".
EMPTY_MARKERS = {"", "missing", "nan", "none", "null", "[]"}


def is_blank(value) -> bool:
    """True for None, NaN and the text markers above."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip().lower() in EMPTY_MARKERS


def clean_display_title(value) -> str | None:
    """The title we show: the source's spelling minus trademark signs.

    "DOOM®"  ->  "DOOM"
    "Half-Life™  2"  ->  "Half-Life 2"

    Nothing else changes. Accents, capitals and punctuation stay exactly as
    the source wrote them, because that is how the game is really called.
    """
    # Only a real blank counts here. A game can genuinely be called "None"
    # or "Missing", so the word list in is_blank is not used for titles.
    if value is None or (isinstance(value, float) and pd.isna(value)) or not str(value).strip():
        return None
    text = TRADEMARK_SIGNS.sub("", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    # A title made only of trademark signs would end up empty; keep the
    # original rather than store an empty title.
    return text or str(value).strip()


TAG_PATTERN = re.compile(r"<[^>]+>")


def clean_html_text(value) -> str | None:
    """Turn HTML leftovers into plain text.

    About 2,000 Steam short descriptions and 7,700 long ones contain things
    like "&amp;" or "&quot;". html.unescape turns those back into & and ".
    We also strip any <b>tags</b>, in case a later snapshot has them.
    Line breaks are kept, because long descriptions use them for paragraphs.
    """
    if is_blank(value):
        return None
    text = html.unescape(str(value))
    text = TAG_PATTERN.sub("", text)
    text = text.strip()
    return text or None


def clean_summary(value, min_chars: int = 15) -> str | None:
    """IGDB summary for long_description. Too-short summaries become NULL.

    560 IGDB summaries are a single word like "Fishing" or "Duh". Those are
    not descriptions, and storing them would make DATA checks and the TF-IDF
    comparison think we have text when we do not.
    """
    text = clean_html_text(value)
    if text is None or len(text) < min_chars:
        return None
    return text


SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def short_summary(value, limit: int = 350, min_chars: int = 15) -> str | None:
    """The summary cut at a sentence end near `limit` characters.

    Steam gives us a one or two sentence blurb for games.description. IGDB
    only has one summary, so we make a blurb from it:
      - short enough already: use it whole
      - otherwise: cut after the last full sentence that ends before `limit`
      - no sentence end in a sensible place: cut at a space and add "..."
    """
    text = clean_summary(value, min_chars)
    if text is None or len(text) <= limit:
        return text
    ends = [m.end() for m in SENTENCE_END.finditer(text) if m.end() <= limit]
    # Only accept a cut that keeps at least about half the space, otherwise
    # one very short first sentence would leave a tiny blurb.
    if ends and ends[-1] >= limit // 2:
        return text[: ends[-1]].strip()
    cut = text.rfind(" ", 0, limit)
    if cut <= 0:
        cut = limit
    return text[:cut].rstrip(" ,;:") + "..."


def parse_list(value) -> list:
    """Read a list cell. The IGDB file stores lists as Python text like ['A', 'B']."""
    if isinstance(value, list):
        return value
    if is_blank(value):
        return []
    text = str(value).strip()
    if text.startswith("["):
        import ast
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return []
        return list(parsed) if isinstance(parsed, (list, tuple)) else []
    return [part for part in text.split(",")]


OPEN_BRACKETS = "([（"
CLOSE_BRACKETS = ")]）"


def _unbalanced(text: str) -> bool:
    """More opening brackets than closing ones."""
    return sum(text.count(b) for b in OPEN_BRACKETS) > sum(text.count(b) for b in CLOSE_BRACKETS)


def clean_list(value, rejoin_suffixes=()) -> list[str]:
    """Tidy one list column.

    Whoever built the IGDB file split some names at their commas, so

        ['4X (explore', 'expand', 'exploit', 'and exterminate)']

    is really ONE theme. We glue items back together until the brackets
    balance. Company names can also lose their suffix ("Studio X", "LLC"), so
    a lone suffix from `rejoin_suffixes` is glued back onto the item before it.
    After that: trim, drop the "Missing" style blanks, drop exact duplicates.
    """
    out: list[str] = []
    pending: str | None = None
    for raw in parse_list(value):
        item = str(raw).strip()
        if pending is not None:
            pending = f"{pending}, {item}"
            if not _unbalanced(pending):
                out.append(pending)
                pending = None
            continue
        if _unbalanced(item):
            pending = item
            continue
        if item in rejoin_suffixes and out:
            out[-1] = f"{out[-1]}, {item}"
            continue
        out.append(item)
    if pending is not None:          # brackets never closed: keep what we have
        out.append(pending)

    seen: list[str] = []
    for item in out:
        if not is_blank(item) and item not in seen:
            seen.append(item)
    return seen


def first_list_item(value) -> str | None:
    """The first entry of a list cell, e.g. the first screenshot URL."""
    items = clean_list(value)
    return items[0] if items else None


def number(value) -> float | None:
    """A plain number, or None."""
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def json_list(items) -> str | None:
    """Store a list as JSON text, or NULL when it is empty."""
    return json.dumps(list(items), ensure_ascii=False) if items else None


def compile_patterns(patterns) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns or []]


def non_game_match(title, compiled: list[re.Pattern]) -> str | None:
    """The first non-game pattern a title matches, or None.

    Returns the pattern itself (not just True) so the report can say WHY a
    title was flagged, and tests can check every flag has a reason.
    """
    if not title:
        return None
    for pattern in compiled:
        if pattern.search(str(title)):
            return pattern.pattern
    return None


# ===========================================================================
# PART 2: matching keys (never stored, never shown)
# ===========================================================================

QUOTES = re.compile(r"[‘’‚‛ʼ`´′]")
DOUBLE_QUOTES = re.compile(r"[“”„‟″]")
DASHES = re.compile(r"[‐‑‒–—―−]")


def fold(text) -> str:
    """Make visually identical text actually identical.

      NFKC        full-width letters and ligatures become normal ones
      accents     "Brütal" becomes "Brutal", "Pokémon" becomes "Pokemon"
      quotes      ’ ` ´ all become '
      dashes      – — − all become -
    """
    text = unicodedata.normalize("NFKC", str(text))
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    text = QUOTES.sub("'", text)
    text = DOUBLE_QUOTES.sub('"', text)
    return DASHES.sub("-", text)


def key_strict(title) -> str:
    """The main matching key. Same key = probably the same title.

    "Baldur's Gate 3"   -> "baldurs gate 3"
    "Brütal Legend"     -> "brutal legend"
    "Rock & Roll Racing"-> "rock and roll racing"

    "The" is NOT removed here, so "SiN" and "The Sin" stay different. Only
    the edition key (the weakest one) drops it.
    """
    text = fold(title).lower()
    text = TRADEMARK_SIGNS.sub("", text)
    text = text.replace("&", " and ").replace("+", " plus ")
    text = re.sub(r"(\w)'(\w)", r"\1\2", text)          # baldur's -> baldurs
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Symbol-only titles ("***") would become empty. Keep them as they are so
    # they never match everything else that is empty.
    return text or str(title).strip().lower()


# II to XV become digits. I and V are left alone because they are also
# ordinary words and letters ("I Am Bread", "V Rising").
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8",
         "ix": "9", "x": "10", "xi": "11", "xii": "12", "xiii": "13", "xiv": "14",
         "xv": "15"}


def key_roman(title) -> str:
    """Strict key with roman numerals as digits: "Assassin's Creed II" == "... 2"."""
    return " ".join(ROMAN.get(word, word) for word in key_strict(title).split())


def key_compact(title) -> str:
    """Roman key with no spaces at all: "MDK2" == "MDK 2", "X-COM" == "XCOM"."""
    return key_roman(title).replace(" ", "")


def edition_pattern(edition_words) -> re.Pattern:
    words = sorted((re.escape(w) for w in edition_words), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(words) + r")\b")


def key_edition(title, pattern: re.Pattern) -> str:
    """The weakest key: also drop "The", edition words and a (year).

    "Mafia II: Definitive Edition" -> "mafia2"
    "The Sin"                      -> "sin"

    A match on this key ALONE is never merged. It only finds candidates for
    the report, because it is exactly the key that confuses a game with its
    remaster.
    """
    text = re.sub(r"\(\s*(19|20)\d\d\s*\)", " ", str(title))
    text = pattern.sub(" ", key_roman(text))
    return re.sub(r"\s+", "", text)


def company_pattern(suffixes) -> re.Pattern:
    words = sorted((re.escape(w) for w in suffixes), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(words) + r")\b")


def company_keys(names, pattern: re.Pattern) -> frozenset[str]:
    """Company names reduced to their core, for comparing two sources.

    "Bethesda Game Studios" -> "bethesda"
    "Bethesda Softworks LLC" -> "bethesdasoftworks"
    Keys shorter than 3 letters are dropped, they match too much.
    """
    out = set()
    for name in names or []:
        core = pattern.sub(" ", key_strict(name))
        core = re.sub(r"\s+", "", core)
        if len(core) >= 3:
            out.add(core)
    return frozenset(out)


def companies_overlap(a, b) -> bool | None:
    """Do two company sets share a company?

    True   yes, at least one company in common
    False  both sides list companies and none are shared (a conflict)
    None   one side has no company information, so we cannot tell

    "In common" also allows one name inside the other when the shorter one
    has 5+ letters, so "bethesda" matches "bethesdasoftworks".
    """
    if not a or not b:
        return None
    for x in a:
        for y in b:
            if x == y:
                return True
            short, long_ = (x, y) if len(x) <= len(y) else (y, x)
            if len(short) >= 5 and short in long_:
                return True
    return False
