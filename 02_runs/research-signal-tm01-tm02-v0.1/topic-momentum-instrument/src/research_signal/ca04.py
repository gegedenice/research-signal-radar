from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import math
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .ca02 import _age_band, _age_months, _cohort_keys, _metric_counts, _percentile, _windows
from .ca03 import _build_signal, _editorial, _is_candidate, _priority, _timeline
from .config import RunConfig
from .dates import add_months, month_distance, month_end
from .errors import InvariantError
from .storage import RunStore, sha256_json


@dataclass(frozen=True)
class CA04Result:
    scope_mode: str
    scope_dir: Path
    cutoff_count: int
    replayed_signal_count: int
    observed_outcome_count: int
    censored_outcome_count: int
    sustained_outcome_count: int
    quality_report_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cutoffs(config: RunConfig) -> list[date]:
    current = date.fromisoformat(config.citation_acceleration.backtest_start_date)
    end = config.collection.to_publication_date
    values: list[date] = []
    while current <= end:
        values.append(current)
        current = month_end(add_months(current, config.citation_acceleration.backtest_step_months))
    if not values or values[-1] != end:
        values.append(end)
    return values


def _temporal_coverage(coverage: dict[str, Any]) -> float | None:
    if coverage.get("eligibility_status") != "COLLECTED":
        return None
    rows = int(coverage.get("opencitations_event_row_count") or 0)
    usable = int(coverage.get("monthly_usable_event_count") or 0)
    return usable / rows if rows else 1.0


