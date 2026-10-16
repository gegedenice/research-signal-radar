from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .config import RunConfig
from .dates import add_months, month_distance, month_end
from .errors import InvariantError
from .storage import RunStore


HORIZONS_MONTHS = (6, 12)
RETENTION_FLOOR = 0.5
OUTCOME_POLICY = "topic-momentum-outcome/0.1"
EPISODE_POLICY = "topic-momentum-episode/0.2"
CALIBRATION_SCHEMA = "topic-momentum-calibration/0.3"
REVIEW_SAMPLE_SCHEMA = "topic-momentum-rising-review-sample/0.2"
SOURCE_MATURITY_POLICY = "openalex-source-maturity/0.1"
SOURCE_MATURITY_LAGS_MONTHS = (3, 6, 9)
DEFAULT_SOURCE_MATURITY_LAG_MONTHS = 6
REVIEW_LABELS = ("STRENGTHENED", "RETAINED", "FADED", "MIXED", "REVERSED")
REVIEW_ITEMS_PER_LABEL = 6
TIER_ORDER = {
    "EXPLORATION": 0,
    "WATCH": 1,
    "HEADLINE_CANDIDATE": 2,
}
CONFIDENCE_ORDER = {"VERY_LOW": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(frozen=True)
class TM08Result:
    scope_mode: str
    scope_dir: Path
    event_outcome_count: int
    observed_outcome_count: int
    censored_outcome_count: int
    episode_count: int
    headline_episode_count: int
    review_sample_count: int
    quality_report_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: float) -> float:
    return round(value, 12)


def _target_cutoff(cutoff: str, horizon_months: int) -> str:
    target = month_end(add_months(date.fromisoformat(cutoff), horizon_months))
    return target.isoformat()


def outcome_label(count_retention: float, share_retention: float) -> str:
    if count_retention <= 0 and share_retention <= 0:
        return "REVERSED"
    if count_retention <= 0 or share_retention <= 0:
        return "MIXED"
    if count_retention >= 1 and share_retention >= 1:
        return "STRENGTHENED"
    if count_retention >= RETENTION_FLOOR and share_retention >= RETENTION_FLOOR:
        return "RETAINED"
    return "FADED"


def _detection_summary(signal: dict[str, Any]) -> dict[str, Any]:
    payload = signal["payload"]
    return {
        "cutoff": signal["analysis_context"]["current_window"]["end"],
        "window": signal["analysis_context"]["current_window"],
        "direction": payload["signal_label"],
        "editorial_tier": payload["editorial"]["tier"],
        "confidence_level": signal["confidence"]["level"],
        "priority_score": signal["priority"]["score"],
        "rank_within_cutoff": payload["replay"]["rank_within_cutoff"],
        "reference_count": payload["reference_count"],
        "current_count": payload["current_count"],
        "reference_share": payload["reference_share"],
        "current_share": payload["current_share"],
    }


