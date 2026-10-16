from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import RunConfig
from .errors import InvariantError
from .storage import RunStore, sha256_json


@dataclass(frozen=True)
class CA03Result:
    scope_mode: str
    scope_dir: Path
    candidate_count: int
    signal_count: int
    headline_candidate_count: int
    review_required_count: int
    quality_report_path: Path


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_candidate(item: dict[str, Any], config: RunConfig) -> bool:
    metrics = item["metrics"]
    cohort = item["cohort"]
    params = config.citation_acceleration
    return bool(
        item.get("eligible_for_detection")
        and metrics["current"] >= params.min_recent_citations
        and metrics["absolute_delta"] >= params.min_absolute_delta
        and metrics["acceleration_ratio"] >= params.min_acceleration_ratio
        and cohort["percentile"] >= params.min_cohort_percentile
        and cohort["size"] >= params.min_cohort_size
    )


def _source_concordance(ratio: float | None) -> float:
    if ratio is None or ratio <= 0:
        return 0.5
    return max(0.0, 1.0 - min(abs(math.log(ratio)) / math.log(2), 1.0))


def _confidence(item: dict[str, Any], config: RunConfig) -> dict[str, Any]:
    coverage = item["coverage"]
    cohort = item["cohort"]
    metrics = item["metrics"]
    temporal = float(coverage["temporal_coverage_ratio"])
    ratio = coverage.get("cross_source_ratio")
    specificity = {
        "primary_topic_age_type": 1.0,
        "subfield_age_type": 0.85,
        "portfolio_age_type": 0.65,
    }[cohort["kind"]]
    size_support = min(
        1.0,
        0.5 + 0.5 * max(0.0, math.log10(cohort["size"] / config.citation_acceleration.min_cohort_size)),
    )
    self_robustness = (
        0.85 if metrics["known_author_self_citations_current"] > 0 else 1.0
    )
    components = {
        "temporal_coverage": temporal,
        "source_concordance": _source_concordance(ratio),
        "cohort_specificity": specificity,
        "cohort_size_support": size_support,
        "self_citation_robustness": self_robustness,
    }
    score = round(
        0.30 * temporal
        + 0.25 * components["source_concordance"]
        + 0.25 * specificity
        + 0.10 * size_support
        + 0.10 * self_robustness,
        6,
    )
    limitations: list[str] = []
    factors: list[str] = []
    if cohort["fallback_level"] == 0:
        factors.append("TOPIC_SPECIFIC_COHORT")
    elif cohort["fallback_level"] == 1:
        limitations.append("SUBFIELD_COHORT_FALLBACK")
    else:
        limitations.append("PORTFOLIO_COHORT_FALLBACK")
    if temporal >= 0.9:
        factors.append("HIGH_TEMPORAL_COVERAGE")
    elif temporal < 0.8:
        limitations.append("LIMITED_TEMPORAL_COVERAGE")
    if ratio is None:
        limitations.append("NO_CROSS_SOURCE_RATIO")
    elif 0.5 <= ratio <= 1.5:
        factors.append("CROSS_SOURCE_COUNTS_CONCORDANT")
    else:
        limitations.append("CROSS_SOURCE_COUNT_DIVERGENCE")
    if metrics["known_author_self_citations_current"]:
        limitations.append("KNOWN_CURRENT_SELF_CITATIONS_PRESENT")
    else:
        factors.append("NO_KNOWN_CURRENT_SELF_CITATION")
    if cohort["size"] < 30:
        limitations.append("SMALL_REFERENCE_COHORT")
    else:
        factors.append("SUPPORTED_REFERENCE_COHORT")
    level = "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.6 else "LOW"
    return {
        "level": level,
        "score": score,
        "factors": factors,
        "limitations": limitations,
        "components": {key: round(value, 6) for key, value in components.items()},
    }


def _ecdf(values: list[float], value: float) -> float:
    return sum(item <= value for item in values) / len(values)


