"""`radar export`: the static data bundle read by the UI (specs/06 §2)."""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .config import Config
from .engine import cutoffs

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "research-signal-radar-bundle/0.1"
DETECTOR_ORDER = ["topics", "citations", "collaborations"]
VOLCANO_MAX = 3000
TARGET_MB = {"points.json": 5, "works.json": 15, "bundle.json": 8}
QUALITY_KEYS = ["works", "works_per_year", "abstract_share", "abstract_share_per_year", "publication_date_missing",
                "counts_by_year_coverage", "anchor_materialized_share", "authorships_null_institution_share",
                "distinct"]


def _num(value, digits=None):
    """JSON-safe number: numpy → Python, NaN → None, optional rounding."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, digits) if digits is not None else value
    return value


def _sig(value, digits=4):
    """Round to significant digits (q-values span many orders of magnitude)."""
    value = _num(value)
    if value is None or value == 0:
        return value
    return float(f"{value:.{digits}g}")


def _plain(obj):
    """Recursively convert numpy containers/scalars to JSON-ready Python objects."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (np.integer, np.floating, float)):
        return _num(obj)
    if obj is pd.NA:
        return None
    return obj


def _dump(path: Path, data) -> int:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _steps(config: Config) -> list[dict]:
    u, p = config.universe, config.periods
    cut_months = {c.month for c in cutoffs(u.first_year, u.last_year, p.mode, p.window_months, p.baseline_months)}
    size = 12 if p.mode == "year" else 6
    steps = []
    for start in range(0, (u.last_year - u.first_year + 1) * 12, size):
        year = u.first_year + start // 12
        label = str(year) if p.mode == "year" else f"{year}-H{1 + (start % 12) // 6}"
        end = start + size - 1
        steps.append({"label": label, "start_month": start, "end_month": end, "is_cutoff": end in cut_months})
    return steps


def _points(map_points: pd.DataFrame) -> dict:
    return {
        "n": int(len(map_points)),
        **{axis: [round(float(v), 4) for v in map_points[axis]] for axis in ("x", "y", "x3", "y3", "z3")},
        "year": [int(v) for v in map_points["year"]],
        "pub_month": [int(v) for v in map_points["pub_month"]],
        "cluster": [int(v) for v in map_points["cluster"]],
        "region": [int(v) for v in map_points["region_id"]],
        "has_abstract": [1 if bool(v) else 0 for v in map_points["has_abstract"].fillna(False)],
    }


def _works(map_points: pd.DataFrame, works: pd.DataFrame) -> dict:
    w = map_points[["work_id"]].merge(works, on="work_id", how="left")
    topics = sorted(w["primary_topic"].dropna().unique())
    subfields = sorted(w["subfield"].dropna().unique())
    topic_idx = {t: i for i, t in enumerate(topics)}
    subfield_idx = {s: i for i, s in enumerate(subfields)}
    return {
        "id": w["work_id"].tolist(),
        "title": [None if pd.isna(t) else str(t) for t in w["title"]],
        "year": [None if pd.isna(y) else int(y) for y in w["publication_year"]],
        "doi": [None if pd.isna(d) else str(d) for d in w["doi"]],
        "cited_by_count": [0 if pd.isna(c) else int(c) for c in w["cited_by_count"]],
        "topic": [topic_idx.get(t, -1) if not pd.isna(t) else -1 for t in w["primary_topic"]],
        "subfield": [subfield_idx.get(s, -1) if not pd.isna(s) else -1 for s in w["subfield"]],
        "topics": topics,
        "subfields": subfields,
    }


