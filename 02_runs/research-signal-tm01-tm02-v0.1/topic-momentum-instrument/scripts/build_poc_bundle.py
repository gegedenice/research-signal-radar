from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


BUNDLE_SCHEMA_VERSION = "research-signal-poc/0.1"
DEFAULT_OUTPUT = Path("ui/public/data/research-signal-poc.json")


@dataclass(frozen=True)
class DetectorSpec:
    key: str
    title: str
    description: str
    current_result: str | None
    current_signal_path: str
    current_evidence_path: str
    current_quality_path: str | None
    backtest_result: str | None
    backtest_summary_path: str | None
    backtest_quality_path: str | None
    extra_optional_backtest_paths: tuple[str, ...] = ()


DETECTORS: tuple[DetectorSpec, ...] = (
    DetectorSpec(
        key="topic_momentum",
        title="Topic Momentum",
        description="Quels thèmes montent, reculent ou changent de rythme ?",
        current_result="tm07-result.json",
        current_signal_path="signals/topic-momentum-signals.jsonl.gz",
        current_evidence_path="evidence/topic-momentum-evidence.jsonl.gz",
        current_quality_path="quality/tm07-quality-report.json",
        backtest_result="tm08-result.json",
        backtest_summary_path="backtest/outcomes/topic-momentum-calibration-summary.json",
        backtest_quality_path="quality/tm08-quality-report.json",
    ),
    DetectorSpec(
        key="citation_acceleration",
        title="Citation Acceleration",
        description="Quels travaux reçoivent des citations anormalement vite par rapport à une cohorte comparable ?",
        current_result="ca03-result.json",
        current_signal_path="signals/citation-acceleration-signals.jsonl.gz",
        current_evidence_path="evidence/citation-acceleration-evidence.jsonl.gz",
        current_quality_path="quality/ca03-quality-report.json",
        backtest_result="ca04-result.json",
        backtest_summary_path="backtest/citation-acceleration-backtest-summary.json",
        backtest_quality_path="quality/ca04-quality-report.json",
        extra_optional_backtest_paths=("backtest/citation-acceleration-cutoff-summaries.json",),
    ),
    DetectorSpec(
        key="actor_collaboration_novelty",
        title="Actor/Collaboration Novelty",
        description="Quels partenaires ou liens institutionnels apparaissent ou reviennent dans le portefeuille ?",
        current_result="acn03-result.json",
        current_signal_path="signals/actor-collaboration-novelty-signals.jsonl.gz",
        current_evidence_path="evidence/actor-collaboration-novelty-evidence.jsonl.gz",
        current_quality_path="quality/acn03-quality-report.json",
        backtest_result="acn04-result.json",
        backtest_summary_path="backtest/actor-collaboration-novelty-backtest-summary.json",
        backtest_quality_path="quality/acn04-quality-report.json",
        extra_optional_backtest_paths=("backtest/actor-collaboration-novelty-cutoff-summaries.json",),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construit le bundle statique du POC Research Signal."
    )
    parser.add_argument("--run-root", required=True, help="Racine du run existant")
    parser.add_argument("--scope", required=True, help="Scope à lire, ex: lineage")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Chemin du bundle JSON généré",
    )
    parser.add_argument(
        "--include-generated-at",
        action="store_true",
        help="Inclut un horodatage de génération non déterministe",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle = build_poc_bundle(
        run_root=Path(args.run_root),
        scope=args.scope,
        include_generated_at=args.include_generated_at,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_poc_bundle(
    *,
    run_root: Path,
    scope: str,
    include_generated_at: bool = False,
) -> dict[str, Any]:
    scope_root = run_root / scope
    if not scope_root.exists():
        raise FileNotFoundError(f"Scope introuvable: {scope_root}")

    query_manifest = _read_json_required(scope_root / "query-manifest.json")
    _require_schema_prefix(query_manifest, "query-manifest/")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    warnings: set[str] = set()
    detectors: list[dict[str, Any]] = []
    normalized_signals: list[dict[str, Any]] = []
    backtests: dict[str, Any] = {}

    for spec in DETECTORS:
        current_result = _read_json_optional(scope_root / spec.current_result) if spec.current_result else None
        backtest_result = _read_json_optional(scope_root / spec.backtest_result) if spec.backtest_result else None

        signal_path = _resolve_output_path(
            scope_root,
            current_result,
            primary_output_keys=("signals", "replay_signals"),
            fallback_path=spec.current_signal_path,
            required=True,
            context=f"{spec.key} signals",
        )
        evidence_path = _resolve_output_path(
            scope_root,
            current_result,
            primary_output_keys=("evidence", "replay_evidence"),
            fallback_path=spec.current_evidence_path,
            required=True,
            context=f"{spec.key} evidence",
        )

        signal_items = list(_read_jsonl_gz_required(signal_path))
        evidence_items = list(_read_jsonl_gz_required(evidence_path))
        evidence_lookup = _build_evidence_lookup(evidence_items)

        current_quality = _read_json_optional(
            _resolve_output_path(
                scope_root,
                current_result,
                primary_output_keys=("quality_report",),
                fallback_path=spec.current_quality_path,
                required=False,
                context=f"{spec.key} current quality",
            )
        )
        backtest_summary_path = _resolve_output_path(
            scope_root,
            backtest_result,
            primary_output_keys=("summary", "calibration_summary"),
            fallback_path=spec.backtest_summary_path,
            required=False,
            context=f"{spec.key} backtest summary",
        )
        backtest_summary = (
            _read_json_optional(backtest_summary_path) if backtest_summary_path else None
        )
        backtest_quality_path = _resolve_output_path(
            scope_root,
            backtest_result,
            primary_output_keys=("quality_report",),
            fallback_path=spec.backtest_quality_path,
            required=False,
            context=f"{spec.key} backtest quality",
        )
        backtest_quality = (
            _read_json_optional(backtest_quality_path) if backtest_quality_path else None
        )

        detector_signals = [
            _normalize_signal(
                signal,
                spec=spec,
                query_manifest=query_manifest,
                evidence_lookup=evidence_lookup,
            )
            for signal in signal_items
        ]
        for item in detector_signals:
            bundle_id = item["evidence_bundle_id"]
            if bundle_id is not None:
                evidence_by_id[bundle_id] = evidence_lookup[bundle_id]
        normalized_signals.extend(detector_signals)

        detectors.append(
            _build_detector_summary(
                spec=spec,
                current_result=current_result,
                signal_items=signal_items,
            )
        )
        backtests[spec.key] = _build_backtest_payload(
            spec=spec,
            result=backtest_result,
            summary=backtest_summary,
            quality=backtest_quality,
            scope_root=scope_root,
            warnings=warnings,
        )
        warnings.update(_extract_quality_warnings(current_quality))
        warnings.update(_extract_quality_warnings(backtest_quality))

    normalized_signals.sort(
        key=lambda item: (
            -item["priority"]["score"],
            item["detector"]["key"],
            item["signal_id"],
        )
    )
    for index, signal in enumerate(normalized_signals, start=1):
        signal["feed_rank"] = index

    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source": _build_source(query_manifest, run_root, scope),
        "detectors": detectors,
        "signals": normalized_signals,
        "top_topics": _build_top_topics(scope_root),
        "evidence_by_id": dict(sorted(evidence_by_id.items())),
        "backtests": backtests,
        "warnings": sorted(warnings),
    }
    if include_generated_at:
        bundle["generated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    return bundle


def _build_source(query_manifest: dict[str, Any], run_root: Path, scope: str) -> dict[str, Any]:
    temporal_mode = _manifest_temporal_mode(query_manifest)
    return {
        "run_id": query_manifest.get("run_id"),
        "manifest_id": query_manifest.get("manifest_id"),
        "run_root": str(run_root),
        "scope_mode": scope,
        "portfolio_label": query_manifest.get("universe", {}).get("label"),
        "information_cutoff": query_manifest.get("to_publication_date"),
        "observation_vintage": query_manifest.get("data_vintage"),
        "temporal_mode": temporal_mode,
        "retrospective_reconstruction": temporal_mode == "retrospective_reconstruction",
        "manifest": {
            "universe_id": query_manifest.get("universe", {}).get("id"),
            "root_ror": query_manifest.get("universe", {}).get("root_ror"),
            "stream_id": query_manifest.get("stream", {}).get("id"),
            "from_publication_date": query_manifest.get("from_publication_date"),
            "to_publication_date": query_manifest.get("to_publication_date"),
            "topic_axis": query_manifest.get("topic_axis"),
            "bucket_granularity": query_manifest.get("bucket_granularity"),
        },
    }


def _build_detector_summary(
    *,
    spec: DetectorSpec,
    current_result: dict[str, Any] | None,
    signal_items: list[dict[str, Any]],
) -> dict[str, Any]:
    editorial_counts = Counter(
        _editorial_tier(signal) for signal in signal_items if _editorial_tier(signal)
    )
    return {
        "key": spec.key,
        "title": spec.title,
        "description": spec.description,
        "signal_count": len(signal_items),
        "headline_count": editorial_counts.get("HEADLINE_CANDIDATE", 0),
        "watch_count": editorial_counts.get("WATCH", 0),
        "exploration_count": editorial_counts.get("EXPLORATION", 0),
        "result_counts": {
            key: value
            for key, value in (current_result or {}).items()
            if key.endswith("_count")
        },
        "current_result_schema": (current_result or {}).get("schema_version"),
        "current_result_version": (current_result or {}).get("emitter_version"),
    }


def _build_backtest_payload(
    *,
    spec: DetectorSpec,
    result: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    scope_root: Path,
    warnings: set[str],
) -> dict[str, Any]:
    payload = {
        "available": summary is not None,
        "result": result,
        "summary": summary,
        "quality": quality,
        "extra": {},
    }
    for relative_path in spec.extra_optional_backtest_paths:
        path = scope_root / relative_path
        if path.exists():
            payload["extra"][path.stem] = _read_json_required(path)
        else:
            warnings.add(f"OPTIONAL_BACKTEST_MISSING:{spec.key}:{relative_path}")
    if summary is None:
        warnings.add(f"OPTIONAL_BACKTEST_MISSING:{spec.key}:summary")
    return payload


def _normalize_signal(
    signal: dict[str, Any],
    *,
    spec: DetectorSpec,
    query_manifest: dict[str, Any],
    evidence_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    _require_schema_prefix(signal, "signal-envelope/")
    signal_cutoff = _signal_cutoff(signal, query_manifest)
    evidence_bundle_id = _signal_evidence_bundle_id(signal, spec, evidence_lookup, signal_cutoff)
    normalized = {
        "signal_id": signal["signal_id"],
        "source_schema_version": signal.get("schema_version"),
        "detector": {
            "key": spec.key,
            "title": spec.title,
            "type": signal.get("detector", {}).get("type"),
            "version": signal.get("detector", {}).get("version"),
        },
        "subject": signal.get("subject"),
        "signal_label": signal.get("payload", {}).get("signal_label"),
        "scale_corroboration": signal.get("payload", {}).get("scale_corroboration"),
        "priority": signal.get("priority"),
        "confidence": signal.get("confidence"),
        "editorial": {
            "tier": _editorial_tier(signal),
            "review_status": _editorial_review_status(signal),
            "review_reasons": _editorial_review_reasons(signal),
        },
        "summary": signal.get("summary"),
        "why_unusual": signal.get("summary", {}).get("why_unusual"),
        "analysis_context": signal.get("analysis_context"),
        "temporal_context": _normalized_temporal_context(signal, query_manifest),
        "quality_flags": signal.get("quality_flags", []),
        "provenance": signal.get("provenance", {}),
        "metrics": _signal_metrics(signal),
        "payload": signal.get("payload", {}),
        "evidence_refs": signal.get("evidence", []),
        "evidence_bundle_id": evidence_bundle_id,
        "evidence_bundle_available": evidence_bundle_id in evidence_lookup if evidence_bundle_id else False,
        "dossier_path": _signal_dossier_path(signal),
        "limitations": signal.get("confidence", {}).get("limitations", []),
    }
    return normalized


def _signal_metrics(signal: dict[str, Any]) -> dict[str, Any]:
    payload = signal.get("payload", {})
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "payload_schema",
            "signal_label",
            "editorial",
            "evidence_bundle_id",
            "dossier_path",
            "scale_corroboration",
        }
    }


def _normalized_temporal_context(
    signal: dict[str, Any], query_manifest: dict[str, Any]
) -> dict[str, Any]:
    temporal_context = dict(signal.get("temporal_context", {}))
    if "mode" not in temporal_context:
        temporal_context["mode"] = (
            signal.get("provenance", {}).get("backtest_data_mode")
            or _manifest_temporal_mode(query_manifest)
        )
    if "observation_vintage" not in temporal_context:
        temporal_context["observation_vintage"] = (
            signal.get("provenance", {}).get("observation_vintage")
            or query_manifest.get("data_vintage")
        )
    if "information_cutoff" not in temporal_context:
        temporal_context["information_cutoff"] = (
            f"{_signal_cutoff(signal, query_manifest)}T23:59:59Z"
        )
    if "emitted_at" not in temporal_context:
        temporal_context["emitted_at"] = signal.get("detected_at")
    if "cutoff_basis" not in temporal_context:
        temporal_context["cutoff_basis"] = "publication_date"
    return temporal_context


def _manifest_temporal_mode(query_manifest: dict[str, Any]) -> str:
    semantics = query_manifest.get("temporal_semantics")
    if semantics == "retrospective_snapshot":
        return "retrospective_reconstruction"
    return semantics or "unknown"


def _signal_cutoff(signal: dict[str, Any], query_manifest: dict[str, Any]) -> str:
    temporal_context = signal.get("temporal_context", {})
    value = temporal_context.get("information_cutoff")
    if isinstance(value, str) and value:
        return value[:10]
    current_window_end = signal.get("analysis_context", {}).get("current_window", {}).get("end")
    if current_window_end:
        return current_window_end
    manifest_cutoff = query_manifest.get("to_publication_date")
    if manifest_cutoff:
        return manifest_cutoff
    raise ValueError(f"Impossible de déterminer le cutoff pour {signal.get('signal_id')}")


def _signal_evidence_bundle_id(
    signal: dict[str, Any],
    spec: DetectorSpec,
    evidence_lookup: dict[str, dict[str, Any]],
    signal_cutoff: str,
) -> str | None:
    payload_bundle_id = signal.get("payload", {}).get("evidence_bundle_id")
    if payload_bundle_id:
        return payload_bundle_id

    subject = signal.get("subject", {})
    subject_id = subject.get("id")
    if spec.key == "topic_momentum":
        for bundle_id, evidence in evidence_lookup.items():
            topic_id = evidence.get("topic", {}).get("id")
            evaluation_date = evidence.get("evaluation_date")
            if topic_id == subject_id and evaluation_date == signal_cutoff:
                return bundle_id
    else:
        for bundle_id, evidence in evidence_lookup.items():
            evidence_subject_id = evidence.get("subject", {}).get("id")
            evidence_cutoff = evidence.get("information_cutoff")
            if evidence_subject_id == subject_id and evidence_cutoff == signal_cutoff:
                return bundle_id
    return None


def _signal_dossier_path(signal: dict[str, Any]) -> str | None:
    payload = signal.get("payload", {})
    if payload.get("dossier_path"):
        return payload["dossier_path"]
    if signal.get("subject", {}).get("kind") == "topic":
        signal_id = signal.get("signal_id", "")
        parts = signal_id.split(":")
        if len(parts) >= 4:
            return f"dossiers/by-topic/{parts[2]}-{parts[3]}.md"
    return None


def _editorial_tier(signal: dict[str, Any]) -> str | None:
    return signal.get("payload", {}).get("editorial", {}).get("tier")


def _editorial_review_status(signal: dict[str, Any]) -> str | None:
    return signal.get("payload", {}).get("editorial", {}).get("review_status")


def _editorial_review_reasons(signal: dict[str, Any]) -> list[str]:
    return list(signal.get("payload", {}).get("editorial", {}).get("review_reasons", []))


def _build_evidence_lookup(evidence_items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in evidence_items:
        bundle_id = item.get("evidence_bundle_id")
        if not bundle_id:
            raise ValueError("Evidence bundle sans evidence_bundle_id")
        lookup[bundle_id] = item
    return lookup


def _extract_quality_warnings(value: dict[str, Any] | None) -> list[str]:
    if not value:
        return []
    return list(value.get("warnings", []))


def _resolve_output_path(
    scope_root: Path,
    result: dict[str, Any] | None,
    *,
    primary_output_keys: tuple[str, ...],
    fallback_path: str | None,
    required: bool,
    context: str,
) -> Path | None:
    outputs = (result or {}).get("outputs", {})
    for key in primary_output_keys:
        relative = outputs.get(key)
        if relative:
            path = scope_root / relative
            if path.exists():
                return path
    if fallback_path:
        path = scope_root / fallback_path
        if path.exists():
            return path
    if required:
        expected = ", ".join(primary_output_keys)
        raise FileNotFoundError(
            f"Artefact indispensable absent pour {context}: outputs[{expected}] ou {fallback_path}"
        )
    return None


def _read_json_required(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier JSON introuvable: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_optional(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return _read_json_required(path)


def _read_jsonl_gz_required(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier JSONL gzip introuvable: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON invalide dans {path} ligne {line_number}") from exc


def _build_top_topics(scope_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    """Vue « stock » : les plus gros thèmes par volume total sur la période.

    Complète la vue « flux » (signaux de mouvement) en listant les topics les plus
    volumineux — qu'ils bougent ou non — avec leur direction courante, pour relier
    un thème important à son éventuel signal (par topic_id).
    """
    path = scope_root / "classifications" / "topic-momentum-latest.jsonl.gz"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for item in _read_jsonl_gz_required(path):
        topic = item.get("topic", {})
        observation = item.get("observation", {})
        classification = item.get("classification", {})
        current = observation.get("current_count", 0) or 0
        previous = observation.get("previous_count", 0) or 0
        history = observation.get("history_count", 0) or 0
        subfield = (topic.get("subfield") or {}).get("display_name")
        rows.append(
            {
                "topic_id": topic.get("id"),
                "label": topic.get("display_name"),
                "subfield": subfield,
                "total_count": history + previous + current,
                "current_count": current,
                "previous_count": previous,
                "current_share": observation.get("current_share"),
                "direction": classification.get("momentum_direction"),
                "presence": classification.get("presence_status"),
            }
        )
    rows.sort(key=lambda row: (-row["total_count"], row["label"] or ""))
    return rows[:limit]


def _require_schema_prefix(value: dict[str, Any], prefix: str) -> None:
    schema_version = value.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.startswith(prefix):
        raise ValueError(
            f"Version de schéma inattendue: {schema_version!r}, préfixe attendu {prefix!r}"
        )


if __name__ == "__main__":
    main()