def _priority(
    item: dict[str, Any], candidates: list[dict[str, Any]], confidence: dict[str, Any],
    minimum_percentile: float,
) -> dict[str, Any]:
    params = item["cohort"]["percentile"]
    available_range = max(1.0 - minimum_percentile, 1e-12)
    anomaly = max(0.0, min(1.0, (params - minimum_percentile) / available_range))
    recent = [candidate["metrics"]["current"] for candidate in candidates]
    deltas = [candidate["metrics"]["absolute_delta"] for candidate in candidates]
    components = {
        "cohort_anomaly": anomaly,
        "recent_volume_rank": _ecdf(recent, item["metrics"]["current"]),
        "absolute_delta_rank": _ecdf(deltas, item["metrics"]["absolute_delta"]),
        "confidence": confidence["score"],
    }
    score = round(
        0.35 * anomaly
        + 0.25 * components["recent_volume_rank"]
        + 0.20 * components["absolute_delta_rank"]
        + 0.20 * confidence["score"],
        6,
    )
    return {
        "score": score,
        "method": "ca03-salience-v0.1",
        "interpretation": "ranking_only_not_probability",
        "components": {key: round(value, 6) for key, value in components.items()},
    }


def _timeline(item: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = item["windows"]["previous"]
    current = item["windows"]["current"]
    months: dict[str, dict[str, Any]] = {}
    for event in events:
        month = event.get("creation_month")
        if not month or not previous["from_month"] <= month <= current["to_month"]:
            continue
        row = months.setdefault(month, {"month": month, "primary_count": 0, "including_known_self_citations": 0})
        row["including_known_self_citations"] += 1
        if event.get("author_self_citation") != "yes":
            row["primary_count"] += 1
    return [months[key] for key in sorted(months)]


def _editorial(priority: dict[str, Any], confidence: dict[str, Any], threshold: float) -> dict[str, Any]:
    if priority["score"] >= threshold and confidence["level"] != "LOW":
        tier = "HEADLINE_CANDIDATE"
    elif confidence["level"] != "LOW":
        tier = "WATCH"
    else:
        tier = "EXPLORATION"
    review_reasons = [
        item for item in confidence["limitations"]
        if item in {
            "LIMITED_TEMPORAL_COVERAGE",
            "NO_CROSS_SOURCE_RATIO",
            "CROSS_SOURCE_COUNT_DIVERGENCE",
            "KNOWN_CURRENT_SELF_CITATIONS_PRESENT",
        }
    ]
    if confidence["level"] == "LOW":
        review_reasons.append("LOW_CONFIDENCE")
    return {
        "tier": tier,
        "review_status": "REQUIRED" if review_reasons else "OPTIONAL",
        "review_reasons": sorted(set(review_reasons)),
    }


def _universe(manifest: dict[str, Any], config: RunConfig, scope_mode: str) -> dict[str, Any]:
    source = manifest.get("universe", {})
    return {
        "universe_id": source.get("id", config.universe.id),
        "kind": "institution",
        "label": source.get("label", config.universe.label),
        "scope_mode": scope_mode,
        "entity_ids": source.get("included_institution_ids", []),
    }


def _build_signal(
    item: dict[str, Any], confidence: dict[str, Any], priority: dict[str, Any],
    editorial: dict[str, Any], manifest: dict[str, Any], config: RunConfig,
    scope_mode: str, emitted_at: str, evidence_id: str,
) -> dict[str, Any]:
    work_id = item["subject"]["id"]
    cutoff = item["information_cutoff"]
    signal_id = f"sig:citation-acceleration:{work_id}:{cutoff}"
    label = "BREAKOUT" if item["metrics"]["previous"] <= 1 else "ACCELERATING"
    mode = (
        "observed_vintage" if config.temporal_semantics == "observed_vintage"
        else "retrospective_reconstruction"
    )
    quality_flags = sorted(set(confidence["limitations"] + editorial["review_reasons"]))
    recent = item["metrics"]["current"]
    previous = item["metrics"]["previous"]
    return {
        "schema_version": "signal-envelope/0.2",
        "signal_id": signal_id,
        "detected_at": emitted_at,
        "detector": {"type": "citation_acceleration", "version": "citation-acceleration/0.1"},
        "universe": _universe(manifest, config, scope_mode),
        "subject": {"kind": "work", "id": work_id, "label": item["subject"]["label"], "member_ids": []},
        "analysis_context": {
            "current_window": {"start": item["windows"]["current"]["from"], "end": item["windows"]["current"]["to"]},
            "reference": {
                "kind": "cohort_and_previous_window",
                "reference_id": item["cohort"]["cohort_id"],
                "window": {"start": item["windows"]["previous"]["from"], "end": item["windows"]["previous"]["to"]},
            },
        },
        "priority": priority,
        "confidence": confidence,
        "summary": {
            "headline": f"Accélération citationnelle — {item['subject']['label']}",
            "why_unusual": (
                f"{recent} citations dans la fenêtre récente contre {previous} auparavant; "
                f"delta +{item['metrics']['absolute_delta']}, ratio {item['metrics']['acceleration_ratio']:.2f}, "
                f"percentile de cohorte {item['cohort']['percentile']:.1%}."
            ),
        },
        "evidence": [
            {
                "evidence_id": f"{signal_id}:work",
                "type": "observation",
                "role": "cited_work",
                "observed_at": manifest.get("data_vintage") or config.data_vintage.isoformat(),
                "locator": {"kind": "work_observation", "id": work_id},
                "supports": "Identité, date, type et topic de l'œuvre citée.",
            },
            {
                "evidence_id": f"{signal_id}:bundle",
                "type": "metric",
                "role": "citation_timeline_and_cohort",
                "observed_at": manifest.get("data_vintage") or config.data_vintage.isoformat(),
                "locator": {"kind": "evidence_bundle", "id": evidence_id},
                "supports": "Chronologie, compteurs, cohorte et contrôles qualité du signal.",
            },
        ],
        "provenance": {
            "run_id": manifest.get("run_id", config.run_id),
            "query_manifest_id": manifest.get("manifest_id", "query-manifest.json"),
            "observation_vintage": manifest.get("data_vintage") or config.data_vintage.isoformat(),
            "code_version": f"research-signal-instrument/{__version__}",
            "parameter_set_id": item["source"]["parameter_fingerprint"],
            "backtest_data_mode": mode,
        },
        "temporal_context": {
            "mode": mode,
            "emitted_at": emitted_at,
            "information_cutoff": f"{cutoff}T23:59:59Z",
            "observation_vintage": manifest.get("data_vintage") or config.data_vintage.isoformat(),
            "cutoff_basis": "publication_date",
        },
        "quality_flags": quality_flags,
        "payload": {
            "payload_schema": "citation_acceleration",
            "signal_label": label,
            "recent_citation_count": recent,
            "previous_citation_count": previous,
            "absolute_delta": item["metrics"]["absolute_delta"],
            "acceleration_ratio": item["metrics"]["acceleration_ratio"],
            "raw_acceleration": item["metrics"]["raw_acceleration"],
            "cohort": item["cohort"],
            "coverage": item["coverage"],
            "known_self_citation_sensitivity": {
                "recent_including_known_self": item["metrics"]["current_including_known_self_citations"],
                "previous_including_known_self": item["metrics"]["previous_including_known_self_citations"],
            },
            "editorial": editorial,
            "evidence_bundle_id": evidence_id,
            "dossier_path": "dossiers/citation-acceleration-dossier-de-preuves.md",
        },
    }


def _markdown(signals: list[dict[str, Any]], limit: int) -> str:
    chosen = signals[:limit]
    lines = [
        "# Citation acceleration — dossier de preuves", "",
        f"Ce dossier présente les {len(chosen)} signaux prioritaires sur {len(signals)} candidats. ",
        "Le score sert uniquement au tri; les preuves complètes sont conservées en JSON.", "",
        "| Rang | Œuvre | Label | Récent / avant | Percentile | Confiance | Priorité | Revue |", "|---:|---|---|---:|---:|---|---:|---|",
    ]
    for rank, signal in enumerate(chosen, 1):
        payload = signal["payload"]
        editorial = payload["editorial"]
        label = signal["subject"]["label"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {rank} | {label} | {payload['signal_label']} | "
            f"{payload['recent_citation_count']} / {payload['previous_citation_count']} | "
            f"{payload['cohort']['percentile']:.1%} | {signal['confidence']['level']} | "
            f"{signal['priority']['score']:.3f} | {editorial['review_status']} |"
        )
    lines.extend(["", "## Lecture", "", "- `BREAKOUT` : au plus une citation dans la fenêtre précédente.", "- `ACCELERATING` : rythme antérieur déjà établi puis en hausse.", "- `REQUIRED` : le signal reste détecté, mais une limite de couverture justifie une revue humaine."])
    return "\n".join(lines)


def run_ca03(
    config: RunConfig, run_dir: Path, scope_mode: str, *, resume: bool = False, rebuild: bool = False
) -> CA03Result:
    if resume and rebuild:
        raise InvariantError("CA-03 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json", "ca02-result.json", "quality/ca02-quality-report.json",
        "citations/citation-acceleration-eligible.jsonl.gz",
        "citations/citation-events.jsonl.gz", "observations/work-observations.jsonl.gz",
    ]
    missing = [path for path in required if not store.path(path).exists()]
    if missing:
        raise InvariantError(f"CA-03 requires completed CA-02 artifacts: {missing}")
    result_path = store.path("ca03-result.json")
    quality_path = store.path("quality/ca03-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        done = store.read_json("ca03-result.json")
        if done.get("emitter_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError("CA-03 result was produced by another version; use --rebuild")
        return CA03Result(scope_mode, store.root, done["candidate_count"], done["signal_count"], done["headline_candidate_count"], done["review_required_count"], quality_path)
    if result_path.exists() and not rebuild:
        raise InvariantError("CA-03 result already exists; use --resume or --rebuild")

    manifest = store.read_json("query-manifest.json")
    ca02 = store.read_json("ca02-result.json")
    quality02 = store.read_json("quality/ca02-quality-report.json")
    if ca02.get("schema_version") != "ca02-result/0.1" or quality02.get("schema_version") != "ca02-quality-report/0.1":
        raise InvariantError("CA-03 requires CA-02 schema version 0.1")
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("CA-03 scope differs from query manifest")
    assessments = store.read_jsonl_gz("citations/citation-acceleration-eligible.jsonl.gz")
    candidates = [item for item in assessments if _is_candidate(item, config)]
    works = {item["work_id"]: item for item in store.read_jsonl_gz("observations/work-observations.jsonl.gz")}
    events_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in store.read_jsonl_gz("citations/citation-events.jsonl.gz"):
        events_by_work[event["cited_work_id"]].append(event)
    emitted_at = _iso_now()
    signals: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for item in candidates:
        confidence = _confidence(item, config)
        priority = _priority(
            item, candidates, confidence,
            config.citation_acceleration.min_cohort_percentile,
        )
        editorial = _editorial(priority, confidence, config.citation_acceleration.headline_priority_threshold)
        work_id = item["subject"]["id"]
        evidence_id = f"evidence:citation-acceleration:{work_id}:{item['information_cutoff']}"
        work_events = events_by_work[work_id]
        current = item["windows"]["current"]
        representatives = [
            event for event in work_events
            if event.get("creation_month")
            and current["from_month"] <= event["creation_month"] <= current["to_month"]
            and event.get("author_self_citation") != "yes"
        ]
        representatives.sort(key=lambda event: (event.get("creation_date") or event.get("creation_month"), event["event_id"]), reverse=True)
        bundle = {
            "schema_version": "citation-acceleration-evidence/0.1",
            "evidence_bundle_id": evidence_id,
            "subject": item["subject"],
            "work_observation": works.get(work_id),
            "information_cutoff": item["information_cutoff"],
            "windows": item["windows"],
            "metrics": item["metrics"],
            "cohort": item["cohort"],
            "coverage": item["coverage"],
            "monthly_timeline": _timeline(item, work_events),
            "representative_recent_citation_events": representatives[:5],
            "count_crosscheck": {
                "previous_matches": sum(row["primary_count"] for row in _timeline(item, work_events) if item["windows"]["previous"]["from_month"] <= row["month"] <= item["windows"]["previous"]["to_month"]) == item["metrics"]["previous"],
                "current_matches": sum(row["primary_count"] for row in _timeline(item, work_events) if current["from_month"] <= row["month"] <= current["to_month"]) == item["metrics"]["current"],
            },
        }
        evidence.append(bundle)
        signals.append(_build_signal(item, confidence, priority, editorial, manifest, config, scope_mode, emitted_at, evidence_id))
    signals.sort(key=lambda item: (-item["priority"]["score"], item["signal_id"]))
    evidence_by_id = {item["evidence_bundle_id"]: item for item in evidence}
    evidence = [evidence_by_id[item["payload"]["evidence_bundle_id"]] for item in signals]
    label_counts = Counter(item["payload"]["signal_label"] for item in signals)
    confidence_counts = Counter(item["confidence"]["level"] for item in signals)
    tier_counts = Counter(item["payload"]["editorial"]["tier"] for item in signals)
    review_count = sum(item["payload"]["editorial"]["review_status"] == "REQUIRED" for item in signals)
    mismatches = sum(not all(item["count_crosscheck"].values()) for item in evidence)
    params = {
        "schema_version": "citation-acceleration-signal-parameters/0.1",
        "detector_stage": "CA-03", "parameters": asdict(config.citation_acceleration),
        "candidate_rule": "all_thresholds_conjunctive", "input_ca02_version": ca02["calculator_version"],
    }
    params["parameter_fingerprint"] = sha256_json(params)
    overwrite = rebuild
    params_path = store.write_json("citations/citation-acceleration-signal-parameters.json", params, overwrite=overwrite)
    signals_path = store.write_jsonl_gz("signals/citation-acceleration-signals.jsonl.gz", signals, overwrite=overwrite)
    evidence_path = store.write_jsonl_gz("evidence/citation-acceleration-evidence.jsonl.gz", evidence, overwrite=overwrite)
    index = [{"rank": rank, "signal_id": item["signal_id"], "work_id": item["subject"]["id"], "label": item["payload"]["signal_label"], "priority_score": item["priority"]["score"], "confidence_level": item["confidence"]["level"], "editorial_tier": item["payload"]["editorial"]["tier"], "review_status": item["payload"]["editorial"]["review_status"]} for rank, item in enumerate(signals, 1)]
    index_path = store.write_json("signals/citation-acceleration-signal-index.json", index, overwrite=overwrite)
    dossier_path = store.write_text("dossiers/citation-acceleration-dossier-de-preuves.md", _markdown(signals, config.citation_acceleration.dossier_limit), overwrite=overwrite)
    quality = {
        "schema_version": "ca03-quality-report/0.1", "run_id": manifest.get("run_id", config.run_id),
        "emitter_version": f"research-signal-instrument/{__version__}", "scope_mode": scope_mode,
        "information_cutoff": config.collection.to_publication_date.isoformat(),
        "eligible_input_count": len(assessments), "candidate_count": len(candidates), "signal_count": len(signals),
        "candidate_rate_among_eligible": round(len(candidates) / len(assessments), 6) if assessments else 0.0,
        "label_counts": dict(sorted(label_counts.items())), "confidence_counts": dict(sorted(confidence_counts.items())),
        "editorial_tier_counts": dict(sorted(tier_counts.items())), "review_required_count": review_count,
        "evidence_count_mismatch_count": mismatches, "post_cutoff_events_used": 0,
        "warnings": ["EVIDENCE_COUNT_MISMATCH"] if mismatches else [], "resumed": resume, "rebuilt": rebuild,
    }
    quality_path = store.write_json("quality/ca03-quality-report.json", quality, overwrite=overwrite)
    result = {
        "schema_version": "ca03-result/0.1", "scope_mode": scope_mode,
        "emitter_version": f"research-signal-instrument/{__version__}", "candidate_count": len(candidates),
        "signal_count": len(signals), "headline_candidate_count": tier_counts["HEADLINE_CANDIDATE"],
        "review_required_count": review_count,
        "outputs": {"parameters": params_path.relative_to(store.root).as_posix(), "signals": signals_path.relative_to(store.root).as_posix(), "signal_index": index_path.relative_to(store.root).as_posix(), "evidence": evidence_path.relative_to(store.root).as_posix(), "dossier": dossier_path.relative_to(store.root).as_posix(), "quality_report": quality_path.relative_to(store.root).as_posix()},
    }
    store.write_json("ca03-result.json", result, overwrite=overwrite)
    return CA03Result(scope_mode, store.root, len(candidates), len(signals), tier_counts["HEADLINE_CANDIDATE"], review_count, quality_path)
