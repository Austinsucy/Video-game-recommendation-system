"""Loads and validates config/map_config.yaml (MAINT 2).

Every tunable value lives in that one file. This module is the only place that
reads it, so a change there never requires a code change anywhere else.
"""
import math
import re
from pathlib import Path

import yaml

from backend.app.models import VALID_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "data" / "artifacts"
MAP_DB_PATH = REPO_ROOT / "data" / "map.db"
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
LAYOUT_METHODS = ("pca", "tsne")  # pipeline/build_map.py LAYOUTS
VERSION_ID = re.compile(r"[A-Za-z0-9._-]+")
CONFIG_PATH = REPO_ROOT / "config" / "map_config.yaml"


class ConfigError(ValueError):
    pass


# The ways the importer knows how to pick which games get imported.
#   popular_recent   games from min_year onward, most reviewed first
#   popular_pre2019  games up to max_year, most reviewed first
#   all              everything that passes the minimums, no year filter
#                    (used by the full-catalogue test build)
SELECTION_MODES = ("popular_recent", "popular_pre2019", "all")

# Conversions a column in fields.column_sources is allowed to ask for. Each
# one is a function in pipeline/ingest.py. Listing them here means a typo in
# the config fails when the config loads, not a minute into an import.
KNOWN_TRANSFORMS = {
    "clean_text",
    "normalise_title",
    "year_from_date",
    "iso_date",
    "join_list",
    "minutes_to_hours",
    "json_dump",
    "store_url_template",
}


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
                "category_weights", "vocabulary", "aliases", "vectorization",
                "layout"):
        if key not in cfg:
            raise ConfigError(f"config is missing required section: {key}")

    bad = set(cfg["vocabulary"]) - set(VALID_CATEGORIES)
    if bad:
        raise ConfigError(f"vocabulary has unapproved categories: {sorted(bad)}")

    validate_category_weights(cfg["category_weights"])

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

    validate_selection(cfg["selection"])

    # Every games column has to say which CSV column it comes from.
    validate_column_sources(cfg)

    if not is_valid_version_id(cfg["map_version"]):
        raise ConfigError(
            "map_version must match [A-Za-z0-9._-]+ without '..': it becomes a filename"
        )
    cluster_count = cfg.get("cluster_count")
    if not (_is_int(cluster_count) and cluster_count >= 1):
        raise ConfigError("cluster_count must be a positive integer")
    n_init = cfg.get("kmeans_n_init")
    if not (_is_int(n_init) and n_init >= 1):
        raise ConfigError("kmeans_n_init must be a positive integer")
    if not _is_int(cfg.get("random_seed")):
        raise ConfigError("random_seed must be an integer")

    _validate_vectorization(cfg["vectorization"])
    _validate_layout(cfg["layout"], cluster_count)


def validate_category_weights(weights) -> None:
    """One finite weight >= 0 per category, at least one above 0.

    Also the check for any weights that arrive from outside the config file.
    """
    if not isinstance(weights, dict):
        raise ConfigError("category_weights must be a mapping")
    expected = set(VALID_CATEGORIES)
    missing, unknown = expected - set(weights), set(weights) - expected
    if missing or unknown:
        raise ConfigError(
            f"category_weights must name exactly the approved categories; "
            f"missing: {sorted(missing)}, unapproved: {sorted(unknown)}"
        )
    for category, weight in weights.items():
        if not (_is_number(weight) and math.isfinite(weight) and weight >= 0):
            raise ConfigError(f"category_weights.{category} must be a finite number >= 0")
    if not any(weight > 0 for weight in weights.values()):
        raise ConfigError("category_weights needs at least one weight above 0")


def is_valid_version_id(value) -> bool:
    """A map version names a file (map_<version>.json), so keep it path-safe."""
    return (
        isinstance(value, str)
        and VERSION_ID.fullmatch(value) is not None
        and ".." not in value
    )


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
    if not (_is_int(depth) and depth >= 20):
        raise ConfigError("vectorization.rank_depth must be an integer >= 20")
    for key in ("embedding_model", "embedding_revision"):
        value = vec.get(key)
        if not (isinstance(value, str) and value.strip()):
            raise ConfigError(f"vectorization.{key} must be a non-empty string")
    template = vec.get("embedding_tag_template")
    if not (isinstance(template, str) and "{tag}" in template):
        raise ConfigError("vectorization.embedding_tag_template must contain {tag}")
    if vec.get("text_field", "description") not in ("description", "long_description"):
        raise ConfigError("vectorization.text_field must be description or long_description")
    if not isinstance(vec.get("embedding_device", "cpu"), str):
        raise ConfigError("vectorization.embedding_device must be a string")


