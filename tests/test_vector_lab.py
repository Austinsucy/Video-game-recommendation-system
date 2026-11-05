"""The vector lab output: what the viewer decodes, and that reruns are byte-identical."""
import base64
import copy
import gzip
import json

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Game
from pipeline.config import load_config, vectorization_params
from pipeline.vector_lab import DEFAULT_METHODS, build_lab, main
from pipeline.vectorize import load_corpus_for, neighbor_indices, vectorize
from tests.conftest import fake_embed

N_SMALL, N_BIG = 30, 45


def make_db(path, games):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        s.add_all(
            Game(
                game_id=i + 1,
                title=f"Game {g}",
                title_search=f"game {g}",
                description=f"short {g}",
                long_description=f"long text about topic {g}" if g % 7 else None,
                store_url=f"https://store/{g}",
                rating_count=-1 if g % 4 == 0 else g * 10,
                raw_tags_json=json.dumps(tags(g)) if g % 11 else None,  # some games have no tags
            )
            for i, g in enumerate(games)
        )
    engine.dispose()


def tags(g):
    group = g % 3
    return {f"tag{group * 3 + j}": 100 - 10 * j - g % 5 for j in range(3)} | {f"extra{g % 4}": 5 + g}


@pytest.fixture
def cfg():
    cfg = copy.deepcopy(load_config())
    cfg["cluster_count"] = 3
    return cfg


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.vectorize._embed", fake_embed)
    small, big = tmp_path / "small.db", tmp_path / "big.db"
    make_db(small, range(N_SMALL))
    make_db(big, range(N_BIG))
    return {"small": small, "full": big}


def decode(out, layout, file):
    raw = gzip.decompress(base64.b64decode((out / file).read_text()))
    return {
        a["name"]: np.frombuffer(raw, np.dtype(a["dtype"]), a["length"], a["offset"]) for a in layout
    }


def run_lab(dbs, cfg, out):
    return build_lab(**dbs, out=out, cfg=cfg, log=lambda _: None)


