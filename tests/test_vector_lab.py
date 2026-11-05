"""The vector lab output: what the viewer decodes, and that reruns are byte-identical."""
import base64
import copy
import gzip
import json
import zlib

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Game
from pipeline.config import load_config
from pipeline.vector_lab import DEFAULT_METHODS, build_lab, main

N_SMALL, N_BIG = 30, 45


def fake_embed(texts, params):
    rows = []
    for text in texts:
        v = np.random.default_rng(zlib.crc32(text.encode())).normal(size=6)
        rows.append(v / np.linalg.norm(v))
    return np.array(rows)


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
    return [("small", small), ("big", big)]


def decode(out, layout, file):
    raw = gzip.decompress(base64.b64decode((out / file).read_text()))
    return {
        a["name"]: np.frombuffer(raw, np.dtype(a["dtype"]), a["length"], a["offset"]) for a in layout
    }


def test_output_decodes_with_the_declared_lengths(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    build_lab(dbs, DEFAULT_METHODS, out, cfg, log=lambda _: None)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["methodOrder"] == [f"{b}:{m}" for b in ("small", "big") for m in DEFAULT_METHODS]
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
        if m["build"] == "big":
            assert 0 <= m["vs1k"] <= 1 and 0 <= m["newcomers"] <= 1


def test_games_without_a_vector_are_left_off_tag_methods_but_kept_by_semantic(dbs, cfg, tmp_path):
    out = tmp_path / "lab"
    build_lab(dbs, ["votes_max", "semantic"], out, cfg, log=lambda _: None)
    methods = json.loads((out / "meta.json").read_text())["methods"]
    tagless = len([g for g in range(N_BIG) if g % 11 == 0])
    assert methods["big:votes_max"]["n"] == N_BIG - tagless
    assert methods["big:semantic"]["n"] == N_BIG


def test_a_second_run_is_byte_identical(dbs, cfg, tmp_path):
    for name in ("one", "two"):
        build_lab(dbs, ["votes_max", "hybrid_semantic"], tmp_path / name, cfg, log=lambda _: None)
    files = sorted(p.name for p in (tmp_path / "one").iterdir())
    assert files == sorted(p.name for p in (tmp_path / "two").iterdir())
    for f in files:
        assert (tmp_path / "one" / f).read_bytes() == (tmp_path / "two" / f).read_bytes()


def test_a_game_missing_from_the_last_build_fails_loudly(dbs, cfg, tmp_path):
    with pytest.raises(SystemExit, match="15 games"):
        build_lab(dbs[::-1], ["votes_max"], tmp_path / "lab", cfg, log=lambda _: None)


def test_cli_rejects_a_label_with_a_colon(tmp_path):
    with pytest.raises(SystemExit):
        main(["--build", "a:b=x.db", "--out", str(tmp_path)])
