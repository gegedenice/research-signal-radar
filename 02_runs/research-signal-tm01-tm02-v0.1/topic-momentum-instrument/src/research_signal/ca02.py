from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .config import CitationAccelerationConfig, RunConfig
from .dates import add_months, month_distance, month_end
from .errors import InvariantError
from .storage import RunStore, sha256_json


@dataclass(frozen=True)
class CA02Result:
    scope_mode: str
    scope_dir: Path
    assessment_count: int
    eligible_count: int
    abstained_count: int
    cohort_count: int
    quality_report_path: Path


def _windows(cutoff: date, window_months: int) -> dict[str, dict[str, str | int]]:
    cutoff_month_start = date(cutoff.year, cutoff.month, 1)
    current_start = add_months(cutoff_month_start, -(window_months - 1))
    previous_start = add_months(current_start, -window_months)
    previous_end = current_start - timedelta(days=1)
    return {
        "previous": {
            "from": previous_start.isoformat(),
            "to": previous_end.isoformat(),
            "from_month": previous_start.strftime("%Y-%m"),
            "to_month": previous_end.strftime("%Y-%m"),
            "months": window_months,
        },
        "current": {
            "from": current_start.isoformat(),
            "to": cutoff.isoformat(),
            "from_month": current_start.strftime("%Y-%m"),
            "to_month": cutoff.strftime("%Y-%m"),
            "months": window_months,
        },
    }


def _age_months(publication_date: str, cutoff: date) -> int:
    published = date.fromisoformat(publication_date)
    months = month_distance(published, cutoff)
    if cutoff.day < published.day:
        months -= 1
    return max(months, 0)


def _age_band(age_months: int, boundaries: tuple[int, ...]) -> str:
    lower = 12
    for upper in boundaries:
        if age_months < upper:
            return f"{lower}-{upper - 1}m"
        lower = upper
    return f"{lower}m+"


def _metric_counts(
    events: list[dict[str, Any]], windows: dict[str, dict[str, str | int]]
) -> dict[str, Any]:
    counts = {
        "previous": 0,
        "current": 0,
        "previous_including_known_self_citations": 0,
        "current_including_known_self_citations": 0,
        "known_author_self_citations_previous": 0,
        "known_author_self_citations_current": 0,
        "post_cutoff_event_count": 0,
    }
    cutoff_month = str(windows["current"]["to_month"])
    for event in events:
        month = event.get("creation_month")
        if not month:
            continue
        if month > cutoff_month:
            counts["post_cutoff_event_count"] += 1
            continue
        period = None
        if windows["previous"]["from_month"] <= month <= windows["previous"]["to_month"]:
            period = "previous"
        elif windows["current"]["from_month"] <= month <= windows["current"]["to_month"]:
            period = "current"
        if period is None:
            continue
        counts[f"{period}_including_known_self_citations"] += 1
        if event.get("author_self_citation") == "yes":
            counts[f"known_author_self_citations_{period}"] += 1
        else:
            counts[period] += 1

    recent = counts["current"]
    previous = counts["previous"]
    recent_all = counts["current_including_known_self_citations"]
    previous_all = counts["previous_including_known_self_citations"]
    counts.update(
        {
            "absolute_delta": recent - previous,
            "acceleration_ratio": round((recent + 1) / (previous + 1), 12),
            "raw_acceleration": round(math.log1p(recent) - math.log1p(previous), 12),
            "absolute_delta_including_known_self_citations": recent_all - previous_all,
            "acceleration_ratio_including_known_self_citations": round(
                (recent_all + 1) / (previous_all + 1), 12
            ),
            "raw_acceleration_including_known_self_citations": round(
                math.log1p(recent_all) - math.log1p(previous_all), 12
            ),
        }
    )
    return counts


def _percentile(values: list[float], value: float) -> float:
    return round(sum(item <= value for item in values) / len(values), 12)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return round(ordered[index], 12)


