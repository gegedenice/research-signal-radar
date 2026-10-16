from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from . import __version__
from .config import RunConfig, TopicMomentumConfig
from .errors import InvariantError
from .storage import RunStore, sha256_json
from .tm04 import classify_windows


@dataclass(frozen=True)
class TM05Result:
    scope_mode: str
    scope_dir: Path
    assessment_count: int
    latest_candidate_count: int
    eligible_count: int
    quality_report_path: Path


def sensitivity_profiles(
    base: TopicMomentumConfig,
) -> dict[str, TopicMomentumConfig]:
    return {
        "lenient": replace(
            base,
            min_total_history=4,
            min_current=2,
            min_previous=2,
            min_active_months=1,
            min_abs_delta=1,
            rise_count_ratio=1.35,
            fall_count_ratio=0.74,
            rise_share_ratio=1.15,
            fall_share_ratio=0.87,
            min_topic_coverage=0.90,
        ),
        "default": base,
        "strict": replace(
            base,
            min_total_history=12,
            min_current=5,
            min_previous=5,
            min_active_months=3,
            min_abs_delta=3,
            rise_count_ratio=1.75,
            fall_count_ratio=0.57,
            rise_share_ratio=1.40,
            fall_share_ratio=0.71,
            min_topic_coverage=0.95,
        ),
    }


def _signal_label(classification: dict[str, Any]) -> str:
    direction = classification["momentum_direction"]
    if direction in {"RISING", "FALLING"}:
        return direction
    presence = classification["presence_status"]
    if presence in {"NEW", "REACTIVATED", "DORMANT"}:
        return presence
    return "NONE"


def _signal_support(record: dict[str, Any]) -> int:
    classification = record["classification"]
    direction = classification["momentum_direction"]
    presence = classification["presence_status"]
    observation = record["observation"]
    if direction == "RISING" or presence in {"NEW", "REACTIVATED"}:
        return observation["current_count"]
    if direction == "FALLING" or presence == "DORMANT":
        return observation["previous_count"]
    return max(observation["current_count"], observation["previous_count"])


def _reclassify(
    record: dict[str, Any], parameters: TopicMomentumConfig
) -> dict[str, Any]:
    observation = record["observation"]
    return classify_windows(
        current=record["effective_window"],
        previous=record["comparison_window"],
        prior=record["prior_window"],
        history_count=observation["history_count"],
        total_history_count=(
            observation["history_count"]
            + observation["previous_count"]
            + observation["current_count"]
        ),
        baseline_windows=[],
        parameters=parameters,
    )["classification"]


