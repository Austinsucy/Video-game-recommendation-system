"""The config file is the only tunable surface (MAINT 2), so it gets tested."""
import pytest

from backend.app.models import VALID_CATEGORIES
from pipeline.config import ConfigError, load_config, validate_config


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
