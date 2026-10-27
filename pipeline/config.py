"""Loads and validates config/map_config.yaml (MAINT 2).

Every tunable value lives in that one file. This module is the only place that
reads it, so a change there never requires a code change anywhere else.
"""
import re
from pathlib import Path

import yaml

from backend.app.models import VALID_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[1]
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
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
                "category_weights", "vocabulary", "aliases", "vectorization"):
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

    _validate_vectorization(cfg["vectorization"])
    _validate_layout(cfg)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_vectorization(vec) -> None:
    """Shape and range checks only. `vectorize()` owns the method-name check."""
    if not isinstance(vec, dict):
        raise ConfigError("vectorization must be a mapping")
    if not isinstance(vec.get("method"), str):
        raise ConfigError("vectorization.method must be a string")
    for key in ("description_floor", "hybrid_alpha"):
        value = vec.get(key)
        if not (_is_number(value) and 0 <= value <= 1):
            raise ConfigError(f"vectorization.{key} must be a number between 0 and 1")
    depth = vec.get("rank_depth")
    # Steam keeps each game's top 20 tags; a smaller depth zeroes out present tags.
    if not (isinstance(depth, int) and not isinstance(depth, bool) and depth >= 20):
        raise ConfigError("vectorization.rank_depth must be an integer >= 20")
    for key in ("embedding_model", "embedding_revision"):
        value = vec.get(key)
        if not (isinstance(value, str) and value.strip()):
            raise ConfigError(f"vectorization.{key} must be a non-empty string")
    template = vec.get("embedding_tag_template")
    if not (isinstance(template, str) and "{tag}" in template):
        raise ConfigError("vectorization.embedding_tag_template must contain {tag}")


def _validate_layout(cfg: dict) -> None:
    layout = cfg.get("layout")
    if not isinstance(layout, dict):
        raise ConfigError("config is missing required section: layout")
    count = layout.get("neighbor_count")
    if not (isinstance(count, int) and not isinstance(count, bool) and 10 <= count <= 15):
        raise ConfigError("layout.neighbor_count must be an integer from 10 to 15")
    for key in ("coordinate_extent", "collision_min_distance"):
        value = layout.get(key)
        if not (_is_number(value) and value > 0):
            raise ConfigError(f"layout.{key} must be a positive number")
    clusters = cfg.get("cluster_count")
    if not (isinstance(clusters, int) and not isinstance(clusters, bool) and clusters >= 1):
        raise ConfigError("cluster_count must be a positive integer")
    colors = layout.get("cluster_colors")
    if not isinstance(colors, list) or not all(
        isinstance(c, str) and _HEX_COLOR.fullmatch(c) for c in colors
    ):
        raise ConfigError("layout.cluster_colors must be a list of #RRGGBB colours")
    if len({c.lower() for c in colors}) < clusters:
        raise ConfigError(
            f"layout.cluster_colors needs at least {clusters} distinct colours"
        )


def alias_lookup(cfg: dict) -> dict[str, tuple[str, str]]:
    """Case-insensitive raw-string -> (category, name) map."""
    return {raw.strip().lower(): (t[0], t[1]) for raw, t in cfg["aliases"].items()}
