"""Loads and validates config/map_config.yaml (MAINT 2).

Every tunable value lives in that one file. This module is the only place that
reads it, so a change there never requires a code change anywhere else.
"""
from pathlib import Path

import yaml

from backend.app.models import VALID_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "map_config.yaml"


class ConfigError(ValueError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """YAML silently keeps the LAST of two identical keys.

    With a hand-edited alias map that means a mapping can disappear without a
    word. This loader refuses instead.
    """


def _no_duplicate_keys(loader, node, deep=False):
    seen = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ConfigError(f"duplicate key in config: {key!r}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def load_config(path: Path | str | None = None) -> dict:
    path = Path(path) if path else CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.load(fh, Loader=_StrictLoader)
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict) -> None:
    """Fail loudly on a malformed config rather than importing bad data."""
    for key in ("map_version", "dataset", "selection", "fields",
                "category_weights", "vocabulary", "aliases"):
        if key not in cfg:
            raise ConfigError(f"config is missing required section: {key}")

    bad = set(cfg["vocabulary"]) - set(VALID_CATEGORIES)
    if bad:
        raise ConfigError(f"vocabulary has unapproved categories: {sorted(bad)}")

    bad = set(cfg["category_weights"]) - set(VALID_CATEGORIES)
    if bad:
        raise ConfigError(f"category_weights has unapproved categories: {sorted(bad)}")

    # Every alias target must exist in the vocabulary, or the importer would
    # silently drop features Austin and Kayne think they defined.
    known = {
        (cat, entry["name"])
        for cat, entries in cfg["vocabulary"].items()
        for entry in entries
    }
    for raw, target in cfg["aliases"].items():
        if not (isinstance(target, list) and len(target) == 2):
            raise ConfigError(f"alias {raw!r} must be [category, name]")
        if tuple(target) not in known:
            raise ConfigError(
                f"alias {raw!r} points at {target} which is not in the vocabulary"
            )

    mode = cfg["selection"].get("mode")
    if mode not in ("popular_recent", "popular_pre2019"):
        raise ConfigError(f"selection.mode must be popular_recent or popular_pre2019, got {mode!r}")


def alias_lookup(cfg: dict) -> dict[str, tuple[str, str]]:
    """Case-insensitive raw-string -> (category, name) map."""
    return {raw.strip().lower(): (t[0], t[1]) for raw, t in cfg["aliases"].items()}
