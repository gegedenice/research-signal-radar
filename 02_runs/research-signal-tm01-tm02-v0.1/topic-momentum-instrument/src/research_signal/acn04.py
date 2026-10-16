from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .acn02 import _assessment, _attach_internal_events, _base_reasons, _history, _period, _windows
from .acn03 import _build_evidence, _build_signal, _cluster_id, _confidence, _editorial, _priorities
from .config import RunConfig
from .dates import add_months, month_end
from .errors import InvariantError
from .storage import RunStore, sha256_json


REVIEW_PER_OUTCOME = 10


@dataclass(frozen=True)
class ACN04Result:
    scope_mode: str
    scope_dir: Path
    cutoff_count: int
    eligible_cutoff_count: int
    replayed_signal_count: int
    observed_outcome_count: int
    censored_outcome_count: int
    continued_outcome_count: int
    quality_report_path: Path


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _cutoffs(config: RunConfig) -> list[date]:
    current = date.fromisoformat(
        config.citation_acceleration.backtest_start_date
    )
    end = config.collection.to_publication_date
    values: list[date] = []
    while current <= end:
        values.append(current)
        current = month_end(
            add_months(
                current, config.citation_acceleration.backtest_step_months
            )
        )
    if not values or values[-1] != end:
        values.append(end)
    return values


