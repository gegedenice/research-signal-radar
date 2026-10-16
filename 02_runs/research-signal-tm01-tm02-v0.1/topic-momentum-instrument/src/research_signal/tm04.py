from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .config import RunConfig, TopicMomentumConfig
from .errors import InvariantError
from .storage import RunStore, sha256_json


@dataclass(frozen=True)
class TM04Result:
    scope_mode: str
    scope_dir: Path
    classification_count: int
    latest_topic_count: int
    candidate_count: int
    quality_report_path: Path


def _aggregate(months: list[dict[str, Any]]) -> dict[str, Any]:
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


def _median_absolute_deviation(values: list[float]) -> float | None:
    if not values:
        return None
    center = median(values)
    return median(abs(value - center) for value in values)


def _theil_sen_slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    slopes = [
        (values[right] - values[left]) / (right - left)
        for left in range(len(values) - 1)
        for right in range(left + 1, len(values))
    ]
    return median(slopes)


def _presence_status(
    current: dict[str, Any],
    previous: dict[str, Any],
    history_count: int,
    total_history_count: int,
    parameters: TopicMomentumConfig,
) -> str:
    c0 = current["topic_count"]
    c1 = previous["topic_count"]
    if c0 >= parameters.min_current and c1 == 0:
        return "REACTIVATED" if history_count >= parameters.min_total_history else "NEW"
    if c0 == 0 and c1 >= parameters.min_previous:
        return "DORMANT"
    if c0 > 0 and c1 > 0:
        return "PERSISTING"
    if total_history_count >= parameters.min_total_history:
        return "INTERMITTENT"
    return "INSUFFICIENT"


def _growth_mode(
    count_delta: int,
    count_ratio: float,
    share_delta: float,
    share_ratio: float,
    parameters: TopicMomentumConfig,
) -> tuple[str, bool, bool, bool, bool]:
    count_up = (
        count_delta >= parameters.min_abs_delta
        and count_ratio >= parameters.rise_count_ratio
    )
    count_down = (
        count_delta <= -parameters.min_abs_delta
        and count_ratio <= parameters.fall_count_ratio
    )
    share_up = share_delta > 0 and share_ratio >= parameters.rise_share_ratio
    share_down = share_delta < 0 and share_ratio <= parameters.fall_share_ratio
    if (count_up and share_up) or (count_down and share_down):
        mode = "ABSOLUTE_AND_PORTFOLIO"
    elif (count_up and share_down) or (count_down and share_up):
        mode = "CONTRADICTORY"
    elif count_up or count_down:
        mode = "ABSOLUTE_ONLY"
    elif share_up or share_down:
        mode = "PORTFOLIO_ONLY"
    else:
        mode = "NONE"
    return mode, count_up, count_down, share_up, share_down


