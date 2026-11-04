"""
Quick tests for the small cleaning functions in pipeline/ingest.py.

These do not need a database or the CSV, so they run in a fraction of a
second. That is the point: the edge cases here were only found by building
the full 90,000-game catalogue, and nobody wants to wait for a full import
just to check that a bug stays fixed.
"""
from pipeline.ingest import iso_date, join_list, normalise_title


def test_normal_title_is_cleaned():
    assert normalise_title("The Witcher 3: Wild Hunt") == "the witcher 3 wild hunt"


def test_non_latin_title_survives():
    """An old version blanked every Chinese and Japanese title."""
    assert normalise_title("觅长生") == "觅长生"


def test_symbol_only_titles_are_never_empty():
    """Real titles from the Steam catalogue that used to clean down to ""."""
    for title in ("***", ".", "...", "∞"):
        result = normalise_title(title)
        assert result != "", f"{title!r} became an empty search string"
        assert result == title.strip().lower()


def test_symbol_only_titles_stay_distinct():
    """If they all became the same string they would look like duplicates."""
    results = {normalise_title(t) for t in ("***", ".", "...", "∞")}
    assert len(results) == 4


def test_iso_date_keeps_the_standard_format():
    assert iso_date("2022-02-24") == "2022-02-24"


def test_iso_date_returns_none_for_junk():
    assert iso_date("not a date") is None


def test_join_list_handles_several_and_removes_repeats():
    assert join_list("['Valve', 'Hidden Path', 'Valve']") == "Valve, Hidden Path"


def test_join_list_keeps_commas_inside_a_name():
    """'FromSoftware, Inc.' is one studio, not two."""
    assert join_list("['FromSoftware, Inc.']") == "FromSoftware, Inc."


def test_join_list_empty_becomes_none():
    assert join_list("[]") is None
