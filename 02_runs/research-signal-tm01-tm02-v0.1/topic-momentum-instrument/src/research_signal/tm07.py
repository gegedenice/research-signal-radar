from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .config import RunConfig
from .errors import InvariantError
from .storage import RunStore
from .tm06 import (
    _in_window,
    _signal_envelope,
    priority_scores,
    scope_evidence_summary,
    select_representative_works,
)


@dataclass(frozen=True)
class TM07Result:
    scope_mode: str
    scope_dir: Path
    cutoff_count: int
    replayed_signal_count: int
    headline_candidate_count: int
    review_required_count: int
    evidence_mismatch_count: int
    quality_report_path: Path


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cutoff_iso(value: str) -> str:
    cutoff = datetime.combine(
        date.fromisoformat(value), time(23, 59, 59), tzinfo=timezone.utc
    )
    return cutoff.isoformat().replace("+00:00", "Z")


def _temporal_mode(manifest: dict[str, Any]) -> str:
    if manifest["temporal_semantics"] == "observed_vintage":
        return "observed_vintage"
    return "retrospective_reconstruction"


def temporal_context(
    manifest: dict[str, Any], information_cutoff: str, emitted_at: str
) -> dict[str, str]:
    context = {
        "mode": _temporal_mode(manifest),
        "emitted_at": emitted_at,
        "information_cutoff": _cutoff_iso(information_cutoff),
        "observation_vintage": manifest["data_vintage"],
        "cutoff_basis": "publication_date",
    }
    if _parse_datetime(context["information_cutoff"]) > _parse_datetime(emitted_at):
        raise InvariantError(
            f"TM-07 information cutoff {information_cutoff} is after emission time"
        )
    return context