def evaluate_signal(
    signal: dict[str, Any],
    horizon_months: int,
    *,
    latest_available_cutoff: str,
    windows: dict[tuple[str, str], dict[str, Any]],
    classifications: dict[tuple[str, str], dict[str, Any]],
    evaluated_at: str,
) -> dict[str, Any]:
    if horizon_months not in HORIZONS_MONTHS:
        raise InvariantError(f"unsupported TM-08 horizon: {horizon_months}")
    topic_id = signal["subject"]["id"]
    detection = _detection_summary(signal)
    cutoff = detection["cutoff"]
    if signal["temporal_context"]["information_cutoff"][:10] != cutoff:
        raise InvariantError(f"{signal['signal_id']}: TM-07 cutoff mismatch")
    current_window = windows.get((topic_id, cutoff))
    if current_window is None:
        raise InvariantError(
            f"{signal['signal_id']}: detection window absent from TM-03 series"
        )
    if (
        current_window["topic_count"] != detection["current_count"]
        or current_window["topic_share"] != detection["current_share"]
    ):
        raise InvariantError(
            f"{signal['signal_id']}: detection values differ from TM-03 series"
        )

    target = _target_cutoff(cutoff, horizon_months)
    if date.fromisoformat(target) <= date.fromisoformat(cutoff):
        raise InvariantError(f"{signal['signal_id']}: outcome target is not future")
    base = {
        "schema_version": OUTCOME_POLICY,
        "outcome_id": f"tm08:{signal['signal_id']}:+{horizon_months}m",
        "signal_id": signal["signal_id"],
        "topic": {"id": topic_id, "label": signal["subject"]["label"]},
        "horizon_months": horizon_months,
        "status": "RIGHT_CENSORED",
        "detection": detection,
        "target_cutoff": target,
        "latest_available_cutoff": latest_available_cutoff,
        "outcome": None,
        "censoring": None,
        "provenance": {
            "run_id": signal["provenance"]["run_id"],
            "source_signal_schema": signal["schema_version"],
            "source_signal_information_cutoff": signal["temporal_context"][
                "information_cutoff"
            ],
            "observation_vintage": signal["temporal_context"][
                "observation_vintage"
            ],
            "backtest_data_mode": signal["temporal_context"]["mode"],
            "evaluated_at": evaluated_at,
            "code_version": f"research-signal-instrument/{__version__}",
        },
    }
    if target > latest_available_cutoff:
        base["censoring"] = {
            "type": "RIGHT_CENSORED",
            "reason": "TARGET_AFTER_LAST_COMPLETE_EVALUATION",
        }
        return base

    target_window = windows.get((topic_id, target))
    if target_window is None:
        raise InvariantError(
            f"{signal['signal_id']}: target {target} should be available but is absent"
        )
    target_classification = classifications.get((topic_id, target))
    if target_classification is None:
        raise InvariantError(
            f"{signal['signal_id']}: target classification {target} is absent"
        )

    positive_labels = {"RISING", "NEW", "REACTIVATED"}
    negative_labels = {"FALLING", "DORMANT"}
    if detection["direction"] not in positive_labels | negative_labels:
        raise InvariantError(
            f"{signal['signal_id']}: unsupported Topic Momentum signal label"
        )
    sign = 1 if detection["direction"] in positive_labels else -1
    count_detection = sign * (
        detection["current_count"] - detection["reference_count"]
    )
    share_detection = sign * (
        detection["current_share"] - detection["reference_share"]
    )
    if count_detection <= 0 or share_detection <= 0:
        raise InvariantError(
            f"{signal['signal_id']}: non-positive directional displacement"
        )
    count_horizon = sign * (
        target_window["topic_count"] - detection["reference_count"]
    )
    share_horizon = sign * (
        target_window["topic_share"] - detection["reference_share"]
    )
    count_retention = count_horizon / count_detection
    share_retention = share_horizon / share_detection
    label = outcome_label(count_retention, share_retention)
    future_classification = target_classification["classification"]
    future_direction = future_classification["momentum_direction"]
    future_presence = future_classification["presence_status"]
    future_label = (
        future_direction
        if future_direction in {"RISING", "FALLING"}
        else future_presence
        if future_presence in {"NEW", "REACTIVATED", "DORMANT"}
        else "NONE"
    )
    overlap_start = max(
        date.fromisoformat(detection["window"]["start"]),
        date.fromisoformat(target_window["from"]),
    )
    overlap_end = min(
        date.fromisoformat(detection["window"]["end"]),
        date.fromisoformat(target_window["to"]),
    )
    overlap_months = (
        month_distance(overlap_start, overlap_end) + 1
        if overlap_start <= overlap_end
        else 0
    )

    base["status"] = "OBSERVED"
    base["outcome"] = {
        "label": label,
        "confirmed": label in {"STRENGTHENED", "RETAINED"},
        "target_window": {
            "from": target_window["from"],
            "to": target_window["to"],
            "topic_count": target_window["topic_count"],
            "topic_share": target_window["topic_share"],
            "classified_works_count": target_window["classified_works_count"],
            "topic_coverage": target_window["topic_coverage"],
            "overlap_with_detection_window_months": overlap_months,
        },
        "metrics": {
            "signed_count_displacement_at_detection": count_detection,
            "signed_count_displacement_at_horizon": count_horizon,
            "count_retention_ratio": _round(count_retention),
            "signed_share_displacement_at_detection": _round(share_detection),
            "signed_share_displacement_at_horizon": _round(share_horizon),
            "share_retention_ratio": _round(share_retention),
            "signed_count_change_after_detection": sign
            * (target_window["topic_count"] - detection["current_count"]),
            "signed_share_change_after_detection": _round(
                sign
                * (target_window["topic_share"] - detection["current_share"])
            ),
        },
        "future_classification": {
            "presence_status": future_classification["presence_status"],
            "momentum_direction": future_classification["momentum_direction"],
            "growth_mode": future_classification["growth_mode"],
            "acceleration_status": future_classification["acceleration_status"],
            "same_momentum_direction": future_classification[
                "momentum_direction"
            ]
            == detection["direction"]
            if detection["direction"] in {"RISING", "FALLING"}
            else None,
            "signal_label": future_label,
            "same_signal_label": future_label == detection["direction"],
        },
    }
    return base


def _episode_anchor(
    signal: dict[str, Any] | None,
    outcomes_by_signal: dict[str, dict[int, dict[str, Any]]],
) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "signal_id": signal["signal_id"],
        "cutoff": signal["analysis_context"]["current_window"]["end"],
        "editorial_tier": signal["payload"]["editorial"]["tier"],
        "priority_score": signal["priority"]["score"],
        "outcomes": {
            f"+{horizon}m": {
                "outcome_id": outcomes_by_signal[signal["signal_id"]][horizon][
                    "outcome_id"
                ],
                "status": outcomes_by_signal[signal["signal_id"]][horizon][
                    "status"
                ],
                "target_cutoff": outcomes_by_signal[signal["signal_id"]][horizon][
                    "target_cutoff"
                ],
                "label": (
                    outcomes_by_signal[signal["signal_id"]][horizon]["outcome"][
                        "label"
                    ]
                    if outcomes_by_signal[signal["signal_id"]][horizon]["outcome"]
                    else None
                ),
                "confirmed": (
                    outcomes_by_signal[signal["signal_id"]][horizon]["outcome"][
                        "confirmed"
                    ]
                    if outcomes_by_signal[signal["signal_id"]][horizon]["outcome"]
                    else None
                ),
            }
            for horizon in HORIZONS_MONTHS
        },
    }


def _maturity_class(
    *, reached_headline: bool, occurrence_count: int, status: str
) -> str:
    if reached_headline:
        return "ESCALATED"
    if occurrence_count >= 2:
        return "PERSISTENT"
    if status == "OPEN":
        return "OPEN_ONSET"
    return "ISOLATED"


