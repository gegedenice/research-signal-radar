import json

import numpy as np
import pandas as pd
import pytest

from radar.semantic.landscape import rescale_uniform, run_map, stopwords

VOCAB = [["rice", "paddy", "irrigation", "yield"], ["coral", "reef", "bleaching", "lagoon"],
         ["malaria", "mosquito", "vector", "parasite"], ["drought", "sahel", "rainfall", "monsoon"],
         ["fisheries", "tuna", "stock", "catch"]]


def synthetic_sweep(path, seed=0, per_blob=300):
    """5 well-separated Gaussian blobs, blob-specific vocabulary, spread over 2016–2025."""
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(5, 64)) * 4
    rows, vectors = [], []
    n = 0
    for k, words in enumerate(VOCAB):
        for i in range(per_blob):
            year = 2016 + int(rng.integers(0, 10))
            text = "Study of " + " ".join(rng.choice(words, 6)) + " using data and common methods"
            rows.append({"work_id": f"W{n}", "text_for_embedding": text, "publication_year": year,
                         "pub_month": (year - 2016) * 12 + int(rng.integers(0, 12)),
                         "primary_topic_id": f"T{k}", "primary_topic": f"Topic {k}",
                         "subfield_id": f"S{k}", "subfield": f"Subfield {k}", "has_abstract": i % 4 != 0})
            v = centers[k] + rng.normal(size=64)
            vectors.append(v / np.linalg.norm(v))
            n += 1
    path.mkdir(parents=True)
    works = pd.DataFrame(rows)
    works.drop(columns=["has_abstract"]).to_parquet(path / "works.parquet")
    (path / "derived").mkdir()
    pd.DataFrame({"work_id": works.work_id, "text_hash": works.work_id, "has_abstract": works.has_abstract,
                  "vector": [v.astype(np.float32) for v in vectors]}).to_parquet(path / "derived" / "embeddings.parquet")
    return works


@pytest.fixture(scope="module")
def mapped(tmp_path_factory):
    import tomllib
    from conftest import CONFIG_PATH
    from radar.config import parse_config
    table = tomllib.load(open(CONFIG_PATH, "rb"))
    config = parse_config(table)
    root = tmp_path_factory.mktemp("map")
    runs = []
    for name in ("a", "b"):
        sweep = root / name
        synthetic_sweep(sweep)
        meta = run_map(sweep, config)
        runs.append((sweep, meta))
    return runs


def test_five_clusters_with_blob_vocabulary(mapped):
    sweep, meta = mapped[0]
    clusters = pd.read_parquet(sweep / "derived" / "clusters.parquet")
    real = clusters[clusters.cluster != -1]
    assert len(real) == 5 and meta["clusters"] == 5
    found = [set(t) for t in real["terms"]]
    for words in VOCAB:
        assert any(set(words) & terms for terms in found)
    for label, terms in zip(real["label"], real["terms"]):
        assert label == " · ".join(terms[:3])
        assert "study" not in terms and "using" not in terms  # stop words
    assert all(t[0]["share"] == 1.0 for t in real["top_topics"])


def test_coordinates_counts_and_trend(mapped):
    sweep, meta = mapped[0]
    points = pd.read_parquet(sweep / "derived" / "map_points.parquet")
    assert len(points) == 1500 and meta["points"] == 1500
    for col in ("x", "y", "x3", "y3", "z3"):
        assert points[col].between(0, 1).all()
    assert points[["x", "y"]].min().tolist() == [0, 0] and points[["x", "y"]].max().tolist() == [1, 1]
    spans = (points[["x3", "y3", "z3"]].max() - points[["x3", "y3", "z3"]].min()).round(6)
    assert spans.max() == 1.0  # one factor for the three axes
    clusters = pd.read_parquet(sweep / "derived" / "clusters.parquet")
    total = sum(sum(json.loads(c).values()) for c in clusters["counts_by_year"])
    assert total == 1500
    trend = json.loads(clusters[clusters.cluster != -1]["trend"].iloc[0])
    assert set(trend) <= {str(y) for y in range(2019, 2026)} and trend
    assert {"label", "log2_sr", "ci_low", "ci_high", "q"} == set(next(iter(trend.values())))
    regions = pd.read_parquet(sweep / "derived" / "regions.parquet")
    assert 1 <= len(regions) <= 5 and {"x3", "y3", "z3", "label"} <= set(regions.columns)
    assert (sweep / "derived" / "semantic_model" / "umap_3d.pkl").exists()
    saved = json.loads((sweep / "derived" / "semantic_meta.json").read_text())["map"]
    assert saved["outlier_share_after"] <= saved["outlier_share_before"]


def test_determinism(mapped):
    (a, _), (b, _) = mapped
    pa = pd.read_parquet(a / "derived" / "map_points.parquet")
    pb = pd.read_parquet(b / "derived" / "map_points.parquet")
    assert (pa.cluster.to_numpy() == pb.cluster.to_numpy()).all()
    assert np.allclose(pa[["x", "y", "x3", "y3", "z3"]], pb[["x", "y", "x3", "y3", "z3"]])


def test_rescale_uniform_keeps_proportions():
    coords = np.array([[0, 0, 0], [10, 5, 2], [4, 1, 1]], dtype=float)
    out = rescale_uniform(coords)
    spans = out.max(axis=0) - out.min(axis=0)
    assert np.allclose(spans, [1.0, 0.5, 0.2])
    assert np.allclose(out.min(axis=0) + out.max(axis=0), 1.0)  # centred


def test_stopwords_cover_four_languages():
    words = set(stopwords(["Paper"]))
    assert {"the", "les", "los", "não", "paper"} <= words