def assess_candidate(
    record: dict[str, Any],
    profiles: dict[str, TopicMomentumConfig],
) -> dict[str, Any]:
    original_label = _signal_label(record["classification"])
    if original_label == "NONE" or not record["candidate"]:
        raise InvariantError(
            f"{record['classification_id']}: TM-05 received a non-candidate"
        )

    sensitivity: dict[str, dict[str, Any]] = {}
    for name, parameters in profiles.items():
        classification = _reclassify(record, parameters)
        label = _signal_label(classification)
        sensitivity[name] = {
            "parameters_hash": sha256_json(asdict(parameters)),
            "signal_label": label,
            "presence_status": classification["presence_status"],
            "momentum_direction": classification["momentum_direction"],
            "growth_mode": classification["growth_mode"],
            "candidate": label != "NONE",
            "matches_default_label": label == original_label,
        }
    if sensitivity["default"]["signal_label"] != original_label:
        raise InvariantError(
            f"{record['classification_id']}: stored TM-04 result is not reproducible"
        )
    stable_profile_count = sum(
        item["matches_default_label"] for item in sensitivity.values()
    )
    parameter_stability = stable_profile_count / len(sensitivity)

    observation = record["observation"]
    support = _signal_support(record)
    history = observation["history_count"]
    coverage = min(
        observation["topic_coverage_current"],
        observation["topic_coverage_previous"],
    )
    complete = all(
        record[field]["is_complete"]
        for field in ("effective_window", "comparison_window", "prior_window")
    )
    streak = record["direction_streak"]
    presence = record["classification"]["presence_status"]
    direction = record["classification"]["momentum_direction"]

    if support >= 5 and history >= 12:
        sample_score = 1.0
        sample_status = "strong"
    elif support >= 3 and history >= 6:
        sample_score = 0.7
        sample_status = "adequate"
    else:
        sample_score = 0.35
        sample_status = "weak"

    if coverage >= 0.95:
        coverage_score = 1.0
    elif coverage >= 0.90:
        coverage_score = 0.7
    else:
        coverage_score = 0.2

    if streak >= 2:
        temporal_score = 1.0
    elif streak == 1:
        temporal_score = 0.65
    elif presence in {"NEW", "REACTIVATED", "DORMANT"}:
        temporal_score = 0.4
    else:
        temporal_score = 0.2

    temporal_semantics = record["provenance"]["temporal_semantics"]
    taxonomy_change = record["classification"]["taxonomy_change"]
    if not taxonomy_change:
        taxonomy_score = 1.0
        taxonomy_status = "stable_in_vintage"
    elif temporal_semantics == "retrospective_snapshot":
        taxonomy_score = 0.8
        taxonomy_status = "retrospective_taxonomy_projection"
    else:
        taxonomy_score = 0.3
        taxonomy_status = "change_during_observed_baseline"

    components = {
        "sample_support": sample_score,
        "coverage": coverage_score,
        "temporal_consistency": temporal_score,
        "window_completeness": 1.0 if complete else 0.0,
        "scope_stability": 1.0,
        "taxonomy_stability": taxonomy_score,
        "parameter_stability": round(parameter_stability, 12),
    }
    weights = {
        "sample_support": 0.25,
        "coverage": 0.15,
        "temporal_consistency": 0.20,
        "window_completeness": 0.10,
        "scope_stability": 0.10,
        "taxonomy_stability": 0.10,
        "parameter_stability": 0.10,
    }
    score = round(
        sum(components[name] * weight for name, weight in weights.items()), 12
    )

    very_low = (
        not complete
        or coverage < 0.90
        or taxonomy_status == "change_during_observed_baseline"
    )
    high = (
        not very_low
        and direction in {"RISING", "FALLING"}
        and sample_status == "strong"
        and coverage >= 0.95
        and streak >= 2
        and stable_profile_count == len(sensitivity)
    )
    medium = (
        not very_low
        and sample_status in {"strong", "adequate"}
        and stable_profile_count >= 2
        and (streak >= 1 or presence in {"NEW", "REACTIVATED", "DORMANT"})
    )
    if very_low:
        level = "VERY_LOW"
    elif high:
        level = "HIGH"
    elif medium:
        level = "MEDIUM"
    else:
        level = "LOW"

    reasons = []
    limitations = []
    if sample_status == "strong":
        reasons.append("STRONG_SAMPLE_SUPPORT")
    elif sample_status == "adequate":
        reasons.append("ADEQUATE_SAMPLE_SUPPORT")
    else:
        limitations.append("WEAK_SAMPLE_SUPPORT")
    if coverage >= 0.95:
        reasons.append("HIGH_TOPIC_COVERAGE")
    elif coverage < 0.90:
        limitations.append("LOW_TOPIC_COVERAGE")
    if streak >= 2:
        reasons.append("MULTI_EVALUATION_DIRECTION")
    elif streak == 1:
        limitations.append("SINGLE_EVALUATION_DIRECTION")
    else:
        limitations.append("NO_SUSTAINED_DIRECTION")
    if stable_profile_count == len(sensitivity):
        reasons.append("STABLE_ACROSS_PARAMETER_PROFILES")
    elif stable_profile_count == 2:
        limitations.append("PARTIAL_PARAMETER_SENSITIVITY")
    else:
        limitations.append("HIGH_PARAMETER_SENSITIVITY")
    if taxonomy_status == "retrospective_taxonomy_projection":
        limitations.append("RETROSPECTIVE_TAXONOMY_PROJECTION")
    elif taxonomy_status == "change_during_observed_baseline":
        limitations.append("TAXONOMY_CHANGE_DURING_OBSERVED_BASELINE")
    if not complete:
        limitations.append("INCOMPLETE_WINDOW")

    # Corroboration multi-échelle (v0.2) : n'introduit aucun seuil de détection et
    # ne masque aucun signal. CONTRADICTED (topic en mouvement, subfield parent en
    # sens opposé) pose la limitation SCALE_CONTRADICTED — le signal reste visible et
    # explorable, mais TM-06 exige une revue et lui interdit le rang « headline ».
    # CORROBORATED est enregistré comme raison de confiance.
    scale_corroboration = record["classification"].get("scale_corroboration") or {}
    scale_concordance = scale_corroboration.get("concordance")
    if scale_concordance == "CORROBORATED":
        reasons.append("SCALE_CORROBORATED")
    elif scale_concordance == "CONTRADICTED":
        limitations.append("SCALE_CONTRADICTED")

    eligible = level in {"HIGH", "MEDIUM"}
    return {
        "schema_version": "topic-momentum-confidence/0.1",
        "assessment_id": f"tm05:{record['classification_id']}",
        "source_classification_id": record["classification_id"],
        "run_id": record["run_id"],
        "query_manifest_ref": record["query_manifest_ref"],
        "universe": record["universe"],
        "stream_id": record["stream_id"],
        "topic": record["topic"],
        "evaluation_date": record["evaluation_date"],
        "signal_label": original_label,
        "classification": record["classification"],
        "direction_streak": streak,
        "observation": record["observation"],
        "delta": record["delta"],
        "baseline": record["baseline"],
        "effective_window": record["effective_window"],
        "comparison_window": record["comparison_window"],
        "prior_window": record["prior_window"],
        "confidence": {
            "level": level,
            "score": score,
            "components": components,
            "weights": weights,
            "reasons": reasons,
            "limitations": limitations,
            "scale_concordance": scale_concordance,
        },
        "sensitivity": {
            "stable_profile_count": stable_profile_count,
            "profile_count": len(sensitivity),
            "profiles": sensitivity,
        },
        "taxonomy_status": taxonomy_status,
        "default_alert_eligible": eligible,
        "provenance": record["provenance"],
    }