def build_episodes(
    signals: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    *,
    evaluation_step_months: int,
) -> list[dict[str, Any]]:
    outcomes_by_signal: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for outcome in outcomes:
        outcomes_by_signal[outcome["signal_id"]][outcome["horizon_months"]] = outcome
    if any(set(items) != set(HORIZONS_MONTHS) for items in outcomes_by_signal.values()):
        raise InvariantError("TM-08 outcome horizons are incomplete")

    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        by_topic[signal["subject"]["id"]].append(signal)
    latest_cutoff = max(
        signal["analysis_context"]["current_window"]["end"] for signal in signals
    )
    raw_episodes: list[list[dict[str, Any]]] = []
    for topic_signals in by_topic.values():
        topic_signals.sort(
            key=lambda item: item["analysis_context"]["current_window"]["end"]
        )
        episode: list[dict[str, Any]] = []
        for signal in topic_signals:
            if episode:
                previous = episode[-1]
                previous_cutoff = date.fromisoformat(
                    previous["analysis_context"]["current_window"]["end"]
                )
                cutoff = date.fromisoformat(
                    signal["analysis_context"]["current_window"]["end"]
                )
                contiguous = (
                    month_distance(previous_cutoff, cutoff)
                    == evaluation_step_months
                )
                same_direction = (
                    previous["payload"]["signal_label"]
                    == signal["payload"]["signal_label"]
                )
                if not (contiguous and same_direction):
                    raw_episodes.append(episode)
                    episode = []
            episode.append(signal)
        if episode:
            raw_episodes.append(episode)

    episodes: list[dict[str, Any]] = []
    for raw in raw_episodes:
        first = raw[0]
        last = raw[-1]
        topic_id = first["subject"]["id"]
        direction = first["payload"]["signal_label"]
        start = first["analysis_context"]["current_window"]["end"]
        end = last["analysis_context"]["current_window"]["end"]
        first_headline = next(
            (
                item
                for item in raw
                if item["payload"]["editorial"]["tier"]
                == "HEADLINE_CANDIDATE"
            ),
            None,
        )
        all_topic_signals = by_topic[topic_id]
        next_signal = next(
            (
                item
                for item in all_topic_signals
                if item["analysis_context"]["current_window"]["end"] > end
            ),
            None,
        )
        if end == latest_cutoff:
            termination = "OPEN_AT_LAST_CUTOFF"
            status = "OPEN"
        elif (
            next_signal is not None
            and month_distance(
                date.fromisoformat(end),
                date.fromisoformat(
                    next_signal["analysis_context"]["current_window"]["end"]
                ),
            )
            == evaluation_step_months
            and next_signal["payload"]["signal_label"] != direction
        ):
            termination = "DIRECTION_CHANGE"
            status = "CLOSED"
        else:
            termination = "SIGNAL_GAP"
            status = "CLOSED"
        peak_tier = max(
            (item["payload"]["editorial"]["tier"] for item in raw),
            key=lambda tier: TIER_ORDER[tier],
        )
        episode_id = f"tme:{topic_id}:{direction.lower()}:{start}"
        maturity_class = _maturity_class(
            reached_headline=first_headline is not None,
            occurrence_count=len(raw),
            status=status,
        )
        episodes.append(
            {
                "schema_version": EPISODE_POLICY,
                "episode_id": episode_id,
                "topic": {
                    "id": topic_id,
                    "label": first["subject"]["label"],
                },
                "direction": direction,
                "start_cutoff": start,
                "end_cutoff": end,
                "status": status,
                "termination_reason": termination,
                "signal_occurrence_count": len(raw),
                "observed_span_months": month_distance(
                    date.fromisoformat(start), date.fromisoformat(end)
                ),
                "signal_ids": [item["signal_id"] for item in raw],
                "editorial": {
                    "initial_tier": first["payload"]["editorial"]["tier"],
                    "peak_tier": peak_tier,
                    "reached_headline": first_headline is not None,
                    "first_headline_cutoff": (
                        first_headline["analysis_context"]["current_window"]["end"]
                        if first_headline
                        else None
                    ),
                    "early_warning_lead_months": (
                        month_distance(
                            date.fromisoformat(start),
                            date.fromisoformat(
                                first_headline["analysis_context"]["current_window"][
                                    "end"
                                ]
                            ),
                        )
                        if first_headline
                        else None
                    ),
                    "maturity_class": maturity_class,
                },
                "priority": {
                    "initial_score": first["priority"]["score"],
                    "maximum_score": max(item["priority"]["score"] for item in raw),
                },
                "confidence": {
                    "initial_level": first["confidence"]["level"],
                    "maximum_level": max(
                        (item["confidence"]["level"] for item in raw),
                        key=lambda level: CONFIDENCE_ORDER[level],
                    ),
                },
                "anchors": {
                    "onset": _episode_anchor(first, outcomes_by_signal),
                    "first_headline": _episode_anchor(
                        first_headline, outcomes_by_signal
                    ),
                },
                "quality_flags": sorted(
                    {flag for item in raw for flag in item["quality_flags"]}
                ),
                "provenance": {
                    "run_id": first["provenance"]["run_id"],
                    "episode_policy": EPISODE_POLICY,
                    "source_signal_schema": first["schema_version"],
                    "backtest_data_mode": first["temporal_context"]["mode"],
                },
            }
        )
    episodes.sort(key=lambda item: (item["start_cutoff"], item["episode_id"]))
    return episodes


