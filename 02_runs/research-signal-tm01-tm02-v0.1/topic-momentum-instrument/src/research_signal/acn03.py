from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import RunConfig
from .errors import InvariantError
from .storage import RunStore, sha256_json


HEADLINE_PRIORITY_THRESHOLD = 0.75
DOSSIER_LIMIT = 25
DOSSIER_MAX_PER_EVIDENCE_CLUSTER = 2
SHARED_EVIDENCE_REVIEW_THRESHOLD = 3
REPRESENTATIVE_WORK_LIMIT = 5


@dataclass(frozen=True)
class ACN03Result:
    scope_mode: str
    scope_dir: Path
    candidate_count: int
    signal_count: int
    headline_candidate_count: int
    review_required_count: int
    dossier_selected_count: int
    evidence_mismatch_count: int
    quality_report_path: Path


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _universe(
    manifest: dict[str, Any], config: RunConfig, scope_mode: str
) -> dict[str, Any]:
    source = manifest.get("universe", {})
    return {
        "universe_id": source.get("id", config.universe.id),
        "kind": "institution",
        "label": source.get("label", config.universe.label),
        "scope_mode": scope_mode,
        "entity_ids": source.get("included_institution_ids", []),
    }


def _cluster_id(work_ids: list[str]) -> str:
    digest = sha256_json(sorted(work_ids)).split(":", 1)[1][:16]
    return f"acn-support:{digest}"


def _subject_id(item: dict[str, Any]) -> str:
    external_id = item["external_institution"]["id"]
    anchor = item.get("anchor_institution")
    if anchor:
        return f"edge:{anchor['id']}:{external_id}"
    return external_id


def _subject(item: dict[str, Any]) -> dict[str, Any]:
    external = item["external_institution"]
    anchor = item.get("anchor_institution")
    if anchor:
        return {
            "kind": "collaboration",
            "id": _subject_id(item),
            "label": f"{anchor['label']} ↔ {external['label']}",
            "member_ids": [anchor["id"], external["id"]],
        }
    return {
        "kind": "institution",
        "id": external["id"],
        "label": external["label"],
        "member_ids": [],
    }


def _ecdf(values: list[float], value: float) -> float:
    return sum(item <= value for item in values) / len(values)


def _confidence(
    item: dict[str, Any], cluster_size: int
) -> dict[str, Any]:
    metrics = item["metrics"]
    current_count = metrics["current_work_count"]
    active_months = metrics["current_active_months"]
    pair_count = metrics[
        "current_observed_distinct_author_pair_count_lower_bound"
    ]
    components = {
        "anchor_materialization": min(
            1.0,
            metrics["locally_verified_supporting_works"]
            / max(current_count, 1),
        ),
        "work_support": min(1.0, current_count / 5.0),
        "author_pair_diversity": min(1.0, pair_count / 4.0),
        "temporal_spread": min(1.0, active_months / 4.0),
    }
    score = round(
        0.35 * components["anchor_materialization"]
        + 0.25 * components["work_support"]
        + 0.20 * components["author_pair_diversity"]
        + 0.20 * components["temporal_spread"],
        6,
    )
    factors = ["LOCALLY_VERIFIED_ANCHOR_SUPPORT", "MULTI_MONTH_SUPPORT"]
    limitations: list[str] = []
    if current_count == 2:
        limitations.append("MINIMUM_WORK_SUPPORT")
    else:
        factors.append("ABOVE_MINIMUM_WORK_SUPPORT")
    if active_months == 2:
        limitations.append("MINIMUM_TEMPORAL_SPREAD")
    else:
        factors.append("EXTENDED_TEMPORAL_SPREAD")
    if pair_count >= 4:
        factors.append("DIVERSE_OBSERVED_AUTHOR_PAIRS")
    else:
        limitations.append("LIMITED_OBSERVED_AUTHOR_PAIR_DIVERSITY")
    if not metrics["current_author_pair_sample_complete"]:
        limitations.append("AUTHOR_PAIR_SAMPLE_TRUNCATED")
    if cluster_size >= SHARED_EVIDENCE_REVIEW_THRESHOLD:
        limitations.append("SHARED_EVIDENCE_CLUSTER")
    level = "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.6 else "LOW"
    return {
        "level": level,
        "score": score,
        "factors": sorted(set(factors)),
        "limitations": sorted(set(limitations)),
        "components": {
            key: round(value, 6) for key, value in components.items()
        },
    }