def classify_windows(
    *,
    current: dict[str, Any],
    previous: dict[str, Any],
    prior: dict[str, Any],
    history_count: int,
    total_history_count: int,
    baseline_windows: list[dict[str, Any]],
    parameters: TopicMomentumConfig,
) -> dict[str, Any]:
    c0 = current["topic_count"]
    c1 = previous["topic_count"]
    c2 = prior["topic_count"]
    s0 = current["topic_share"]
    s1 = previous["topic_share"]
    count_delta = c0 - c1
    count_ratio = (c0 + 0.5) / (c1 + 0.5)
    share_delta = s0 - s1
    share_ratio = (s0 + parameters.share_epsilon) / (
        s1 + parameters.share_epsilon
    )
    growth_now = math.log((c0 + 0.5) / (c1 + 0.5))
    growth_before = math.log((c1 + 0.5) / (c2 + 0.5))
    acceleration_value = growth_now - growth_before

    presence = _presence_status(
        current, previous, history_count, total_history_count, parameters
    )
    mode, count_up, count_down, share_up, share_down = _growth_mode(
        count_delta, count_ratio, share_delta, share_ratio, parameters
    )
    windows_valid = (
        current["is_complete"]
        and previous["is_complete"]
        and prior["is_complete"]
        and min(current["topic_coverage"], previous["topic_coverage"])
        >= parameters.min_topic_coverage
    )
    rising = (
        windows_valid
        and count_up
        and share_up
        and current["active_months"] >= parameters.min_active_months
        and c0 >= parameters.min_current
    )
    falling = (
        windows_valid
        and count_down
        and share_down
        and previous["active_months"] >= parameters.min_active_months
        and c1 >= parameters.min_previous
    )
    support_sufficient = c0 + c1 >= parameters.min_total_history
    if rising:
        direction = "RISING"
    elif falling:
        direction = "FALLING"
    elif windows_valid and support_sufficient:
        direction = "STABLE"
    else:
        direction = "UNDETERMINED"

    if direction == "RISING":
        if acceleration_value > parameters.acceleration_epsilon:
            acceleration = "ACCELERATING"
        elif acceleration_value < -parameters.acceleration_epsilon:
            acceleration = "SLOWING"
        else:
            acceleration = "STEADY"
    elif direction == "FALLING":
        if acceleration_value < -parameters.acceleration_epsilon:
            acceleration = "ACCELERATING"
        elif acceleration_value > parameters.acceleration_epsilon:
            acceleration = "SLOWING"
        else:
            acceleration = "STEADY"
    else:
        acceleration = "NA"

    baseline_counts = [item["topic_count"] for item in baseline_windows]
    baseline_shares = [item["topic_share"] for item in baseline_windows]
    percentile = (
        sum(value <= s0 for value in baseline_shares) / len(baseline_shares)
        if baseline_shares
        else None
    )
    return {
        "observation": {
            "current_count": c0,
            "previous_count": c1,
            "prior_count": c2,
            "current_classified_total": current["classified_works_count"],
            "previous_classified_total": previous["classified_works_count"],
            "current_share": s0,
            "previous_share": s1,
            "active_months_current": current["active_months"],
            "active_months_previous": previous["active_months"],
            "history_count": history_count,
            "topic_coverage_current": current["topic_coverage"],
            "topic_coverage_previous": previous["topic_coverage"],
        },
        "delta": {
            "count": count_delta,
            "count_rate_ratio": round(count_ratio, 12),
            "share": round(share_delta, 12),
            "share_rate_ratio": round(share_ratio, 12),
            "growth_now": round(growth_now, 12),
            "growth_before": round(growth_before, 12),
            "acceleration_value": round(acceleration_value, 12),
            "historical_percentile": round(percentile, 12)
            if percentile is not None
            else None,
        },
        "baseline": {
            "window_count": len(baseline_windows),
            "median_count": median(baseline_counts) if baseline_counts else None,
            "median_share": round(median(baseline_shares), 12)
            if baseline_shares
            else None,
            "share_mad": round(_median_absolute_deviation(baseline_shares), 12)
            if baseline_shares
            else None,
            "robust_share_slope": round(_theil_sen_slope(baseline_shares), 12)
            if len(baseline_shares) >= 2
            else None,
        },
        "classification": {
            "presence_status": presence,
            "momentum_direction": direction,
            "growth_mode": mode,
            "acceleration_status": acceleration,
        },
    }


def _taxonomy_change(topic: dict[str, Any], history_start: str, window_end: str) -> bool:
    created = topic.get("created_date")
    if not created:
        return False
    try:
        created_day = date.fromisoformat(str(created)[:10])
    except ValueError as exc:
        raise InvariantError(
            f"topic {topic.get('id', '[unknown]')} has invalid created_date: {created!r}"
        ) from exc
    return date.fromisoformat(history_start) <= created_day <= date.fromisoformat(window_end)


_OPPOSITE_DIRECTION = {"RISING": "FALLING", "FALLING": "RISING"}


def _attach_scale_corroboration(
    classification: dict[str, Any],
    topic_identity: dict[str, dict[str, Any]],
    parent_direction: dict[tuple[str, str, str], str],
    scale_levels: list[str],
) -> None:
    """Annote une classification topic avec la direction de ses niveaux parents.

    N'introduit aucun seuil : la concordance est dérivée des directions déjà
    calculées à chaque niveau, au même ``evaluation_date``.
    """
    topic_id = classification["topic"]["id"]
    eval_date = classification["evaluation_date"]
    direction = classification["classification"]["momentum_direction"]
    identity = topic_identity.get(topic_id, {})

    subfield_id = (identity.get("subfield") or {}).get("id")
    field_id = (identity.get("field") or {}).get("id")
    subfield_direction = (
        parent_direction.get(("subfield", subfield_id, eval_date))
        if "subfield" in scale_levels and subfield_id
        else None
    )
    field_direction = (
        parent_direction.get(("field", field_id, eval_date))
        if "field" in scale_levels and field_id
        else None
    )

    # Le subfield est le corroborant primaire ; à défaut, le field.
    primary = subfield_direction if "subfield" in scale_levels else field_direction
    concordance = "NEUTRAL"
    note: str | None = None
    if direction in ("RISING", "FALLING"):
        if primary == direction:
            concordance = "CORROBORATED"
        elif primary == _OPPOSITE_DIRECTION[direction]:
            concordance, note = "CONTRADICTED", "opposite_parent_direction"
        else:  # parent STABLE, UNDETERMINED ou absent
            concordance, note = "ISOLATED_WITHIN_PARENT", "focused_emergence"

    classification["classification"]["scale_corroboration"] = {
        "subfield_direction": subfield_direction,
        "field_direction": field_direction,
        "concordance": concordance,
        "note": note,
    }