def _validate_layout(layout, cluster_count: int) -> None:
    if not isinstance(layout, dict):
        raise ConfigError("layout must be a mapping")
    # publish.py owns the 10..15 range check.
    count = layout.get("neighbor_count")
    if not (_is_int(count) and count >= 1):
        raise ConfigError("layout.neighbor_count must be a positive integer")
    extent = layout.get("coordinate_extent")
    min_distance = layout.get("collision_min_distance")
    for key, value in (("coordinate_extent", extent), ("collision_min_distance", min_distance)):
        if not (_is_number(value) and math.isfinite(value) and value > 0):
            raise ConfigError(f"layout.{key} must be a finite positive number")
    if layout.get("method") not in LAYOUT_METHODS:
        raise ConfigError(f"layout.method must be one of {sorted(LAYOUT_METHODS)}")
    perplexity = layout.get("tsne_perplexity")
    if not (_is_number(perplexity) and math.isfinite(perplexity) and perplexity > 0):
        raise ConfigError("layout.tsne_perplexity must be a finite positive number")
    if min_distance >= extent:
        raise ConfigError("layout.collision_min_distance must be less than coordinate_extent")
    colors = layout.get("cluster_colors")
    if not isinstance(colors, list) or not all(
        isinstance(c, str) and _HEX_COLOR.fullmatch(c) for c in colors
    ):
        raise ConfigError("layout.cluster_colors must be a list of #RRGGBB colours")
    # cluster_rows indexes colours by position, so the first cluster_count must differ.
    if len({c.lower() for c in colors[:cluster_count]}) < cluster_count:
        raise ConfigError(
            f"the first {cluster_count} layout.cluster_colors must be distinct #RRGGBB colours"
        )


def validate_selection(selection: dict) -> None:
    """Check the rules for choosing which games get imported."""
    mode = selection.get("mode")
    if mode not in SELECTION_MODES:
        raise ConfigError(
            f"selection.mode must be one of {sorted(SELECTION_MODES)}, got {mode!r}"
        )

    # target_count may be null (no limit), but only with mode: all. With the
    # other modes a null would quietly import the whole 90,000-game catalogue
    # when someone meant to import 1,000.
    target = selection.get("target_count")
    if target is None and mode != "all":
        raise ConfigError(
            f"selection.target_count is null, which means no limit. That is only "
            f"allowed with mode: all, not mode: {mode!r}."
        )
    if target is not None and not (_is_int(target) and target >= 1):
        raise ConfigError(
            f"selection.target_count must be a positive whole number or null, got {target!r}"
        )


def validate_column_sources(cfg: dict) -> None:
    """Check fields.column_sources: every column names its CSV source.

    This is the section that answers "where did this value come from?", so a
    column without a `from:` would be a column nobody can trace.
    """
    sources = cfg["fields"].get("column_sources")
    if not isinstance(sources, dict) or not sources:
        raise ConfigError("config is missing fields.column_sources")

    for column, spec in sources.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("from"), str):
            raise ConfigError(
                f"fields.column_sources.{column} needs a 'from:' line naming the "
                "CSV column it reads"
            )
        transform = spec.get("transform")
        if transform is not None and transform not in KNOWN_TRANSFORMS:
            raise ConfigError(
                f"fields.column_sources.{column} asks for transform {transform!r}, "
                f"which does not exist. Known: {sorted(KNOWN_TRANSFORMS)}"
            )


def csv_columns_needed(cfg: dict) -> list[str]:
    """Exactly which CSV columns the import has to read.

    Built from the config instead of a hardcoded list, so we never load columns
    we do not use out of a 447 MB file, and a new mapping in the config just
    works with no code change. Sorted so the order is the same every run.
    """
    needed: set[str] = set()
    for spec in cfg["fields"]["column_sources"].values():
        needed.add(spec["from"])
        if spec.get("fallback"):
            needed.add(spec["fallback"])

    # The column we sort by when picking the top N games.
    needed.add(cfg["selection"]["rank_by"])

    # The feature matching needs these. They are not in column_sources because
    # they feed the features tables, not a single `games` column.
    needed.update(["appid", "release_date", "genres", "categories", "tags",
                   "windows", "mac", "linux"])
    return sorted(needed)


def alias_lookup(cfg: dict) -> dict[str, tuple[str, str]]:
    """Case-insensitive raw-string -> (category, name) map."""
    return {raw.strip().lower(): (t[0], t[1]) for raw, t in cfg["aliases"].items()}


def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return s.strip("_") or "unknown"


def map_raw_tag(raw: str, aliases: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """The (category, name) a raw Steam tag becomes: its alias, else a `tag` feature."""
    return aliases.get(raw.strip().lower()) or ("tag", slugify(raw))


def vectorization_params(cfg: dict) -> dict:
    """Everything `pipeline.vectorize.vectorize` reads from the config."""
    return {**cfg["vectorization"], "category_weights": cfg["category_weights"]}