def _signals(signals: pd.DataFrame, point_of: dict, cluster_of: np.ndarray) -> list[dict]:
    order = {d: i for i, d in enumerate(DETECTOR_ORDER)}
    signals = signals.assign(_d=signals["detector"].map(order)).sort_values(
        ["_d", "level", "cutoff", "rank", "q", "signal_id"], ascending=[True, True, True, False, True, True],
        kind="mergesort")
    out = []
    for s in signals.itertuples():
        work_ids = list(s.work_ids_current)
        idx = sorted(point_of[w] for w in work_ids if w in point_of)
        clusters = pd.Series(cluster_of[idx]).value_counts() if idx else pd.Series(dtype=int)
        clusters = clusters.sort_index().sort_values(ascending=False, kind="mergesort").head(3)
        out.append({
            "id": s.signal_id, "detector": s.detector, "level": s.level, "cutoff": s.cutoff,
            "entity": {"id": s.entity_id, "label": _num(s.entity_label),
                       "parent_id": _num(s.parent_id), "parent_label": _num(s.parent_label)},
            "label": s.label, "returning": bool(s.returning),
            "c": int(s.c), "b": int(s.b), "C": int(s.C), "B": int(s.B),
            "share_c": _sig(s.share_c, 5), "share_b": _sig(s.share_b, 5),
            "log2_sr": _num(s.log2_sr, 4), "ci_low": _num(s.ci_low, 4), "ci_high": _num(s.ci_high, 4),
            "p": _sig(s.p), "q": _sig(s.q), "rank": _num(s.rank, 4),
            "why": s.why,
            "series": _plain(list(s.series)),
            "work_idx": idx,
            "n_unmapped": len(work_ids) - len(idx),
            "top_work_idx": [point_of[w] for w in s.top_work_ids if w in point_of],
            "clusters": [{"cluster": int(c), "share": round(int(n) / len(idx), 3)} for c, n in clusters.items()],
            "extra": _plain(json.loads(s.extra) if isinstance(s.extra, str) and s.extra else {}),
        })
    return out


def _volcano(assessments: pd.DataFrame, signal_index: dict) -> dict:
    out = {}
    for (detector, level, cutoff), group in assessments.groupby(["detector", "level", "cutoff"], sort=True):
        tested = len(group)
        group = group.sort_values(["q", "entity_id"], kind="mergesort")
        if tested > VOLCANO_MAX:
            hits = group[group["is_signal"]]
            rest = group[~group["is_signal"]].head(max(0, VOLCANO_MAX - len(hits)))
            group = pd.concat([hits, rest]).sort_values(["q", "entity_id"], kind="mergesort")
        key = f"{detector}|{level}|{cutoff}"
        out[key] = {
            "n_tested": tested,
            "sampled": tested > len(group),
            "log2_sr": [_num(v, 4) for v in group["log2_sr"]],
            "q": [_sig(v) for v in group["q"]],
            "signal_idx": [signal_index.get(f"{detector}:{level}:{e}:{cutoff}", -1) for e in group["entity_id"]],
        }
    return out


def _detectors(summary: dict) -> list[dict]:
    result = []
    for key in DETECTOR_ORDER:
        runs = [r for r in summary["runs"] if r["detector"] == key]
        if not runs:
            continue
        levels = list(dict.fromkeys(r["level"] for r in runs))
        per_cutoff: dict = {}
        for r in runs:
            per_cutoff.setdefault(r["cutoff"], {})[r["level"]] = {
                "seen": r["seen"], "tested": r["tested"],
                **{label: r["signals"].get(label, 0) for label in ("NEW", "RISING", "FALLING", "GONE")},
            }
        entry = {"key": key, "levels": levels, "summary": per_cutoff}
        if key == "citations":
            entry["skipped"] = {s["cutoff"]: s["reason"] for s in summary.get("citation_cutoffs_skipped", [])}
        result.append(entry)
    return result


def _clusters(clusters: pd.DataFrame) -> list[dict]:
    rows = []
    for c in clusters.sort_values("cluster").itertuples():
        rows.append({
            "cluster": int(c.cluster), "region_id": int(c.region_id), "label": c.label, "terms": list(c.terms),
            "size": int(c.size),
            **{axis: round(float(getattr(c, axis)), 4) for axis in ("x", "y", "x3", "y3", "z3")},
            "counts_by_year": json.loads(c.counts_by_year), "top_topics": _plain(list(c.top_topics)),
            "top_subfields": _plain(list(c.top_subfields)), "trend": json.loads(c.trend),
            "title_only_share": _num(c.title_only_share, 3),
        })
    return rows


