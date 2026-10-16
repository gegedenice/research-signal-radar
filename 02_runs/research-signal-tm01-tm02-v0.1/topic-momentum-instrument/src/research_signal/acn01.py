from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .config import RunConfig
from .errors import InvariantError
from .storage import RunStore, sha256_json


AUTHOR_PAIR_SAMPLE_LIMIT = 20


@dataclass(frozen=True)
class ACN01Result:
    scope_mode: str
    scope_dir: Path
    input_work_count: int
    usable_work_count: int
    collaboration_event_count: int
    coaffiliation_event_count: int
    unique_external_institution_count: int
    quality_report_path: Path


def _institution_map(work: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for authorship in work.get("authorships") or []:
        for institution in authorship.get("institutions") or []:
            identifier = institution.get("id")
            if not identifier:
                continue
            values.setdefault(
                identifier,
                {
                    "id": identifier,
                    "label": institution.get("label") or identifier,
                    "ror": institution.get("ror"),
                },
            )
    return values


def _authors_by_institution(
    work: dict[str, Any], institution_ids: set[str]
) -> tuple[dict[str, set[str]], int, int]:
    authors: dict[str, set[str]] = defaultdict(set)
    unresolved_authors = 0
    unresolved_institutions = 0
    for authorship in work.get("authorships") or []:
        author_id = authorship.get("author_id")
        if not author_id:
            unresolved_authors += 1
        for institution in authorship.get("institutions") or []:
            institution_id = institution.get("id")
            if not institution_id:
                unresolved_institutions += 1
                continue
            if institution_id in institution_ids and author_id:
                authors[institution_id].add(author_id)
    return authors, unresolved_authors, unresolved_institutions


def _event_base(
    work: dict[str, Any],
    anchor: dict[str, Any],
    external: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    observed_at = work.get("observed_at") or manifest.get("data_vintage")
    return {
        "work_id": work["work_id"],
        "publication_date": work["publication_date"],
        "publication_month": work["publication_date"][:7],
        "anchor_institution": anchor,
        "external_institution": external,
        "primary_topic": work.get("primary_topic"),
        "observed_at": observed_at,
        "source": {
            "provider": "OpenAlex",
            "work_observation_id": work.get("observation_id") or work["work_id"],
            "query_manifest_id": manifest.get("manifest_id"),
        },
    }


def _normalize_work(
    work: dict[str, Any],
    anchor_ids: set[str],
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    institutions = _institution_map(work)
    observed_ids = set(institutions)
    materialized_anchors = sorted(observed_ids & anchor_ids)
    external_ids = sorted(observed_ids - anchor_ids)
    authors_by_institution, unresolved_authors, unresolved_institutions = (
        _authors_by_institution(work, observed_ids)
    )
    quality_flags: set[str] = set()
    if unresolved_authors:
        quality_flags.add("UNRESOLVED_AUTHOR_ID")
    if unresolved_institutions:
        quality_flags.add("UNRESOLVED_INSTITUTION_ID")

    collaboration_events: list[dict[str, Any]] = []
    coaffiliation_events: list[dict[str, Any]] = []
    for anchor_id in materialized_anchors:
        anchor = institutions[anchor_id]
        anchor_authors = authors_by_institution.get(anchor_id, set())
        for external_id in external_ids:
            external = institutions[external_id]
            external_authors = authors_by_institution.get(external_id, set())
            dual_authors = sorted(anchor_authors & external_authors)
            if dual_authors:
                event = _event_base(work, anchor, external, manifest)
                event.update(
                    {
                        "schema_version": "coaffiliation-event-observation/0.1",
                        "event_id": f"acn-coaff:{work['work_id']}:{anchor_id}:{external_id}",
                        "dual_affiliated_author_count": len(dual_authors),
                        "dual_affiliated_author_ids": dual_authors[
                            :AUTHOR_PAIR_SAMPLE_LIMIT
                        ],
                        "author_ids_truncated": len(dual_authors)
                        > AUTHOR_PAIR_SAMPLE_LIMIT,
                    }
                )
                coaffiliation_events.append(event)
            pair_count = (
                len(anchor_authors) * len(external_authors) - len(dual_authors)
            )
            if pair_count:
                author_pairs: list[tuple[str, str]] = []
                for anchor_author in sorted(anchor_authors):
                    for external_author in sorted(external_authors):
                        if anchor_author == external_author:
                            continue
                        author_pairs.append((anchor_author, external_author))
                        if len(author_pairs) == AUTHOR_PAIR_SAMPLE_LIMIT:
                            break
                    if len(author_pairs) == AUTHOR_PAIR_SAMPLE_LIMIT:
                        break
                event = _event_base(work, anchor, external, manifest)
                event.update(
                    {
                        "schema_version": "collaboration-event-observation/0.1",
                        "event_id": f"acn-event:{work['work_id']}:{anchor_id}:{external_id}",
                        "author_pairs": [
                            {
                                "anchor_author_id": anchor_author,
                                "external_author_id": external_author,
                            }
                            for anchor_author, external_author in author_pairs
                        ],
                        "author_pair_count": pair_count,
                        "author_pairs_truncated": pair_count
                        > AUTHOR_PAIR_SAMPLE_LIMIT,
                        "dual_affiliated_author_count": len(dual_authors),
                        "dual_affiliated_author_ids": dual_authors[
                            :AUTHOR_PAIR_SAMPLE_LIMIT
                        ],
                    }
                )
                collaboration_events.append(event)

    if not materialized_anchors:
        status = "ANCHOR_NOT_MATERIALIZED"
    elif not external_ids:
        status = "NO_EXTERNAL_INSTITUTION"
    elif collaboration_events:
        status = "USABLE"
    elif coaffiliation_events:
        status = "DUAL_AFFILIATION_ONLY"
    else:
        status = "NO_VALID_AUTHOR_PAIR"
    if status != "USABLE":
        quality_flags.add(status)
    coverage = {
        "schema_version": "collaboration-work-coverage/0.1",
        "work_id": work["work_id"],
        "publication_date": work["publication_date"],
        "status": status,
        "materialized_anchor_institution_ids": materialized_anchors,
        "external_institution_ids": external_ids,
        "resolved_author_count": len(
            {
                authorship["author_id"]
                for authorship in work.get("authorships") or []
                if authorship.get("author_id")
            }
        ),
        "unresolved_authorship_count": unresolved_authors,
        "unresolved_institution_reference_count": unresolved_institutions,
        "collaboration_event_count": len(collaboration_events),
        "coaffiliation_event_count": len(coaffiliation_events),
        "quality_flags": sorted(quality_flags),
    }
    return collaboration_events, coaffiliation_events, coverage, institutions


def run_acn01(
    config: RunConfig,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> ACN01Result:
    if resume and rebuild:
        raise InvariantError("ACN-01 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm02-result.json",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"ACN-01 requires completed TM-02 artifacts: {missing}")
    result_path = store.path("acn01-result.json")
    quality_path = store.path("quality/acn01-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("acn01-result.json")
        if completed.get("normalizer_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError("ACN-01 result was produced by another version; use --rebuild")
        return ACN01Result(
            scope_mode,
            store.root,
            completed["input_work_count"],
            completed["usable_work_count"],
            completed["collaboration_event_count"],
            completed["coaffiliation_event_count"],
            completed["unique_external_institution_count"],
            quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("ACN-01 result already exists; use --resume or --rebuild")

    manifest = store.read_json("query-manifest.json")
    tm02_result = store.read_json("tm02-result.json")
    if tm02_result.get("schema_version") != "tm02-result/0.1":
        raise InvariantError("ACN-01 requires tm02-result/0.1")
    if manifest.get("universe", {}).get("scope_mode") != scope_mode:
        raise InvariantError("ACN-01 scope differs from query manifest")
    anchor_ids = set(manifest.get("universe", {}).get("included_institution_ids") or [])
    if not anchor_ids:
        raise InvariantError("ACN-01 query manifest has no included institution IDs")
    works = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    if not works:
        raise InvariantError("ACN-01 received no WorkObservation")
    if any(item.get("schema_version") != "work-observation/0.1" for item in works):
        raise InvariantError("ACN-01 requires work-observation/0.1 inputs")
    work_ids = [item["work_id"] for item in works]
    if len(work_ids) != len(set(work_ids)):
        raise InvariantError("ACN-01 received duplicate WorkObservation IDs")

    events: list[dict[str, Any]] = []
    coaffiliations: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    catalog: dict[str, dict[str, Any]] = {}
    catalog_work_ids: dict[str, set[str]] = defaultdict(set)
    for work in works:
        work_events, work_coaffiliations, work_coverage, institutions = _normalize_work(
            work, anchor_ids, manifest
        )
        events.extend(work_events)
        coaffiliations.extend(work_coaffiliations)
        coverage.append(work_coverage)
        for institution_id, institution in institutions.items():
            catalog.setdefault(institution_id, institution)
            catalog_work_ids[institution_id].add(work["work_id"])

    event_ids = [item["event_id"] for item in events]
    coaffiliation_ids = [item["event_id"] for item in coaffiliations]
    if len(event_ids) != len(set(event_ids)):
        raise InvariantError("ACN-01 produced duplicate collaboration event IDs")
    if len(coaffiliation_ids) != len(set(coaffiliation_ids)):
        raise InvariantError("ACN-01 produced duplicate coaffiliation event IDs")
    if any(
        pair["anchor_author_id"] == pair["external_author_id"]
        for event in events
        for pair in event["author_pairs"]
    ):
        raise InvariantError("ACN-01 collaboration contains an identical author pair")
    if any(
        event["anchor_institution"]["id"] not in anchor_ids
        or event["external_institution"]["id"] in anchor_ids
        for event in events
    ):
        raise InvariantError("ACN-01 produced an invalid anchor/external edge")

    status_counts = Counter(item["status"] for item in coverage)
    flag_counts = Counter(flag for item in coverage for flag in item["quality_flags"])
    unique_edges = {
        (item["anchor_institution"]["id"], item["external_institution"]["id"])
        for item in events
    }
    collaborating_external_ids = {
        item["external_institution"]["id"] for item in events
    }
    collaborating_institution_ids = {
        endpoint
        for item in events
        for endpoint in (
            item["anchor_institution"]["id"],
            item["external_institution"]["id"],
        )
    }
    observed_external_ids = {
        institution_id for institution_id in catalog if institution_id not in anchor_ids
    }
    institution_catalog = [
        {
            "schema_version": "collaboration-institution-catalog-entry/0.1",
            **catalog[institution_id],
            "roles": [
                "anchor" if institution_id in anchor_ids else "external"
            ],
            "observed_work_count": len(catalog_work_ids[institution_id]),
            "has_valid_collaboration_event": institution_id
            in collaborating_institution_ids,
        }
        for institution_id in sorted(catalog)
    ]
    parameters = {
        "schema_version": "actor-collaboration-normalization-parameters/0.1",
        "detector_stage": "ACN-01",
        "anchor_institution_ids": sorted(anchor_ids),
        "edge_policy": "distinct-authors-anchor-to-external/0.1",
        "work_counting": "one-event-per-work-and-institution-edge",
        "dual_affiliation_policy": "diagnostic-only",
        "author_pair_sample_limit": AUTHOR_PAIR_SAMPLE_LIMIT,
        "input_hash": sha256_json(works),
    }
    parameters["parameter_fingerprint"] = sha256_json(parameters)
    overwrite = rebuild
    parameters_path = store.write_json(
        "collaborations/acn01-normalization-parameters.json",
        parameters,
        overwrite=overwrite,
    )
    events_path = store.write_jsonl_gz(
        "collaborations/collaboration-events.jsonl.gz", events, overwrite=overwrite
    )
    coaffiliations_path = store.write_jsonl_gz(
        "collaborations/coaffiliation-events.jsonl.gz",
        coaffiliations,
        overwrite=overwrite,
    )
    coverage_path = store.write_jsonl_gz(
        "collaborations/collaboration-work-coverage.jsonl.gz",
        coverage,
        overwrite=overwrite,
    )
    catalog_path = store.write_json(
        "collaborations/institution-catalog.json",
        institution_catalog,
        overwrite=overwrite,
    )
    warnings = []
    if status_counts["ANCHOR_NOT_MATERIALIZED"]:
        warnings.append("PARTIAL_ANCHOR_MATERIALIZATION")
    if flag_counts["UNRESOLVED_AUTHOR_ID"]:
        warnings.append("UNRESOLVED_AUTHOR_IDENTITIES_PRESENT")
    if coaffiliations:
        warnings.append("DUAL_AFFILIATIONS_EXCLUDED_FROM_COLLABORATION_EDGES")
    quality = {
        "schema_version": "acn01-quality-report/0.1",
        "run_id": manifest.get("run_id", config.run_id),
        "normalizer_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest.get("manifest_id"),
        "input_work_count": len(works),
        "locally_materialized_work_count": len(works) - status_counts["ANCHOR_NOT_MATERIALIZED"],
        "anchor_materialization_rate": round(
            (len(works) - status_counts["ANCHOR_NOT_MATERIALIZED"]) / len(works), 12
        ),
        "work_with_external_institution_count": sum(bool(item["external_institution_ids"]) for item in coverage),
        "usable_work_count": status_counts["USABLE"],
        "collaboration_yield_rate": round(status_counts["USABLE"] / len(works), 12),
        "collaboration_event_count": len(events),
        "coaffiliation_event_count": len(coaffiliations),
        "unique_collaboration_edge_count": len(unique_edges),
        "unique_external_institution_count": len(observed_external_ids),
        "unique_collaborating_external_institution_count": len(collaborating_external_ids),
        "work_status_counts": dict(sorted(status_counts.items())),
        "quality_flag_counts": dict(sorted(flag_counts.items())),
        "all_events_resolve_to_input_works": all(
            item["work_id"] in set(work_ids) for item in events
        ),
        "all_edges_have_distinct_authors": True,
        "no_signal_emission": True,
        "warnings": warnings,
        "resumed": resume,
        "rebuilt": rebuild,
    }
    quality_path = store.write_json(
        "quality/acn01-quality-report.json", quality, overwrite=overwrite
    )
    result = {
        "schema_version": "acn01-result/0.1",
        "scope_mode": scope_mode,
        "normalizer_version": f"research-signal-instrument/{__version__}",
        "input_work_count": len(works),
        "usable_work_count": status_counts["USABLE"],
        "collaboration_event_count": len(events),
        "coaffiliation_event_count": len(coaffiliations),
        "unique_external_institution_count": len(observed_external_ids),
        "outputs": {
            "parameters": parameters_path.relative_to(store.root).as_posix(),
            "events": events_path.relative_to(store.root).as_posix(),
            "coaffiliations": coaffiliations_path.relative_to(store.root).as_posix(),
            "coverage": coverage_path.relative_to(store.root).as_posix(),
            "institution_catalog": catalog_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("acn01-result.json", result, overwrite=overwrite)
    return ACN01Result(
        scope_mode,
        store.root,
        len(works),
        status_counts["USABLE"],
        len(events),
        len(coaffiliations),
        len(observed_external_ids),
        quality_path,
    )
