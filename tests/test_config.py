"""The config file is the only tunable surface (MAINT 2), so it gets tested."""
import pytest

from backend.app.models import VALID_CATEGORIES
from pipeline.config import ConfigError, load_config, validate_category_weights, validate_config


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