def _actor_reach(
    item: dict[str, Any], actor_histories: dict[str, dict[str, Any]]
) -> int:
    history = actor_histories[item["external_institution"]["id"]]
    return len(history["windows"]["current"]["anchor_institution_ids"])


def _priorities(
    candidates: list[dict[str, Any]],
    confidences: dict[str, dict[str, Any]],
    actor_histories: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    support_values = [item["metrics"]["current_work_count"] for item in candidates]
    reach_values = [_actor_reach(item, actor_histories) for item in candidates]
    topic_values = [len(item["metrics"]["current_topic_ids"]) for item in candidates]
    values: dict[str, dict[str, Any]] = {}
    for item in candidates:
        assessment_id = item["assessment_id"]
        components = {
            "current_support_rank": _ecdf(
                support_values, item["metrics"]["current_work_count"]
            ),
            "internal_reach_rank": _ecdf(
                reach_values, _actor_reach(item, actor_histories)
            ),
            "topic_diversity_rank": _ecdf(
                topic_values, len(item["metrics"]["current_topic_ids"])
            ),
            "confidence": confidences[assessment_id]["score"],
        }
        score = round(
            0.35 * components["current_support_rank"]
            + 0.25 * components["internal_reach_rank"]
            + 0.20 * components["topic_diversity_rank"]
            + 0.20 * components["confidence"],
            6,
        )
        values[assessment_id] = {
            "score": score,
            "method": "actor-collaboration-novelty-priority/0.1",
            "interpretation": "ranking_only_not_probability",
            "components": {
                key: round(value, 6) for key, value in components.items()
            },
        }
    return values


def _editorial(
    priority: dict[str, Any],
    confidence: dict[str, Any],
    cluster_size: int,
) -> dict[str, Any]:
    if (
        priority["score"] >= HEADLINE_PRIORITY_THRESHOLD
        and confidence["level"] == "HIGH"
    ):
        tier = "HEADLINE_CANDIDATE"
    elif (
        priority["score"] >= HEADLINE_PRIORITY_THRESHOLD
        or confidence["level"] == "HIGH"
    ):
        tier = "WATCH"
    else:
        tier = "EXPLORATION"
    review_reasons: list[str] = []
    if cluster_size >= SHARED_EVIDENCE_REVIEW_THRESHOLD:
        review_reasons.append("SHARED_EVIDENCE_CLUSTER")
    if "AUTHOR_PAIR_SAMPLE_TRUNCATED" in confidence["limitations"]:
        review_reasons.append("AUTHOR_PAIR_SAMPLE_TRUNCATED")
    if confidence["level"] == "LOW":
        review_reasons.append("LOW_CONFIDENCE")
    return {
        "tier": tier,
        "review_status": "REQUIRED" if review_reasons else "OPTIONAL",
        "review_reasons": sorted(set(review_reasons)),
        "dossier_selected": False,
        "dossier_rank": None,
    }


def _why_unusual(item: dict[str, Any]) -> str:
    metrics = item["metrics"]
    external = item["external_institution"]["label"]
    anchor = item.get("anchor_institution")
    support = (
        f"{metrics['current_work_count']} œuvres réparties sur "
        f"{metrics['current_active_months']} mois"
    )
    label = item["signal_label"]
    if label == "NEW_EXTERNAL_ACTOR":
        return f"{external} apparaît pour la première fois dans le portefeuille avec {support}."
    if label == "REACTIVATED_EXTERNAL_ACTOR":
        return (
            f"{external} réapparaît avec {support} après trente-six mois sans "
            f"collaboration observée; {metrics['older_history_work_count']} œuvre(s) "
            "étaient visibles auparavant."
        )
    relation = f"{anchor['label']} ↔ {external}"
    if label == "NEW_COLLABORATION":
        return (
            f"La relation {relation} apparaît avec {support}, alors que le partenaire "
            "était déjà actif avec une autre unité du périmètre."
        )
    return (
        f"La relation {relation} réapparaît avec {support} après trente-six mois "
        f"d'absence; {metrics['older_history_work_count']} œuvre(s) matérialisaient "
        "la relation auparavant."
    )


def _relevant_events(
    item: dict[str, Any],
    events_by_work: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    external_id = item["external_institution"]["id"]
    anchor = item.get("anchor_institution")
    values = []
    for work_id in item["current_supporting_work_ids"]:
        for event in events_by_work.get(work_id, []):
            if event["external_institution"]["id"] != external_id:
                continue
            if anchor and event["anchor_institution"]["id"] != anchor["id"]:
                continue
            values.append(event)
    return values


def _representative_work_ids(
    work_ids: list[str], works: dict[str, dict[str, Any]]
) -> list[str]:
    ordered = sorted(
        work_ids,
        key=lambda work_id: (
            works[work_id]["publication_date"],
            work_id,
        ),
        reverse=True,
    )
    chosen: list[str] = []
    seen_topics: set[str | None] = set()
    for work_id in ordered:
        topic = works[work_id].get("primary_topic") or {}
        topic_id = topic.get("id")
        if topic_id not in seen_topics:
            chosen.append(work_id)
            seen_topics.add(topic_id)
        if len(chosen) == REPRESENTATIVE_WORK_LIMIT:
            return chosen
    for work_id in ordered:
        if work_id not in chosen:
            chosen.append(work_id)
        if len(chosen) == REPRESENTATIVE_WORK_LIMIT:
            break
    return chosen


def _work_evidence(
    work: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    materializing_author_ids = {
        author_id
        for event in events
        for pair in event.get("author_pairs") or []
        for author_id in (
            pair["anchor_author_id"],
            pair["external_author_id"],
        )
    }
    authorships = [
        authorship
        for authorship in work.get("authorships") or []
        if authorship.get("author_id") in materializing_author_ids
    ]
    return {
        "work_id": work["work_id"],
        "title": work.get("title"),
        "publication_date": work["publication_date"],
        "work_type": work.get("work_type"),
        "doi": work.get("doi"),
        "primary_topic": work.get("primary_topic"),
        "materializing_authorships": authorships,
        "collaboration_events": events,
        "work_quality_flags": work.get("quality_flags") or [],
    }


def _build_evidence(
    item: dict[str, Any],
    history: dict[str, Any],
    cluster: dict[str, Any],
    works: dict[str, dict[str, Any]],
    events_by_work: dict[str, list[dict[str, Any]]],
    config: RunConfig,
) -> dict[str, Any]:
    work_ids = item["current_supporting_work_ids"]
    missing_work_ids = sorted(set(work_ids) - set(works))
    relevant_events = _relevant_events(item, events_by_work)
    event_work_ids = {event["work_id"] for event in relevant_events}
    missing_event_work_ids = sorted(set(work_ids) - event_work_ids)
    if missing_work_ids or missing_event_work_ids:
        raise InvariantError(
            f"{item['assessment_id']}: supporting evidence is not locally resolvable"
        )
    representative_ids = _representative_work_ids(work_ids, works)
    representative_works = []
    for work_id in representative_ids:
        work_events = [
            event for event in relevant_events if event["work_id"] == work_id
        ]
        representative_works.append(_work_evidence(works[work_id], work_events))
    cutoff = item["information_cutoff"]
    count_matches = len(set(work_ids)) == item["metrics"]["current_work_count"]
    no_post_cutoff_evidence = all(
        event["publication_date"] <= cutoff for event in relevant_events
    ) and all(works[work_id]["publication_date"] <= cutoff for work_id in work_ids)
    pair_authors_resolve = all(
        {
            author_id
            for pair in event.get("author_pairs") or []
            for author_id in (
                pair["anchor_author_id"],
                pair["external_author_id"],
            )
        }
        <= {
            authorship.get("author_id")
            for authorship in works[event["work_id"]].get("authorships") or []
            if authorship.get("author_id")
        }
        for event in relevant_events
    )
    limitations = [
        "NOUVEAUTY_LIMITED_TO_VERSIONED_PORTFOLIO_HISTORY",
        "RETROSPECTIVE_OPENALEX_SNAPSHOT",
    ]
    if not item["metrics"]["current_author_pair_sample_complete"]:
        limitations.append("AUTHOR_PAIR_SAMPLE_TRUNCATED")
    if cluster["size"] >= SHARED_EVIDENCE_REVIEW_THRESHOLD:
        limitations.append("SHARED_EVIDENCE_CLUSTER")
    return {
        "schema_version": "actor-collaboration-novelty-evidence/0.1",
        "evidence_bundle_id": (
            f"evidence:actor-collaboration-novelty:{_subject_id(item)}:"
            f"{item['information_cutoff']}"
        ),
        "assessment_id": item["assessment_id"],
        "subject": _subject(item),
        "signal_label": item["signal_label"],
        "information_cutoff": cutoff,
        "corpus_observed_from": config.collection.from_publication_date.isoformat(),
        "history": history,
        "metrics": item["metrics"],
        "supporting_work_ids": work_ids,
        "supporting_collaboration_events": relevant_events,
        "representative_works": representative_works,
        "shared_evidence_cluster": cluster,
        "limitations": limitations,
        "count_crosscheck": {
            "supporting_work_count_matches": count_matches,
            "all_supporting_works_resolved": not missing_work_ids,
            "all_supporting_events_resolved": not missing_event_work_ids,
            "all_sampled_author_pairs_resolve": pair_authors_resolve,
            "no_post_cutoff_evidence": no_post_cutoff_evidence,
        },
    }


def _build_signal(
    item: dict[str, Any],
    confidence: dict[str, Any],
    priority: dict[str, Any],
    editorial: dict[str, Any],
    evidence: dict[str, Any],
    parameters: dict[str, Any],
    manifest: dict[str, Any],
    config: RunConfig,
    scope_mode: str,
    emitted_at: str,
) -> dict[str, Any]:
    subject = _subject(item)
    cutoff = item["information_cutoff"]
    signal_id = (
        f"sig:actor-collaboration-novelty:{_subject_id(item)}:{cutoff}"
    )
    mode = (
        "observed_vintage"
        if config.temporal_semantics == "observed_vintage"
        else "retrospective_reconstruction"
    )
    observed_at = manifest.get("data_vintage") or config.data_vintage.isoformat()
    quality_flags = sorted(
        set(confidence["limitations"] + editorial["review_reasons"])
    )
    evidence_items = [
        {
            "evidence_id": f"{signal_id}:bundle",
            "type": "metric",
            "role": "network_history_and_supporting_works",
            "observed_at": observed_at,
            "locator": {
                "kind": "evidence_bundle",
                "id": evidence["evidence_bundle_id"],
            },
            "supports": "Historique, collaborations, œuvres et contrôles du signal.",
        },
        {
            "evidence_id": f"{signal_id}:manifest",
            "type": "query_manifest",
            "role": "versioned_observation_scope",
            "observed_at": observed_at,
            "locator": {
                "kind": "query_manifest",
                "id": manifest.get("manifest_id", "query-manifest.json"),
            },
            "supports": "Périmètre institutionnel et vintage de l'observation.",
        },
    ]
    for index, work in enumerate(evidence["representative_works"], 1):
        evidence_items.append(
            {
                "evidence_id": f"{signal_id}:work:{index}",
                "type": "observation",
                "role": "supporting_collaboration_work",
                "observed_at": observed_at,
                "locator": {"kind": "work_observation", "id": work["work_id"]},
                "supports": "Œuvre et authorships matérialisant la relation.",
            }
        )
    current = parameters["windows"]["current"]
    baseline = parameters["windows"]["recent_baseline"]
    metrics = item["metrics"]
    return {
        "schema_version": "signal-envelope/0.2",
        "signal_id": signal_id,
        "detected_at": emitted_at,
        "detector": {
            "type": "actor_collaboration_novelty",
            "version": "actor-collaboration-novelty/0.1",
        },
        "universe": _universe(manifest, config, scope_mode),
        "subject": subject,
        "analysis_context": {
            "current_window": {
                "start": current["from"],
                "end": current["to"],
            },
            "reference": {
                "kind": "network_history",
                "reference_id": item["history_ref"],
                "window": {
                    "start": baseline["from"],
                    "end": baseline["to"],
                },
            },
        },
        "priority": priority,
        "confidence": confidence,
        "summary": {
            "headline": f"{item['signal_label']} — {subject['label']}",
            "why_unusual": _why_unusual(item),
        },
        "evidence": evidence_items,
        "provenance": {
            "run_id": manifest.get("run_id", config.run_id),
            "query_manifest_id": manifest.get(
                "manifest_id", "query-manifest.json"
            ),
            "observation_vintage": observed_at,
            "code_version": f"research-signal-instrument/{__version__}",
            "parameter_set_id": parameters["parameter_fingerprint"],
            "backtest_data_mode": mode,
        },
        "temporal_context": {
            "mode": mode,
            "emitted_at": emitted_at,
            "information_cutoff": f"{cutoff}T23:59:59Z",
            "observation_vintage": observed_at,
            "cutoff_basis": "publication_date",
        },
        "quality_flags": quality_flags,
        "payload": {
            "payload_schema": "actor_collaboration_novelty",
            "signal_label": item["signal_label"],
            "subject_type": item["subject_type"],
            "external_institution": item["external_institution"],
            "anchor_institution": item.get("anchor_institution"),
            "current_work_count": metrics["current_work_count"],
            "current_active_months": metrics["current_active_months"],
            "recent_baseline_work_count": metrics[
                "recent_baseline_work_count"
            ],
            "older_history_work_count": metrics["older_history_work_count"],
            "first_observed_date": metrics["first_observed_date"],
            "anchor_institution_ids": metrics[
                "current_anchor_institution_ids"
            ],
            "distinct_author_pair_count_lower_bound": metrics[
                "current_observed_distinct_author_pair_count_lower_bound"
            ],
            "distinct_topic_count": len(metrics["current_topic_ids"]),
            "topic_ids": metrics["current_topic_ids"],
            "supporting_work_ids": item["current_supporting_work_ids"],
            "shared_evidence_cluster": evidence["shared_evidence_cluster"],
            "editorial": editorial,
            "evidence_bundle_id": evidence["evidence_bundle_id"],
            "dossier_path": "dossiers/actor-collaboration-novelty-dossier-de-preuves.md",
        },
    }


def _select_for_dossier(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    chosen: list[dict[str, Any]] = []
    for signal in signals:
        cluster_id = signal["payload"]["shared_evidence_cluster"]["cluster_id"]
        if counts[cluster_id] >= DOSSIER_MAX_PER_EVIDENCE_CLUSTER:
            continue
        counts[cluster_id] += 1
        chosen.append(signal)
        if len(chosen) == DOSSIER_LIMIT:
            break
    for rank, signal in enumerate(chosen, 1):
        editorial = signal["payload"]["editorial"]
        editorial["dossier_selected"] = True
        editorial["dossier_rank"] = rank
    return chosen


def _escape(value: str | None) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")


def _markdown(
    signals: list[dict[str, Any]],
    chosen: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "# Actor & collaboration novelty — dossier de preuves",
        "",
        f"Ce dossier présente {len(chosen)} signaux sur {len(signals)} candidats. "
        "Tous les signaux restent disponibles en JSONL.",
        "",
        "La sélection retient au plus deux représentants partageant exactement "
        "les mêmes œuvres. La priorité sert au tri et ne constitue pas une probabilité.",
        "",
        "| Rang | Sujet | Label | Œuvres / mois | Portée | Topics | Confiance | Priorité | Groupe | Revue |",
        "|---:|---|---|---:|---:|---:|---|---:|---:|---|",
    ]
    for signal in chosen:
        payload = signal["payload"]
        editorial = payload["editorial"]
        lines.append(
            f"| {editorial['dossier_rank']} | {_escape(signal['subject']['label'])} | "
            f"{payload['signal_label']} | {payload['current_work_count']} / "
            f"{payload['current_active_months']} | {len(payload['anchor_institution_ids'])} | "
            f"{payload['distinct_topic_count']} | {signal['confidence']['level']} | "
            f"{signal['priority']['score']:.3f} | "
            f"{payload['shared_evidence_cluster']['size']} | "
            f"{editorial['review_status']} |"
        )
    lines.extend(["", "## Signaux sélectionnés", ""])
    for signal in chosen:
        payload = signal["payload"]
        editorial = payload["editorial"]
        evidence = evidence_by_id[payload["evidence_bundle_id"]]
        lines.extend(
            [
                f"### {editorial['dossier_rank']}. {signal['subject']['label']}",
                "",
                signal["summary"]["why_unusual"],
                "",
                f"- Label : `{payload['signal_label']}`",
                f"- Confiance : **{signal['confidence']['level']}** "
                f"({signal['confidence']['score']:.3f})",
                f"- Priorité : **{signal['priority']['score']:.3f}**",
                f"- Groupe de preuves partagé : "
                f"`{payload['shared_evidence_cluster']['cluster_id']}` "
                f"({payload['shared_evidence_cluster']['size']} signal(s))",
                f"- Revue humaine : **{editorial['review_status']}**"
                + (
                    f" — {', '.join(editorial['review_reasons'])}"
                    if editorial["review_reasons"]
                    else ""
                ),
                f"- Limites : {', '.join(signal['confidence']['limitations']) or 'aucune'}",
                "",
                "| Date | Œuvre | Topic | ID |",
                "|---|---|---|---|",
            ]
        )
        for work in evidence["representative_works"]:
            topic = work.get("primary_topic") or {}
            lines.append(
                f"| {work['publication_date']} | {_escape(work.get('title'))} | "
                f"{_escape(topic.get('label'))} | `{work['work_id']}` |"
            )
        lines.append("")
    lines.extend(
        [
            "## Lecture",
            "",
            "- `NEW_*` signifie nouveau dans l'historique observable du portefeuille, pas dans le monde académique.",
            "- `REACTIVATED_*` signifie présent avant la baseline récente, absent pendant celle-ci, puis revenu.",
            "- Un groupe supérieur à un indique que plusieurs signaux reposent exactement sur les mêmes œuvres.",
            "- `REQUIRED` conserve le signal mais demande une validation humaine avant diffusion.",
        ]
    )
    return "\n".join(lines)


def run_acn03(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> ACN03Result:
    if resume and rebuild:
        raise InvariantError("ACN-03 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "acn02-result.json",
        "quality/acn02-quality-report.json",
        "collaborations/acn02-window-parameters.json",
        "collaborations/actor-collaboration-candidates.jsonl.gz",
        "collaborations/external-actor-histories.jsonl.gz",
        "collaborations/collaboration-edge-histories.jsonl.gz",
        "collaborations/collaboration-events.jsonl.gz",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"ACN-03 requires completed ACN-02 artifacts: {missing}")
    result_path = store.path("acn03-result.json")
    quality_path = store.path("quality/acn03-quality-report.json")
    emitter_version = f"research-signal-instrument/{__version__}"
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("acn03-result.json")
        if completed.get("emitter_version") != emitter_version:
            raise InvariantError(
                "ACN-03 result was produced by another version; use --rebuild"
            )
        return ACN03Result(
            scope_mode,
            store.root,
            completed["candidate_count"],
            completed["signal_count"],
            completed["headline_candidate_count"],
            completed["review_required_count"],
            completed["dossier_selected_count"],
            completed["evidence_mismatch_count"],
            quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("ACN-03 result already exists; use --resume or --rebuild")

    manifest = store.read_json("query-manifest.json")
    acn02_result = store.read_json("acn02-result.json")
    acn02_quality = store.read_json("quality/acn02-quality-report.json")
    acn02_parameters = store.read_json(
        "collaborations/acn02-window-parameters.json"
    )
    if acn02_result.get("schema_version") != "acn02-result/0.1":
        raise InvariantError("ACN-03 requires acn02-result/0.1")
    if acn02_quality.get("schema_version") != "acn02-quality-report/0.1":
        raise InvariantError("ACN-03 requires acn02-quality-report/0.1")
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("ACN-03 scope differs from query manifest")
    if not acn02_quality.get("all_candidates_satisfy_rule"):
        raise InvariantError("ACN-03 requires contract-valid ACN-02 candidates")

    candidates = store.read_jsonl_gz(
        "collaborations/actor-collaboration-candidates.jsonl.gz"
    )
    if len(candidates) != acn02_result["candidate_count"]:
        raise InvariantError("ACN-03 candidate count differs from ACN-02 result")
    if any(
        item.get("schema_version")
        != "actor-collaboration-novelty-assessment/0.1"
        or not item.get("eligible_for_detection")
        for item in candidates
    ):
        raise InvariantError("ACN-03 received invalid ACN-02 candidates")

    actor_histories = {
        item["external_institution"]["id"]: item
        for item in store.read_jsonl_gz(
            "collaborations/external-actor-histories.jsonl.gz"
        )
    }
    edge_histories = {
        item["history_id"]: item
        for item in store.read_jsonl_gz(
            "collaborations/collaboration-edge-histories.jsonl.gz"
        )
    }
    histories = {item["history_id"]: item for item in actor_histories.values()}
    histories.update(edge_histories)
    missing_histories = sorted(
        {item["history_ref"] for item in candidates} - set(histories)
    )
    if missing_histories:
        raise InvariantError("ACN-03 candidate histories are not resolvable")
    works = {
        item["work_id"]: item
        for item in store.read_jsonl_gz(
            "observations/work-observations.jsonl.gz"
        )
    }
    events_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in store.read_jsonl_gz(
        "collaborations/collaboration-events.jsonl.gz"
    ):
        events_by_work[event["work_id"]].append(event)

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
    priorities = _priorities(candidates, confidences, actor_histories)
    parameters = {
        "schema_version": "actor-collaboration-novelty-signal-parameters/0.1",
        "detector_stage": "ACN-03",
        "input_acn02_version": acn02_result["calculator_version"],
        "windows": acn02_parameters["windows"],
        "confidence_method": "actor-collaboration-novelty-confidence/0.1",
        "confidence_weights": {
            "anchor_materialization": 0.35,
            "work_support": 0.25,
            "author_pair_diversity": 0.20,
            "temporal_spread": 0.20,
        },
        "priority_method": "actor-collaboration-novelty-priority/0.1",
        "priority_weights": {
            "current_support_rank": 0.35,
            "internal_reach_rank": 0.25,
            "topic_diversity_rank": 0.20,
            "confidence": 0.20,
        },
        "editorial_policy": {
            "headline_priority_threshold": HEADLINE_PRIORITY_THRESHOLD,
            "dossier_limit": DOSSIER_LIMIT,
            "max_per_exact_support_cluster": DOSSIER_MAX_PER_EVIDENCE_CLUSTER,
            "shared_evidence_review_threshold": SHARED_EVIDENCE_REVIEW_THRESHOLD,
        },
    }
    parameters["parameter_fingerprint"] = sha256_json(parameters)
    emitted_at = _iso_now()
    signals: list[dict[str, Any]] = []
    evidence_bundles: list[dict[str, Any]] = []
    for item in candidates:
        assessment_id = item["assessment_id"]
        confidence = confidences[assessment_id]
        priority = priorities[assessment_id]
        cluster = clusters[assessment_id]
        editorial = _editorial(priority, confidence, cluster["size"])
        evidence = _build_evidence(
            item,
            histories[item["history_ref"]],
            cluster,
            works,
            events_by_work,
            config,
        )
        evidence_bundles.append(evidence)
        signals.append(
            _build_signal(
                item,
                confidence,
                priority,
                editorial,
                evidence,
                parameters,
                manifest,
                config,
                scope_mode,
                emitted_at,
            )
        )
    signals.sort(key=lambda item: (-item["priority"]["score"], item["signal_id"]))
    evidence_by_id = {
        item["evidence_bundle_id"]: item for item in evidence_bundles
    }
    evidence_bundles = [
        evidence_by_id[item["payload"]["evidence_bundle_id"]]
        for item in signals
    ]
    chosen = _select_for_dossier(signals)

    label_counts = Counter(item["payload"]["signal_label"] for item in signals)
    confidence_counts = Counter(item["confidence"]["level"] for item in signals)
    tier_counts = Counter(
        item["payload"]["editorial"]["tier"] for item in signals
    )
    review_count = sum(
        item["payload"]["editorial"]["review_status"] == "REQUIRED"
        for item in signals
    )
    unique_clusters = {
        item["payload"]["shared_evidence_cluster"]["cluster_id"]
        for item in signals
    }
    multi_signal_clusters = {
        item["payload"]["shared_evidence_cluster"]["cluster_id"]
        for item in signals
        if item["payload"]["shared_evidence_cluster"]["size"] > 1
    }
    evidence_mismatches = [
        item["evidence_bundle_id"]
        for item in evidence_bundles
        if not all(item["count_crosscheck"].values())
    ]
    post_cutoff_used = sum(
        not item["count_crosscheck"]["no_post_cutoff_evidence"]
        for item in evidence_bundles
    )

    overwrite = rebuild
    parameters_path = store.write_json(
        "collaborations/actor-collaboration-signal-parameters.json",
        parameters,
        overwrite=overwrite,
    )
    signals_path = store.write_jsonl_gz(
        "signals/actor-collaboration-novelty-signals.jsonl.gz",
        signals,
        overwrite=overwrite,
    )
    evidence_path = store.write_jsonl_gz(
        "evidence/actor-collaboration-novelty-evidence.jsonl.gz",
        evidence_bundles,
        overwrite=overwrite,
    )
    index = [
        {
            "rank": rank,
            "signal_id": signal["signal_id"],
            "subject": signal["subject"],
            "label": signal["payload"]["signal_label"],
            "priority_score": signal["priority"]["score"],
            "confidence_level": signal["confidence"]["level"],
            "editorial_tier": signal["payload"]["editorial"]["tier"],
            "review_status": signal["payload"]["editorial"]["review_status"],
            "shared_evidence_cluster_id": signal["payload"][
                "shared_evidence_cluster"
            ]["cluster_id"],
            "shared_evidence_cluster_size": signal["payload"][
                "shared_evidence_cluster"
            ]["size"],
            "dossier_selected": signal["payload"]["editorial"][
                "dossier_selected"
            ],
            "dossier_rank": signal["payload"]["editorial"]["dossier_rank"],
        }
        for rank, signal in enumerate(signals, 1)
    ]
    index_path = store.write_json(
        "signals/actor-collaboration-novelty-signal-index.json",
        index,
        overwrite=overwrite,
    )
    dossier_path = store.write_text(
        "dossiers/actor-collaboration-novelty-dossier-de-preuves.md",
        _markdown(signals, chosen, evidence_by_id),
        overwrite=overwrite,
    )
    warnings: list[str] = []
    if evidence_mismatches:
        warnings.append("EVIDENCE_CROSSCHECK_MISMATCH")
    if multi_signal_clusters:
        warnings.append("SHARED_EVIDENCE_CLUSTERS_PRESENT")
    quality = {
        "schema_version": "acn03-quality-report/0.1",
        "run_id": manifest.get("run_id", config.run_id),
        "emitter_version": emitter_version,
        "scope_mode": scope_mode,
        "information_cutoff": config.collection.to_publication_date.isoformat(),
        "candidate_count": len(candidates),
        "signal_count": len(signals),
        "all_candidates_emitted": len(candidates) == len(signals),
        "label_counts": dict(sorted(label_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "editorial_tier_counts": dict(sorted(tier_counts.items())),
        "review_required_count": review_count,
        "dossier_selected_count": len(chosen),
        "unique_evidence_cluster_count": len(unique_clusters),
        "multi_signal_evidence_cluster_count": len(multi_signal_clusters),
        "max_evidence_cluster_size": max(
            (
                item["payload"]["shared_evidence_cluster"]["size"]
                for item in signals
            ),
            default=0,
        ),
        "evidence_bundle_count": len(evidence_bundles),
        "evidence_mismatch_count": len(evidence_mismatches),
        "evidence_mismatches": evidence_mismatches,
        "post_cutoff_evidence_used_count": post_cutoff_used,
        "all_signals_resolve_to_at_least_two_works": all(
            len(item["payload"]["supporting_work_ids"]) >= 2
            for item in signals
        ),
        "priority_method": "actor-collaboration-novelty-priority/0.1",
        "confidence_method": "actor-collaboration-novelty-confidence/0.1",
        "no_backtest_outcome_in_signal": True,
        "warnings": warnings,
        "resumed": resume,
        "rebuilt": rebuild,
    }
    quality_path = store.write_json(
        "quality/acn03-quality-report.json", quality, overwrite=overwrite
    )
    result = {
        "schema_version": "acn03-result/0.1",
        "scope_mode": scope_mode,
        "emitter_version": emitter_version,
        "candidate_count": len(candidates),
        "signal_count": len(signals),
        "headline_candidate_count": tier_counts["HEADLINE_CANDIDATE"],
        "review_required_count": review_count,
        "dossier_selected_count": len(chosen),
        "evidence_mismatch_count": len(evidence_mismatches),
        "outputs": {
            "parameters": parameters_path.relative_to(store.root).as_posix(),
            "signals": signals_path.relative_to(store.root).as_posix(),
            "signal_index": index_path.relative_to(store.root).as_posix(),
            "evidence": evidence_path.relative_to(store.root).as_posix(),
            "dossier": dossier_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("acn03-result.json", result, overwrite=overwrite)
    return ACN03Result(
        scope_mode,
        store.root,
        len(candidates),
        len(signals),
        tier_counts["HEADLINE_CANDIDATE"],
        review_count,
        len(chosen),
        len(evidence_mismatches),
        quality_path,
    )
