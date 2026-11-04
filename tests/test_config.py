"""The config file is the only tunable surface (MAINT 2), so it gets tested."""
import pytest

from backend.app.models import VALID_CATEGORIES
from pipeline.config import (
    ConfigError,
    csv_columns_needed,
    load_config,
    validate_category_weights,
    validate_config,
)


def test_real_config_loads():
    cfg = load_config()
    assert cfg["map_version"]
    assert set(cfg["category_weights"]) <= set(VALID_CATEGORIES)


def test_every_alias_target_is_in_the_vocabulary():
    cfg = load_config()
    known = {
        (c, e["name"]) for c, entries in cfg["vocabulary"].items() for e in entries
    }
    for raw, target in cfg["aliases"].items():
        assert tuple(target) in known, f"alias {raw} points at an undefined feature"


def test_display_tags_are_not_weighted():
    """Scrum doc: display tags must not become an extra weighted category."""
    assert load_config()["category_weights"]["tag"] == 0.0


def test_unknown_category_is_rejected():
    cfg = load_config()
    cfg["vocabulary"]["nonsense"] = [{"name": "x", "display_name": "X"}]
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_bad_alias_target_is_rejected():
    cfg = load_config()
    cfg["aliases"]["Totally Made Up"] = ["genre", "does_not_exist"]
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_selection_mode_is_validated():
    cfg = load_config()
    cfg["selection"]["mode"] = "whatever"
    with pytest.raises(ConfigError):
        validate_config(cfg)


def _with_vectorization(**changes):
    cfg = load_config()
    cfg["vectorization"] = {**cfg["vectorization"], **changes}
    return cfg


@pytest.mark.parametrize(
    "changes",
    [
        {"hybrid_alpha": 1.5},
        {"description_floor": -0.1},
        {"description_floor": "high"},
        {"rank_depth": 5},
        {"rank_depth": 20.5},
        {"embedding_model": ""},
        {"embedding_revision": ""},
        {"embedding_tag_template": "a video game"},
    ],
)
def test_bad_vectorization_values_are_rejected(changes):
    with pytest.raises(ConfigError):
        validate_config(_with_vectorization(**changes))


@pytest.mark.parametrize("section", [None, [], "votes_log_idf", {}])
def test_malformed_vectorization_section_is_rejected(section):
    cfg = load_config()
    cfg["vectorization"] = section
    with pytest.raises(ConfigError):
        validate_config(cfg)


@pytest.mark.parametrize(
    "changes",
    [
        {"method": "umap"},
        {"method": None},
        {"tsne_perplexity": 0},
        {"tsne_perplexity": "30"},
        {"neighbor_count": 0},
        {"neighbor_count": True},
        {"coordinate_extent": 0},
        {"coordinate_extent": float("inf")},
        {"collision_min_distance": -1.0},
        {"collision_min_distance": float("nan")},
        {"collision_min_distance": 2000.0},
        {"cluster_colors": ["#E69F00", "#E69F00"]},
        {"cluster_colors": ["red"] * 12},
        {"cluster_colors": ["#E69F00", "#E69F00"] + ["#56B4E9"] * 10},
    ],
)
def test_bad_layout_values_are_rejected(changes):
    cfg = load_config()
    cfg["layout"] = {**cfg["layout"], **changes}
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_layout_needs_a_colour_for_every_cluster():
    cfg = load_config()
    cfg["cluster_count"] = len(cfg["layout"]["cluster_colors"]) + 1
    with pytest.raises(ConfigError):
        validate_config(cfg)


@pytest.mark.parametrize(
    "changes",
    [
        {"cluster_count": 0},
        {"cluster_count": True},
        {"cluster_count": 2.5},
        {"kmeans_n_init": 0},
        {"kmeans_n_init": None},
        {"kmeans_n_init": True},
        {"random_seed": None},
        {"random_seed": True},
        {"random_seed": "42"},
        {"map_version": "../evil"},
        {"map_version": "a/b"},
        {"map_version": "v..1"},
        {"map_version": ""},
        {"map_version": 1},
    ],
)
def test_bad_top_level_values_are_rejected(changes):
    cfg = {**load_config(), **changes}
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_layout_section_is_required():
    cfg = load_config()
    del cfg["layout"]
    with pytest.raises(ConfigError):
        validate_config(cfg)


def _weights(**changes) -> dict:
    return {**load_config()["category_weights"], **changes}


