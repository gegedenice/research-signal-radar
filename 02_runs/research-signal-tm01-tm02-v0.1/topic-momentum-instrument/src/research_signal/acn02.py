from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import __version__
from .config import ActorCollaborationNoveltyConfig, RunConfig
from .dates import add_months
from .errors import InvariantError
from .storage import RunStore, sha256_json


@dataclass(frozen=True)
class ACN02Result:
    scope_mode: str
    scope_dir: Path
    actor_history_count: int
    edge_history_count: int
    assessment_count: int
    candidate_count: int
    actor_candidate_count: int
    collaboration_candidate_count: int
    quality_report_path: Path


def _windows(
    cutoff: date, config: ActorCollaborationNoveltyConfig
) -> dict[str, dict[str, str | int | None]]:
    cutoff_month_start = date(cutoff.year, cutoff.month, 1)
    current_start = add_months(
        cutoff_month_start, -(config.current_window_months - 1)
    )
    recent_start = add_months(current_start, -config.recent_baseline_months)
    return {
        "older_history": {
            "from": None,
            "to": (recent_start - timedelta(days=1)).isoformat(),
        },
        "recent_baseline": {
            "from": recent_start.isoformat(),
            "to": (current_start - timedelta(days=1)).isoformat(),
            "months": config.recent_baseline_months,
        },
        "current": {
            "from": current_start.isoformat(),
            "to": cutoff.isoformat(),
            "months": config.current_window_months,
        },
    }


def _period(publication_date: str, windows: dict[str, dict[str, Any]]) -> str:
    published = date.fromisoformat(publication_date)
    if published >= date.fromisoformat(windows["current"]["from"]):
        return "current"
    if published >= date.fromisoformat(windows["recent_baseline"]["from"]):
        return "recent_baseline"
    return "older_history"