def temporal_invariant_errors(
    signal: dict[str, Any], evidence_bundle: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    context = signal["temporal_context"]
    emitted_at = _parse_datetime(context["emitted_at"])
    cutoff = _parse_datetime(context["information_cutoff"])
    cutoff_date = cutoff.date().isoformat()

    if signal["detected_at"] != context["emitted_at"]:
        errors.append("DETECTED_AT_DIFFERS_FROM_EMITTED_AT")
    if signal["provenance"]["observation_vintage"] != context["observation_vintage"]:
        errors.append("PROVENANCE_VINTAGE_DIFFERS_FROM_TEMPORAL_CONTEXT")
    if signal["provenance"]["backtest_data_mode"] != context["mode"]:
        errors.append("PROVENANCE_MODE_DIFFERS_FROM_TEMPORAL_CONTEXT")
    if signal["analysis_context"]["current_window"]["end"] != cutoff_date:
        errors.append("CURRENT_WINDOW_END_DIFFERS_FROM_INFORMATION_CUTOFF")
    if cutoff > emitted_at:
        errors.append("INFORMATION_CUTOFF_AFTER_EMISSION")
    for work in evidence_bundle["representative_works"]:
        if work["publication_date"] > cutoff_date:
            errors.append(f"POST_CUTOFF_WORK:{work['work_id']}")
    cutoff_validation = evidence_bundle["cutoff_validation"]
    if cutoff_validation["post_cutoff_work_ids"]:
        errors.append("POST_CUTOFF_WORKS_IN_FULL_EVIDENCE_BUNDLE")
    if not cutoff_validation["passes"]:
        errors.append("FULL_EVIDENCE_CUTOFF_VALIDATION_FAILED")
    for evidence in signal["evidence"]:
        observed_at = _parse_datetime(evidence["observed_at"])
        if observed_at > emitted_at:
            errors.append(f"POST_EMISSION_EVIDENCE:{evidence['evidence_id']}")
        if context["mode"] == "observed_vintage" and observed_at > cutoff:
            errors.append(f"POST_CUTOFF_EVIDENCE_IN_OBSERVED_MODE:{evidence['evidence_id']}")
    return errors


def _evidence_bundle(
    assessment: dict[str, Any],
    current: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
    manifest: dict[str, Any],
    emitted_at: str,
) -> dict[str, Any]:
    expected_current = assessment["observation"]["current_count"]
    expected_comparison = assessment["observation"]["previous_count"]
    matches = len(current) == expected_current and len(comparison) == expected_comparison
    cutoff = assessment["evaluation_date"]
    all_works = current + comparison
    post_cutoff = sorted(
        item["work_id"] for item in all_works if item["publication_date"] > cutoff
    )
    return {
        "schema_version": "topic-momentum-replay-evidence/0.1",
        "evidence_bundle_id": (
            f"tmre:{assessment['topic']['id']}:{assessment['evaluation_date']}"
        ),
        "assessment_id": assessment["assessment_id"],
        "topic": assessment["topic"],
        "evaluation_date": assessment["evaluation_date"],
        "temporal_context": temporal_context(
            manifest, assessment["evaluation_date"], emitted_at
        ),
        "current_work_ids": sorted(item["work_id"] for item in current),
        "comparison_work_ids": sorted(item["work_id"] for item in comparison),
        "cutoff_validation": {
            "cutoff_basis": "publication_date",
            "information_cutoff": cutoff,
            "maximum_publication_date": max(
                (item["publication_date"] for item in all_works), default=None
            ),
            "post_cutoff_work_ids": post_cutoff,
            "passes": not post_cutoff,
        },
        "representative_works": select_representative_works(current, comparison),
        "scope_evidence": {
            "current_window": scope_evidence_summary(current),
            "comparison_window": scope_evidence_summary(comparison),
            "overall": scope_evidence_summary(current + comparison),
        },
        "selection_method": "citation-recency-actor-diversity/0.1",
        "count_crosscheck": {
            "expected_current": expected_current,
            "observed_current": len(current),
            "expected_comparison": expected_comparison,
            "observed_comparison": len(comparison),
            "matches": matches,
        },
        "query_manifest_ref": manifest["manifest_id"],
    }


def run_tm07(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM07Result:
    if resume and rebuild:
        raise InvariantError("TM-07 --resume and --rebuild are mutually exclusive")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm05-result.json",
        "tm06-result.json",
        "confidence/topic-momentum-assessments.jsonl.gz",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(
            f"TM-07 requires completed TM-05, TM-06 and TM-02 artifacts: {missing}"
        )

    result_path = store.path("tm07-result.json")
    quality_path = store.path("quality/tm07-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm07-result.json")
        if completed.get("emitter_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError(
                "TM-07 result was produced by another emitter version; use --rebuild"
            )
        return TM07Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            cutoff_count=completed["cutoff_count"],
            replayed_signal_count=completed["replayed_signal_count"],
            headline_candidate_count=completed["headline_candidate_count"],
            review_required_count=completed["review_required_count"],
            evidence_mismatch_count=completed["evidence_mismatch_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-07 result already exists; use --resume to reuse it or --rebuild "
            "to regenerate TM-07 replay artifacts only"
        )

    manifest = store.read_json("query-manifest.json")
    tm05_result = store.read_json("tm05-result.json")
    tm06_result = store.read_json("tm06-result.json")
    if tm06_result.get("schema_version") != "tm06-result/0.2":
        raise InvariantError("TM-07 requires TM-06.1 outputs; rerun TM-06 with --rebuild")
    emitted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    assessments = store.read_jsonl_gz(
        "confidence/topic-momentum-assessments.jsonl.gz"
    )
    observations = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    if len(assessments) != tm05_result["assessment_count"]:
        raise InvariantError("TM-07 assessment count differs from TM-05 result")
    if any(item["universe"]["scope_mode"] != scope_mode for item in assessments):
        raise InvariantError("TM-07 input contains another scope")

    observations_by_topic: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        topic = observation["primary_topic"]
        if topic is not None:
            observations_by_topic.setdefault(topic["id"], []).append(observation)

    by_cutoff: dict[str, list[dict[str, Any]]] = {}
    for assessment in assessments:
        by_cutoff.setdefault(assessment["evaluation_date"], []).append(assessment)

    replay_signals: list[dict[str, Any]] = []
    evidence_bundles: list[dict[str, Any]] = []
    replay_index: list[dict[str, Any]] = []
    cutoff_summaries: list[dict[str, Any]] = []
    mismatch_records: list[dict[str, Any]] = []
    invariant_records: list[dict[str, Any]] = []

    for cutoff in sorted(by_cutoff):
        cutoff_assessments = by_cutoff[cutoff]
        eligible = [
            item for item in cutoff_assessments if item["default_alert_eligible"]
        ]
        priorities = priority_scores(eligible)
        cutoff_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for assessment in eligible:
            topic_id = assessment["topic"]["id"]
            topic_observations = observations_by_topic.get(topic_id, [])
            current = [
                item
                for item in topic_observations
                if _in_window(item, assessment["effective_window"])
            ]
            comparison = [
                item
                for item in topic_observations
                if _in_window(item, assessment["comparison_window"])
            ]
            if not current and not comparison:
                raise InvariantError(
                    f"{topic_id}@{cutoff}: no WorkObservation available for replay evidence"
                )
            bundle = _evidence_bundle(
                assessment, current, comparison, manifest, emitted_at
            )
            if not bundle["count_crosscheck"]["matches"]:
                mismatch_records.append(
                    {
                        "topic_id": topic_id,
                        "information_cutoff": cutoff,
                        **bundle["count_crosscheck"],
                    }
                )
            signal_id = f"sig:topic-momentum:replay:{topic_id}:{cutoff}"
            signal = _signal_envelope(
                assessment,
                bundle,
                priorities[assessment["assessment_id"]],
                manifest,
                signal_id=signal_id,
                schema_version="signal-envelope/0.2",
                temporal_context=bundle["temporal_context"],
                detected_at=emitted_at,
            )
            signal["payload"]["replay"] = {
                "source_assessment_id": assessment["assessment_id"],
                "outcome_evaluated": False,
            }
            errors = temporal_invariant_errors(signal, bundle)
            if errors:
                invariant_records.append(
                    {"signal_id": signal_id, "errors": errors}
                )
            cutoff_pairs.append((signal, bundle))

        cutoff_pairs.sort(
            key=lambda pair: (-pair[0]["priority"]["score"], pair[0]["signal_id"])
        )
        for rank, (signal, bundle) in enumerate(cutoff_pairs, 1):
            signal["payload"]["replay"]["rank_within_cutoff"] = rank
            replay_signals.append(signal)
            evidence_bundles.append(bundle)
            replay_index.append(
                {
                    "information_cutoff": cutoff,
                    "rank_within_cutoff": rank,
                    "signal_id": signal["signal_id"],
                    "topic_id": signal["subject"]["id"],
                    "topic_label": signal["subject"]["label"],
                    "signal_label": signal["payload"]["signal_label"],
                    "confidence_level": signal["confidence"]["level"],
                    "priority_score": signal["priority"]["score"],
                    "editorial_tier": signal["payload"]["editorial"]["tier"],
                    "review_status": signal["payload"]["editorial"][
                        "review_status"
                    ],
                    "evidence_bundle_id": bundle["evidence_bundle_id"],
                }
            )

        cutoff_signals = [item[0] for item in cutoff_pairs]
        cutoff_summaries.append(
            {
                "schema_version": "topic-momentum-replay-cutoff/0.1",
                "information_cutoff": cutoff,
                "temporal_context": temporal_context(manifest, cutoff, emitted_at),
                "candidate_assessment_count": len(cutoff_assessments),
                "eligible_signal_count": len(cutoff_signals),
                "confidence_counts": dict(
                    sorted(
                        Counter(
                            item["confidence"]["level"] for item in cutoff_signals
                        ).items()
                    )
                ),
                "signal_label_counts": dict(
                    sorted(
                        Counter(
                            item["payload"]["signal_label"]
                            for item in cutoff_signals
                        ).items()
                    )
                ),
                "editorial_tier_counts": dict(
                    sorted(
                        Counter(
                            item["payload"]["editorial"]["tier"]
                            for item in cutoff_signals
                        ).items()
                    )
                ),
                "review_required_count": sum(
                    item["payload"]["editorial"]["review_status"] == "REQUIRED"
                    for item in cutoff_signals
                ),
            }
        )

    if invariant_records:
        raise InvariantError(
            f"TM-07 temporal invariants failed: {invariant_records[:3]}"
        )
    if not replay_signals:
        raise InvariantError("TM-07 produced no eligible historical signal")

    signals_path = store.write_jsonl_gz(
        "backtest/replay/topic-momentum-replay-signals.jsonl.gz",
        replay_signals,
        overwrite=rebuild,
    )
    evidence_path = store.write_jsonl_gz(
        "backtest/replay/topic-momentum-replay-evidence.jsonl.gz",
        evidence_bundles,
        overwrite=rebuild,
    )
    index_path = store.write_json(
        "backtest/replay/topic-momentum-replay-index.json",
        replay_index,
        overwrite=rebuild,
    )
    summaries_path = store.write_json(
        "backtest/replay/topic-momentum-cutoff-summaries.json",
        cutoff_summaries,
        overwrite=rebuild,
    )

    tier_counts = Counter(
        item["payload"]["editorial"]["tier"] for item in replay_signals
    )
    review_counts = Counter(
        item["payload"]["editorial"]["review_status"] for item in replay_signals
    )
    signals_per_cutoff = [item["eligible_signal_count"] for item in cutoff_summaries]
    partial_scope_count = sum(
        not item["scope_evidence"]["overall"]["fully_materialized"]
        for item in evidence_bundles
    )
    warnings = []
    if _temporal_mode(manifest) == "retrospective_reconstruction":
        warnings.append("RETROSPECTIVE_RECONSTRUCTION_NOT_OBSERVED_HISTORY")
    if mismatch_records:
        warnings.append("EVIDENCE_COUNT_MISMATCH")
    if partial_scope_count:
        warnings.append("SCOPE_EVIDENCE_PARTIALLY_MATERIALIZED")
    quality = {
        "schema_version": "tm07-quality-report/0.1",
        "run_id": manifest["run_id"],
        "emitter_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "temporal_contract": "research-signal-temporal/0.2",
        "backtest_data_mode": _temporal_mode(manifest),
        "emitted_at": emitted_at,
        "cutoff_count": len(cutoff_summaries),
        "earliest_information_cutoff": cutoff_summaries[0]["information_cutoff"],
        "latest_information_cutoff": cutoff_summaries[-1]["information_cutoff"],
        "candidate_assessment_count": len(assessments),
        "replayed_signal_count": len(replay_signals),
        "signals_per_cutoff": {
            "minimum": min(signals_per_cutoff),
            "median": median(signals_per_cutoff),
            "maximum": max(signals_per_cutoff),
        },
        "editorial_tier_counts": dict(sorted(tier_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "evidence_bundle_count": len(evidence_bundles),
        "evidence_mismatch_count": len(mismatch_records),
        "evidence_mismatches": mismatch_records,
        "signals_with_partially_materialized_scope_evidence": partial_scope_count,
        "temporal_invariant_error_count": 0,
        "future_outcomes_included": False,
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/tm07-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm07-result/0.1",
        "scope_mode": scope_mode,
        "emitter_version": f"research-signal-instrument/{__version__}",
        "temporal_contract": "research-signal-temporal/0.2",
        "emitted_at": emitted_at,
        "cutoff_count": len(cutoff_summaries),
        "replayed_signal_count": len(replay_signals),
        "headline_candidate_count": tier_counts["HEADLINE_CANDIDATE"],
        "review_required_count": review_counts["REQUIRED"],
        "evidence_mismatch_count": len(mismatch_records),
        "outputs": {
            "replay_signals": signals_path.relative_to(store.root).as_posix(),
            "replay_evidence": evidence_path.relative_to(store.root).as_posix(),
            "replay_index": index_path.relative_to(store.root).as_posix(),
            "cutoff_summaries": summaries_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("tm07-result.json", result, overwrite=rebuild)
    return TM07Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        cutoff_count=len(cutoff_summaries),
        replayed_signal_count=len(replay_signals),
        headline_candidate_count=tier_counts["HEADLINE_CANDIDATE"],
        review_required_count=review_counts["REQUIRED"],
        evidence_mismatch_count=len(mismatch_records),
        quality_report_path=quality_path,
    )
