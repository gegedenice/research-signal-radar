"""`radar map`: BERTopic clusters, 2-D and 3-D coordinates, regions, taxonomy link, trend (specs/05 §4–§6)."""

import json
import logging
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
from bertopic import BERTopic
from bertopic.vectorizers import ClassTfidfTransformer
from hdbscan import HDBSCAN
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP

from ..config import Config
from ..engine import assess, cutoffs

logger = logging.getLogger(__name__)

STOPWORD_DIR = Path(__file__).parent / "stopwords"
TOKEN_PATTERN = r"(?u)\b[^\W\d_]{3,}\b"
OUTLIER_THRESHOLD = 0.5


def stopwords(extra: list[str]) -> list[str]:
    words = set(w.lower() for w in extra)
    for path in sorted(STOPWORD_DIR.glob("*.txt")):
        words |= {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    return sorted(words)


def make_vectorizer(words: list[str], min_df: int = 1, max_df: float = 0.5) -> CountVectorizer:
    # BERTopic fits this vectorizer on one concatenated document per cluster, so df counts clusters:
    # min_df=1 keeps terms specific to a single cluster (the most telling ones), max_df=0.5 drops
    # terms found in more than half of the clusters.
    return CountVectorizer(stop_words=words, ngram_range=(1, 2), min_df=min_df, max_df=max_df,
                           token_pattern=TOKEN_PATTERN)


def rescale_axes(coords: np.ndarray) -> np.ndarray:
    """2-D: each axis to [0, 1] (specs/05 §4.2)."""
    low, high = coords.min(axis=0), coords.max(axis=0)
    return (coords - low) / np.where(high > low, high - low, 1)


def rescale_uniform(coords: np.ndarray) -> np.ndarray:
    """3-D: one factor for all axes, the largest range spans [0, 1], the others are centred."""
    low, high = coords.min(axis=0), coords.max(axis=0)
    span = float((high - low).max()) or 1.0
    scaled = (coords - low) / span
    return scaled + (1 - scaled.max(axis=0)) / 2


def _terms(model: BERTopic, cluster: int, n: int = 10) -> list[str]:
    topic = model.get_topic(cluster) or []
    return [term for term, _ in topic[:n] if term]


def _top_shares(frame: pd.DataFrame, id_col: str, label_col: str, n: int = 3) -> list[dict]:
    counts = frame.groupby([id_col, label_col]).size().sort_values(ascending=False).head(n)
    total = len(frame)
    return [{"id": i, "label": label, "share": round(int(v) / total, 3)} for (i, label), v in counts.items()]


def _regions(vectors, clusters, docs, n_regions, words):
    """Agglomerative grouping of cluster centroids, labelled by c-TF-IDF over concatenated documents."""
    ids = sorted(c for c in set(clusters) if c != -1)
    if not ids:
        return {}, pd.DataFrame(columns=["region_id", "label", "terms"])
    centroids = np.stack([vectors[clusters == c].mean(axis=0) for c in ids])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    if len(ids) > 1:
        k = min(n_regions, len(ids))
        groups = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(centroids)
    else:
        groups = np.zeros(1, dtype=int)
    region_of = dict(zip(ids, (int(g) for g in groups)))
    region_ids = sorted(set(region_of.values()))
    region_docs = []
    doc_regions = np.array([region_of.get(c, -1) for c in clusters])
    for r in region_ids:
        region_docs.append(" ".join(d for d, keep in zip(docs, doc_regions == r) if keep))
    vectorizer = make_vectorizer(words, min_df=1, max_df=1.0)
    counts = vectorizer.fit_transform(region_docs)
    weights = ClassTfidfTransformer(reduce_frequent_words=True).fit_transform(counts).toarray()
    vocab = np.array(vectorizer.get_feature_names_out())
    rows = []
    for r, w in zip(region_ids, weights):
        terms = [str(t) for t in vocab[np.argsort(-w)[:10]] if t]
        rows.append({"region_id": r, "label": " · ".join(terms[:3]), "terms": terms})
    return region_of, pd.DataFrame(rows)


def cluster_trends(points: pd.DataFrame, config: Config) -> dict:
    """Engine trend per cluster and cutoff; denominators = all mapped works (outliers included)."""
    u, p = config.universe, config.periods
    trends: dict = {}
    months = points["pub_month"]
    for cut in cutoffs(u.first_year, u.last_year, p.mode, p.window_months, p.baseline_months):
        cur = months.between(cut.current.start, cut.current.stop - 1)
        base = months.between(cut.baseline.start, cut.baseline.stop - 1)
        before = months < cut.baseline.start
        grouped = points.assign(c=cur, b=base, history_before=before)[points["cluster"] != -1] \
            .groupby("cluster")[["c", "b", "history_before"]].sum().astype(int)
        grouped = grouped[(grouped.c + grouped.b) > 0]
        if grouped.empty:
            continue
        frame = grouped.reset_index().rename(columns={"cluster": "entity_id"})
        frame["C"], frame["B"] = int(cur.sum()), int(base.sum())
        out = assess(frame, alpha=config.engine.alpha, min_log2_ratio=config.engine.min_log2_ratio)
        for r in out.itertuples():
            trends.setdefault(int(r.entity_id), {})[cut.label] = {
                "label": r.label, "log2_sr": round(float(r.log2_sr), 4), "ci_low": round(float(r.ci_low), 4),
                "ci_high": round(float(r.ci_high), 4), "q": float(r.q),
            }
    return trends


def run_map(sweep_dir: Path, config: Config) -> dict:
    started = time.monotonic()
    sweep_dir = Path(sweep_dir)
    sem = config.semantic
    seed = sem.random_state
    derived = sweep_dir / "derived"

    emb = pd.read_parquet(derived / "embeddings.parquet")
    works = pd.read_parquet(sweep_dir / "works.parquet", columns=[
        "work_id", "text_for_embedding", "publication_year", "pub_month", "primary_topic_id", "primary_topic",
        "subfield_id", "subfield"])
    data = emb.drop(columns=["text_hash"]).merge(works, on="work_id", how="left")
    vectors = np.stack(data["vector"].to_numpy()).astype(np.float32)
    docs = data["text_for_embedding"].fillna("").tolist()
    words = stopwords(sem.extra_stopwords)
    logger.info("map: %d works, %d-d vectors", len(data), vectors.shape[1])

    vectorizer = make_vectorizer(words)
    model = BERTopic(
        embedding_model=None,
        umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=seed),
        hdbscan_model=HDBSCAN(min_cluster_size=sem.min_cluster_size, min_samples=10, metric="euclidean",
                              cluster_selection_method="eom", prediction_data=True),
        vectorizer_model=vectorizer,
        ctfidf_model=ClassTfidfTransformer(reduce_frequent_words=True),
        calculate_probabilities=False,
    )
    raw, _ = model.fit_transform(docs, embeddings=vectors)
    raw = np.asarray(raw)
    outlier_before = float((raw == -1).mean())
    if (raw == -1).any() and (raw != -1).any():
        cluster = np.asarray(model.reduce_outliers(docs, raw.tolist(), strategy="embeddings",
                                                   embeddings=vectors, threshold=OUTLIER_THRESHOLD))
        model.update_topics(docs, topics=cluster.tolist(), vectorizer_model=vectorizer)
    else:
        cluster = raw.copy()
    outlier_after = float((cluster == -1).mean())
    logger.info("clusters: %d, outliers %.1f%% → %.1f%%", len(set(cluster) - {-1}),
                100 * outlier_before, 100 * outlier_after)

    logger.info("UMAP 2-D")
    reducer2 = UMAP(n_neighbors=15, n_components=2, min_dist=0.1, metric="cosine", random_state=seed)
    xy = rescale_axes(reducer2.fit_transform(vectors))
    logger.info("UMAP 3-D")
    reducer3 = UMAP(n_neighbors=15, n_components=3, min_dist=0.1, metric="cosine", random_state=seed)
    xyz = rescale_uniform(reducer3.fit_transform(vectors))

    region_of, regions = _regions(vectors, cluster, docs, sem.n_regions, words)
    points = pd.DataFrame({
        "work_id": data["work_id"], "x": xy[:, 0], "y": xy[:, 1],
        "x3": xyz[:, 0], "y3": xyz[:, 1], "z3": xyz[:, 2],
        "cluster": cluster.astype(int), "cluster_raw": raw.astype(int),
        "region_id": [region_of.get(int(c), -1) for c in cluster],
        "year": data["publication_year"], "pub_month": data["pub_month"],
        "has_abstract": data["has_abstract"], "primary_topic_id": data["primary_topic_id"],
        "subfield_id": data["subfield_id"],
    })

    years = list(range(config.universe.first_year, config.universe.last_year + 1))
    trends = cluster_trends(points, config)
    meta_data = data.assign(cluster=cluster)
    rows = []
    for c, group in points.groupby("cluster"):
        members = meta_data[meta_data["cluster"] == c]
        terms = _terms(model, int(c)) if c != -1 else []
        counts = group["year"].value_counts()
        rows.append({
            "cluster": int(c), "region_id": region_of.get(int(c), -1),
            "label": " · ".join(terms[:3]) if c != -1 else "unassigned", "terms": terms, "size": int(len(group)),
            "x": float(group.x.median()), "y": float(group.y.median()),
            "x3": float(group.x3.median()), "y3": float(group.y3.median()), "z3": float(group.z3.median()),
            "counts_by_year": json.dumps({str(y): int(counts.get(y, 0)) for y in years}),
            "top_topics": _top_shares(members.dropna(subset=["primary_topic_id"]), "primary_topic_id", "primary_topic"),
            "top_subfields": _top_shares(members.dropna(subset=["subfield_id"]), "subfield_id", "subfield"),
            "trend": json.dumps(trends.get(int(c), {})),
            "title_only_share": round(float((~group["has_abstract"].fillna(False).astype(bool)).mean()), 3),
        })
    clusters = pd.DataFrame(rows)

    if len(regions):
        stats = points[points.region_id != -1].groupby("region_id").agg(
            size=("work_id", "size"), x=("x", "median"), y=("y", "median"),
            x3=("x3", "median"), y3=("y3", "median"), z3=("z3", "median")).reset_index()
        regions = regions.merge(stats, on="region_id", how="left")

    points.to_parquet(derived / "map_points.parquet", index=False)
    clusters.to_parquet(derived / "clusters.parquet", index=False)
    regions.to_parquet(derived / "regions.parquet", index=False)
    model_dir = derived / "semantic_model"
    model_dir.mkdir(exist_ok=True)
    model.save(str(model_dir / "bertopic"), serialization="safetensors", save_ctfidf=True)
    for name, reducer in (("umap_2d.pkl", reducer2), ("umap_3d.pkl", reducer3)):
        with open(model_dir / name, "wb") as fh:
            pickle.dump(reducer, fh)

    real = clusters[clusters.cluster != -1]
    top1 = [t[0]["share"] for t in real["top_topics"] if len(t)]
    quality = {
        "outlier_share_before": round(outlier_before, 4),
        "outlier_share_after": round(outlier_after, 4),
        "largest_cluster_share": round(float(real["size"].max() / len(points)), 4) if len(real) else None,
        "clusters_mostly_title_only": real.loc[real.title_only_share > 0.5, "cluster"].astype(int).tolist(),
        "median_top1_topic_share": round(float(np.median(top1)), 3) if top1 else None,
    }
    warnings = []
    if quality["outlier_share_after"] > 0.25:
        warnings.append(f"outlier share after reduction {quality['outlier_share_after']:.1%} > 25%")
    if quality["largest_cluster_share"] and quality["largest_cluster_share"] > 0.10:
        warnings.append(f"largest cluster holds {quality['largest_cluster_share']:.1%} of works (> 10%): "
                        "probably a generic cluster, adjust stop words")
    if quality["clusters_mostly_title_only"]:
        warnings.append(f"{len(quality['clusters_mostly_title_only'])} clusters are > 50% title-only")
    for w in warnings:
        logger.warning(w)

    meta_path = derived / "semantic_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["map"] = {
        "points": int(len(points)),
        "clusters": int(len(real)),
        "regions": int(len(regions)),
        **quality,
        "warnings": warnings,
        "parameters": {"min_cluster_size": sem.min_cluster_size, "n_regions": sem.n_regions,
                       "random_state": seed, "outlier_threshold": OUTLIER_THRESHOLD,
                       "extra_stopwords": list(sem.extra_stopwords)},
        "seconds": round(time.monotonic() - started, 1),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta["map"]