def _deduplicated_work_events(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for event in events:
        values.setdefault(event["work_id"], event)
    return values


def _summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    works = _deduplicated_work_events(events)
    months = Counter(event["publication_month"] for event in works.values())
    anchor_ids = sorted(
        {event["anchor_institution"]["id"] for event in events}
    )
    topic_ids = sorted(
        {
            topic["id"]
            for event in events
            if (topic := event.get("primary_topic")) and topic.get("id")
        }
    )
    author_ids: set[str] = set()
    author_pairs: set[tuple[str, str]] = set()
    pair_sample_complete = True
    for event in events:
        pair_sample_complete = pair_sample_complete and not event.get(
            "author_pairs_truncated", False
        )
        for pair in event.get("author_pairs") or []:
            anchor_author = pair["anchor_author_id"]
            external_author = pair["external_author_id"]
            author_ids.update((anchor_author, external_author))
            author_pairs.add((anchor_author, external_author))
    dates = sorted(event["publication_date"] for event in works.values())
    return {
        "work_count": len(works),
        "active_months": len(months),
        "monthly_work_counts": [
            {"month": month, "work_count": count}
            for month, count in sorted(months.items())
        ],
        "first_observed_date": dates[0] if dates else None,
        "last_observed_date": dates[-1] if dates else None,
        "anchor_institution_ids": anchor_ids,
        "topic_ids": topic_ids,
        "locally_verified_work_count": len(works),
        "observed_distinct_author_count_lower_bound": len(author_ids),
        "observed_distinct_author_pair_count_lower_bound": len(author_pairs),
        "author_pair_sample_complete": pair_sample_complete,
    }


def _history(
    *,
    subject_type: str,
    external_institution: dict[str, Any],
    anchor_institution: dict[str, Any] | None,
    events: list[dict[str, Any]],
    windows: dict[str, dict[str, Any]],
    cutoff: date,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_period(event["publication_date"], windows)].append(event)
    identifier = external_institution["id"]
    if anchor_institution:
        identifier = f"{anchor_institution['id']}:{identifier}"
    return {
        "schema_version": "actor-collaboration-history/0.1",
        "history_id": f"acn-history:{subject_type}:{identifier}",
        "subject_type": subject_type,
        "external_institution": external_institution,
        "anchor_institution": anchor_institution,
        "information_cutoff": cutoff.isoformat(),
        "first_observed_date": min(event["publication_date"] for event in events),
        "last_observed_date": max(event["publication_date"] for event in events),
        "windows": {
            name: _summary(grouped.get(name, []))
            for name in ("older_history", "recent_baseline", "current")
        },
    }


def _base_reasons(
    history: dict[str, Any],
    config: ActorCollaborationNoveltyConfig,
    sufficient_history: bool,
) -> list[str]:
    current = history["windows"]["current"]
    recent = history["windows"]["recent_baseline"]
    reasons: list[str] = []
    if not sufficient_history:
        reasons.append("INSUFFICIENT_HISTORY")
    if current["work_count"] < config.min_current_works:
        reasons.append("INSUFFICIENT_CURRENT_SUPPORT")
    elif current["active_months"] < config.min_active_months:
        reasons.append("SINGLE_ACTIVE_MONTH")
    if (
        current["locally_verified_work_count"]
        < config.min_locally_verified_works
    ):
        reasons.append("INSUFFICIENT_LOCALLY_VERIFIED_SUPPORT")
    if recent["work_count"]:
        reasons.append("RECENT_BASELINE_PRESENT")
    return reasons


def _assessment(
    history: dict[str, Any],
    *,
    label: str | None,
    reasons: list[str],
    cutoff: date,
) -> dict[str, Any]:
    current = history["windows"]["current"]
    recent = history["windows"]["recent_baseline"]
    older = history["windows"]["older_history"]
    external_id = history["external_institution"]["id"]
    anchor = history.get("anchor_institution")
    subject_key = f"{anchor['id']}:{external_id}" if anchor else external_id
    return {
        "schema_version": "actor-collaboration-novelty-assessment/0.1",
        "assessment_id": (
            f"acn02:{cutoff.isoformat()}:{history['subject_type']}:{subject_key}"
        ),
        "detector_id": "actor_collaboration_novelty",
        "detector_version": "actor-collaboration-novelty/0.1",
        "information_cutoff": cutoff.isoformat(),
        "subject_type": history["subject_type"],
        "history_ref": history["history_id"],
        "external_institution": history["external_institution"],
        "anchor_institution": anchor,
        "signal_label": label,
        "metrics": {
            "current_work_count": current["work_count"],
            "current_active_months": current["active_months"],
            "locally_verified_supporting_works": current[
                "locally_verified_work_count"
            ],
            "recent_baseline_work_count": recent["work_count"],
            "older_history_work_count": older["work_count"],
            "first_observed_date": history["first_observed_date"],
            "last_observed_date": history["last_observed_date"],
            "current_anchor_institution_ids": current[
                "anchor_institution_ids"
            ],
            "current_topic_ids": current["topic_ids"],
            "current_observed_distinct_author_pair_count_lower_bound": current[
                "observed_distinct_author_pair_count_lower_bound"
            ],
            "current_author_pair_sample_complete": current[
                "author_pair_sample_complete"
            ],
        },
        "current_supporting_work_ids": sorted(
            {
                item["work_id"]
                for item in history.get("_events", [])
                if item.get("_period") == "current"
            }
        ),
        "eligible_for_detection": not reasons and label is not None,
        "abstention": {
            "is_abstained": bool(reasons) or label is None,
            "reasons": reasons or ([] if label else ["NO_MATCHING_NOVELTY_LABEL"]),
        },
    }


def _attach_internal_events(
    history: dict[str, Any],
    events: list[dict[str, Any]],
    windows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    value = dict(history)
    value["_events"] = [
        {**event, "_period": _period(event["publication_date"], windows)}
        for event in events
    ]
    return value


def run_acn02(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> ACN02Result:
    if resume and rebuild:
        raise InvariantError("ACN-02 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "acn01-result.json",
        "quality/acn01-quality-report.json",
        "collaborations/collaboration-events.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"ACN-02 requires completed ACN-01 artifacts: {missing}")

    result_path = store.path("acn02-result.json")
    quality_path = store.path("quality/acn02-quality-report.json")
    calculator_version = f"research-signal-instrument/{__version__}"
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("acn02-result.json")
        if completed.get("calculator_version") != calculator_version:
            raise InvariantError(
                "ACN-02 result was produced by another version; use --rebuild"
            )
        return ACN02Result(
            scope_mode,
            store.root,
            completed["actor_history_count"],
            completed["edge_history_count"],
            completed["assessment_count"],
            completed["candidate_count"],
            completed["actor_candidate_count"],
            completed["collaboration_candidate_count"],
            quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("ACN-02 result already exists; use --resume or --rebuild")

    manifest = store.read_json("query-manifest.json")
    acn01_result = store.read_json("acn01-result.json")
    acn01_quality = store.read_json("quality/acn01-quality-report.json")
    if acn01_result.get("schema_version") != "acn01-result/0.1":
        raise InvariantError("ACN-02 requires acn01-result/0.1")
    if acn01_quality.get("schema_version") != "acn01-quality-report/0.1":
        raise InvariantError("ACN-02 requires acn01-quality-report/0.1")
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("ACN-02 scope differs from query manifest")
    if not acn01_quality.get("all_events_resolve_to_input_works"):
        raise InvariantError("ACN-02 requires resolvable ACN-01 collaboration events")
    if not acn01_quality.get("all_edges_have_distinct_authors"):
        raise InvariantError("ACN-02 requires distinct-author collaboration edges")

    all_events = store.read_jsonl_gz(
        "collaborations/collaboration-events.jsonl.gz"
    )
    if any(
        event.get("schema_version") != "collaboration-event-observation/0.1"
        for event in all_events
    ):
        raise InvariantError(
            "ACN-02 requires collaboration-event-observation/0.1 inputs"
        )
    event_ids = [event["event_id"] for event in all_events]
    if len(event_ids) != len(set(event_ids)):
        raise InvariantError("ACN-02 received duplicate collaboration event IDs")

    cutoff = config.collection.to_publication_date
    windows = _windows(cutoff, config.actor_collaboration_novelty)
    post_cutoff_events = [
        event
        for event in all_events
        if date.fromisoformat(event["publication_date"]) > cutoff
    ]
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

    actor_histories_internal: list[dict[str, Any]] = []
    for external_id in sorted(actor_groups):
        grouped_events = actor_groups[external_id]
        history = _history(
            subject_type="institution",
            external_institution=grouped_events[0]["external_institution"],
            anchor_institution=None,
            events=grouped_events,
            windows=windows,
            cutoff=cutoff,
        )
        actor_histories_internal.append(
            _attach_internal_events(history, grouped_events, windows)
        )

    edge_histories_internal: list[dict[str, Any]] = []
    for edge_key in sorted(edge_groups):
        grouped_events = edge_groups[edge_key]
        history = _history(
            subject_type="institution_edge",
            external_institution=grouped_events[0]["external_institution"],
            anchor_institution=grouped_events[0]["anchor_institution"],
            events=grouped_events,
            windows=windows,
            cutoff=cutoff,
        )
        edge_histories_internal.append(
            _attach_internal_events(history, grouped_events, windows)
        )

    recent_start = date.fromisoformat(windows["recent_baseline"]["from"])
    sufficient_history = config.collection.from_publication_date <= recent_start
    actor_assessments: list[dict[str, Any]] = []
    actor_candidate_ids: set[str] = set()
    for history in actor_histories_internal:
        reasons = _base_reasons(
            history, config.actor_collaboration_novelty, sufficient_history
        )
        older_count = history["windows"]["older_history"]["work_count"]
        label = None
        if not reasons:
            label = (
                "REACTIVATED_EXTERNAL_ACTOR"
                if older_count
                else "NEW_EXTERNAL_ACTOR"
            )
            actor_candidate_ids.add(history["external_institution"]["id"])
        actor_assessments.append(
            _assessment(history, label=label, reasons=reasons, cutoff=cutoff)
        )

    edge_assessments: list[dict[str, Any]] = []
    for history in edge_histories_internal:
        reasons = _base_reasons(
            history, config.actor_collaboration_novelty, sufficient_history
        )
        external_id = history["external_institution"]["id"]
        anchor_id = history["anchor_institution"]["id"]
        other_anchor_in_recent_baseline = any(
            _period(event["publication_date"], windows) == "recent_baseline"
            and event["anchor_institution"]["id"] != anchor_id
            for event in actor_groups[external_id]
        )
        if not other_anchor_in_recent_baseline:
            reasons.append("ACTOR_NOT_ACTIVE_WITH_OTHER_ANCHOR_IN_RECENT_BASELINE")
        older_count = history["windows"]["older_history"]["work_count"]
        label = None
        if not reasons:
            label = (
                "REACTIVATED_COLLABORATION"
                if older_count
                else "NEW_COLLABORATION"
            )
            if external_id in actor_candidate_ids:
                label = None
                reasons.append("ACTOR_SIGNAL_PRECEDENCE")
        assessment = _assessment(
            history, label=label, reasons=reasons, cutoff=cutoff
        )
        assessment["metrics"]["external_actor_active_with_other_anchor_in_recent_baseline"] = (
            other_anchor_in_recent_baseline
        )
        edge_assessments.append(assessment)

    assessments = actor_assessments + edge_assessments
    candidates = [item for item in assessments if item["eligible_for_detection"]]
    abstentions = [item for item in assessments if not item["eligible_for_detection"]]
    actor_candidates = [
        item for item in candidates if item["subject_type"] == "institution"
    ]
    collaboration_candidates = [
        item for item in candidates if item["subject_type"] == "institution_edge"
    ]
    reason_counts = Counter(
        reason
        for item in abstentions
        for reason in item["abstention"]["reasons"]
    )
    label_counts = Counter(item["signal_label"] for item in candidates)

    parameters = {
        "schema_version": "actor-collaboration-novelty-parameters/0.1",
        "detector_stage": "ACN-02",
        "information_cutoff": cutoff.isoformat(),
        "corpus_observed_from": config.collection.from_publication_date.isoformat(),
        "corpus_observed_to": cutoff.isoformat(),
        "windows": windows,
        "candidate_rule": asdict(config.actor_collaboration_novelty),
        "actor_precedence": True,
        "input_event_hash": sha256_json(all_events),
    }
    parameters["parameter_fingerprint"] = sha256_json(parameters)

    actor_histories = [
        {key: value for key, value in history.items() if key != "_events"}
        for history in actor_histories_internal
    ]
    edge_histories = [
        {key: value for key, value in history.items() if key != "_events"}
        for history in edge_histories_internal
    ]
    overwrite = rebuild
    parameters_path = store.write_json(
        "collaborations/acn02-window-parameters.json",
        parameters,
        overwrite=overwrite,
    )
    actor_history_path = store.write_jsonl_gz(
        "collaborations/external-actor-histories.jsonl.gz",
        actor_histories,
        overwrite=overwrite,
    )
    edge_history_path = store.write_jsonl_gz(
        "collaborations/collaboration-edge-histories.jsonl.gz",
        edge_histories,
        overwrite=overwrite,
    )
    assessment_path = store.write_jsonl_gz(
        "collaborations/actor-collaboration-assessments.jsonl.gz",
        assessments,
        overwrite=overwrite,
    )
    candidate_path = store.write_jsonl_gz(
        "collaborations/actor-collaboration-candidates.jsonl.gz",
        candidates,
        overwrite=overwrite,
    )
    abstention_path = store.write_jsonl_gz(
        "collaborations/actor-collaboration-abstentions.jsonl.gz",
        abstentions,
        overwrite=overwrite,
    )

    warnings: list[str] = []
    if not sufficient_history:
        warnings.append("INSUFFICIENT_HISTORY")
    if post_cutoff_events:
        warnings.append("POST_CUTOFF_EVENTS_EXCLUDED")
    if acn01_quality.get("quality_flag_counts", {}).get("UNRESOLVED_AUTHOR_ID"):
        warnings.append("INHERITED_UNRESOLVED_AUTHOR_IDENTITIES")
    quality = {
        "schema_version": "acn02-quality-report/0.1",
        "run_id": manifest.get("run_id", config.run_id),
        "calculator_version": calculator_version,
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest.get("manifest_id"),
        "information_cutoff": cutoff.isoformat(),
        "sufficient_recent_baseline_history": sufficient_history,
        "input_collaboration_event_count": len(all_events),
        "usable_event_count": len(events),
        "post_cutoff_event_count": len(post_cutoff_events),
        "actor_history_count": len(actor_histories),
        "edge_history_count": len(edge_histories),
        "assessment_count": len(assessments),
        "candidate_count": len(candidates),
        "candidate_rate_among_assessments": round(
            len(candidates) / len(assessments), 12
        ) if assessments else 0.0,
        "actor_candidate_count": len(actor_candidates),
        "actor_candidate_rate": round(
            len(actor_candidates) / len(actor_histories), 12
        ) if actor_histories else 0.0,
        "collaboration_candidate_count": len(collaboration_candidates),
        "collaboration_candidate_rate": round(
            len(collaboration_candidates) / len(edge_histories), 12
        ) if edge_histories else 0.0,
        "candidate_label_counts": dict(sorted(label_counts.items())),
        "abstained_count": len(abstentions),
        "abstention_reason_counts": dict(sorted(reason_counts.items())),
        "inherited_work_status_counts": acn01_quality.get(
            "work_status_counts", {}
        ),
        "inherited_quality_flag_counts": acn01_quality.get(
            "quality_flag_counts", {}
        ),
        "all_candidates_satisfy_rule": all(
            item["metrics"]["current_work_count"]
            >= config.actor_collaboration_novelty.min_current_works
            and item["metrics"]["current_active_months"]
            >= config.actor_collaboration_novelty.min_active_months
            and item["metrics"]["recent_baseline_work_count"] == 0
            and item["metrics"]["locally_verified_supporting_works"]
            >= config.actor_collaboration_novelty.min_locally_verified_works
            for item in candidates
        ),
        "actor_precedence_violation_count": sum(
            item["subject_type"] == "institution_edge"
            and item["external_institution"]["id"] in actor_candidate_ids
            for item in candidates
        ),
        "no_signal_emission": True,
        "warnings": warnings,
        "resumed": resume,
        "rebuilt": rebuild,
    }
    quality_path = store.write_json(
        "quality/acn02-quality-report.json", quality, overwrite=overwrite
    )
    result = {
        "schema_version": "acn02-result/0.1",
        "scope_mode": scope_mode,
        "calculator_version": calculator_version,
        "information_cutoff": cutoff.isoformat(),
        "actor_history_count": len(actor_histories),
        "edge_history_count": len(edge_histories),
        "assessment_count": len(assessments),
        "candidate_count": len(candidates),
        "actor_candidate_count": len(actor_candidates),
        "collaboration_candidate_count": len(collaboration_candidates),
        "outputs": {
            "parameters": parameters_path.relative_to(store.root).as_posix(),
            "actor_histories": actor_history_path.relative_to(store.root).as_posix(),
            "edge_histories": edge_history_path.relative_to(store.root).as_posix(),
            "assessments": assessment_path.relative_to(store.root).as_posix(),
            "candidates": candidate_path.relative_to(store.root).as_posix(),
            "abstentions": abstention_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("acn02-result.json", result, overwrite=overwrite)
    return ACN02Result(
        scope_mode,
        store.root,
        len(actor_histories),
        len(edge_histories),
        len(assessments),
        len(candidates),
        len(actor_candidates),
        len(collaboration_candidates),
        quality_path,
    )
