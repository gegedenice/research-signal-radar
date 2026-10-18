import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from openalex_api_client import OpenAlex
from radar.brief import write_brief
from radar.detectors import run_detect
from radar.export import run_export
from radar.sweep import run_sweep

from test_detectors import fixture_works
from conftest import FakeSession


def fake_map(sweep):
    """Map outputs without running UMAP: 4 clusters by topic and year parity, one outlier."""
    works = pd.read_parquet(sweep / "works.parquet")
    rng = np.random.default_rng(0)
    cluster = (works["primary_topic_id"].eq("T2").astype(int) * 2 + works["publication_year"] % 2).to_numpy()
    cluster[0] = -1
    points = pd.DataFrame({
        "work_id": works.work_id, "x": rng.random(len(works)), "y": rng.random(len(works)),
        "x3": rng.random(len(works)), "y3": rng.random(len(works)), "z3": rng.random(len(works)),
        "cluster": cluster, "cluster_raw": cluster, "region_id": np.where(cluster == -1, -1, cluster // 2),
        "year": works.publication_year, "pub_month": works.pub_month, "has_abstract": works.has_abstract,
        "primary_topic_id": works.primary_topic_id, "subfield_id": works.subfield_id,
    }).sample(frac=1, random_state=1)  # shuffled: export must sort by work_id
    derived = sweep / "derived"
    points.to_parquet(derived / "map_points.parquet", index=False)
    rows = []
    for c in sorted(set(cluster)):
        rows.append({"cluster": int(c), "region_id": -1 if c == -1 else int(c) // 2, "label": f"c{c}",
                     "terms": [f"t{c}"], "size": int((cluster == c).sum()), "x": .5, "y": .5, "x3": .5, "y3": .5,
                     "z3": .5, "counts_by_year": json.dumps({"2025": 1}),
                     "top_topics": [{"id": "T1", "label": "Topic T1", "share": 1.0}], "top_subfields": [],
                     "trend": json.dumps({"2025": {"label": None, "log2_sr": 0.1, "ci_low": -1.0, "ci_high": 1.2,
                                                  "q": 0.9}}),
                     "title_only_share": 0.0})
    pd.DataFrame(rows).to_parquet(derived / "clusters.parquet", index=False)
    pd.DataFrame([{"region_id": r, "label": f"r{r}", "terms": [f"r{r}"], "size": 10, "x": .5, "y": .5,
                   "x3": .5, "y3": .5, "z3": .5} for r in (0, 1)]).to_parquet(derived / "regions.parquet", index=False)


@pytest.fixture
def exported(config, tmp_path):
    session = FakeSession(fixture_works(), page_size=100)
    oa = OpenAlex(session=session, cache_dir=config.data_dir / "cache" / "openalex", max_rps=None, api_key=None)
    sweep = run_sweep(config, oa=oa, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    run_detect(sweep, config)
    write_brief(sweep, config)
    fake_map(sweep)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    report = run_export(sweep, config, out_a, now=datetime(2026, 10, 21, 8, tzinfo=timezone.utc))
    run_export(sweep, config, out_b, now=datetime(2026, 10, 22, 9, tzinfo=timezone.utc))
    return sweep, out_a, out_b, report


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_two_exports_identical_except_generated_at(exported):
    _, a, b, _ = exported
    for name in ("points.json", "works.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    ba, bb = load(a / "bundle.json"), load(b / "bundle.json")
    assert ba["generated_at"] != bb["generated_at"]
    ba.pop("generated_at"), bb.pop("generated_at")
    assert ba == bb


def test_sizes_reported_and_within_targets(exported):
    _, _, _, report = exported
    assert set(report["sizes_mb"]) == {"points.json", "works.json", "bundle.json"}
    assert report["warnings"] == []


def test_points_and_works_are_aligned_and_sorted(exported):
    _, a, _, _ = exported
    points, works = load(a / "points.json"), load(a / "works.json")
    n = points["n"]
    assert n == 400 and all(len(points[k]) == n for k in ("x", "y", "x3", "y3", "z3", "year", "cluster", "region"))
    assert works["id"] == sorted(works["id"]) and len(works["title"]) == n
    assert all(0 <= v <= 1 for v in points["z3"])
    assert works["topics"] == sorted(works["topics"]) and max(works["topic"]) < len(works["topics"])


def test_every_work_idx_resolves(exported):
    _, a, _, _ = exported
    bundle, works = load(a / "bundle.json"), load(a / "works.json")
    n = len(works["id"])
    assert bundle["signals"]
    for s in bundle["signals"]:
        assert all(0 <= i < n for i in s["work_idx"] + s["top_work_idx"])
        assert s["c"] == len(s["work_idx"]) + s["n_unmapped"] or s["detector"] == "citations"
        assert sum(c["share"] for c in s["clusters"]) <= 1.0001
    t2 = next(s for s in bundle["signals"] if s["id"] == "topics:topic:T2:2025")
    assert {works["id"][i] for i in t2["work_idx"]} and t2["label"] == "RISING"


def test_bundle_structure(exported, config):
    _, a, _, _ = exported
    bundle = load(a / "bundle.json")
    assert bundle["schema_version"] == "research-signal-radar-bundle/0.1"
    meta = bundle["meta"]
    assert meta["cutoffs"] == [str(y) for y in range(2019, 2026)] and meta["config_hash"] == config.config_hash
    assert [s["label"] for s in meta["steps"]] == [str(y) for y in range(2016, 2026)]
    assert [s["is_cutoff"] for s in meta["steps"]] == [False] * 3 + [True] * 7
    assert {d["key"] for d in bundle["detectors"]} >= {"topics", "collaborations"}
    key = "topics|topic|2025"
    volcano = bundle["volcano"][key]
    assert len(volcano["log2_sr"]) == len(volcano["q"]) == len(volcano["signal_idx"]) == volcano["n_tested"]
    hit = [i for i in volcano["signal_idx"] if i >= 0]
    assert hit and all(bundle["signals"][i]["cutoff"] == "2025" for i in hit)
    assert bundle["clusters"][0]["cluster"] == -1 and isinstance(bundle["clusters"][1]["trend"], dict)
    assert bundle["brief_md"].startswith("# ") and bundle["diff"] is None


def test_volcano_sampling_keeps_all_signals():
    from radar.export import VOLCANO_MAX, _volcano
    n = VOLCANO_MAX + 500
    q = np.linspace(0.0001, 1, n)
    frame = pd.DataFrame({"detector": "citations", "level": "work", "cutoff": "2025",
                          "entity_id": [f"W{i}" for i in range(n)], "log2_sr": 1.0, "q": q,
                          "is_signal": False})
    frame.loc[n - 1, "is_signal"] = True  # a signal with a high q must survive the sampling
    signal_index = {f"citations:work:W{n - 1}:2025": 0}
    v = _volcano(frame, signal_index)["citations|work|2025"]
    assert v["n_tested"] == n and v["sampled"] and len(v["q"]) == VOLCANO_MAX
    assert v["signal_idx"].count(0) == 1