def run_tm05(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM05Result:
    if resume and rebuild:
        raise InvariantError("TM-05 --resume and --rebuild are mutually exclusive")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm04-result.json",
        "classifications/topic-momentum-classifications.jsonl.gz",
        "classifications/topic-momentum-parameters.json",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"TM-05 requires completed TM-04 artifacts: {missing}")

    result_path = store.path("tm05-result.json")
    quality_path = store.path("quality/tm05-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm05-result.json")
        return TM05Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            assessment_count=completed["assessment_count"],
            latest_candidate_count=completed["latest_candidate_count"],
            eligible_count=completed["eligible_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-05 result already exists; use --resume to reuse it or --rebuild "
            "to regenerate TM-05 confidence and quality artifacts"
        )

    manifest = store.read_json("query-manifest.json")
    tm04_result = store.read_json("tm04-result.json")
    stored_parameters = store.read_json(
        "classifications/topic-momentum-parameters.json"
    )
    configured_parameters = asdict(config.topic_momentum)
    if stored_parameters != configured_parameters:
        raise InvariantError("TM-05 configuration differs from TM-04 parameters")
    expected_hash = sha256_json(configured_parameters)

    classifications = store.read_jsonl_gz(
        "classifications/topic-momentum-classifications.jsonl.gz"
    )
    if any(item["detector"]["parameters_hash"] != expected_hash for item in classifications):
        raise InvariantError("TM-05 found a TM-04 parameter hash mismatch")
    if any(item["universe"]["scope_mode"] != scope_mode for item in classifications):
        raise InvariantError("TM-05 found classifications from another scope")
    run_ids = {item["run_id"] for item in classifications}
    manifest_refs = {item["query_manifest_ref"] for item in classifications}
    universe_keys = {
        (item["universe"]["id"], item["universe"]["version"])
        for item in classifications
    }
    if len(run_ids) != 1 or len(manifest_refs) != 1 or len(universe_keys) != 1:
        raise InvariantError("TM-05 scope or provenance is not stable across classifications")

    profiles = sensitivity_profiles(config.topic_momentum)
    candidates = [item for item in classifications if item["candidate"]]
    assessments = [assess_candidate(item, profiles) for item in candidates]
    latest_date = tm04_result["latest_evaluation_date"]
    latest = [item for item in assessments if item["evaluation_date"] == latest_date]
    if len(latest) != tm04_result["candidate_count"]:
        raise InvariantError(
            "TM-05 latest candidate count differs from completed TM-04 result"
        )
    eligible = [item for item in latest if item["default_alert_eligible"]]

    all_path = store.write_jsonl_gz(
        "confidence/topic-momentum-assessments.jsonl.gz", assessments, overwrite=rebuild
    )
    latest_path = store.write_jsonl_gz(
        "confidence/topic-momentum-latest.jsonl.gz", latest, overwrite=rebuild
    )
    eligible_path = store.write_jsonl_gz(
        "confidence/topic-momentum-eligible-latest.jsonl.gz", eligible, overwrite=rebuild
    )
    profile_document = {
        name: {
            "parameters": asdict(parameters),
            "parameters_hash": sha256_json(asdict(parameters)),
        }
        for name, parameters in profiles.items()
    }
    profiles_path = store.write_json(
        "confidence/topic-momentum-sensitivity-profiles.json",
        profile_document,
        overwrite=rebuild,
    )

    level_counts = Counter(item["confidence"]["level"] for item in latest)
    label_counts = Counter(item["signal_label"] for item in latest)
    eligible_label_counts = Counter(item["signal_label"] for item in eligible)
    stability_counts = Counter(
        item["sensitivity"]["stable_profile_count"] for item in latest
    )
    taxonomy_counts = Counter(item["taxonomy_status"] for item in latest)
    scale_concordance_counts = Counter(
        item["confidence"].get("scale_concordance") for item in latest
    )
    warnings = []
    if taxonomy_counts.get("retrospective_taxonomy_projection"):
        warnings.append("RETROSPECTIVE_TAXONOMY_PROJECTION")
    if not level_counts.get("HIGH"):
        warnings.append("NO_HIGH_CONFIDENCE_CANDIDATE")
    quality = {
        "schema_version": "tm05-quality-report/0.1",
        "run_id": manifest["run_id"],
        "guard_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "source_parameters_hash": expected_hash,
        "sensitivity_profiles": profile_document,
        "assessment_count": len(assessments),
        "latest_evaluation_date": latest_date,
        "latest_candidate_count": len(latest),
        "eligible_count": len(eligible),
        "latest_confidence_counts": dict(sorted(level_counts.items())),
        "latest_signal_label_counts": dict(sorted(label_counts.items())),
        "eligible_signal_label_counts": dict(sorted(eligible_label_counts.items())),
        "latest_parameter_stability_counts": {
            str(key): value for key, value in sorted(stability_counts.items())
        },
        "latest_taxonomy_status_counts": dict(sorted(taxonomy_counts.items())),
        "latest_scale_concordance_counts": {
            str(key): value for key, value in sorted(
                scale_concordance_counts.items(), key=lambda kv: (kv[0] is None, kv[0])
            )
        },
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/tm05-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm05-result/0.1",
        "scope_mode": scope_mode,
        "guard_version": f"research-signal-instrument/{__version__}",
        "assessment_count": len(assessments),
        "latest_evaluation_date": latest_date,
        "latest_candidate_count": len(latest),
        "eligible_count": len(eligible),
        "outputs": {
            "all_assessments": str(all_path.relative_to(store.root)),
            "latest_assessments": str(latest_path.relative_to(store.root)),
            "eligible_latest": str(eligible_path.relative_to(store.root)),
            "sensitivity_profiles": str(profiles_path.relative_to(store.root)),
            "quality_report": str(quality_path.relative_to(store.root)),
        },
    }
    store.write_json("tm05-result.json", result, overwrite=rebuild)
    return TM05Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        assessment_count=len(assessments),
        latest_candidate_count=len(latest),
        eligible_count=len(eligible),
        quality_report_path=quality_path,
    )