def classify_topic_series(
    series: dict[str, Any],
    parameters: TopicMomentumConfig,
    parameters_hash: str,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    monthly = series["monthly"]
    window_months = parameters.analysis_window_months
    end_index = {item["end"]: index for index, item in enumerate(monthly)}
    results: list[dict[str, Any]] = []
    direction_streak = 0
    previous_direction: str | None = None

    for rolling in series["rolling_windows"]:
        endpoint = end_index[rolling["to"]]
        months_available = endpoint + 1
        if months_available < parameters.history_min_months:
            continue
        current_months = monthly[endpoint - window_months + 1 : endpoint + 1]
        previous_months = monthly[
            endpoint - 2 * window_months + 1 : endpoint - window_months + 1
        ]
        prior_months = monthly[
            endpoint - 3 * window_months + 1 : endpoint - 2 * window_months + 1
        ]
        if not (
            len(current_months) == len(previous_months) == len(prior_months) == window_months
        ):
            raise InvariantError("TM-04 could not construct three symmetric windows")
        current = _aggregate(current_months)
        previous = _aggregate(previous_months)
        prior = _aggregate(prior_months)
        history_before_previous = monthly[: endpoint - 2 * window_months + 1]
        history_count = sum(item["count"] for item in history_before_previous)
        total_history_count = sum(item["count"] for item in monthly[: endpoint + 1])
        baseline_windows = [
            item
            for item in series["rolling_windows"]
            if item["to"] < current["from"] and item["is_complete"]
        ]
        calculated = classify_windows(
            current=current,
            previous=previous,
            prior=prior,
            history_count=history_count,
            total_history_count=total_history_count,
            baseline_windows=baseline_windows,
            parameters=parameters,
        )
        direction = calculated["classification"]["momentum_direction"]
        if direction in {"RISING", "FALLING"} and direction == previous_direction:
            direction_streak += 1
        elif direction in {"RISING", "FALLING"}:
            direction_streak = 1
        else:
            direction_streak = 0
        previous_direction = direction

        taxonomy_change = _taxonomy_change(
            series["topic"], monthly[0]["start"], current["to"]
        )
        calculated["classification"]["taxonomy_change"] = taxonomy_change
        presence = calculated["classification"]["presence_status"]
        candidate = direction in {"RISING", "FALLING"} or presence in {
            "NEW",
            "REACTIVATED",
            "DORMANT",
        }
        results.append(
            {
                "schema_version": "topic-momentum-classification/0.1",
                "classification_id": (
                    f"tmc:{series['universe_id']}:v{series['universe_version']}:"
                    f"{series['stream_id']}:{series['topic']['id']}:{current['to']}"
                ),
                "detector": {
                    "id": "topic-momentum",
                    "version": "0.1",
                    "parameters_hash": parameters_hash,
                },
                "run_id": series["run_id"],
                "query_manifest_ref": series["query_manifest_ref"],
                "universe": {
                    "id": series["universe_id"],
                    "version": series["universe_version"],
                    "scope_mode": series["scope_mode"],
                },
                "stream_id": series["stream_id"],
                "topic": series["topic"],
                "evaluation_date": current["to"],
                "effective_window": current,
                "comparison_window": previous,
                "prior_window": prior,
                **calculated,
                "direction_streak": direction_streak,
                "candidate": candidate,
                "provenance": {
                    "source": "openalex",
                    "data_vintage": manifest["data_vintage"],
                    "temporal_semantics": manifest["temporal_semantics"],
                    "corpus": manifest["corpus"],
                },
            }
        )
    return results


def run_tm04(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM04Result:
    if resume and rebuild:
        raise InvariantError("TM-04 --resume and --rebuild are mutually exclusive")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm03-result.json",
        "quality/tm03-quality-report.json",
        "series/topic-series.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"TM-04 requires completed TM-03 artifacts: {missing}")
    result_path = store.path("tm04-result.json")
    quality_path = store.path("quality/tm04-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm04-result.json")
        return TM04Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            classification_count=completed["classification_count"],
            latest_topic_count=completed["latest_topic_count"],
            candidate_count=completed["candidate_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-04 result already exists; use --resume to reuse it or --rebuild "
            "to regenerate TM-04 classifications and quality artifacts"
        )

    manifest = store.read_json("query-manifest.json")
    series = store.read_jsonl_gz("series/topic-series.jsonl.gz")
    parameters = asdict(config.topic_momentum)
    parameters_hash = sha256_json(parameters)
    classifications: list[dict[str, Any]] = []
    for item in series:
        classifications.extend(
            classify_topic_series(item, config.topic_momentum, parameters_hash, manifest)
        )
    if not classifications:
        raise InvariantError(
            "TM-04 has no eligible evaluation; extend history or reduce history_min_months"
        )

    scale_levels = config.topic_momentum.scale_levels
    scale_concordance_counts: dict[str, int] = {}
    parent_level_counts: dict[str, int] = {}
    if config.topic_momentum.multi_scale:
        parent_direction: dict[tuple[str, str, str], str] = {}
        parent_classifications: dict[str, list[dict[str, Any]]] = {}
        for level in scale_levels:
            relative = f"series/{level}-series.jsonl.gz"
            if not store.path(relative).exists():
                continue
            rows: list[dict[str, Any]] = []
            for item in store.read_jsonl_gz(relative):
                for classified in classify_topic_series(
                    item, config.topic_momentum, parameters_hash, manifest
                ):
                    rows.append(classified)
                    parent_direction[
                        (level, item["topic"]["id"], classified["evaluation_date"])
                    ] = classified["classification"]["momentum_direction"]
            parent_classifications[level] = rows
        topic_identity = {item["topic"]["id"]: item["topic"] for item in series}
        for classification in classifications:
            _attach_scale_corroboration(
                classification, topic_identity, parent_direction, scale_levels
            )
        for level, rows in parent_classifications.items():
            store.write_jsonl_gz(
                f"classifications/{level}-momentum-classifications.jsonl.gz",
                rows,
                overwrite=rebuild,
            )
            parent_level_counts[level] = len(rows)

    latest_date = max(item["evaluation_date"] for item in classifications)
    latest = [item for item in classifications if item["evaluation_date"] == latest_date]
    candidates = [item for item in latest if item["candidate"]]

    all_path = store.write_jsonl_gz(
        "classifications/topic-momentum-classifications.jsonl.gz",
        classifications,
        overwrite=rebuild,
    )
    latest_path = store.write_jsonl_gz(
        "classifications/topic-momentum-latest.jsonl.gz", latest, overwrite=rebuild
    )
    store.write_json(
        "classifications/topic-momentum-parameters.json", parameters, overwrite=rebuild
    )
    direction_counts = Counter(
        item["classification"]["momentum_direction"] for item in latest
    )
    presence_counts = Counter(
        item["classification"]["presence_status"] for item in latest
    )
    growth_counts = Counter(item["classification"]["growth_mode"] for item in latest)
    acceleration_counts = Counter(
        item["classification"]["acceleration_status"] for item in latest
    )
    if config.topic_momentum.multi_scale:
        scale_concordance_counts = dict(
            sorted(
                Counter(
                    item["classification"]
                    .get("scale_corroboration", {})
                    .get("concordance", "NEUTRAL")
                    for item in latest
                ).items()
            )
        )
    quality = {
        "schema_version": "tm04-quality-report/0.1",
        "run_id": manifest["run_id"],
        "classifier_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "parameters": parameters,
        "parameters_hash": parameters_hash,
        "classification_count": len(classifications),
        "latest_evaluation_date": latest_date,
        "latest_topic_count": len(latest),
        "candidate_count": len(candidates),
        "latest_direction_counts": dict(sorted(direction_counts.items())),
        "latest_presence_counts": dict(sorted(presence_counts.items())),
        "latest_growth_mode_counts": dict(sorted(growth_counts.items())),
        "latest_acceleration_counts": dict(sorted(acceleration_counts.items())),
        "taxonomy_change_count": sum(
            item["classification"]["taxonomy_change"] for item in latest
        ),
        "multi_scale": config.topic_momentum.multi_scale,
        "scale_levels": list(scale_levels),
        "parent_level_classification_counts": parent_level_counts,
        "scale_concordance_counts": scale_concordance_counts,
        "warnings": [],
    }
    quality_path = store.write_json(
        "quality/tm04-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm04-result/0.1",
        "scope_mode": scope_mode,
        "classifier_version": f"research-signal-instrument/{__version__}",
        "classification_count": len(classifications),
        "latest_evaluation_date": latest_date,
        "latest_topic_count": len(latest),
        "candidate_count": len(candidates),
        "outputs": {
            "all_classifications": str(all_path.relative_to(store.root)),
            "latest_classifications": str(latest_path.relative_to(store.root)),
            "parameters": "classifications/topic-momentum-parameters.json",
            "quality_report": str(quality_path.relative_to(store.root)),
        },
    }
    store.write_json("tm04-result.json", result, overwrite=rebuild)
    return TM04Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        classification_count=len(classifications),
        latest_topic_count=len(latest),
        candidate_count=len(candidates),
        quality_report_path=quality_path,
    )