@pytest.mark.parametrize(
    "weights",
    [
        {k: v for k, v in _weights().items() if k != "genre"},
        _weights(genre=-0.1),
        _weights(genre=float("inf")),
        _weights(genre=True),
        {c: 0.0 for c in VALID_CATEGORIES},
        _weights(nonsense=1.0),
    ],
    ids=["missing-key", "negative", "infinite", "bool", "all-zero", "unknown-key"],
)
def test_bad_category_weights_are_rejected(weights):
    with pytest.raises(ConfigError):
        validate_category_weights(weights)
    cfg = load_config()
    cfg["category_weights"] = weights
    with pytest.raises(ConfigError):
        validate_config(cfg)


# ---------------------------------------------------------------------------
# The column mapping section
# ---------------------------------------------------------------------------

def test_every_games_column_has_a_documented_source():
    """Anyone should be able to answer 'where did this value come from?'
    by reading the config, without opening ingest.py."""
    cfg = load_config()
    sources = cfg["fields"]["column_sources"]

    # Every column we expect to fill from the CSV.
    expected = {
        "title", "title_search", "release_date", "release_year", "description",
        "long_description", "developers", "publishers", "cover_image_url",
        "store_url", "playtime_hours", "rating", "rating_count", "popularity",
        "raw_tags_json",
    }
    assert expected <= set(sources), f"undocumented: {expected - set(sources)}"

    for column, spec in sources.items():
        assert "from" in spec, f"{column} does not say which CSV column it reads"


def test_long_description_has_a_fallback():
    """about_the_game is cleaner, but it is missing more often than
    detailed_description, so we fall back rather than losing the text."""
    spec = load_config()["fields"]["column_sources"]["long_description"]
    assert spec["from"] == "about_the_game"
    assert spec["fallback"] == "detailed_description"


def test_developers_and_publishers_are_joined_not_truncated():
    """Around 8% of games have more than one developer, so we must not just
    take the first one. join_list keeps them all."""
    sources = load_config()["fields"]["column_sources"]
    assert sources["developers"]["transform"] == "join_list"
    assert sources["publishers"]["transform"] == "join_list"


def test_release_date_and_year_share_a_source():
    """They have to come from the same column or they could disagree."""
    sources = load_config()["fields"]["column_sources"]
    assert sources["release_date"]["from"] == sources["release_year"]["from"]
    assert sources["release_date"]["transform"] == "iso_date"
    assert sources["release_year"]["transform"] == "year_from_date"


def test_unknown_transform_is_rejected():
    cfg = load_config()
    cfg["fields"]["column_sources"]["title"]["transform"] = "make_it_shiny"
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_csv_column_list_comes_from_the_config():
    """The importer reads only what the config asks for.

    This used to be a hardcoded list and it had drifted: seven columns were
    being loaded out of a 447 MB file and then never used. Deriving it from
    the config means that cannot happen again.
    """
    cfg = load_config()
    needed = csv_columns_needed(cfg)

    # Everything a mapping names must be in the list.
    for spec in cfg["fields"]["column_sources"].values():
        assert spec["from"] in needed
        if spec.get("fallback"):
            assert spec["fallback"] in needed

    # The columns feature matching needs.
    for column in ("genres", "categories", "tags", "windows", "mac", "linux"):
        assert column in needed

    # And nothing we abandoned earlier.
    for dead in ("metacritic_score", "user_score", "positive", "negative",
                 "estimated_owners", "recommendations"):
        assert dead not in needed, f"{dead} is read but never stored"


# ---------------------------------------------------------------------------
# Selection rules
# ---------------------------------------------------------------------------

def test_all_mode_is_accepted():
    cfg = load_config()
    cfg["selection"]["mode"] = "all"
    cfg["selection"]["target_count"] = None
    validate_config(cfg)   # should not raise


def test_no_limit_is_only_allowed_with_all_mode():
    """A null target with a normal mode would import 90,000 games by accident."""
    cfg = load_config()
    cfg["selection"]["mode"] = "popular_recent"
    cfg["selection"]["target_count"] = None
    with pytest.raises(ConfigError):
        validate_config(cfg)


@pytest.mark.parametrize("bad", [0, -5, 2.5, "1000", True])
def test_target_count_must_be_a_positive_whole_number(bad):
    cfg = load_config()
    cfg["selection"]["target_count"] = bad
    with pytest.raises(ConfigError):
        validate_config(cfg)
