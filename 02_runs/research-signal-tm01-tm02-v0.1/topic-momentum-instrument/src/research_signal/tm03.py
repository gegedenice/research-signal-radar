from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .config import RunConfig
from .dates import month_distance
from .errors import InvariantError
from .storage import RunStore


@dataclass(frozen=True)
class TM03Result:
    scope_mode: str
    scope_dir: Path
    topic_count: int
    month_count: int
    evaluation_count: int
    quality_report_path: Path


def _parse_day(value: str) -> date:
    return date.fromisoformat(value)


def _validate_inputs(
    config: RunConfig,
    store: RunStore,
    scope_mode: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    required = [
        "query-manifest.json",
        "tm02-result.json",
        "quality/tm02-quality-report.json",
        "census/topic-buckets.jsonl.gz",
        "census/bucket-summaries.json",
        "topics/topic-catalog.json",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"TM-03 requires completed TM-02 artifacts: {missing}")

    manifest = store.read_json("query-manifest.json")
    quality = store.read_json("quality/tm02-quality-report.json")
    if manifest["universe"]["scope_mode"] != scope_mode:
        raise InvariantError("TM-03 scope differs from query manifest")
    if manifest["from_publication_date"] != config.collection.from_publication_date.isoformat():
        raise InvariantError("TM-03 configuration start date differs from query manifest")
    if manifest["to_publication_date"] != config.collection.to_publication_date.isoformat():
        raise InvariantError("TM-03 configuration end date differs from query manifest")
    if not quality["all_group_pages_complete"] or not quality["all_group_totals_valid"]:
        raise InvariantError("TM-03 refuses an incomplete or inconsistent TM-02 census")

    snapshots = store.read_jsonl_gz("census/topic-buckets.jsonl.gz")
    summaries = store.read_json("census/bucket-summaries.json")
    catalog = store.read_json("topics/topic-catalog.json")
    return manifest, snapshots, summaries, catalog


def _validated_month_axis(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summaries:
        raise InvariantError("TM-03 received no monthly bucket summaries")
    ordered = sorted(summaries, key=lambda item: item["bucket"]["start"])
    starts: set[str] = set()
    for index, summary in enumerate(ordered):
        bucket = summary["bucket"]
        start = _parse_day(bucket["start"])
        if bucket["start"] in starts:
            raise InvariantError(f"duplicate monthly bucket: {bucket['start']}")
        starts.add(bucket["start"])
        if bucket["granularity"] != "month":
            raise InvariantError("TM-03 requires monthly TM-02 buckets")
        if index:
            previous = _parse_day(ordered[index - 1]["bucket"]["start"])
            if month_distance(previous, start) != 1:
                raise InvariantError(
                    f"monthly axis is not contiguous: {previous.isoformat()} -> {start.isoformat()}"
                )
        if (
            summary["classified_works_count"] + summary["unclassified_count"]
            != summary["included_works_count"]
        ):
            raise InvariantError(f"{bucket['start']}: invalid TM-02 group total")
    return ordered


def _window(months: list[dict[str, Any]]) -> dict[str, Any]:
    topic_count = sum(item["count"] for item in months)
    classified_total = sum(item["classified_total"] for item in months)
    included_total = sum(item["included_total"] for item in months)
    return {
        "from": months[0]["start"],
        "to": months[-1]["end"],
        "months": len(months),
        "is_complete": all(item["is_complete"] for item in months),
        "topic_count": topic_count,
        "classified_works_count": classified_total,
        "included_works_count": included_total,
        "topic_share": round(topic_count / classified_total, 12)
        if classified_total
        else 0.0,
        "topic_coverage": round(classified_total / included_total, 12)
        if included_total
        else 1.0,
        "active_months": sum(1 for item in months if item["count"] > 0),
    }


def _evaluation_endpoints(
    summaries: list[dict[str, Any]], window_months: int, step_months: int
) -> list[int]:
    last_complete_index = max(
        (
            index
            for index, summary in enumerate(summaries)
            if summary["bucket"]["is_complete"]
        ),
        default=-1,
    )
    endpoints = list(range(last_complete_index, window_months - 2, -step_months))
    endpoints.reverse()
    return endpoints


def _rolling_windows(
    month_points: list[dict[str, Any]], endpoints: list[int], window_months: int
) -> list[dict[str, Any]]:
    rolling = []
    for endpoint in endpoints:
        members = month_points[endpoint - window_months + 1 : endpoint + 1]
        value = _window(members)
        value["evaluation_date"] = value["to"]
        rolling.append(value)
    return rolling


def _unit_identity(level: str, topic: dict[str, Any]) -> dict[str, Any]:
    """Bloc identité 'topic-shaped' pour un niveau parent de la taxonomie.

    Sans ``created_date`` : _taxonomy_change() (TM-04) renverra donc False, ce qui
    est correct pour des IDs de subfield/field stables.
    """
    node = topic[level]
    identity: dict[str, Any] = {
        "id": node["id"],
        "display_name": node["display_name"],
        "level": level,
    }
    if level == "subfield":
        identity["field"] = topic.get("field")
        identity["domain"] = topic.get("domain")
    elif level == "field":
        identity["domain"] = topic.get("domain")
    return identity


def _calendar_profile(summaries: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    by_month: dict[int, list[int]] = {month: [] for month in range(1, 13)}
    for summary in summaries:
        if summary["bucket"]["is_complete"]:
            month = _parse_day(summary["bucket"]["start"]).month
            by_month[month].append(summary["included_works_count"])
    averages = {
        f"{month:02d}": round(sum(values) / len(values), 6) if values else None
        for month, values in by_month.items()
    }
    observed = [value for value in averages.values() if value is not None]
    typical = median(observed) if observed else 0.0
    january = averages["01"] or 0.0
    ratio = january / typical if typical else None
    warnings = []
    if len(summaries) >= 24 and ratio is not None and ratio >= 2.0:
        warnings.append("JANUARY_PUBLICATION_DATE_CONCENTRATION")
    return (
        {
            "average_included_works_by_month_of_year": averages,
            "january_to_monthly_median_ratio": round(ratio, 6) if ratio is not None else None,
            "diagnostic_threshold": 2.0,
        },
        warnings,
    )


def build_topic_series(
    config: RunConfig,
    manifest: dict[str, Any],
    snapshots: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    summaries = _validated_month_axis(summaries)
    summary_by_start = {item["bucket"]["start"]: item for item in summaries}

    catalog_by_id: dict[str, dict[str, Any]] = {}
    for item in catalog:
        if item["id"] in catalog_by_id:
            raise InvariantError(f"duplicate topic catalog entry: {item['id']}")
        catalog_by_id[item["id"]] = item

    snapshot_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in snapshots:
        key = (item["topic"]["id"], item["bucket"]["start"])
        if key in snapshot_by_key:
            raise InvariantError(f"duplicate topic bucket: {key}")
        if key[0] not in catalog_by_id:
            raise InvariantError(f"topic {key[0]} is absent from the catalog")
        summary = summary_by_start.get(key[1])
        if summary is None:
            raise InvariantError(f"topic bucket outside monthly axis: {key}")
        if item["classified_works_count"] != summary["classified_works_count"]:
            raise InvariantError(f"{key}: classified total differs from bucket summary")
        snapshot_by_key[key] = item

    window_months = config.topic_momentum.analysis_window_months
    step_months = config.topic_momentum.evaluation_step_months
    endpoints = _evaluation_endpoints(summaries, window_months, step_months)

    series: list[dict[str, Any]] = []
    for topic_id, topic in sorted(catalog_by_id.items()):
        month_points: list[dict[str, Any]] = []
        for summary in summaries:
            start = summary["bucket"]["start"]
            snapshot = snapshot_by_key.get((topic_id, start))
            count = snapshot["topic_count"] if snapshot else 0
            classified_total = summary["classified_works_count"]
            included_total = summary["included_works_count"]
            month_points.append(
                {
                    "start": start,
                    "end": summary["bucket"]["end"],
                    "is_complete": summary["bucket"]["is_complete"],
                    "count": count,
                    "share": round(count / classified_total, 12)
                    if classified_total
                    else 0.0,
                    "coverage": summary["topic_coverage"],
                    "classified_total": classified_total,
                    "included_total": included_total,
                    "zero_filled": snapshot is None,
                }
            )
        rolling = _rolling_windows(month_points, endpoints, window_months)
        series.append(
            {
                "schema_version": "topic-series/0.1",
                "run_id": manifest["run_id"],
                "query_manifest_ref": manifest["manifest_id"],
                "universe_id": manifest["universe"]["id"],
                "universe_version": manifest["universe"]["version"],
                "scope_mode": manifest["universe"]["scope_mode"],
                "stream_id": manifest["stream"]["id"],
                "topic": topic,
                "bucket_granularity": "month",
                "monthly": month_points,
                "rolling_windows": rolling,
            }
        )
    return series, [summaries[index]["bucket"]["end"] for index in endpoints]


def build_unit_series(
    level: str,
    config: RunConfig,
    manifest: dict[str, Any],
    snapshots: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Série mensuelle + fenêtres glissantes agrégées à un niveau parent.

    Réutilise la même mécanique que build_topic_series : le count d'une unité
    parente est la somme des counts des topics enfants ; les dénominateurs de
    portefeuille (classified/included/coverage) sont identiques à tous les niveaux.
    """
    summaries = _validated_month_axis(summaries)
    catalog_by_id = {item["id"]: item for item in catalog}

    counts: dict[tuple[str, str], int] = {}
    identities: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        topic_id = snapshot["topic"]["id"]
        topic = catalog_by_id.get(topic_id)
        if topic is None:
            raise InvariantError(
                f"topic {topic_id} absent from catalog during {level} aggregation"
            )
        node = topic.get(level)
        if node and node.get("id"):
            unit_id = node["id"]
            identity = _unit_identity(level, topic)
        else:
            # Topic sans niveau parent résolu : regroupé sous une unité sentinelle
            # pour préserver l'invariant de masse plutôt que d'interrompre le run.
            unit_id = f"UNRESOLVED_{level.upper()}"
            identity = {
                "id": unit_id,
                "display_name": f"Unresolved {level}",
                "level": level,
                "unresolved": True,
            }
        start = snapshot["bucket"]["start"]
        counts[(unit_id, start)] = counts.get((unit_id, start), 0) + snapshot["topic_count"]
        identities.setdefault(unit_id, identity)

    window_months = config.topic_momentum.analysis_window_months
    step_months = config.topic_momentum.evaluation_step_months
    endpoints = _evaluation_endpoints(summaries, window_months, step_months)

    series: list[dict[str, Any]] = []
    for unit_id, identity in sorted(identities.items()):
        month_points: list[dict[str, Any]] = []
        for summary in summaries:
            start = summary["bucket"]["start"]
            count = counts.get((unit_id, start), 0)
            classified_total = summary["classified_works_count"]
            included_total = summary["included_works_count"]
            month_points.append(
                {
                    "start": start,
                    "end": summary["bucket"]["end"],
                    "is_complete": summary["bucket"]["is_complete"],
                    "count": count,
                    "share": round(count / classified_total, 12)
                    if classified_total
                    else 0.0,
                    "coverage": summary["topic_coverage"],
                    "classified_total": classified_total,
                    "included_total": included_total,
                    "zero_filled": (unit_id, start) not in counts,
                }
            )
        rolling = _rolling_windows(month_points, endpoints, window_months)
        series.append(
            {
                "schema_version": "unit-series/0.2",
                "run_id": manifest["run_id"],
                "query_manifest_ref": manifest["manifest_id"],
                "universe_id": manifest["universe"]["id"],
                "universe_version": manifest["universe"]["version"],
                "scope_mode": manifest["universe"]["scope_mode"],
                "stream_id": manifest["stream"]["id"],
                "level": level,
                "topic": identity,
                "bucket_granularity": "month",
                "monthly": month_points,
                "rolling_windows": rolling,
            }
        )
    return series


def _assert_level_mass(
    level: str,
    unit_series: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> None:
    """Invariant : l'agrégation conserve la masse de la couche topic.

    Σ_units count(unit, m) == Σ_topics count(topic, m), pour chaque mois. Comme
    chaque topic appartient à exactement un subfield / field, la somme des counts
    est identique à tous les niveaux. (Dans un census TM-02 valide, cette somme
    vaut aussi ``classified_works_count`` ; on ne s'appuie pas sur ce dénominateur
    ici pour valider uniquement le regroupement.)
    """
    expected: dict[str, int] = {}
    for snapshot in snapshots:
        start = snapshot["bucket"]["start"]
        expected[start] = expected.get(start, 0) + snapshot["topic_count"]
    observed: dict[str, int] = {}
    for item in unit_series:
        for month in item["monthly"]:
            observed[month["start"]] = observed.get(month["start"], 0) + month["count"]
    all_months = set(expected) | set(observed)
    for start in all_months:
        if observed.get(start, 0) != expected.get(start, 0):
            raise InvariantError(
                f"{level} mass mismatch at {start}: "
                f"{observed.get(start, 0)} != {expected.get(start, 0)}"
            )


def run_tm03(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM03Result:
    if resume and rebuild:
        raise InvariantError("TM-03 --resume and --rebuild are mutually exclusive")
    store = RunStore(run_dir / scope_mode)
    result_path = store.path("tm03-result.json")
    quality_path = store.path("quality/tm03-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm03-result.json")
        return TM03Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            topic_count=completed["topic_count"],
            month_count=completed["month_count"],
            evaluation_count=completed["evaluation_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-03 result already exists; use --resume to reuse it or --rebuild "
            "to regenerate TM-03 series and quality artifacts"
        )

    manifest, snapshots, summaries, catalog = _validate_inputs(
        config, store, scope_mode
    )
    series, evaluation_dates = build_topic_series(
        config, manifest, snapshots, summaries, catalog
    )
    ordered_summaries = _validated_month_axis(summaries)
    calendar_profile, warnings = _calendar_profile(ordered_summaries)

    series_path = store.write_jsonl_gz(
        "series/topic-series.jsonl.gz", series, overwrite=rebuild
    )
    zero_count = sum(
        1 for item in series for month in item["monthly"] if month["zero_filled"]
    )

    level_series_counts: dict[str, int] = {}
    if config.topic_momentum.multi_scale:
        for level in config.topic_momentum.scale_levels:
            unit_series = build_unit_series(
                level, config, manifest, snapshots, ordered_summaries, catalog
            )
            _assert_level_mass(level, unit_series, snapshots)
            store.write_jsonl_gz(
                f"series/{level}-series.jsonl.gz", unit_series, overwrite=rebuild
            )
            level_series_counts[level] = len(unit_series)
    quality = {
        "schema_version": "tm03-quality-report/0.1",
        "run_id": manifest["run_id"],
        "builder_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "topic_count": len(series),
        "month_count": len(ordered_summaries),
        "dense_topic_month_count": len(series) * len(ordered_summaries),
        "explicit_zero_count": zero_count,
        "multi_scale": config.topic_momentum.multi_scale,
        "level_series_counts": level_series_counts,
        "evaluation_count": len(evaluation_dates),
        "evaluation_dates": evaluation_dates,
        "analysis_parameters": asdict(config.topic_momentum),
        "all_months_contiguous": True,
        "incomplete_months": [
            item["bucket"]["start"]
            for item in ordered_summaries
            if not item["bucket"]["is_complete"]
        ],
        "calendar_profile": calendar_profile,
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/tm03-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm03-result/0.1",
        "scope_mode": scope_mode,
        "builder_version": f"research-signal-instrument/{__version__}",
        "topic_count": len(series),
        "month_count": len(ordered_summaries),
        "evaluation_count": len(evaluation_dates),
        "outputs": {
            "topic_series": str(series_path.relative_to(store.root)),
            "quality_report": str(quality_path.relative_to(store.root)),
        },
    }
    store.write_json("tm03-result.json", result, overwrite=rebuild)
    return TM03Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        topic_count=len(series),
        month_count=len(ordered_summaries),
        evaluation_count=len(evaluation_dates),
        quality_report_path=quality_path,
    )