def _histories_and_assessments(
    config: RunConfig,
    cutoff: date,
    all_events: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    windows = _windows(cutoff, config.actor_collaboration_novelty)
    events = [
        event
        for event in all_events
        if date.fromisoformat(event["publication_date"]) <= cutoff
    ]
    actor_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    edge_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        external_id = event["external_institution"]["id"]
        anchor_id = event["anchor_institution"]["id"]
        actor_groups[external_id].append(event)
        edge_groups[(anchor_id, external_id)].append(event)

    actor_internal: list[dict[str, Any]] = []
    for external_id in sorted(actor_groups):
        grouped = actor_groups[external_id]
        history = _history(
            subject_type="institution",
            external_institution=grouped[0]["external_institution"],
            anchor_institution=None,
            events=grouped,
            windows=windows,
            cutoff=cutoff,
        )
        actor_internal.append(_attach_internal_events(history, grouped, windows))

    edge_internal: list[dict[str, Any]] = []
    for edge_key in sorted(edge_groups):
        grouped = edge_groups[edge_key]
        history = _history(
            subject_type="institution_edge",
            external_institution=grouped[0]["external_institution"],
            anchor_institution=grouped[0]["anchor_institution"],
            events=grouped,
            windows=windows,
            cutoff=cutoff,
        )
        edge_internal.append(_attach_internal_events(history, grouped, windows))

    recent_start = date.fromisoformat(windows["recent_baseline"]["from"])
    sufficient_history = (
        config.collection.from_publication_date <= recent_start
    )
    actor_assessments: list[dict[str, Any]] = []
    actor_candidate_ids: set[str] = set()
    for history in actor_internal:
        reasons = _base_reasons(
            history, config.actor_collaboration_novelty, sufficient_history
        )
        label = None
        if not reasons:
            label = (
                "REACTIVATED_EXTERNAL_ACTOR"
                if history["windows"]["older_history"]["work_count"]
                else "NEW_EXTERNAL_ACTOR"
            )
            actor_candidate_ids.add(history["external_institution"]["id"])
        actor_assessments.append(
            _assessment(history, label=label, reasons=reasons, cutoff=cutoff)
        )

    edge_assessments: list[dict[str, Any]] = []
    for history in edge_internal:
        reasons = _base_reasons(
            history, config.actor_collaboration_novelty, sufficient_history
        )
        external_id = history["external_institution"]["id"]
        anchor_id = history["anchor_institution"]["id"]
        other_anchor = any(
            _period(event["publication_date"], windows) == "recent_baseline"
            and event["anchor_institution"]["id"] != anchor_id
            for event in actor_groups[external_id]
        )
        if not other_anchor:
            reasons.append("ACTOR_NOT_ACTIVE_WITH_OTHER_ANCHOR_IN_RECENT_BASELINE")
        label = None
        if not reasons:
            label = (
                "REACTIVATED_COLLABORATION"
                if history["windows"]["older_history"]["work_count"]
                else "NEW_COLLABORATION"
            )
            if external_id in actor_candidate_ids:
                label = None
                reasons.append("ACTOR_SIGNAL_PRECEDENCE")
        assessment = _assessment(
            history, label=label, reasons=reasons, cutoff=cutoff
        )
        assessment["metrics"][
            "external_actor_active_with_other_anchor_in_recent_baseline"
        ] = other_anchor
        edge_assessments.append(assessment)

    assessments = actor_assessments + edge_assessments
    candidates = [item for item in assessments if item["eligible_for_detection"]]
    actor_histories = {
        item["external_institution"]["id"]: item for item in actor_internal
    }
    histories = {item["history_id"]: item for item in actor_internal + edge_internal}
    reason_counts = Counter(
        reason
        for item in assessments
        for reason in item["abstention"]["reasons"]
    )
    diagnostics = {
        "sufficient_history": sufficient_history,
        "assessment_count": len(assessments),
        "actor_history_count": len(actor_internal),
        "edge_history_count": len(edge_internal),
        "abstention_reason_counts": dict(sorted(reason_counts.items())),
        "windows": windows,
    }
    return candidates, actor_histories, histories, diagnostics


def _outcome(
    signal: dict[str, Any],
    events: list[dict[str, Any]],
    latest: date,
    horizon_months: int,
    evaluated_at: str,
) -> dict[str, Any]:
    cutoff = date.fromisoformat(signal["payload"]["replay"]["cutoff"])
    target = month_end(add_months(cutoff, horizon_months))
    subject_type = signal["payload"]["subject_type"]
    external_id = signal["payload"]["external_institution"]["id"]
    anchor = signal["payload"].get("anchor_institution")
    base = {
        "schema_version": "actor-collaboration-novelty-outcome/0.1",
        "outcome_id": f"acn04:{signal['signal_id']}:+{horizon_months}m",
        "signal_id": signal["signal_id"],
        "subject": signal["subject"],
        "signal_label": signal["payload"]["signal_label"],
        "horizon_months": horizon_months,
        "detection_cutoff": cutoff.isoformat(),
        "target_cutoff": target.isoformat(),
        "evaluation_window": {
            "from": (cutoff + timedelta(days=1)).isoformat(),
            "to": target.isoformat(),
        },
        "status": "RIGHT_CENSORED",
        "outcome": None,
        "provenance": {
            "evaluated_at": evaluated_at,
            "backtest_data_mode": "retrospective_reconstruction",
            "source_signal_schema": signal["schema_version"],
        },
    }
    if target > latest:
        base["censoring"] = {
            "reason": "TARGET_AFTER_INFORMATION_CUTOFF",
            "latest_available_cutoff": latest.isoformat(),
        }
        return base

    future_events = [
        event
        for event in events
        if cutoff < date.fromisoformat(event["publication_date"]) <= target
        and event["external_institution"]["id"] == external_id
        and (
            subject_type == "institution"
            or (
                anchor is not None
                and event["anchor_institution"]["id"] == anchor["id"]
            )
        )
    ]
    future_work_ids = sorted({event["work_id"] for event in future_events})
    dates = sorted({event["publication_date"] for event in future_events})
    label = "CONTINUED" if future_work_ids else "ONE_OFF"
    base["status"] = "OBSERVED"
    base["outcome"] = {
        "label": label,
        "future_work_count": len(future_work_ids),
        "future_work_ids": future_work_ids,
        "first_future_publication_date": dates[0] if dates else None,
    }
    base["censoring"] = None
    return base


def _review_sample(
    outcomes: list[dict[str, Any]],
    signals_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    observed = [item for item in outcomes if item["status"] == "OBSERVED"]
    observed.sort(
        key=lambda item: (
            -signals_by_id[item["signal_id"]]["priority"]["score"],
            item["signal_id"],
        )
    )
    sample: list[dict[str, Any]] = []
    for label in ("CONTINUED", "ONE_OFF"):
        for item in [
            value for value in observed if value["outcome"]["label"] == label
        ][:REVIEW_PER_OUTCOME]:
            signal = signals_by_id[item["signal_id"]]
            sample.append(
                {
                    **item,
                    "priority_score": signal["priority"]["score"],
                    "confidence_level": signal["confidence"]["level"],
                    "current_work_count": signal["payload"]["current_work_count"],
                }
            )
    return sample


def _markdown(
    summary: dict[str, Any],
    cutoff_summaries: list[dict[str, Any]],
    sample: list[dict[str, Any]],
) -> str:
    rate = summary["continuation_rate"]
    lines = [
        "# Actor & collaboration novelty — backtest minimal",
        "",
        "Replay semestriel rétrospectif. Une continuation signifie seulement qu'au moins une nouvelle œuvre matérialise le même acteur ou la même arête dans les douze mois suivants.",
        "",
        f"- Signaux rejoués : **{summary['replayed_signal_count']}**",
        f"- Issues observées : **{summary['observed_outcome_count']}**",
        f"- `CONTINUED` : **{summary['continued_count']}**",
        f"- `ONE_OFF` : **{summary['one_off_count']}**",
        f"- `RIGHT_CENSORED` : **{summary['censored_outcome_count']}**",
        f"- Taux de continuation : **{rate:.1%}**" if rate is not None else "- Taux de continuation : n/a",
        "",
        "## Cutoffs",
        "",
        "| Cutoff | Historique suffisant | Assessments | Signaux | Issues observables |",
        "|---|---|---:|---:|---:|",
    ]
    for item in cutoff_summaries:
        lines.append(
            f"| {item['cutoff']} | {'oui' if item['sufficient_history'] else 'non'} | "
            f"{item['assessment_count']} | {item['signal_count']} | "
            f"{item['observable_outcome_count']} |"
        )
    lines.extend(
        [
            "",
            "## Échantillon de revue",
            "",
            "| Sujet | Cutoff | Label | Œuvres au signal | Œuvres +12m | Issue |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for item in sample:
        label = item["subject"]["label"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {label} | {item['detection_cutoff']} | {item['signal_label']} | "
            f"{item['current_work_count']} | {item['outcome']['future_work_count']} | "
            f"{item['outcome']['label']} |"
        )
    lines.extend(
        [
            "",
            "## Limites",
            "",
            "Le replay reconstruit le passé depuis le snapshot OpenAlex courant. Il teste la cohérence temporelle et l'utilité potentielle de l'alerte, pas les conditions historiques exactes d'indexation ni l'importance scientifique de la collaboration.",
        ]
    )
    return "\n".join(lines)


def run_acn04(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> ACN04Result:
    if resume and rebuild:
        raise InvariantError("ACN-04 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "acn03-result.json",
        "collaborations/collaboration-events.jsonl.gz",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"ACN-04 requires completed ACN-03 artifacts: {missing}")

    result_path = store.path("acn04-result.json")
    quality_path = store.path("quality/acn04-quality-report.json")
    evaluator_version = f"research-signal-instrument/{__version__}"
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("acn04-result.json")
        if completed.get("evaluator_version") != evaluator_version:
            raise InvariantError(
                "ACN-04 result was produced by another version; use --rebuild"
            )
        return ACN04Result(
            scope_mode,
            store.root,
            completed["cutoff_count"],
            completed["eligible_cutoff_count"],
            completed["replayed_signal_count"],
            completed["observed_outcome_count"],
            completed["censored_outcome_count"],
            completed["continued_outcome_count"],
            quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("ACN-04 result already exists; use --resume or --rebuild")

    manifest = store.read_json("query-manifest.json")
    acn03_result = store.read_json("acn03-result.json")
    if acn03_result.get("schema_version") != "acn03-result/0.1":
        raise InvariantError("ACN-04 requires acn03-result/0.1")
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("ACN-04 scope differs from query manifest")
    events = store.read_jsonl_gz("collaborations/collaboration-events.jsonl.gz")
    if any(
        item.get("schema_version") != "collaboration-event-observation/0.1"
        for item in events
    ):
        raise InvariantError(
            "ACN-04 requires collaboration-event-observation/0.1 inputs"
        )
    event_ids = [item["event_id"] for item in events]
    if len(event_ids) != len(set(event_ids)):
        raise InvariantError("ACN-04 received duplicate collaboration event IDs")
    works = {
        item["work_id"]: item
        for item in store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    }
    unknown_work_ids = sorted({item["work_id"] for item in events} - set(works))
    if unknown_work_ids:
        raise InvariantError("ACN-04 collaboration events do not resolve to works")
    events_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_work[event["work_id"]].append(event)

    emitted_at = _now()
    cutoffs = _cutoffs(config)
    global_parameters = {
        "schema_version": "actor-collaboration-novelty-backtest-parameters/0.1",
        "detector_stage": "ACN-04",
        "candidate_rule": asdict(config.actor_collaboration_novelty),
        "cutoff_policy": {
            "start_date": config.citation_acceleration.backtest_start_date,
            "step_months": config.citation_acceleration.backtest_step_months,
            "outcome_horizon_months": config.citation_acceleration.outcome_horizon_months,
        },
        "outcome_policy": "CONTINUED iff at least one new work materializes the same actor or edge during the next 12 months",
        "temporal_mode": "retrospective_reconstruction",
        "cutoff_parameter_sets": [],
    }
    all_signals: list[dict[str, Any]] = []
    all_evidence: list[dict[str, Any]] = []
    cutoff_summaries: list[dict[str, Any]] = []
    for cutoff in cutoffs:
        candidates, actor_histories, histories, diagnostics = (
            _histories_and_assessments(config, cutoff, events)
        )
        if not diagnostics["sufficient_history"]:
            candidates = []
        cluster_members: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for item in candidates:
            cluster_members[tuple(item["current_supporting_work_ids"])].append(
                item["assessment_id"]
            )
        clusters = {
            assessment_id: {
                "cluster_id": _cluster_id(list(work_ids)),
                "size": len(member_ids),
                "member_assessment_ids": sorted(member_ids),
                "supporting_work_ids": list(work_ids),
            }
            for work_ids, member_ids in cluster_members.items()
            for assessment_id in member_ids
        }
        confidences = {
            item["assessment_id"]: _confidence(
                item, clusters[item["assessment_id"]]["size"]
            )
            for item in candidates
        }
        priorities = (
            _priorities(candidates, confidences, actor_histories)
            if candidates
            else {}
        )
        cutoff_parameters = {
            "schema_version": "actor-collaboration-novelty-replay-parameters/0.1",
            "detector_stage": "ACN-04",
            "information_cutoff": cutoff.isoformat(),
            "windows": diagnostics["windows"],
            "candidate_rule": asdict(config.actor_collaboration_novelty),
            "confidence_method": "actor-collaboration-novelty-confidence/0.1",
            "priority_method": "actor-collaboration-novelty-priority/0.1",
        }
        cutoff_parameters["parameter_fingerprint"] = sha256_json(cutoff_parameters)
        global_parameters["cutoff_parameter_sets"].append(
            {
                "information_cutoff": cutoff.isoformat(),
                "parameter_fingerprint": cutoff_parameters["parameter_fingerprint"],
                "windows": diagnostics["windows"],
            }
        )
        cutoff_signals: list[dict[str, Any]] = []
        for item in candidates:
            cluster = clusters[item["assessment_id"]]
            confidence = confidences[item["assessment_id"]]
            priority = priorities[item["assessment_id"]]
            editorial = _editorial(priority, confidence, cluster["size"])
            evidence = _build_evidence(
                item,
                histories[item["history_ref"]],
                cluster,
                works,
                events_by_work,
                config,
            )
            evidence["schema_version"] = (
                "actor-collaboration-novelty-replay-evidence/0.1"
            )
            signal = _build_signal(
                item,
                confidence,
                priority,
                editorial,
                evidence,
                cutoff_parameters,
                manifest,
                config,
                scope_mode,
                emitted_at,
            )
            signal["quality_flags"] = sorted(
                set(signal["quality_flags"] + ["RETROSPECTIVE_RECONSTRUCTION"])
            )
            signal["payload"]["dossier_path"] = (
                "dossiers/actor-collaboration-novelty-backtest-summary.md"
            )
            signal["payload"]["replay"] = {
                "cutoff": cutoff.isoformat(),
                "rank_within_cutoff": None,
            }
            cutoff_signals.append(signal)
            all_evidence.append(evidence)
        cutoff_signals.sort(
            key=lambda item: (-item["priority"]["score"], item["signal_id"])
        )
        for rank, signal in enumerate(cutoff_signals, 1):
            signal["payload"]["replay"]["rank_within_cutoff"] = rank
        all_signals.extend(cutoff_signals)
        target = month_end(
            add_months(
                cutoff, config.citation_acceleration.outcome_horizon_months
            )
        )
        cutoff_summaries.append(
            {
                "cutoff": cutoff.isoformat(),
                "sufficient_history": diagnostics["sufficient_history"],
                "assessment_count": diagnostics["assessment_count"],
                "actor_history_count": diagnostics["actor_history_count"],
                "edge_history_count": diagnostics["edge_history_count"],
                "signal_count": len(cutoff_signals),
                "headline_count": sum(
                    item["payload"]["editorial"]["tier"]
                    == "HEADLINE_CANDIDATE"
                    for item in cutoff_signals
                ),
                "observable_outcome_count": (
                    len(cutoff_signals)
                    if target <= config.collection.to_publication_date
                    else 0
                ),
                "abstention_reason_counts": diagnostics[
                    "abstention_reason_counts"
                ],
            }
        )

    global_parameters["parameter_fingerprint"] = sha256_json(global_parameters)
    outcomes = [
        _outcome(
            signal,
            events,
            config.collection.to_publication_date,
            config.citation_acceleration.outcome_horizon_months,
            emitted_at,
        )
        for signal in all_signals
    ]
    signals_by_id = {item["signal_id"]: item for item in all_signals}
    observed = [item for item in outcomes if item["status"] == "OBSERVED"]
    continued = [
        item for item in observed if item["outcome"]["label"] == "CONTINUED"
    ]
    one_off = [
        item for item in observed if item["outcome"]["label"] == "ONE_OFF"
    ]
    by_label: dict[str, dict[str, Any]] = {}
    for label in (
        "NEW_EXTERNAL_ACTOR",
        "REACTIVATED_EXTERNAL_ACTOR",
        "NEW_COLLABORATION",
        "REACTIVATED_COLLABORATION",
    ):
        subset = [item for item in observed if item["signal_label"] == label]
        kept = sum(item["outcome"]["label"] == "CONTINUED" for item in subset)
        by_label[label] = {
            "observed_count": len(subset),
            "continued_count": kept,
            "continuation_rate": round(kept / len(subset), 6) if subset else None,
        }
    summary = {
        "schema_version": "actor-collaboration-novelty-backtest-summary/0.1",
        "cutoff_count": len(cutoffs),
        "eligible_cutoff_count": sum(
            item["sufficient_history"] for item in cutoff_summaries
        ),
        "replayed_signal_count": len(all_signals),
        "unique_subject_count": len({item["subject"]["id"] for item in all_signals}),
        "observed_outcome_count": len(observed),
        "censored_outcome_count": len(outcomes) - len(observed),
        "continued_count": len(continued),
        "one_off_count": len(one_off),
        "continuation_rate": (
            round(len(continued) / len(observed), 6) if observed else None
        ),
        "by_signal_label": by_label,
        "interpretation": "Descriptive retrospective replay; continuation is not scientific importance.",
    }
    sample = _review_sample(outcomes, signals_by_id)
    evidence_mismatch_count = sum(
        not all(item["count_crosscheck"].values()) for item in all_evidence
    )
    post_cutoff_evidence_count = sum(
        not item["count_crosscheck"]["no_post_cutoff_evidence"]
        for item in all_evidence
    )
    unresolved_outcome_count = sum(
        item["signal_id"] not in signals_by_id for item in outcomes
    )
    leaked_outcome_count = sum("outcome" in item["payload"] for item in all_signals)
    insufficient_cutoff_count = sum(
        not item["sufficient_history"] for item in cutoff_summaries
    )
    warnings = ["RETROSPECTIVE_RECONSTRUCTION"]
    if insufficient_cutoff_count:
        warnings.append("INSUFFICIENT_HISTORY_CUTOFF_EXCLUDED")
    if evidence_mismatch_count:
        warnings.append("EVIDENCE_COUNT_MISMATCH")
    quality = {
        "schema_version": "acn04-quality-report/0.1",
        "run_id": manifest.get("run_id", config.run_id),
        "evaluator_version": evaluator_version,
        "scope_mode": scope_mode,
        "cutoff_count": len(cutoffs),
        "eligible_cutoff_count": len(cutoffs) - insufficient_cutoff_count,
        "insufficient_history_cutoff_count": insufficient_cutoff_count,
        "replayed_signal_count": len(all_signals),
        "observed_outcome_count": len(observed),
        "censored_outcome_count": len(outcomes) - len(observed),
        "evidence_count_mismatch_count": evidence_mismatch_count,
        "post_cutoff_evidence_used_count": post_cutoff_evidence_count,
        "unresolved_outcome_signal_count": unresolved_outcome_count,
        "outcome_leakage_into_signal_count": leaked_outcome_count,
        "all_replayed_candidates_satisfy_rule": all(
            len(item["payload"]["supporting_work_ids"])
            >= config.actor_collaboration_novelty.min_current_works
            and item["payload"]["current_active_months"]
            >= config.actor_collaboration_novelty.min_active_months
            for item in all_signals
        ),
        "temporal_mode": "retrospective_reconstruction",
        "warnings": warnings,
        "resumed": resume,
        "rebuilt": rebuild,
    }
    overwrite = rebuild
    paths = {
        "parameters": store.write_json(
            "backtest/actor-collaboration-novelty-backtest-parameters.json",
            global_parameters,
            overwrite=overwrite,
        ),
        "signals": store.write_jsonl_gz(
            "backtest/actor-collaboration-novelty-replay-signals.jsonl.gz",
            all_signals,
            overwrite=overwrite,
        ),
        "evidence": store.write_jsonl_gz(
            "backtest/actor-collaboration-novelty-replay-evidence.jsonl.gz",
            all_evidence,
            overwrite=overwrite,
        ),
        "outcomes": store.write_jsonl_gz(
            "backtest/actor-collaboration-novelty-event-outcomes.jsonl.gz",
            outcomes,
            overwrite=overwrite,
        ),
        "cutoffs": store.write_json(
            "backtest/actor-collaboration-novelty-cutoff-summaries.json",
            cutoff_summaries,
            overwrite=overwrite,
        ),
        "summary": store.write_json(
            "backtest/actor-collaboration-novelty-backtest-summary.json",
            summary,
            overwrite=overwrite,
        ),
        "review_sample": store.write_json(
            "backtest/actor-collaboration-novelty-review-sample.json",
            sample,
            overwrite=overwrite,
        ),
        "markdown": store.write_text(
            "dossiers/actor-collaboration-novelty-backtest-summary.md",
            _markdown(summary, cutoff_summaries, sample),
            overwrite=overwrite,
        ),
    }
    quality_path = store.write_json(
        "quality/acn04-quality-report.json", quality, overwrite=overwrite
    )
    result = {
        "schema_version": "acn04-result/0.1",
        "scope_mode": scope_mode,
        "evaluator_version": evaluator_version,
        "cutoff_count": len(cutoffs),
        "eligible_cutoff_count": len(cutoffs) - insufficient_cutoff_count,
        "replayed_signal_count": len(all_signals),
        "observed_outcome_count": len(observed),
        "censored_outcome_count": len(outcomes) - len(observed),
        "continued_outcome_count": len(continued),
        "outputs": {
            key: value.relative_to(store.root).as_posix()
            for key, value in paths.items()
        }
        | {"quality_report": quality_path.relative_to(store.root).as_posix()},
    }
    store.write_json("acn04-result.json", result, overwrite=overwrite)
    return ACN04Result(
        scope_mode,
        store.root,
        len(cutoffs),
        len(cutoffs) - insufficient_cutoff_count,
        len(all_signals),
        len(observed),
        len(outcomes) - len(observed),
        len(continued),
        quality_path,
    )