def _assessments_at_cutoff(
    config: RunConfig,
    cutoff: date,
    works: list[dict[str, Any]],
    coverage_by_id: dict[str, dict[str, Any]],
    events_by_work: dict[str, list[dict[str, Any]]],
    topic_catalog: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    windows = _windows(cutoff, config.citation_acceleration.window_months)
    prepared: dict[str, dict[str, Any]] = {}
    excluded = Counter()
    for work in works:
        work_id = work["work_id"]
        if date.fromisoformat(work["publication_date"]) > cutoff:
            excluded["POST_CUTOFF_WORK"] += 1
            continue
        age = _age_months(work["publication_date"], cutoff)
        if age < 12:
            excluded["TOO_RECENT_AT_CUTOFF"] += 1
            continue
        coverage = coverage_by_id[work_id]
        temporal = _temporal_coverage(coverage)
        if temporal is None:
            excluded[coverage.get("eligibility_status") or "NOT_COLLECTED"] += 1
            continue
        if coverage.get("count_matches_event_rows") is False:
            excluded["OPENCITATIONS_COUNT_ROW_MISMATCH"] += 1
            continue
        if (
            int(coverage.get("opencitations_citation_count") or 0) == 0
            and int(coverage.get("openalex_cited_by_count") or 0) > 0
        ):
            excluded["OPENCITATIONS_UNAVAILABLE"] += 1
            continue
        if temporal < config.citation_acceleration.min_temporal_coverage:
            excluded["INSUFFICIENT_TEMPORAL_COVERAGE"] += 1
            continue
        topic = work.get("primary_topic") or {}
        topic_id = topic.get("id")
        catalog = topic_catalog.get(topic_id) or {}
        subfield = catalog.get("subfield") or {}
        prepared[work_id] = {
            "work": work,
            "work_type": work.get("work_type") or "unknown",
            "topic_id": topic_id,
            "subfield_id": subfield.get("id"),
            "age_months": age,
            "age_band": _age_band(age, config.citation_acceleration.age_band_boundaries_months),
            "temporal_coverage": temporal,
            "metrics": _metric_counts(events_by_work.get(work_id, []), windows),
        }

    members: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for work_id, item in prepared.items():
        for key in _cohort_keys(item):
            members[key].append(work_id)
    assessments: list[dict[str, Any]] = []
    for work_id in sorted(prepared):
        item = prepared[work_id]
        selected = next(
            (key for key in _cohort_keys(item) if len(members[key]) >= config.citation_acceleration.min_cohort_size),
            None,
        )
        if selected is None:
            excluded["INSUFFICIENT_COHORT_SUPPORT"] += 1
            continue
        values = [prepared[member]["metrics"]["raw_acceleration"] for member in members[selected]]
        fallback = {"primary_topic_age_type": 0, "subfield_age_type": 1, "portfolio_age_type": 2}[selected[0]]
        work = item["work"]
        current_coverage = coverage_by_id[work_id]
        assessments.append({
            "schema_version": "citation-acceleration-replay-assessment/0.1",
            "assessment_id": f"ca04:{cutoff.isoformat()}:{work_id}",
            "detector_id": "citation_acceleration",
            "subject": {"type": "work", "id": work_id, "label": work.get("title") or work_id, "doi": current_coverage.get("doi")},
            "information_cutoff": cutoff.isoformat(),
            "publication_date": work["publication_date"],
            "work_type": item["work_type"],
            "primary_topic": work.get("primary_topic"),
            "age_months": item["age_months"],
            "age_band": item["age_band"],
            "windows": windows,
            "metrics": item["metrics"],
            "coverage": {
                "eligibility_status": "COLLECTED",
                "opencitations_count_at_observation_vintage": current_coverage.get("opencitations_citation_count"),
                "openalex_count_at_observation_vintage": current_coverage.get("openalex_cited_by_count"),
                "cross_source_ratio_at_observation_vintage": current_coverage.get("cross_source_ratio"),
                "temporal_coverage_ratio": round(item["temporal_coverage"], 12),
            },
            "cohort": {
                "cohort_id": "ca-replay-cohort:" + sha256_json((cutoff.isoformat(), selected)).split(":", 1)[1][:20],
                "kind": selected[0], "size": len(values),
                "percentile": _percentile(values, item["metrics"]["raw_acceleration"]),
                "fallback_level": fallback,
            },
            "abstention": {"is_abstained": False, "reasons": []},
            "eligible_for_detection": True,
            "source": {"parameter_fingerprint": "pending-ca04-parameter-fingerprint"},
        })
    return assessments, dict(sorted(excluded.items()))


def _replay_confidence(item: dict[str, Any], config: RunConfig) -> dict[str, Any]:
    temporal = float(item["coverage"]["temporal_coverage_ratio"])
    cohort = item["cohort"]
    specificity = {"primary_topic_age_type": 1.0, "subfield_age_type": 0.85, "portfolio_age_type": 0.65}[cohort["kind"]]
    size_support = min(1.0, 0.5 + 0.5 * max(0.0, math.log10(cohort["size"] / config.citation_acceleration.min_cohort_size)))
    self_robustness = 0.85 if item["metrics"]["known_author_self_citations_current"] else 1.0
    score = round(0.40 * temporal + 0.30 * specificity + 0.15 * size_support + 0.15 * self_robustness, 6)
    factors = []
    limitations = ["CURRENT_SNAPSHOT_CROSSCHECK_NOT_USED_IN_REPLAY"]
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
    if item["metrics"]["known_author_self_citations_current"]:
        limitations.append("KNOWN_CURRENT_SELF_CITATIONS_PRESENT")
    else:
        factors.append("NO_KNOWN_CURRENT_SELF_CITATION")
    if cohort["size"] < 30:
        limitations.append("SMALL_REFERENCE_COHORT")
    else:
        factors.append("SUPPORTED_REFERENCE_COHORT")
    level = "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.6 else "LOW"
    return {
        "level": level, "score": score, "factors": factors, "limitations": limitations,
        "components": {"temporal_coverage": round(temporal, 6), "cohort_specificity": specificity, "cohort_size_support": round(size_support, 6), "self_citation_robustness": self_robustness},
    }


def _evidence_bundle(item: dict[str, Any], work: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    current = item["windows"]["current"]
    representatives = [event for event in events if event.get("creation_month") and current["from_month"] <= event["creation_month"] <= current["to_month"] and event.get("author_self_citation") != "yes"]
    representatives.sort(key=lambda event: (event.get("creation_date") or event.get("creation_month"), event["event_id"]), reverse=True)
    timeline = _timeline(item, events)
    previous_count = sum(row["primary_count"] for row in timeline if item["windows"]["previous"]["from_month"] <= row["month"] <= item["windows"]["previous"]["to_month"])
    current_count = sum(row["primary_count"] for row in timeline if current["from_month"] <= row["month"] <= current["to_month"])
    return {
        "schema_version": "citation-acceleration-replay-evidence/0.1",
        "evidence_bundle_id": f"evidence:citation-acceleration:{item['subject']['id']}:{item['information_cutoff']}",
        "subject": item["subject"], "information_cutoff": item["information_cutoff"],
        "work_observation": work, "windows": item["windows"], "metrics": item["metrics"],
        "cohort": item["cohort"], "coverage": item["coverage"], "monthly_timeline": timeline,
        "representative_recent_citation_events": representatives[:5],
        "count_crosscheck": {"previous_matches": previous_count == item["metrics"]["previous"], "current_matches": current_count == item["metrics"]["current"]},
    }


def _outcome(signal: dict[str, Any], events: list[dict[str, Any]], latest: date, horizon: int, evaluated_at: str) -> dict[str, Any]:
    cutoff = date.fromisoformat(signal["analysis_context"]["current_window"]["end"])
    target = month_end(add_months(cutoff, horizon))
    base = {
        "schema_version": "citation-acceleration-outcome/0.1",
        "outcome_id": f"ca04:{signal['signal_id']}:+{horizon}m", "signal_id": signal["signal_id"],
        "work": {"id": signal["subject"]["id"], "label": signal["subject"]["label"]},
        "horizon_months": horizon, "detection_cutoff": cutoff.isoformat(), "target_cutoff": target.isoformat(),
        "status": "RIGHT_CENSORED", "outcome": None,
        "provenance": {"evaluated_at": evaluated_at, "backtest_data_mode": "retrospective_reconstruction", "source_signal_schema": signal["schema_version"]},
    }
    if target > latest:
        base["censoring"] = {"reason": "TARGET_AFTER_INFORMATION_CUTOFF", "latest_available_cutoff": latest.isoformat()}
        return base
    from_month = add_months(date(cutoff.year, cutoff.month, 1), 1).strftime("%Y-%m")
    to_month = target.strftime("%Y-%m")
    future = sum(1 for event in events if event.get("creation_month") and from_month <= event["creation_month"] <= to_month and event.get("author_self_citation") != "yes")
    current = signal["payload"]["recent_citation_count"]
    label = "SUSTAINED" if future >= current else "FADED"
    base["status"] = "OBSERVED"
    base["outcome"] = {"label": label, "future_citation_count": future, "detection_current_count": current, "velocity_retention_ratio": round(future / current, 6) if current else None}
    base["censoring"] = None
    return base


def _markdown(summary: dict[str, Any], cutoffs: list[dict[str, Any]], sample: list[dict[str, Any]]) -> str:
    lines = ["# Citation acceleration — backtest minimal", "", "Replay semestriel rétrospectif, avec issue observée douze mois après chaque signal.", "", f"- Signaux rejoués : **{summary['replayed_signal_count']}**", f"- Issues observées : **{summary['observed_outcome_count']}**", f"- `SUSTAINED` : **{summary['sustained_count']}**", f"- `FADED` : **{summary['faded_count']}**", f"- Censurées : **{summary['censored_outcome_count']}**", f"- Taux de maintien : **{summary['sustained_rate']:.1%}**" if summary["sustained_rate"] is not None else "- Taux de maintien : n/a", "", "## Cutoffs", "", "| Cutoff | Population comparable | Signaux | Headlines | Issues observables |", "|---|---:|---:|---:|---:|"]
    for item in cutoffs:
        lines.append(f"| {item['cutoff']} | {item['eligible_count']} | {item['signal_count']} | {item['headline_count']} | {item['observable_outcome_count']} |")
    lines.extend(["", "## Échantillon de revue", "", "| Œuvre | Cutoff | Label | Citations au signal | Citations +12m | Issue |", "|---|---|---|---:|---:|---|"])
    for item in sample:
        label = item["work"]["label"].replace("|", "\\|").replace("\n", " ")
        outcome = item["outcome"]
        lines.append(f"| {label} | {item['detection_cutoff']} | {item['signal_label']} | {outcome['detection_current_count']} | {outcome['future_citation_count']} | {outcome['label']} |")
    lines.extend(["", "## Limite", "", "Les données sont une reconstruction à partir du snapshot OpenCitations actuel. Elles démontrent la logique et l'utilité potentielle du détecteur, pas les conditions exactes d'indexation disponibles à chaque date historique."])
    return "\n".join(lines)


def run_ca04(config: RunConfig, run_dir: Path, scope_mode: str, *, resume: bool = False, rebuild: bool = False) -> CA04Result:
    if resume and rebuild:
        raise InvariantError("CA-04 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = ["query-manifest.json", "ca03-result.json", "observations/work-observations.jsonl.gz", "topics/topic-catalog.json", "citations/citation-events.jsonl.gz", "citations/work-citation-coverage.jsonl.gz"]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"CA-04 requires completed CA-03 artifacts: {missing}")
    result_path = store.path("ca04-result.json")
    quality_path = store.path("quality/ca04-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        done = store.read_json("ca04-result.json")
        if done.get("evaluator_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError("CA-04 result was produced by another version; use --rebuild")
        return CA04Result(scope_mode, store.root, done["cutoff_count"], done["replayed_signal_count"], done["observed_outcome_count"], done["censored_outcome_count"], done["sustained_outcome_count"], quality_path)
    if result_path.exists() and not rebuild:
        raise InvariantError("CA-04 result already exists; use --resume or --rebuild")
    manifest = store.read_json("query-manifest.json")
    ca03 = store.read_json("ca03-result.json")
    if ca03.get("schema_version") != "ca03-result/0.1":
        raise InvariantError("CA-04 requires ca03-result/0.1")
    works = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    coverage = store.read_jsonl_gz("citations/work-citation-coverage.jsonl.gz")
    events = store.read_jsonl_gz("citations/citation-events.jsonl.gz")
    catalog = {item["id"]: item for item in store.read_json("topics/topic-catalog.json")}
    work_by_id = {item["work_id"]: item for item in works}
    coverage_by_id = {item["work_id"]: item for item in coverage}
    if set(work_by_id) != set(coverage_by_id):
        raise InvariantError("CA-04 work and coverage populations differ")
    events_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["cited_work_id"] not in work_by_id:
            raise InvariantError(f"CA-04 event refers to unknown work {event['cited_work_id']}")
        events_by_work[event["cited_work_id"]].append(event)
    emitted_at = _now()
    cutoffs = _cutoffs(config)
    params = {"schema_version": "citation-acceleration-backtest-parameters/0.1", "detector_stage": "CA-04", "parameters": asdict(config.citation_acceleration), "outcome_policy": "SUSTAINED iff next-12m count >= detection current-12m count", "temporal_mode": "retrospective_reconstruction"}
    params["parameter_fingerprint"] = sha256_json(params)
    all_signals: list[dict[str, Any]] = []
    all_evidence: list[dict[str, Any]] = []
    cutoff_summaries: list[dict[str, Any]] = []
    for cutoff in cutoffs:
        assessments, exclusions = _assessments_at_cutoff(config, cutoff, works, coverage_by_id, events_by_work, catalog)
        for item in assessments:
            item["source"]["parameter_fingerprint"] = params["parameter_fingerprint"]
        candidates = [item for item in assessments if _is_candidate(item, config)]
        cutoff_signals: list[dict[str, Any]] = []
        for item in candidates:
            confidence = _replay_confidence(item, config)
            priority = _priority(item, candidates, confidence, config.citation_acceleration.min_cohort_percentile)
            editorial = _editorial(priority, confidence, config.citation_acceleration.headline_priority_threshold)
            bundle = _evidence_bundle(item, work_by_id[item["subject"]["id"]], events_by_work[item["subject"]["id"]])
            signal = _build_signal(item, confidence, priority, editorial, manifest, config, scope_mode, emitted_at, bundle["evidence_bundle_id"])
            signal["quality_flags"] = sorted(set(signal["quality_flags"] + ["RETROSPECTIVE_RECONSTRUCTION"]))
            signal["payload"]["replay"] = {"cutoff": cutoff.isoformat(), "rank_within_cutoff": None}
            cutoff_signals.append(signal)
            all_evidence.append(bundle)
        cutoff_signals.sort(key=lambda item: (-item["priority"]["score"], item["signal_id"]))
        for rank, signal in enumerate(cutoff_signals, 1):
            signal["payload"]["replay"]["rank_within_cutoff"] = rank
        all_signals.extend(cutoff_signals)
        target = month_end(add_months(cutoff, config.citation_acceleration.outcome_horizon_months))
        cutoff_summaries.append({"cutoff": cutoff.isoformat(), "eligible_count": len(assessments), "signal_count": len(cutoff_signals), "headline_count": sum(item["payload"]["editorial"]["tier"] == "HEADLINE_CANDIDATE" for item in cutoff_signals), "observable_outcome_count": len(cutoff_signals) if target <= config.collection.to_publication_date else 0, "exclusion_counts": exclusions})
    outcomes = [_outcome(signal, events_by_work[signal["subject"]["id"]], config.collection.to_publication_date, config.citation_acceleration.outcome_horizon_months, emitted_at) for signal in all_signals]
    signal_by_id = {item["signal_id"]: item for item in all_signals}
    observed = [item for item in outcomes if item["status"] == "OBSERVED"]
    sustained = [item for item in observed if item["outcome"]["label"] == "SUSTAINED"]
    faded = [item for item in observed if item["outcome"]["label"] == "FADED"]
    first_cutoff: dict[str, str] = {}
    for signal in all_signals:
        work_id = signal["subject"]["id"]
        cutoff = signal["payload"]["replay"]["cutoff"]
        first_cutoff[work_id] = min(first_cutoff.get(work_id, cutoff), cutoff)
    leads = [month_distance(date.fromisoformat(value), config.collection.to_publication_date) for value in first_cutoff.values()]
    by_label: dict[str, dict[str, Any]] = {}
    for label in ("BREAKOUT", "ACCELERATING"):
        subset = [item for item in observed if signal_by_id[item["signal_id"]]["payload"]["signal_label"] == label]
        kept = sum(item["outcome"]["label"] == "SUSTAINED" for item in subset)
        by_label[label] = {"observed_count": len(subset), "sustained_count": kept, "sustained_rate": round(kept / len(subset), 6) if subset else None}
    summary = {"schema_version": "citation-acceleration-backtest-summary/0.1", "replayed_signal_count": len(all_signals), "unique_work_count": len(first_cutoff), "observed_outcome_count": len(observed), "censored_outcome_count": len(outcomes) - len(observed), "sustained_count": len(sustained), "faded_count": len(faded), "sustained_rate": round(len(sustained) / len(observed), 6) if observed else None, "median_first_detection_lead_months_to_latest_cutoff": median(leads) if leads else None, "by_signal_label": by_label, "interpretation": "Descriptive retrospective backtest; not a causal or prospective validation."}
    ranked_outcomes = sorted(observed, key=lambda item: (-signal_by_id[item["signal_id"]]["priority"]["score"], item["signal_id"]))
    sample: list[dict[str, Any]] = []
    for label in ("SUSTAINED", "FADED"):
        for item in [row for row in ranked_outcomes if row["outcome"]["label"] == label][:10]:
            signal = signal_by_id[item["signal_id"]]
            sample.append({**item, "signal_label": signal["payload"]["signal_label"], "priority_score": signal["priority"]["score"]})
    mismatch_count = sum(not all(item["count_crosscheck"].values()) for item in all_evidence)
    quality = {"schema_version": "ca04-quality-report/0.1", "run_id": manifest.get("run_id", config.run_id), "evaluator_version": f"research-signal-instrument/{__version__}", "scope_mode": scope_mode, "cutoff_count": len(cutoffs), "replayed_signal_count": len(all_signals), "observed_outcome_count": len(observed), "censored_outcome_count": len(outcomes) - len(observed), "evidence_count_mismatch_count": mismatch_count, "post_cutoff_events_used_for_detection": 0, "temporal_mode": "retrospective_reconstruction", "warnings": ["RETROSPECTIVE_RECONSTRUCTION"] + (["EVIDENCE_COUNT_MISMATCH"] if mismatch_count else []), "resumed": resume, "rebuilt": rebuild}
    overwrite = rebuild
    paths = {
        "parameters": store.write_json("backtest/citation-acceleration-backtest-parameters.json", params, overwrite=overwrite),
        "signals": store.write_jsonl_gz("backtest/citation-acceleration-replay-signals.jsonl.gz", all_signals, overwrite=overwrite),
        "evidence": store.write_jsonl_gz("backtest/citation-acceleration-replay-evidence.jsonl.gz", all_evidence, overwrite=overwrite),
        "outcomes": store.write_jsonl_gz("backtest/citation-acceleration-event-outcomes.jsonl.gz", outcomes, overwrite=overwrite),
        "cutoffs": store.write_json("backtest/citation-acceleration-cutoff-summaries.json", cutoff_summaries, overwrite=overwrite),
        "summary": store.write_json("backtest/citation-acceleration-backtest-summary.json", summary, overwrite=overwrite),
        "review_sample": store.write_json("backtest/citation-acceleration-review-sample.json", sample, overwrite=overwrite),
        "markdown": store.write_text("dossiers/citation-acceleration-backtest-summary.md", _markdown(summary, cutoff_summaries, sample), overwrite=overwrite),
    }
    quality_path = store.write_json("quality/ca04-quality-report.json", quality, overwrite=overwrite)
    result = {"schema_version": "ca04-result/0.1", "scope_mode": scope_mode, "evaluator_version": f"research-signal-instrument/{__version__}", "cutoff_count": len(cutoffs), "replayed_signal_count": len(all_signals), "observed_outcome_count": len(observed), "censored_outcome_count": len(outcomes) - len(observed), "sustained_outcome_count": len(sustained), "outputs": {key: value.relative_to(store.root).as_posix() for key, value in paths.items()} | {"quality_report": quality_path.relative_to(store.root).as_posix()}}
    store.write_json("ca04-result.json", result, overwrite=overwrite)
    return CA04Result(scope_mode, store.root, len(cutoffs), len(all_signals), len(observed), len(outcomes) - len(observed), len(sustained), quality_path)