def _regions(regions: pd.DataFrame) -> list[dict]:
    return [{
        "region_id": int(r.region_id), "label": r.label, "terms": list(r.terms), "size": _num(r.size),
        **{axis: _num(getattr(r, axis), 4) for axis in ("x", "y", "x3", "y3", "z3")},
    } for r in regions.sort_values("region_id").itertuples()]


def run_export(sweep_dir: Path, config: Config, out_dir: Path, now: datetime | None = None) -> dict:
    sweep_dir, out_dir = Path(sweep_dir), Path(out_dir)
    derived = sweep_dir / "derived"
    read_json = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    manifest = read_json(sweep_dir / "manifest.json")
    quality = read_json(sweep_dir / "quality.json")
    summary = read_json(derived / "detect_summary.json")
    semantic = read_json(derived / "semantic_meta.json") if (derived / "semantic_meta.json").exists() else {}

    map_points = pd.read_parquet(derived / "map_points.parquet").sort_values("work_id", kind="mergesort")
    map_points = map_points.reset_index(drop=True)
    point_of = {w: i for i, w in enumerate(map_points["work_id"])}
    works = pd.read_parquet(sweep_dir / "works.parquet", columns=[
        "work_id", "title", "publication_year", "doi", "cited_by_count", "primary_topic", "subfield"])
    signals = _signals(pd.read_parquet(derived / "signals.parquet"), point_of, map_points["cluster"].to_numpy())
    signal_index = {s["id"]: i for i, s in enumerate(signals)}

    u, p, e = config.universe, config.periods, config.engine
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "meta": {
            "universe": manifest["universe"], "sweep_id": manifest["sweep_id"],
            "observed_at": manifest["observed_at"], "n_works": manifest["harvested_count"],
            "n_mapped": int(len(map_points)), "years": [u.first_year, u.last_year], "period_mode": p.mode,
            "steps": _steps(config), "cutoffs": summary["cutoffs"],
            "params": {"alpha": e.alpha, "min_log2_ratio": e.min_log2_ratio, "window_months": p.window_months,
                       "baseline_months": p.baseline_months, **summary["parameters"]},
            "config_hash": config.config_hash, "radar_version": __version__,
        },
        "quality": {**{k: quality[k] for k in QUALITY_KEYS if k in quality},
                    "jan1_share": quality.get("jan1", {}).get("share"),
                    "consortium_works_excluded": summary.get("consortium_works_excluded"),
                    "semantic": {**semantic.get("map", {}), "embed": semantic.get("embed", {})}},
        "detectors": _detectors(summary),
        "signals": signals,
        "volcano": _volcano(pd.read_parquet(derived / "assessments.parquet"), signal_index),
        "clusters": _clusters(pd.read_parquet(derived / "clusters.parquet")),
        "regions": _regions(pd.read_parquet(derived / "regions.parquet")),
        "diff": read_json(sweep_dir / "diff.json") if (sweep_dir / "diff.json").exists() else None,
        "brief_md": (derived / "brief.md").read_text(encoding="utf-8") if (derived / "brief.md").exists() else "",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {
        "points.json": _dump(out_dir / "points.json", _points(map_points)),
        "works.json": _dump(out_dir / "works.json", _works(map_points, works)),
        "bundle.json": _dump(out_dir / "bundle.json", _plain(bundle)),
    }
    report = {"out_dir": str(out_dir), "signals": len(signals),
              "sizes_mb": {k: round(v / 1e6, 2) for k, v in sizes.items()}, "warnings": []}
    for name, size in sizes.items():
        if size > TARGET_MB[name] * 1e6:
            report["warnings"].append(f"{name} is {size / 1e6:.1f} MB (target < {TARGET_MB[name]} MB)")
    for w in report["warnings"]:
        logger.warning(w)
    return report
