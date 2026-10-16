from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .config import RunConfig
from .errors import InvariantError
from .storage import RunStore


@dataclass(frozen=True)
class TM06Result:
    scope_mode: str
    scope_dir: Path
    signal_count: int
    representative_work_count: int
    evidence_mismatch_count: int
    headline_candidate_count: int
    review_required_count: int
    quality_report_path: Path


EDITORIAL_POLICY = "topic-momentum-editorial/0.1"
HEADLINE_PRIORITY_THRESHOLD = 0.75


def _signal_support(assessment: dict[str, Any]) -> int:
    if assessment["signal_label"] == "RISING":
        return assessment["observation"]["current_count"]
    if assessment["signal_label"] == "FALLING":
        return assessment["observation"]["previous_count"]
    presence = assessment["classification"]["presence_status"]
    if presence in {"NEW", "REACTIVATED"}:
        return assessment["observation"]["current_count"]
    return assessment["observation"]["previous_count"]


def _empirical_rank(value: float, population: list[float]) -> float:
    if not population:
        return 0.0
    return sum(item <= value for item in population) / len(population)


def priority_scores(
    assessments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    magnitudes = [abs(item["delta"]["share"]) for item in assessments]
    output: dict[str, dict[str, Any]] = {}
    for item in assessments:
        label = item["signal_label"]
        percentile = item["delta"]["historical_percentile"]
        if percentile is None:
            percentile = 0.5
        anomaly = percentile if label == "RISING" else 1.0 - percentile
        components = {
            "portfolio_magnitude": _empirical_rank(abs(item["delta"]["share"]), magnitudes),
            "historical_anomaly": max(0.0, min(1.0, anomaly)),
            "temporal_persistence": min(1.0, item["direction_streak"] / 3),
            "signal_support": min(1.0, _signal_support(item) / 10),
        }
        score = (
            0.35 * components["portfolio_magnitude"]
            + 0.25 * components["historical_anomaly"]
            + 0.20 * components["temporal_persistence"]
            + 0.20 * components["signal_support"]
        )
        output[item["assessment_id"]] = {
            "score": round(score, 12),
            "method": "topic-momentum-priority/0.1",
            "components": {
                name: round(value, 12) for name, value in components.items()
            },
        }
    return output


def _in_window(observation: dict[str, Any], window: dict[str, Any]) -> bool:
    published = observation["publication_date"]
    return window["from"] <= published <= window["to"]


def _actors(observation: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    authors: dict[str, dict[str, Any]] = {}
    institutions: dict[str, dict[str, Any]] = {}
    for authorship in observation["authorships"]:
        author_key = authorship["author_id"] or f"unresolved:{authorship['author_label']}"
        authors.setdefault(
            author_key,
            {
                "id": authorship["author_id"],
                "label": authorship["author_label"],
                "identity_status": authorship["identity_status"],
            },
        )
        for institution in authorship["institutions"]:
            institutions.setdefault(
                institution["id"],
                {"id": institution["id"], "label": institution["label"]},
            )
    return list(authors.values()), list(institutions.values())


def scope_evidence_summary(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(
        item["inclusion"]["match_status"] for item in observations
    )
    matched_ids = {
        institution_id
        for item in observations
        for institution_id in item["inclusion"]["matched_entity_ids"]
    }
    matched_institutions: dict[str, dict[str, str]] = {}
    for observation in observations:
        for authorship in observation["authorships"]:
            for institution in authorship["institutions"]:
                if institution["id"] in matched_ids:
                    matched_institutions.setdefault(
                        institution["id"],
                        {
                            "id": institution["id"],
                            "label": institution["label"],
                        },
                    )
    total = len(observations)
    verified = status_counts["verified_local"]
    asserted = status_counts["asserted_by_source_filter"]
    return {
        "work_count": total,
        "verified_local_count": verified,
        "asserted_by_source_filter_count": asserted,
        "verified_local_ratio": round(verified / total, 12) if total else None,
        "matched_entity_ids": sorted(matched_ids),
        "matched_institutions": sorted(
            matched_institutions.values(), key=lambda item: item["id"]
        ),
        "fully_materialized": asserted == 0,
    }


def _representative_record(
    observation: dict[str, Any], window_role: str
) -> dict[str, Any]:
    authors, institutions = _actors(observation)
    matched_ids = set(observation["inclusion"]["matched_entity_ids"])
    matched_institutions = [
        item for item in institutions if item["id"] in matched_ids
    ]
    return {
        "observation_id": observation["observation_id"],
        "work_id": observation["work_id"],
        "title": observation["title"],
        "doi": observation["doi"],
        "publication_date": observation["publication_date"],
        "work_type": observation["work_type"],
        "cited_by_count_at_vintage": observation["citation_snapshot"]["cited_by_count"],
        "window_role": window_role,
        "authors": authors[:8],
        "institutions": institutions[:8],
        "scope_evidence": {
            "match_status": observation["inclusion"]["match_status"],
            "matched_entity_ids": sorted(matched_ids),
            "matched_institutions": matched_institutions,
            "reason": observation["inclusion"]["reason"],
        },
        "quality_flags": observation["quality_flags"],
    }


def editorial_status(
    assessment: dict[str, Any],
    priority: dict[str, Any],
    evidence_bundle: dict[str, Any],
) -> dict[str, Any]:
    confidence = assessment["confidence"]["level"]
    score = priority["score"]
    if confidence == "HIGH" and score >= HEADLINE_PRIORITY_THRESHOLD:
        tier = "HEADLINE_CANDIDATE"
    elif confidence == "HIGH" or score >= HEADLINE_PRIORITY_THRESHOLD:
        tier = "WATCH"
    else:
        tier = "EXPLORATION"

    reasons = []
    scope_evidence = evidence_bundle["scope_evidence"]
    if not scope_evidence["overall"]["fully_materialized"]:
        reasons.append("SCOPE_EVIDENCE_PARTIALLY_MATERIALIZED")
    if (
        scope_evidence["overall"]["work_count"] > 0
        and scope_evidence["overall"]["verified_local_count"] == 0
    ):
        reasons.append("NO_LOCALLY_VERIFIED_SCOPE_EVIDENCE")
    if not evidence_bundle["count_crosscheck"]["matches"]:
        reasons.append("EVIDENCE_COUNT_MISMATCH")
    # Corroboration multi-échelle (v0.2) : un topic en mouvement dont le subfield
    # parent va en sens opposé est probablement un artefact de petit effectif. Le
    # signal reste dans le flux (exploration), mais on exige une revue humaine et on
    # lui interdit le rang « À examiner en priorité » (jamais de headline sur un
    # artefact probable).
    scale_corroboration = assessment["classification"].get("scale_corroboration") or {}
    if scale_corroboration.get("concordance") == "CONTRADICTED":
        reasons.append("SCALE_CONTRADICTED")
        if tier == "HEADLINE_CANDIDATE":
            tier = "WATCH"
    return {
        "policy": EDITORIAL_POLICY,
        "tier": tier,
        "review_status": "REQUIRED" if reasons else "NOT_REQUIRED",
        "review_reasons": reasons,
    }


def select_representative_works(
    current: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    selected: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()

    def add(observation: dict[str, Any] | None, role: str) -> None:
        if observation is None or observation["work_id"] in seen or len(selected) >= limit:
            return
        selected.append((observation, role))
        seen.add(observation["work_id"])

    def most_cited(values: list[dict[str, Any]]) -> dict[str, Any] | None:
        return max(
            values,
            key=lambda item: (
                item["citation_snapshot"]["cited_by_count"],
                item["publication_date"],
                item["work_id"],
            ),
            default=None,
        )

    def most_recent(values: list[dict[str, Any]]) -> dict[str, Any] | None:
        return max(
            values,
            key=lambda item: (item["publication_date"], item["work_id"]),
            default=None,
        )

    add(most_cited(current), "current_window")
    add(most_cited(comparison), "comparison_window")
    add(most_recent(current), "current_window")
    add(most_recent(comparison), "comparison_window")

    all_values = [(item, "current_window") for item in current] + [
        (item, "comparison_window") for item in comparison
    ]
    represented_authors: set[str] = set()
    represented_institutions: set[str] = set()
    for observation, _ in selected:
        authors, institutions = _actors(observation)
        represented_authors.update(item["id"] or item["label"] for item in authors)
        represented_institutions.update(item["id"] for item in institutions)

    while len(selected) < limit:
        remaining = [item for item in all_values if item[0]["work_id"] not in seen]
        if not remaining:
            break

        def diversity_key(pair: tuple[dict[str, Any], str]):
            observation, _ = pair
            authors, institutions = _actors(observation)
            new_authors = sum(
                (item["id"] or item["label"]) not in represented_authors
                for item in authors
            )
            new_institutions = sum(
                item["id"] not in represented_institutions for item in institutions
            )
            return (
                new_institutions + new_authors,
                observation["citation_snapshot"]["cited_by_count"],
                observation["publication_date"],
                observation["work_id"],
            )

        observation, role = max(remaining, key=diversity_key)
        add(observation, role)
        authors, institutions = _actors(observation)
        represented_authors.update(item["id"] or item["label"] for item in authors)
        represented_institutions.update(item["id"] for item in institutions)

    return [_representative_record(item, role) for item, role in selected]


def _headline(assessment: dict[str, Any]) -> str:
    label = assessment["topic"]["display_name"]
    if assessment["signal_label"] == "RISING":
        return f"{label} progresse dans le portefeuille de recherche"
    if assessment["signal_label"] == "FALLING":
        return f"{label} recule dans le portefeuille de recherche"
    if assessment["signal_label"] == "NEW":
        return f"{label} apparaît dans l'activité récente"
    if assessment["signal_label"] == "REACTIVATED":
        return f"{label} se réactive après une période d'absence"
    return f"{label} devient dormant dans l'activité récente"


def _why_unusual(assessment: dict[str, Any]) -> str:
    observation = assessment["observation"]
    delta = assessment["delta"]
    percentile = delta["historical_percentile"]
    percentile_text = (
        f"{percentile:.1%}" if percentile is not None else "non calculable"
    )
    return (
        f"Le volume passe de {observation['previous_count']} à "
        f"{observation['current_count']} œuvres et la part de portefeuille de "
        f"{observation['previous_share']:.4%} à {observation['current_share']:.4%}. "
        f"La direction est observée sur {assessment['direction_streak']} évaluation(s) "
        f"consécutive(s), avec un percentile historique de "
        f"{percentile_text}."
    )


def _signal_envelope(
    assessment: dict[str, Any],
    evidence_bundle: dict[str, Any],
    priority: dict[str, Any],
    manifest: dict[str, Any],
    *,
    signal_id: str | None = None,
    schema_version: str = "signal-envelope/0.1",
    temporal_context: dict[str, Any] | None = None,
    dossier_path: str | None = None,
    detected_at: str | None = None,
) -> dict[str, Any]:
    topic_id = assessment["topic"]["id"]
    evaluation_date = assessment["evaluation_date"]
    signal_id = signal_id or f"sig:topic-momentum:{topic_id}:{evaluation_date}"
    evidence = []
    for index, work in enumerate(evidence_bundle["representative_works"], 1):
        evidence.append(
            {
                "evidence_id": f"{signal_id}:work:{index}",
                "type": "observation",
                "role": work["window_role"],
                "observed_at": manifest["data_vintage"],
                "locator": {
                    "kind": "observation",
                    "id": work["observation_id"],
                },
                "supports": (
                    f"L'œuvre {work['work_id']} est attribuée au topic dans "
                    f"la fenêtre {work['window_role']}."
                ),
            }
        )
    evidence.append(
        {
            "evidence_id": f"{signal_id}:manifest",
            "type": "query_manifest",
            "role": "provenance",
            "observed_at": manifest["data_vintage"],
            "locator": {"kind": "query_manifest", "id": manifest["manifest_id"]},
            "supports": "Le manifeste fixe le périmètre, le corpus et le vintage du signal.",
        }
    )
    backtest_mode = (
        "observed_vintage"
        if manifest["temporal_semantics"] == "observed_vintage"
        else "retrospective_reconstruction"
    )
    editorial = editorial_status(assessment, priority, evidence_bundle)
    confidence_limitations = set(assessment["confidence"]["limitations"])
    confidence_limitations.update(editorial["review_reasons"])
    quality_flags = set(confidence_limitations)
    for work in evidence_bundle["representative_works"]:
        quality_flags.update(work["quality_flags"])
    if not evidence_bundle["count_crosscheck"]["matches"]:
        quality_flags.add("EVIDENCE_COUNT_MISMATCH")
    payload = {
        "payload_schema": "topic_momentum",
        "signal_label": assessment["signal_label"],
        **assessment["classification"],
        "current_count": assessment["observation"]["current_count"],
        "reference_count": assessment["observation"]["previous_count"],
        "count_ratio_smoothed": assessment["delta"]["count_rate_ratio"],
        "current_share": assessment["observation"]["current_share"],
        "reference_share": assessment["observation"]["previous_share"],
        "share_rate_ratio": assessment["delta"]["share_rate_ratio"],
        "acceleration_value": assessment["delta"]["acceleration_value"],
        "historical_percentile": assessment["delta"]["historical_percentile"],
        "direction_streak": assessment["direction_streak"],
        "editorial": editorial,
        "scope_evidence": evidence_bundle["scope_evidence"],
        "evidence_bundle_id": evidence_bundle["evidence_bundle_id"],
    }
    if dossier_path is None and schema_version == "signal-envelope/0.1":
        dossier_path = f"dossiers/by-topic/{topic_id}-{evaluation_date}.md"
    if dossier_path is not None:
        payload["dossier_path"] = dossier_path

    envelope = {
        "schema_version": schema_version,
        "signal_id": signal_id,
        "detected_at": detected_at or manifest["data_vintage"],
        "detector": {"type": "topic_momentum", "version": "topic-momentum/0.1"},
        "universe": {
            "universe_id": manifest["universe"]["id"],
            "kind": "institution",
            "label": manifest["universe"]["label"],
            "scope_mode": manifest["universe"]["scope_mode"],
            "entity_ids": manifest["universe"]["included_institution_ids"],
        },
        "subject": {
            "kind": "topic",
            "id": topic_id,
            "label": assessment["topic"]["display_name"],
            "member_ids": [],
        },
        "analysis_context": {
            "current_window": {
                "start": assessment["effective_window"]["from"],
                "end": assessment["effective_window"]["to"],
            },
            "reference": {
                "kind": "historical_window",
                "reference_id": "previous-12-months",
                "window": {
                    "start": assessment["comparison_window"]["from"],
                    "end": assessment["comparison_window"]["to"],
                },
            },
        },
        "priority": priority,
        "confidence": {
            "level": assessment["confidence"]["level"],
            "score": assessment["confidence"]["score"],
            "factors": assessment["confidence"]["reasons"],
            "limitations": sorted(confidence_limitations),
        },
        "summary": {
            "headline": _headline(assessment),
            "why_unusual": _why_unusual(assessment),
        },
        "evidence": evidence,
        "provenance": {
            "run_id": manifest["run_id"],
            "query_manifest_id": manifest["manifest_id"],
            "observation_vintage": manifest["data_vintage"],
            "code_version": f"research-signal-instrument/{__version__}",
            "parameter_set_id": assessment["sensitivity"]["profiles"]["default"][
                "parameters_hash"
            ],
            "backtest_data_mode": backtest_mode,
        },
        "quality_flags": sorted(quality_flags),
        "payload": payload,
    }
    if temporal_context is not None:
        envelope["temporal_context"] = temporal_context
    return envelope


def _escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _scope_evidence_label(work: dict[str, Any]) -> str:
    scope = work["scope_evidence"]
    if scope["match_status"] == "verified_local":
        labels = ", ".join(
            _escape(item["label"]) for item in scope["matched_institutions"]
        )
        return f"verified_local — {labels or ', '.join(scope['matched_entity_ids'])}"
    return "server assertion — affiliation non matérialisée"


def _acceleration_label(payload: dict[str, Any]) -> str:
    status = payload["acceleration_status"]
    direction = payload["momentum_direction"]
    if status == "ACCELERATING" and direction == "RISING":
        return "hausse accélérée"
    if status == "ACCELERATING" and direction == "FALLING":
        return "recul accéléré"
    if status == "SLOWING" and direction == "RISING":
        return "hausse ralentie"
    if status == "SLOWING" and direction == "FALLING":
        return "recul ralenti"
    return status.lower()


def _scale_corroboration_label(payload: dict[str, Any]) -> str:
    sc = payload.get("scale_corroboration") or {}
    concordance = sc.get("concordance")
    subfield = sc.get("subfield_direction") or "—"
    labels = {
        "CORROBORATED": f"confirmé par le sous-domaine ({subfield})",
        "ISOLATED_WITHIN_PARENT": f"isolé dans son sous-domaine ({subfield})",
        "CONTRADICTED": f"contredit par le sous-domaine ({subfield})",
        "NEUTRAL": "sans objet",
    }
    return labels.get(concordance, str(concordance))


def dossier_markdown(
    signal: dict[str, Any], evidence_bundle: dict[str, Any]
) -> str:
    payload = signal["payload"]
    lines = [
        f"# {signal['summary']['headline']}",
        "",
        f"- Signal : `{signal['signal_id']}`",
        f"- Topic : `{signal['subject']['id']}` — {signal['subject']['label']}",
        f"- Direction : **{payload['momentum_direction']}**",
        f"- Présence : `{payload['presence_status']}`",
        f"- Dynamique : **{_acceleration_label(payload)}**",
        f"- Confiance : **{signal['confidence']['level']}** ({signal['confidence']['score']:.3f})",
        f"- Priorité : **{signal['priority']['score']:.3f}**",
        f"- Niveau éditorial : **{payload['editorial']['tier']}**",
        f"- Revue humaine : **{payload['editorial']['review_status']}**",
        *(
            [f"- Corroboration multi-échelle : **{_scale_corroboration_label(payload)}**"]
            if payload.get("scale_corroboration")
            else []
        ),
        "",
        "## Pourquoi ce signal",
        "",
        signal["summary"]["why_unusual"],
        "",
        "| Mesure | Fenêtre actuelle | Fenêtre précédente |",
        "|---|---:|---:|",
        f"| Œuvres | {payload['current_count']} | {payload['reference_count']} |",
        f"| Part du portefeuille | {payload['current_share']:.4%} | {payload['reference_share']:.4%} |",
        "",
        "## Confiance et limites",
        "",
        f"Facteurs favorables : {', '.join(signal['confidence']['factors']) or 'aucun'}.",
        "",
        f"Limites : {', '.join(signal['confidence']['limitations']) or 'aucune'}.",
        "",
        "## Rattachement au périmètre institutionnel",
        "",
        "| Fenêtre | Œuvres | Vérifiées localement | Assertion serveur | Taux vérifié |",
        "|---|---:|---:|---:|---:|",
    ]
    for role, label in (
        ("current_window", "Actuelle"),
        ("comparison_window", "Précédente"),
        ("overall", "Ensemble"),
    ):
        scope = evidence_bundle["scope_evidence"][role]
        ratio = (
            f"{scope['verified_local_ratio']:.1%}"
            if scope["verified_local_ratio"] is not None
            else "n/a"
        )
        lines.append(
            f"| {label} | {scope['work_count']} | {scope['verified_local_count']} "
            f"| {scope['asserted_by_source_filter_count']} | {ratio} |"
        )
    lines.extend(
        [
        "",
        "## Œuvres représentatives",
        "",
        "| Fenêtre | Date | Œuvre | Citations | Lien au périmètre | Auteurs | Institutions |",
        "|---|---|---|---:|---|---|---|",
        ]
    )
    for work in evidence_bundle["representative_works"]:
        title = _escape(work["title"])
        if work["doi"]:
            title = f"[{title}]({work['doi']})"
        authors = ", ".join(_escape(item["label"]) for item in work["authors"][:4])
        institutions = ", ".join(
            _escape(item["label"]) for item in work["institutions"][:4]
        )
        lines.append(
            f"| {work['window_role']} | {work['publication_date']} | {title} "
            f"| {work['cited_by_count_at_vintage']} | {_scope_evidence_label(work)} "
            f"| {authors} | {institutions} |"
        )
    lines.extend(
        [
            "",
            "## Traçabilité",
            "",
            f"- Manifeste : `{signal['provenance']['query_manifest_id']}`",
            f"- Vintage : `{signal['provenance']['observation_vintage']}`",
            f"- Mode de backtest : `{signal['provenance']['backtest_data_mode']}`",
            f"- Bundle de preuves : `{evidence_bundle['evidence_bundle_id']}`",
            f"- Concordance census/preuves : `{evidence_bundle['count_crosscheck']['matches']}`",
        ]
    )
    return "\n".join(lines)


def run_tm06(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> TM06Result:
    if resume and rebuild:
        raise InvariantError("TM-06 --resume and --rebuild are mutually exclusive")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm05-result.json",
        "confidence/topic-momentum-eligible-latest.jsonl.gz",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"TM-06 requires completed TM-05 and TM-02 artifacts: {missing}")

    result_path = store.path("tm06-result.json")
    quality_path = store.path("quality/tm06-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("tm06-result.json")
        if completed.get("emitter_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError(
                "TM-06 result was produced by another emitter version; use --rebuild"
            )
        return TM06Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            signal_count=completed["signal_count"],
            representative_work_count=completed["representative_work_count"],
            evidence_mismatch_count=completed["evidence_mismatch_count"],
            headline_candidate_count=completed["headline_candidate_count"],
            review_required_count=completed["review_required_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError(
            "TM-06 result already exists; use --resume to reuse it or --rebuild "
            "to regenerate TM-06 artifacts only"
        )

    manifest = store.read_json("query-manifest.json")
    tm05_result = store.read_json("tm05-result.json")
    assessments = store.read_jsonl_gz(
        "confidence/topic-momentum-eligible-latest.jsonl.gz"
    )
    observations = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    if len(assessments) != tm05_result["eligible_count"]:
        raise InvariantError("TM-06 eligible assessment count differs from TM-05 result")
    if any(not item["default_alert_eligible"] for item in assessments):
        raise InvariantError("TM-06 input contains a non-eligible assessment")
    if any(item["universe"]["scope_mode"] != scope_mode for item in assessments):
        raise InvariantError("TM-06 input contains another scope")

    observations_by_topic: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        topic = observation["primary_topic"]
        if topic is not None:
            observations_by_topic.setdefault(topic["id"], []).append(observation)

    priorities = priority_scores(assessments)
    evidence_bundles = []
    signals = []
    mismatch_records = []
    for assessment in assessments:
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
            raise InvariantError(f"{topic_id}: no WorkObservation available for evidence")
        expected_current = assessment["observation"]["current_count"]
        expected_comparison = assessment["observation"]["previous_count"]
        matches = len(current) == expected_current and len(comparison) == expected_comparison
        crosscheck = {
            "expected_current": expected_current,
            "observed_current": len(current),
            "expected_comparison": expected_comparison,
            "observed_comparison": len(comparison),
            "matches": matches,
        }
        if not matches:
            mismatch_records.append({"topic_id": topic_id, **crosscheck})
        representatives = select_representative_works(current, comparison)
        scope_evidence = {
            "current_window": scope_evidence_summary(current),
            "comparison_window": scope_evidence_summary(comparison),
            "overall": scope_evidence_summary(current + comparison),
        }
        bundle = {
            "schema_version": "topic-momentum-evidence/0.2",
            "evidence_bundle_id": f"tme:{topic_id}:{assessment['evaluation_date']}",
            "assessment_id": assessment["assessment_id"],
            "topic": assessment["topic"],
            "evaluation_date": assessment["evaluation_date"],
            "current_work_ids": sorted(item["work_id"] for item in current),
            "comparison_work_ids": sorted(item["work_id"] for item in comparison),
            "representative_works": representatives,
            "scope_evidence": scope_evidence,
            "selection_method": "citation-recency-actor-diversity/0.1",
            "count_crosscheck": crosscheck,
            "query_manifest_ref": manifest["manifest_id"],
        }
        signal = _signal_envelope(
            assessment,
            bundle,
            priorities[assessment["assessment_id"]],
            manifest,
        )
        evidence_bundles.append(bundle)
        signals.append(signal)

    ordered = sorted(
        zip(signals, evidence_bundles),
        key=lambda pair: (-pair[0]["priority"]["score"], pair[0]["signal_id"]),
    )
    signals = [item[0] for item in ordered]
    evidence_bundles = [item[1] for item in ordered]

    for signal, bundle in ordered:
        topic_id = signal["subject"]["id"]
        day = signal["analysis_context"]["current_window"]["end"]
        store.write_text(
            f"dossiers/by-topic/{topic_id}-{day}.md",
            dossier_markdown(signal, bundle),
            overwrite=rebuild,
        )

    signal_path = store.write_jsonl_gz(
        "signals/topic-momentum-signals.jsonl.gz", signals, overwrite=rebuild
    )
    evidence_path = store.write_jsonl_gz(
        "evidence/topic-momentum-evidence.jsonl.gz",
        evidence_bundles,
        overwrite=rebuild,
    )
    index = [
        {
            "rank": rank,
            "signal_id": signal["signal_id"],
            "topic_id": signal["subject"]["id"],
            "topic_label": signal["subject"]["label"],
            "signal_label": signal["payload"]["signal_label"],
            "confidence_level": signal["confidence"]["level"],
            "confidence_score": signal["confidence"]["score"],
            "priority_score": signal["priority"]["score"],
            "editorial_tier": signal["payload"]["editorial"]["tier"],
            "review_status": signal["payload"]["editorial"]["review_status"],
            "review_reasons": signal["payload"]["editorial"]["review_reasons"],
            "dossier_path": signal["payload"]["dossier_path"],
        }
        for rank, signal in enumerate(signals, 1)
    ]
    index_path = store.write_json(
        "signals/topic-momentum-signal-index.json", index, overwrite=rebuild
    )

    index_lines = [
        "# Dossiers de preuves — Topic Momentum",
        "",
        f"Run : `{manifest['run_id']}`  ",
        f"Vintage : `{manifest['data_vintage']}`  ",
        f"Signaux : **{len(signals)}**",
        "",
        "| Rang | Topic | Direction | Confiance | Priorité | Niveau | Revue | Dossier |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for item, (signal, bundle) in zip(index, ordered):
        index_lines.append(
            f"| {item['rank']} | {_escape(item['topic_label'])} | "
            f"{item['signal_label']} | {item['confidence_level']} | "
            f"{item['priority_score']:.3f} | {item['editorial_tier']} | "
            f"{item['review_status']} | "
            f"[ouvrir](by-topic/{item['topic_id']}-{signal['analysis_context']['current_window']['end']}.md) |"
        )
    consolidated = list(index_lines)
    for signal, bundle in ordered:
        consolidated.extend(["", "---", "", dossier_markdown(signal, bundle)])
    index_md_path = store.write_text(
        "dossiers/index.md", "\n".join(index_lines), overwrite=rebuild
    )
    dossier_path = store.write_text(
        "dossiers/dossier-de-preuves.md",
        "\n".join(consolidated),
        overwrite=rebuild,
    )

    representative_count = sum(
        len(item["representative_works"]) for item in evidence_bundles
    )
    confidence_counts = Counter(item["confidence"]["level"] for item in signals)
    direction_counts = Counter(item["payload"]["momentum_direction"] for item in signals)
    scale_concordance_counts = Counter(
        (item["payload"].get("scale_corroboration") or {}).get("concordance")
        for item in signals
    )
    tier_counts = Counter(item["payload"]["editorial"]["tier"] for item in signals)
    review_counts = Counter(
        item["payload"]["editorial"]["review_status"] for item in signals
    )
    unresolved_evidence_count = sum(
        "UNRESOLVED_AUTHOR_ID" in work["quality_flags"]
        for item in evidence_bundles
        for work in item["representative_works"]
    )
    warnings = []
    if mismatch_records:
        warnings.append("EVIDENCE_COUNT_MISMATCH")
    if unresolved_evidence_count:
        warnings.append("UNRESOLVED_AUTHOR_IDENTITIES_IN_REPRESENTATIVE_WORKS")
    partial_scope_count = sum(
        not item["scope_evidence"]["overall"]["fully_materialized"]
        for item in evidence_bundles
    )
    no_verified_scope_count = sum(
        item["scope_evidence"]["overall"]["work_count"] > 0
        and item["scope_evidence"]["overall"]["verified_local_count"] == 0
        for item in evidence_bundles
    )
    if partial_scope_count:
        warnings.append("SCOPE_EVIDENCE_PARTIALLY_MATERIALIZED")
    if no_verified_scope_count:
        warnings.append("NO_LOCALLY_VERIFIED_SCOPE_EVIDENCE")
    quality = {
        "schema_version": "tm06-quality-report/0.2",
        "run_id": manifest["run_id"],
        "emitter_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "signal_count": len(signals),
        "evidence_bundle_count": len(evidence_bundles),
        "representative_work_count": representative_count,
        "evidence_mismatch_count": len(mismatch_records),
        "evidence_mismatches": mismatch_records,
        "representative_works_with_unresolved_authors": unresolved_evidence_count,
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "direction_counts": dict(sorted(direction_counts.items())),
        "editorial_tier_counts": dict(sorted(tier_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "scale_concordance_counts": {
            str(key): value
            for key, value in sorted(
                scale_concordance_counts.items(),
                key=lambda kv: (kv[0] is None, kv[0]),
            )
        },
        "signals_with_partially_materialized_scope_evidence": partial_scope_count,
        "signals_without_locally_verified_scope_evidence": no_verified_scope_count,
        "editorial_policy": EDITORIAL_POLICY,
        "selection_method": "citation-recency-actor-diversity/0.1",
        "priority_method": "topic-momentum-priority/0.1",
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/tm06-quality-report.json", quality, overwrite=rebuild
    )
    result = {
        "schema_version": "tm06-result/0.2",
        "scope_mode": scope_mode,
        "emitter_version": f"research-signal-instrument/{__version__}",
        "signal_count": len(signals),
        "representative_work_count": representative_count,
        "evidence_mismatch_count": len(mismatch_records),
        "headline_candidate_count": tier_counts["HEADLINE_CANDIDATE"],
        "review_required_count": review_counts["REQUIRED"],
        "outputs": {
            "signals": signal_path.relative_to(store.root).as_posix(),
            "signal_index": index_path.relative_to(store.root).as_posix(),
            "evidence": evidence_path.relative_to(store.root).as_posix(),
            "dossier_index": index_md_path.relative_to(store.root).as_posix(),
            "consolidated_dossier": dossier_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("tm06-result.json", result, overwrite=rebuild)
    return TM06Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        signal_count=len(signals),
        representative_work_count=representative_count,
        evidence_mismatch_count=len(mismatch_records),
        headline_candidate_count=tier_counts["HEADLINE_CANDIDATE"],
        review_required_count=review_counts["REQUIRED"],
        quality_report_path=quality_path,
    )