def test_output_decodes_with_the_declared_lengths(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    run_lab(dbs, cfg, out)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["methodOrder"] == [f"{b}:{m}" for b in ("1k", "90k") for m in DEFAULT_METHODS]
    assert (out / "index.html").read_text().startswith("<!DOCTYPE html>")

    shared = decode(out, meta["shared"], meta["sharedFile"])
    assert len(shared["rawIdx"]) == N_BIG * meta["rawK"]
    assert shared["in1k"].sum() == N_SMALL
    assert shared["ratingCount"].min() == 0  # unknown (-1) is clipped, not wrapped

    for key, m in meta["methods"].items():
        a = decode(out, m["layout"], m["file"])
        n = m["n"]
        assert len(a["rows"]) == n and a["nb"].shape == (n * meta["showK"],)
        assert len(a["sim"]) == n * meta["showK"] and len(a["xy"]) == 2 * n and len(a["cluster"]) == n
        assert a["nb"].max() < N_BIG and a["cluster"].max() < cfg["cluster_count"]
        assert a["xy"].dtype == np.float32 and a["sim"].dtype == np.int16
        assert ("tagIdx" in a) == (m["space"] == "tags")
        if "tagIdx" in a:
            assert len(a["tagIdx"]) == len(a["tagW"]) == n * meta["topTags"]
        if m["build"] == "90k":
            assert 0 <= m["vs1k"] <= 1 and 0 <= m["newcomers"] <= 1


def test_meta_carries_what_the_viewer_reads(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    run_lab(dbs, cfg, out)
    meta = json.loads((out / "meta.json").read_text())
    for build in ("1k", "90k"):
        for method in DEFAULT_METHODS:
            assert f"{build}:{method}" in meta["methods"]
    assert meta["textField"] == cfg["vectorization"]["text_field"]
    assert meta["descriptionFloor"] == cfg["vectorization"]["description_floor"]


def test_exported_neighbours_are_the_pipelines_neighbours(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    run_lab(dbs, cfg, out)
    meta = json.loads((out / "meta.json").read_text())
    exported = decode(out, meta["methods"]["1k:votes_max"]["layout"], meta["methods"]["1k:votes_max"]["file"])

    corpus = load_corpus_for(dbs["small"], cfg)
    vectors = vectorize(corpus, "votes_max", vectorization_params(cfg))
    valid = np.flatnonzero(np.linalg.norm(vectors, axis=1) > 0)
    expected = valid[neighbor_indices(vectors[valid], cfg["layout"]["neighbor_count"])[:, : meta["showK"]]]

    got = exported["nb"].reshape(-1, meta["showK"])
    universe_titles = np.array(meta["titles"])
    np.testing.assert_array_equal(universe_titles[got], np.array(corpus.titles)[expected])
    np.testing.assert_array_equal(universe_titles[exported["rows"]], np.array(corpus.titles)[valid])


def test_games_without_a_vector_are_left_off_tag_methods_but_kept_by_semantic(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    run_lab(dbs, cfg, out)
    methods = json.loads((out / "meta.json").read_text())["methods"]
    tagless = len([g for g in range(N_BIG) if g % 11 == 0])
    assert methods["90k:votes_max"]["n"] == N_BIG - tagless
    assert methods["90k:semantic"]["n"] == N_BIG


def test_a_run_set_without_tag_space_methods_still_writes(dbs, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.vector_lab.DEFAULT_METHODS", ["semantic"])
    out = tmp_path / "lab"
    run_lab(dbs, cfg, out)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["methodOrder"] == ["1k:semantic", "90k:semantic"]
    assert meta["tags"]


def test_a_second_run_is_byte_identical(dbs, cfg, tmp_path):
    for name in ("one", "two"):
        run_lab(dbs, cfg, tmp_path / name)
    files = sorted(p.name for p in (tmp_path / "one").iterdir())
    assert files == sorted(p.name for p in (tmp_path / "two").iterdir())
    for f in files:
        assert (tmp_path / "one" / f).read_bytes() == (tmp_path / "two" / f).read_bytes()


def test_a_game_missing_from_the_full_database_fails_loudly(dbs, cfg, tmp_path):
    with pytest.raises(SystemExit, match="15 games"):
        build_lab(small=dbs["full"], full=dbs["small"], out=tmp_path / "lab", cfg=cfg, log=lambda _: None)


def test_cli_wants_both_databases(tmp_path):
    with pytest.raises(SystemExit):
        main(["--small", "x.db", "--out", str(tmp_path)])


def test_cli_text_field_overrides_the_config_for_the_run(dbs, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr("pipeline.vector_lab.build_lab", lambda small, full, out, cfg: seen.update(cfg["vectorization"]))
    main(["--small", "a.db", "--full", "b.db", "--out", str(tmp_path)])
    assert seen["text_field"] == "long_description"
    main(["--small", "a.db", "--full", "b.db", "--text-field", "description", "--device", "cpu"])
    assert seen["text_field"] == "description"
    assert load_config()["vectorization"]["text_field"] == "description"


def test_collision_spreading_is_skipped_only_above_the_game_cap(dbs, cfg, tmp_path, monkeypatch):
    def spread_flags(name):
        out = tmp_path / name
        run_lab(dbs, cfg, out)
        methods = json.loads((out / "meta.json").read_text())["methods"]
        return {k: m["collisionsSpread"] for k, m in methods.items() if k.endswith(":votes_max")}

    assert spread_flags("capped") == {"1k:votes_max": True, "90k:votes_max": True}
    monkeypatch.setattr("pipeline.publish.MAX_GAMES", 35)
    assert spread_flags("over") == {"1k:votes_max": True, "90k:votes_max": False}
    assert cfg["layout"]["collision_min_distance"] > 0