def _calibration(records: list[dict[str, Any]]) -> dict[str, Any]:
    observed = [item for item in records if item["status"] == "OBSERVED"]
    censored = [item for item in records if item["status"] == "RIGHT_CENSORED"]
    labels = Counter(item["outcome"]["label"] for item in observed)
    confirmed = sum(item["outcome"]["confirmed"] for item in observed)
    directional_survival = (
        labels["STRENGTHENED"] + labels["RETAINED"] + labels["FADED"]
    )
    non_reversal = len(observed) - labels["REVERSED"]
    return {
        "total": len(records),
        "observed": len(observed),
        "right_censored": len(censored),
        "outcome_label_counts": dict(sorted(labels.items())),
        "confirmed_count": confirmed,
        "confirmation_rate": _round(confirmed / len(observed)) if observed else None,
        "strict_retention_count": confirmed,
        "strict_retention_rate": (
            _round(confirmed / len(observed)) if observed else None
        ),
        "directional_survival_count": directional_survival,
        "directional_survival_rate": (
            _round(directional_survival / len(observed)) if observed else None
        ),
        "non_reversal_count": non_reversal,
        "non_reversal_rate": (
            _round(non_reversal / len(observed)) if observed else None
        ),
        "reversal_count": labels["REVERSED"],
        "reversal_rate": (
            _round(labels["REVERSED"] / len(observed)) if observed else None
        ),
    }