def _cohort_keys(item: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    work_type = item["work_type"]
    age_band = item["age_band"]
    keys = []
    if item.get("topic_id"):
        keys.append(("primary_topic_age_type", work_type, age_band, item["topic_id"]))
    if item.get("subfield_id"):
        keys.append(("subfield_age_type", work_type, age_band, item["subfield_id"]))
    keys.append(("portfolio_age_type", work_type, age_band, "portfolio"))
    return keys


def _validate_inputs(
    store: RunStore,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    required = [
        "query-manifest.json",
        "ca01-result.json",
        "quality/ca01-quality-report.json",
        "observations/work-observations.jsonl.gz",
        "topics/topic-catalog.json",
        "citations/citation-events.jsonl.gz",
        "citations/work-citation-coverage.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"CA-02 requires completed CA-01.1 artifacts: {missing}")
    manifest = store.read_json("query-manifest.json")
    ca01_result = store.read_json("ca01-result.json")
    ca01_quality = store.read_json("quality/ca01-quality-report.json")
    if ca01_result.get("schema_version") != "ca01-result/0.2":
        raise InvariantError("CA-02 requires ca01-result/0.2; run ca01 --rebuild")
    if ca01_quality.get("schema_version") != "ca01-quality-report/0.2":
        raise InvariantError("CA-02 requires ca01-quality-report/0.2")
    if not ca01_quality.get("all_eligible_works_collected"):
        raise InvariantError("CA-02 refuses an incomplete CA-01 collection")
    works = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    catalog = store.read_json("topics/topic-catalog.json")
    events = store.read_jsonl_gz("citations/citation-events.jsonl.gz")
    coverage = store.read_jsonl_gz("citations/work-citation-coverage.jsonl.gz")
    if any(item.get("schema_version") != "citation-event-observation/0.2" for item in events):
        raise InvariantError("CA-02 requires citation-event-observation/0.2")
    if len(works) != len(coverage):
        raise InvariantError("CA-02 work and coverage populations differ")
    return manifest, works, catalog, events, coverage


def run_ca02(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> CA02Result:
    if resume and rebuild:
        raise InvariantError("CA-02 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    result_path = store.path("ca02-result.json")
    quality_path = store.path("quality/ca02-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("ca02-result.json")
        if completed.get("calculator_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError("CA-02 result was produced by another version; use --rebuild")
        return CA02Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            assessment_count=completed["assessment_count"],
            eligible_count=completed["eligible_count"],
            abstained_count=completed["abstained_count"],
            cohort_count=completed["cohort_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("CA-02 result already exists; use --resume or --rebuild")

    manifest, works, catalog, events, coverage = _validate_inputs(store)
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("CA-02 scope differs from query manifest")
    cutoff = config.collection.to_publication_date
    if cutoff != month_end(cutoff):
        raise InvariantError(
            "CA-02 requires a month-end information cutoff for month-precision events"
        )
    windows = _windows(cutoff, config.citation_acceleration.window_months)
    params = {
        "schema_version": "citation-acceleration-parameters/0.1",
        "detector_stage": "CA-02",
        "information_cutoff": cutoff.isoformat(),
        "temporal_semantics": config.temporal_semantics,
        "parameters": asdict(config.citation_acceleration),
        "windows": windows,
        "input_hashes": {
            "work_observations": sha256_json(works),
            "citation_events": sha256_json(events),
            "work_coverage": sha256_json(coverage),
        },
    }
    params["parameter_fingerprint"] = sha256_json(params)

    work_by_id = {item["work_id"]: item for item in works}
    if len(work_by_id) != len(works):
        raise InvariantError("CA-02 received duplicate WorkObservation IDs")
    coverage_by_id = {item["work_id"]: item for item in coverage}
    if set(work_by_id) != set(coverage_by_id):
        raise InvariantError("CA-02 work and coverage IDs differ")
    events_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        work_id = event["cited_work_id"]
        if work_id not in work_by_id:
            raise InvariantError(f"CA-02 citation event refers to unknown work {work_id}")
        events_by_work[work_id].append(event)
    topic_catalog = {item["id"]: item for item in catalog}

    prepared: dict[str, dict[str, Any]] = {}
    for work_id, work in work_by_id.items():
        work_coverage = coverage_by_id[work_id]
        status = work_coverage["eligibility_status"]
        reasons: list[str] = []
        if status != "COLLECTED":
            reasons.append(status)
        row_count = work_coverage.get("opencitations_event_row_count")
        usable_count = work_coverage.get("monthly_usable_event_count")
        temporal_coverage = None
        if status == "COLLECTED":
            row_count = int(row_count or 0)
            usable_count = int(usable_count or 0)
            temporal_coverage = usable_count / row_count if row_count else 1.0
            if work_coverage.get("count_matches_event_rows") is False:
                reasons.append("OPENCITATIONS_COUNT_ROW_MISMATCH")
            if (
                int(work_coverage.get("opencitations_citation_count") or 0) == 0
                and int(work_coverage.get("openalex_cited_by_count") or 0) > 0
            ):
                reasons.append("OPENCITATIONS_UNAVAILABLE")
            if temporal_coverage < config.citation_acceleration.min_temporal_coverage:
                reasons.append("INSUFFICIENT_TEMPORAL_COVERAGE")
        metrics = (
            _metric_counts(events_by_work.get(work_id, []), windows)
            if status == "COLLECTED"
            else None
        )
        topic = work.get("primary_topic") or {}
        topic_id = topic.get("id")
        catalog_item = topic_catalog.get(topic_id) or {}
        subfield = catalog_item.get("subfield") or {}
        age = _age_months(work["publication_date"], cutoff)
        prepared[work_id] = {
            "work_id": work_id,
            "work_type": work.get("work_type") or "unknown",
            "topic_id": topic_id,
            "subfield_id": subfield.get("id"),
            "age_months": age,
            "age_band": _age_band(
                age, config.citation_acceleration.age_band_boundaries_months
            ),
            "metrics": metrics,
            "temporal_coverage": temporal_coverage,
            "initial_reasons": reasons,
        }

    ready_ids = [
        work_id
        for work_id, item in prepared.items()
        if not item["initial_reasons"] and item["metrics"] is not None
    ]
    cohort_members: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for work_id in ready_ids:
        for key in _cohort_keys(prepared[work_id]):
            cohort_members[key].append(work_id)

    selected_cohorts: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    assessments: list[dict[str, Any]] = []
    fallback_counts: Counter[str] = Counter()
    abstention_counts: Counter[str] = Counter()
    for work_id in sorted(work_by_id):
        work = work_by_id[work_id]
        item = prepared[work_id]
        reasons = list(item["initial_reasons"])
        cohort = None
        if not reasons:
            selected_key = next(
                (
                    key
                    for key in _cohort_keys(item)
                    if len(cohort_members[key]) >= config.citation_acceleration.min_cohort_size
                ),
                None,
            )
            if selected_key is None:
                reasons.append("INSUFFICIENT_COHORT_SUPPORT")
            else:
                member_ids = cohort_members[selected_key]
                values = [prepared[member]["metrics"]["raw_acceleration"] for member in member_ids]
                cohort_id = "ca-cohort:" + sha256_json(selected_key).split(":", 1)[1][:20]
                if selected_key not in selected_cohorts:
                    selected_cohorts[selected_key] = {
                        "schema_version": "citation-acceleration-cohort/0.1",
                        "cohort_id": cohort_id,
                        "kind": selected_key[0],
                        "work_type": selected_key[1],
                        "age_band": selected_key[2],
                        "classification_id": selected_key[3],
                        "size": len(values),
                        "distribution": {
                            "minimum": round(min(values), 12),
                            "median": round(median(values), 12),
                            "p90": _quantile(values, 0.90),
                            "maximum": round(max(values), 12),
                        },
                    }
                fallback_level = {
                    "primary_topic_age_type": 0,
                    "subfield_age_type": 1,
                    "portfolio_age_type": 2,
                }[selected_key[0]]
                fallback_counts[selected_key[0]] += 1
                cohort = {
                    "cohort_id": cohort_id,
                    "kind": selected_key[0],
                    "size": len(values),
                    "percentile": _percentile(
                        values, item["metrics"]["raw_acceleration"]
                    ),
                    "fallback_level": fallback_level,
                }
        for reason in reasons:
            abstention_counts[reason] += 1
        work_coverage = coverage_by_id[work_id]
        assessment = {
            "schema_version": "citation-acceleration-assessment/0.1",
            "assessment_id": f"ca02:{cutoff.isoformat()}:{work_id}",
            "detector_id": "citation_acceleration",
            "subject": {
                "type": "work",
                "id": work_id,
                "label": work.get("title") or work_id,
                "doi": work_coverage.get("doi"),
            },
            "information_cutoff": cutoff.isoformat(),
            "publication_date": work["publication_date"],
            "work_type": item["work_type"],
            "primary_topic": work.get("primary_topic"),
            "age_months": item["age_months"],
            "age_band": item["age_band"],
            "windows": windows,
            "metrics": item["metrics"],
            "coverage": {
                "eligibility_status": work_coverage["eligibility_status"],
                "opencitations_count": work_coverage.get(
                    "opencitations_citation_count"
                ),
                "openalex_count_at_vintage": work_coverage.get(
                    "openalex_cited_by_count"
                ),
                "cross_source_ratio": work_coverage.get("cross_source_ratio"),
                "monthly_usable_event_count": work_coverage.get(
                    "monthly_usable_event_count"
                ),
                "temporal_coverage_ratio": (
                    round(item["temporal_coverage"], 12)
                    if item["temporal_coverage"] is not None
                    else None
                ),
            },
            "cohort": cohort,
            "abstention": {
                "is_abstained": bool(reasons),
                "reasons": reasons,
            },
            "eligible_for_detection": not reasons,
            "source": {
                "work_observation_ref": "observations/work-observations.jsonl.gz",
                "citation_events_ref": "citations/citation-events.jsonl.gz",
                "coverage_ref": "citations/work-citation-coverage.jsonl.gz",
                "parameter_fingerprint": params["parameter_fingerprint"],
            },
        }
        assessments.append(assessment)

    eligible = [item for item in assessments if item["eligible_for_detection"]]
    cohorts = sorted(selected_cohorts.values(), key=lambda item: item["cohort_id"])
    overwrite = rebuild
    params_path = store.write_json(
        "citations/citation-acceleration-parameters.json", params, overwrite=overwrite
    )
    assessments_path = store.write_jsonl_gz(
        "citations/citation-acceleration-assessments.jsonl.gz",
        assessments,
        overwrite=overwrite,
    )
    eligible_path = store.write_jsonl_gz(
        "citations/citation-acceleration-eligible.jsonl.gz",
        eligible,
        overwrite=overwrite,
    )
    cohorts_path = store.write_jsonl_gz(
        "citations/citation-acceleration-cohorts.jsonl.gz",
        cohorts,
        overwrite=overwrite,
    )
    future_event_count = sum(
        item["metrics"]["post_cutoff_event_count"]
        for item in prepared.values()
        if item["metrics"] is not None
    )
    quality = {
        "schema_version": "ca02-quality-report/0.1",
        "run_id": manifest["run_id"],
        "calculator_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "information_cutoff": cutoff.isoformat(),
        "resumed": resume,
        "rebuilt": rebuild,
        "assessment_count": len(assessments),
        "eligible_count": len(eligible),
        "abstained_count": len(assessments) - len(eligible),
        "abstention_reason_counts": dict(sorted(abstention_counts.items())),
        "cohort_count": len(cohorts),
        "cohort_assignment_counts": dict(sorted(fallback_counts.items())),
        "post_cutoff_event_count_excluded": future_event_count,
        "minimum_temporal_coverage": config.citation_acceleration.min_temporal_coverage,
        "minimum_cohort_size": config.citation_acceleration.min_cohort_size,
        "no_signal_emission": True,
        "warnings": (
            ["POST_CUTOFF_EVENTS_EXCLUDED"] if future_event_count else []
        ),
    }
    quality_path = store.write_json(
        "quality/ca02-quality-report.json", quality, overwrite=overwrite
    )
    result = {
        "schema_version": "ca02-result/0.1",
        "scope_mode": scope_mode,
        "calculator_version": f"research-signal-instrument/{__version__}",
        "information_cutoff": cutoff.isoformat(),
        "assessment_count": len(assessments),
        "eligible_count": len(eligible),
        "abstained_count": len(assessments) - len(eligible),
        "cohort_count": len(cohorts),
        "outputs": {
            "parameters": params_path.relative_to(store.root).as_posix(),
            "assessments": assessments_path.relative_to(store.root).as_posix(),
            "eligible": eligible_path.relative_to(store.root).as_posix(),
            "cohorts": cohorts_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("ca02-result.json", result, overwrite=overwrite)
    return CA02Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        assessment_count=len(assessments),
        eligible_count=len(eligible),
        abstained_count=len(assessments) - len(eligible),
        cohort_count=len(cohorts),
        quality_report_path=quality_path,
    )