def _stratify(
    records: list[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        groups[str(item["detection"][field])].append(item)
    return {name: _calibration(items) for name, items in sorted(groups.items())}


def _anchor_calibration(
    episodes: list[dict[str, Any]], anchor_name: str, horizon: int
) -> dict[str, Any]:
    records = []
    for episode in episodes:
        anchor = episode["anchors"][anchor_name]
        if anchor is None:
            continue
        item = anchor["outcomes"][f"+{horizon}m"]
        records.append(
            {
                "status": item["status"],
                "outcome": (
                    {"label": item["label"], "confirmed": item["confirmed"]}
                    if item["label"] is not None
                    else None
                ),
            }
        )
    return _calibration(records)


def _episode_anchor_records(
    episodes: list[dict[str, Any]], anchor_name: str, horizon: int
) -> list[dict[str, Any]]:
    records = []
    for episode in episodes:
        anchor = episode["anchors"][anchor_name]
        if anchor is None:
            continue
        item = anchor["outcomes"][f"+{horizon}m"]
        records.append(
            {
                "episode": episode,
                "status": item["status"],
                "target_cutoff": item["target_cutoff"],
                "outcome": (
                    {"label": item["label"], "confirmed": item["confirmed"]}
                    if item["label"] is not None
                    else None
                ),
            }
        )
    return records


def _episode_maturity_calibration(
    episodes: list[dict[str, Any]], horizon: int
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in _episode_anchor_records(episodes, "onset", horizon):
        maturity = record["episode"]["editorial"]["maturity_class"]
        groups[maturity].append(record)
    return {name: _calibration(items) for name, items in sorted(groups.items())}


def _temporal_holdout_calibration(
    episodes: list[dict[str, Any]],
    horizon: int,
    *,
    latest_mature_target_cutoff: str | None = None,
) -> dict[str, Any]:
    records = [
        item
        for item in _episode_anchor_records(episodes, "onset", horizon)
        if item["status"] == "OBSERVED"
        and (
            latest_mature_target_cutoff is None
            or item["target_cutoff"] <= latest_mature_target_cutoff
        )
    ]
    if not records:
        return {
            "status": "UNAVAILABLE",
            "holdout_start_cutoff": None,
            "historical_reference": _calibration([]),
            "recent_holdout": _calibration([]),
        }
    latest_source_cutoff = max(item["episode"]["start_cutoff"] for item in records)
    holdout_start = month_end(
        add_months(date.fromisoformat(latest_source_cutoff), -9)
    ).isoformat()
    historical = [
        item for item in records if item["episode"]["start_cutoff"] < holdout_start
    ]
    holdout = [
        item for item in records if item["episode"]["start_cutoff"] >= holdout_start
    ]

    def direction_groups(items: list[dict[str, Any]]) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            groups[item["episode"]["direction"]].append(item)
        return {name: _calibration(group) for name, group in sorted(groups.items())}

    return {
        "status": "AVAILABLE",
        "policy": "last-four-observable-quarterly-onsets/0.1",
        "latest_observable_source_cutoff": latest_source_cutoff,
        "holdout_start_cutoff": holdout_start,
        "historical_reference": {
            "overall": _calibration(historical),
            "by_direction": direction_groups(historical),
        },
        "recent_holdout": {
            "overall": _calibration(holdout),
            "by_direction": direction_groups(holdout),
        },
    }


def _latest_mature_evaluation_cutoff(
    observation_vintage: str,
    lag_months: int,
    evaluation_dates: set[str],
) -> tuple[str, str | None]:
    if lag_months < 0:
        raise InvariantError("source maturity lag must be non-negative")
    vintage_date = date.fromisoformat(observation_vintage[:10])
    mature_through = add_months(vintage_date, -lag_months).isoformat()
    eligible = [cutoff for cutoff in evaluation_dates if cutoff <= mature_through]
    return mature_through, max(eligible) if eligible else None


def _direction_calibration(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        groups[item["episode"]["direction"]].append(item)
    return {name: _calibration(items) for name, items in sorted(groups.items())}


def build_source_maturity_sensitivity(
    episodes: list[dict[str, Any]],
    *,
    observation_vintage: str,
    evaluation_dates: set[str],
) -> dict[str, Any]:
    """Compare +12m episode-onset calibration under simple indexing lags."""
    onset_records = _episode_anchor_records(episodes, "onset", 12)
    calendar_observed = [
        item for item in onset_records if item["status"] == "OBSERVED"
    ]
    profiles = {}
    for lag_months in SOURCE_MATURITY_LAGS_MONTHS:
        mature_through, latest_mature_cutoff = _latest_mature_evaluation_cutoff(
            observation_vintage,
            lag_months,
            evaluation_dates,
        )
        mature_records = [
            item
            for item in calendar_observed
            if latest_mature_cutoff is not None
            and item["target_cutoff"] <= latest_mature_cutoff
        ]
        profiles[f"lag_{lag_months}m"] = {
            "lag_months": lag_months,
            "mature_through_date": mature_through,
            "latest_mature_evaluation_cutoff": latest_mature_cutoff,
            "calendar_observed_count": len(calendar_observed),
            "mature_observed_count": len(mature_records),
            "provisional_observed_count": len(calendar_observed)
            - len(mature_records),
            "episode_onset_12m": {
                "overall": _calibration(mature_records),
                "by_direction": _direction_calibration(mature_records),
                "temporal_validation": _temporal_holdout_calibration(
                    episodes,
                    12,
                    latest_mature_target_cutoff=latest_mature_cutoff,
                ),
            },
        }
    return {
        "policy": SOURCE_MATURITY_POLICY,
        "semantics": (
            "A calendar-complete target is retained for calibration only when "
            "it predates the observation vintage by the selected lag."
        ),
        "observation_vintage": observation_vintage,
        "default_profile": f"lag_{DEFAULT_SOURCE_MATURITY_LAG_MONTHS}m",
        "profiles": profiles,
    }


def _round_robin_review_selection(
    candidates: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        episode = item["episode"]
        key = (
            episode["editorial"]["maturity_class"],
            episode["editorial"]["initial_tier"],
        )
        buckets[key].append(item)
    for values in buckets.values():
        values.sort(
            key=lambda item: (
                item["episode"]["start_cutoff"],
                item["episode"]["episode_id"],
            )
        )
    selected: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(selected) < limit and any(buckets[key] for key in keys):
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))
    return selected


def build_rising_review_sample(
    episodes: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    *,
    latest_mature_target_cutoff: str | None = None,
) -> dict[str, Any]:
    outcome_by_id = {item["outcome_id"]: item for item in outcomes}
    signal_by_id = {item["signal_id"]: item for item in signals}
    candidates_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        onset = episode["anchors"]["onset"]
        anchor = onset["outcomes"]["+12m"]
        if (
            episode["direction"] != "RISING"
            or anchor["status"] != "OBSERVED"
            or (
                latest_mature_target_cutoff is not None
                and anchor["target_cutoff"] > latest_mature_target_cutoff
            )
        ):
            continue
        candidates_by_label[anchor["label"]].append(
            {"episode": episode, "anchor": anchor}
        )

    selected: list[dict[str, Any]] = []
    strata = {}
    for label in REVIEW_LABELS:
        candidates = candidates_by_label[label]
        chosen = _round_robin_review_selection(
            candidates, REVIEW_ITEMS_PER_LABEL
        )
        strata[label] = {
            "available": len(candidates),
            "selected": len(chosen),
        }
        selected.extend(chosen)

    items = []
    for ordinal, item in enumerate(selected, 1):
        episode = item["episode"]
        onset = episode["anchors"]["onset"]
        signal = signal_by_id[onset["signal_id"]]
        outcome = outcome_by_id[item["anchor"]["outcome_id"]]
        items.append(
            {
                "review_item_id": f"tm08-review-rising-{ordinal:02d}",
                "review_status": "PENDING",
                "outcome_stratum": outcome["outcome"]["label"],
                "episode": {
                    "episode_id": episode["episode_id"],
                    "topic": episode["topic"],
                    "start_cutoff": episode["start_cutoff"],
                    "end_cutoff": episode["end_cutoff"],
                    "signal_occurrence_count": episode[
                        "signal_occurrence_count"
                    ],
                    "maturity_class": episode["editorial"]["maturity_class"],
                    "reached_headline": episode["editorial"][
                        "reached_headline"
                    ],
                    "early_warning_lead_months": episode["editorial"][
                        "early_warning_lead_months"
                    ],
                },
                "onset_signal": {
                    "signal_id": signal["signal_id"],
                    "headline": signal.get("summary", {}).get("headline"),
                    "why_unusual": signal.get("summary", {}).get("why_unusual"),
                    "editorial_tier": signal["payload"]["editorial"]["tier"],
                    "confidence_level": signal["confidence"]["level"],
                    "priority_score": signal["priority"]["score"],
                    "reference_count": signal["payload"]["reference_count"],
                    "current_count": signal["payload"]["current_count"],
                    "reference_share": signal["payload"]["reference_share"],
                    "current_share": signal["payload"]["current_share"],
                    "evidence_bundle_id": signal["payload"].get(
                        "evidence_bundle_id"
                    ),
                    "quality_flags": signal["quality_flags"],
                },
                "outcome_12m": {
                    "target_cutoff": outcome["target_cutoff"],
                    "label": outcome["outcome"]["label"],
                    "strictly_retained": outcome["outcome"]["confirmed"],
                    "target_window": outcome["outcome"]["target_window"],
                    "metrics": outcome["outcome"]["metrics"],
                    "future_classification": outcome["outcome"][
                        "future_classification"
                    ],
                },
            }
        )
    return {
        "schema_version": REVIEW_SAMPLE_SCHEMA,
        "detector": "topic_momentum",
        "direction": "RISING",
        "anchor": "episode_onset",
        "horizon_months": 12,
        "source_maturity": {
            "policy": SOURCE_MATURITY_POLICY,
            "profile": f"lag_{DEFAULT_SOURCE_MATURITY_LAG_MONTHS}m",
            "latest_mature_target_cutoff": latest_mature_target_cutoff,
        },
        "selection_policy": {
            "method": "mature-outcome-strata-and-maturity-tier-round-robin/0.2",
            "outcome_labels": list(REVIEW_LABELS),
            "target_per_label": REVIEW_ITEMS_PER_LABEL,
            "within_label_buckets": ["maturity_class", "initial_tier"],
            "within_bucket_order": ["start_cutoff", "episode_id"],
        },
        "requested_count": len(REVIEW_LABELS) * REVIEW_ITEMS_PER_LABEL,
        "selected_count": len(items),
        "strata": strata,
        "review_questions": [
            "Le mouvement correspond-il à une évolution intellectuelle identifiable plutôt qu'à un artefact taxonomique ?",
            "Les œuvres à l'origine du signal forment-elles un ensemble cohérent et stratégiquement interprétable ?",
            "Le label de résultat à douze mois décrit-il correctement le devenir du mouvement ?",
            "Le signal aurait-il justifié une lecture, une veille ou une action au moment de l'onset ?",
            "Quels éléments de preuve manquent pour soutenir cette décision ?",
        ],
        "items": items,
    }


def run_tm08(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM08Result:
    if resume and rebuild:
        raise InvariantError("TM-08 --resume and --rebuild are mutually exclusive")
    if any(
        horizon % config.topic_momentum.evaluation_step_months
        for horizon in HORIZONS_MONTHS
    ):
        raise InvariantError(
            "TM-08 horizons must be divisible by the evaluation step"
        )
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm03-result.json",
        "tm04-result.json",
        "tm07-result.json",
        "quality/tm07-quality-report.json",
        "series/topic-series.jsonl.gz",
        "classifications/topic-momentum-classifications.jsonl.gz",
        "backtest/replay/topic-momentum-replay-signals.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"TM-08 requires completed TM-03, TM-04 and TM-07: {missing}")

    result_path = store.path("tm08-result.json")
    quality_path = store.path("quality/tm08-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm08-result.json")
        if completed.get("evaluator_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError(
                "TM-08 result was produced by another evaluator version; use --rebuild"
            )
        return TM08Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            event_outcome_count=completed["event_outcome_count"],
            observed_outcome_count=completed["observed_outcome_count"],
            censored_outcome_count=completed["censored_outcome_count"],
            episode_count=completed["episode_count"],
            headline_episode_count=completed["headline_episode_count"],
            review_sample_count=completed["review_sample_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-08 result already exists; use --resume or --rebuild"
        )

    manifest = store.read_json("query-manifest.json")
    tm07_result = store.read_json("tm07-result.json")
    tm07_quality = store.read_json("quality/tm07-quality-report.json")
    if tm07_result.get("schema_version") != "tm07-result/0.1":
        raise InvariantError("TM-08 requires TM-07 replay outputs")
    if tm07_result.get("temporal_contract") != "research-signal-temporal/0.2":
        raise InvariantError("TM-08 requires the temporal contract 0.2")
    if tm07_quality.get("future_outcomes_included") is not False:
        raise InvariantError("TM-08 source signals already contain future outcomes")

    series = store.read_jsonl_gz("series/topic-series.jsonl.gz")
    classification_rows = store.read_jsonl_gz(
        "classifications/topic-momentum-classifications.jsonl.gz"
    )
    signals = store.read_jsonl_gz(
        "backtest/replay/topic-momentum-replay-signals.jsonl.gz"
    )
    if len(signals) != tm07_result["replayed_signal_count"]:
        raise InvariantError("TM-08 replay signal count differs from TM-07 result")
    if not signals:
        raise InvariantError("TM-08 received no replay signal")
    if any(item["schema_version"] != "signal-envelope/0.2" for item in signals):
        raise InvariantError("TM-08 requires signal-envelope/0.2 inputs")
    if any(item["universe"]["scope_mode"] != scope_mode for item in signals):
        raise InvariantError("TM-08 input contains another scope")
    if {item["provenance"]["run_id"] for item in signals} != {manifest["run_id"]}:
        raise InvariantError("TM-08 replay signals differ from the query-manifest run")
    if {item["temporal_context"]["mode"] for item in signals} != {
        tm07_quality["backtest_data_mode"]
    }:
        raise InvariantError("TM-08 replay signals have inconsistent temporal modes")
    observation_vintages = {
        item["temporal_context"]["observation_vintage"] for item in signals
    }
    if len(observation_vintages) != 1:
        raise InvariantError("TM-08 replay signals have inconsistent source vintages")
    observation_vintage = next(iter(observation_vintages))

    windows: dict[tuple[str, str], dict[str, Any]] = {}
    evaluation_dates: set[str] = set()
    for item in series:
        topic_id = item["topic"]["id"]
        for window in item["rolling_windows"]:
            key = (topic_id, window["evaluation_date"])
            if key in windows:
                raise InvariantError(f"duplicate TM-03 outcome window: {key}")
            windows[key] = window
            if window["is_complete"]:
                evaluation_dates.add(window["evaluation_date"])
    if not evaluation_dates:
        raise InvariantError("TM-08 found no complete TM-03 evaluation")
    latest_available_cutoff = max(evaluation_dates)

    classifications: dict[tuple[str, str], dict[str, Any]] = {}
    for item in classification_rows:
        key = (item["topic"]["id"], item["evaluation_date"])
        if key in classifications:
            raise InvariantError(f"duplicate TM-04 outcome classification: {key}")
        classifications[key] = item

    evaluated_at = _now()
    outcomes = [
        evaluate_signal(
            signal,
            horizon,
            latest_available_cutoff=latest_available_cutoff,
            windows=windows,
            classifications=classifications,
            evaluated_at=evaluated_at,
        )
        for signal in signals
        for horizon in HORIZONS_MONTHS
    ]
    outcome_ids = [item["outcome_id"] for item in outcomes]
    if len(outcome_ids) != len(set(outcome_ids)):
        raise InvariantError("TM-08 produced duplicate outcome identifiers")

    episodes = build_episodes(
        signals,
        outcomes,
        evaluation_step_months=config.topic_momentum.evaluation_step_months,
    )
    episode_ids = [item["episode_id"] for item in episodes]
    if len(episode_ids) != len(set(episode_ids)):
        raise InvariantError("TM-08 produced duplicate episode identifiers")
    episode_index = [
        {
            "episode_id": item["episode_id"],
            "topic_id": item["topic"]["id"],
            "topic_label": item["topic"]["label"],
            "direction": item["direction"],
            "start_cutoff": item["start_cutoff"],
            "end_cutoff": item["end_cutoff"],
            "signal_occurrence_count": item["signal_occurrence_count"],
            "status": item["status"],
            "initial_tier": item["editorial"]["initial_tier"],
            "peak_tier": item["editorial"]["peak_tier"],
            "maturity_class": item["editorial"]["maturity_class"],
            "reached_headline": item["editorial"]["reached_headline"],
            "early_warning_lead_months": item["editorial"][
                "early_warning_lead_months"
            ],
            "onset_6m_label": item["anchors"]["onset"]["outcomes"]["+6m"][
                "label"
            ],
            "onset_12m_label": item["anchors"]["onset"]["outcomes"]["+12m"][
                "label"
            ],
        }
        for item in episodes
    ]

    calibration_by_horizon = {}
    for horizon in HORIZONS_MONTHS:
        horizon_records = [
            item for item in outcomes if item["horizon_months"] == horizon
        ]
        calibration_by_horizon[f"+{horizon}m"] = {
            "outcome_window_overlap_months": max(
                0, config.topic_momentum.analysis_window_months - horizon
            ),
            "overall": _calibration(horizon_records),
            "by_direction": _stratify(horizon_records, "direction"),
            "by_editorial_tier": _stratify(horizon_records, "editorial_tier"),
            "by_confidence_level": _stratify(horizon_records, "confidence_level"),
        }
    headline_episodes = [
        item for item in episodes if item["editorial"]["reached_headline"]
    ]
    leads = [
        item["editorial"]["early_warning_lead_months"]
        for item in headline_episodes
    ]
    source_maturity = build_source_maturity_sensitivity(
        episodes,
        observation_vintage=observation_vintage,
        evaluation_dates=evaluation_dates,
    )
    default_maturity = source_maturity["profiles"][
        source_maturity["default_profile"]
    ]
    review_sample = build_rising_review_sample(
        episodes,
        outcomes,
        signals,
        latest_mature_target_cutoff=default_maturity[
            "latest_mature_evaluation_cutoff"
        ],
    )
    calibration = {
        "schema_version": CALIBRATION_SCHEMA,
        "run_id": manifest["run_id"],
        "scope_mode": scope_mode,
        "outcome_policy": OUTCOME_POLICY,
        "episode_policy": EPISODE_POLICY,
        "retention_floor": RETENTION_FLOOR,
        "metric_semantics": {
            "strict_retention": (
                "Both count and portfolio-share retention ratios are at least "
                "the versioned retention floor."
            ),
            "directional_survival": (
                "Count and portfolio share both remain on the detected side of "
                "the original reference window."
            ),
            "non_reversal": (
                "The outcome is not a full reversal on both count and portfolio share."
            ),
            "priority": (
                "Current salience and evidence strength; not a forecast probability."
            ),
        },
        "horizons": calibration_by_horizon,
        "source_maturity_sensitivity": source_maturity,
        "episodes": {
            "count": len(episodes),
            "headline_episode_count": len(headline_episodes),
            "single_cutoff_episode_count": sum(
                item["signal_occurrence_count"] == 1 for item in episodes
            ),
            "open_episode_count": sum(item["status"] == "OPEN" for item in episodes),
            "termination_reason_counts": dict(
                sorted(Counter(item["termination_reason"] for item in episodes).items())
            ),
            "maturity_class_counts": dict(
                sorted(
                    Counter(
                        item["editorial"]["maturity_class"] for item in episodes
                    ).items()
                )
            ),
            "early_warning_lead_months": {
                "minimum": min(leads) if leads else None,
                "median": median(leads) if leads else None,
                "maximum": max(leads) if leads else None,
                "distribution": {
                    str(key): value for key, value in sorted(Counter(leads).items())
                },
            },
            "onset_outcomes": {
                f"+{horizon}m": _anchor_calibration(episodes, "onset", horizon)
                for horizon in HORIZONS_MONTHS
            },
            "first_headline_outcomes": {
                f"+{horizon}m": _anchor_calibration(
                    headline_episodes, "first_headline", horizon
                )
                for horizon in HORIZONS_MONTHS
            },
            "onset_outcomes_by_maturity": {
                f"+{horizon}m": _episode_maturity_calibration(episodes, horizon)
                for horizon in HORIZONS_MONTHS
            },
            "temporal_validation": {
                "+12m": _temporal_holdout_calibration(episodes, 12)
            },
        },
        "limitations": [
            "OUTCOME_IS_BIBLIOMETRIC_PERSISTENCE_NOT_SCIENTIFIC_VALIDATION",
            "RETROSPECTIVE_TAXONOMY_AND_SOURCE_SNAPSHOT",
        ],
    }

    outcomes_path = store.write_jsonl_gz(
        "backtest/outcomes/topic-momentum-event-outcomes.jsonl.gz",
        outcomes,
        overwrite=rebuild,
    )
    episodes_path = store.write_jsonl_gz(
        "backtest/outcomes/topic-momentum-episodes.jsonl.gz",
        episodes,
        overwrite=rebuild,
    )
    episode_index_path = store.write_json(
        "backtest/outcomes/topic-momentum-episode-index.json",
        episode_index,
        overwrite=rebuild,
    )
    calibration_path = store.write_json(
        "backtest/outcomes/topic-momentum-calibration-summary.json",
        calibration,
        overwrite=rebuild,
    )
    review_sample_path = store.write_json(
        "backtest/outcomes/topic-momentum-rising-review-sample.json",
        review_sample,
        overwrite=rebuild,
    )

    observed = sum(item["status"] == "OBSERVED" for item in outcomes)
    censored = len(outcomes) - observed
    warnings = []
    if manifest["temporal_semantics"] == "retrospective_snapshot":
        warnings.append("RETROSPECTIVE_RECONSTRUCTION_NOT_OBSERVED_HISTORY")
    if censored:
        warnings.append("RIGHT_CENSORED_RECENT_SIGNALS")
    if any(
        horizon < config.topic_momentum.analysis_window_months
        for horizon in HORIZONS_MONTHS
    ):
        warnings.append("SHORT_HORIZON_WINDOW_OVERLAPS_DETECTION_WINDOW")
    if review_sample["selected_count"] < review_sample["requested_count"]:
        warnings.append("RISING_REVIEW_SAMPLE_UNDERFILLED")
    quality = {
        "schema_version": "tm08-quality-report/0.2",
        "run_id": manifest["run_id"],
        "evaluator_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "outcome_contract": "topic-momentum-backtest/0.1",
        "outcome_policy": OUTCOME_POLICY,
        "episode_policy": EPISODE_POLICY,
        "backtest_data_mode": signals[0]["temporal_context"]["mode"],
        "evaluated_at": evaluated_at,
        "latest_available_cutoff": latest_available_cutoff,
        "source_maturity_policy": SOURCE_MATURITY_POLICY,
        "default_source_maturity_lag_months": (
            DEFAULT_SOURCE_MATURITY_LAG_MONTHS
        ),
        "latest_default_mature_cutoff": default_maturity[
            "latest_mature_evaluation_cutoff"
        ],
        "source_signal_count": len(signals),
        "expected_outcome_count": len(signals) * len(HORIZONS_MONTHS),
        "event_outcome_count": len(outcomes),
        "observed_outcome_count": observed,
        "right_censored_outcome_count": censored,
        "episode_count": len(episodes),
        "headline_episode_count": len(headline_episodes),
        "review_sample_count": review_sample["selected_count"],
        "review_sample_requested_count": review_sample["requested_count"],
        "unique_outcome_id_count": len(set(outcome_ids)),
        "unique_episode_id_count": len(set(episode_ids)),
        "source_value_mismatch_count": 0,
        "missing_available_target_count": 0,
        "invariant_error_count": 0,
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/tm08-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm08-result/0.2",
        "scope_mode": scope_mode,
        "evaluator_version": f"research-signal-instrument/{__version__}",
        "outcome_contract": "topic-momentum-backtest/0.1",
        "evaluated_at": evaluated_at,
        "event_outcome_count": len(outcomes),
        "observed_outcome_count": observed,
        "censored_outcome_count": censored,
        "episode_count": len(episodes),
        "headline_episode_count": len(headline_episodes),
        "review_sample_count": review_sample["selected_count"],
        "outputs": {
            "event_outcomes": outcomes_path.relative_to(store.root).as_posix(),
            "episodes": episodes_path.relative_to(store.root).as_posix(),
            "episode_index": episode_index_path.relative_to(store.root).as_posix(),
            "calibration_summary": calibration_path.relative_to(store.root).as_posix(),
            "rising_review_sample": review_sample_path.relative_to(
                store.root
            ).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("tm08-result.json", result, overwrite=rebuild)
    return TM08Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        event_outcome_count=len(outcomes),
        observed_outcome_count=observed,
        censored_outcome_count=censored,
        episode_count=len(episodes),
        headline_episode_count=len(headline_episodes),
        review_sample_count=review_sample["selected_count"],
        quality_report_path=quality_path,
    )
