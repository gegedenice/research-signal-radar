from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote

from . import __version__
from .config import RunConfig
from .dates import add_months
from .errors import InvariantError, OpenCitationsError
from .storage import RunStore, sha256_json


_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_PID_RE = re.compile(r"\b(doi|pmid|omid):([^\s;]+)", re.IGNORECASE)
_OCI_RE = re.compile(r"\b([0-9]+-[0-9]+)\b")
_PARTIAL_DATE_RE = re.compile(
    r"(?<![0-9])([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?)?(?![0-9])"
)


class OpenCitationsReader(Protocol):
    def citations(self, doi: str) -> list[dict[str, Any]]: ...
    def citation_count(self, doi: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CA01Result:
    scope_mode: str
    scope_dir: Path
    input_work_count: int
    eligible_work_count: int
    collected_work_count: int
    citation_event_count: int
    quality_report_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unquote(value.strip())
    normalized = _DOI_PREFIX_RE.sub("", normalized).strip().lower()
    if not normalized.startswith("10.") or "/" not in normalized:
        return None
    if any(character.isspace() for character in normalized):
        return None
    return normalized


def _first_pid(value: Any) -> tuple[str | None, list[str]]:
    matches = [
        f"{kind.lower()}:{identifier.rstrip('.,')}"
        for kind, identifier in _PID_RE.findall(str(value or ""))
    ]
    unique = list(dict.fromkeys(matches))
    preferred = next((item for item in unique if item.startswith("doi:")), None)
    return preferred or (unique[0] if unique else None), unique


def _status(value: Any) -> str:
    lowered = str(value or "").lower()
    has_yes = bool(re.search(r"\byes\b", lowered))
    has_no = bool(re.search(r"\bno\b", lowered))
    if has_yes and has_no:
        return "mixed"
    if has_yes:
        return "yes"
    if has_no:
        return "no"
    return "unknown"


def _creation_time(value: Any) -> dict[str, Any]:
    """Preserve OpenCitations date precision without inventing a day or month."""
    parsed: list[tuple[int, int | None, int | None, str]] = []
    for match in _PARTIAL_DATE_RE.finditer(str(value or "")):
        year = int(match.group(1))
        month = int(match.group(2)) if match.group(2) else None
        day = int(match.group(3)) if match.group(3) else None
        try:
            if not 1 <= year <= 9999:
                continue
            if day is not None:
                canonical = date(year, month or 0, day).isoformat()
            elif month is not None:
                if not 1 <= month <= 12:
                    continue
                canonical = f"{year:04d}-{month:02d}"
            else:
                canonical = f"{year:04d}"
        except ValueError:
            continue
        item = (year, month, day, canonical)
        if item not in parsed:
            parsed.append(item)

    values = [item[3] for item in parsed]
    if not parsed:
        return {
            "creation_date": None,
            "creation_month": None,
            "creation_year": None,
            "creation_precision": "MISSING",
            "creation_values": [],
            "precision_reduced_by_conflict": False,
        }

    years = {item[0] for item in parsed}
    if len(years) != 1:
        return {
            "creation_date": None,
            "creation_month": None,
            "creation_year": None,
            "creation_precision": "CONFLICTING",
            "creation_values": values,
            "precision_reduced_by_conflict": True,
        }

    year = next(iter(years))
    months = {item[1] for item in parsed if item[1] is not None}
    if len(months) > 1:
        return {
            "creation_date": None,
            "creation_month": None,
            "creation_year": f"{year:04d}",
            "creation_precision": "YEAR",
            "creation_values": values,
            "precision_reduced_by_conflict": True,
        }
    if not months:
        return {
            "creation_date": None,
            "creation_month": None,
            "creation_year": f"{year:04d}",
            "creation_precision": "YEAR",
            "creation_values": values,
            "precision_reduced_by_conflict": False,
        }

    month = next(iter(months))
    full_dates = {item[3] for item in parsed if item[2] is not None}
    if len(full_dates) == 1:
        return {
            "creation_date": next(iter(full_dates)),
            "creation_month": f"{year:04d}-{month:02d}",
            "creation_year": f"{year:04d}",
            "creation_precision": "DAY",
            "creation_values": values,
            "precision_reduced_by_conflict": False,
        }
    return {
        "creation_date": None,
        "creation_month": f"{year:04d}-{month:02d}",
        "creation_year": f"{year:04d}",
        "creation_precision": "MONTH",
        "creation_values": values,
        "precision_reduced_by_conflict": len(full_dates) > 1,
    }


def _oci(value: Any) -> str | None:
    match = _OCI_RE.search(str(value or ""))
    return match.group(1) if match else None


def _raw_key(doi: str) -> str:
    return hashlib.sha256(doi.encode("utf-8")).hexdigest()[:24]


def _event_id(row: dict[str, Any], cited_work_id: str, ordinal: int) -> str:
    oci = _oci(row.get("oci"))
    if oci:
        return f"oc:oci:{oci}"
    fallback = sha256_json(
        {
            "cited_work_id": cited_work_id,
            "citing": row.get("citing"),
            "cited": row.get("cited"),
            "creation": row.get("creation"),
            "ordinal": ordinal,
        }
    ).split(":", 1)[1][:32]
    return f"oc:synthetic:{fallback}"


def normalize_citation_event(
    row: dict[str, Any],
    *,
    cited_work_id: str,
    cited_doi: str,
    observed_at: str,
    raw_response_ref: str,
    ordinal: int,
) -> dict[str, Any]:
    citing_pid, citing_pids = _first_pid(row.get("citing"))
    creation = _creation_time(row.get("creation"))
    quality_flags = []
    if citing_pid is None:
        quality_flags.append("MISSING_CITING_PID")
    if creation["creation_precision"] == "MISSING":
        quality_flags.append("MISSING_CREATION_VALUE")
    elif creation["creation_precision"] == "CONFLICTING":
        quality_flags.append("CONFLICTING_CREATION_VALUES")
    elif creation["creation_precision"] == "YEAR":
        quality_flags.append("PARTIAL_CREATION_YEAR")
    elif creation["creation_precision"] == "MONTH":
        quality_flags.append("PARTIAL_CREATION_MONTH")
    if creation["precision_reduced_by_conflict"]:
        quality_flags.append("CREATION_PRECISION_REDUCED_BY_CONFLICT")
    if creation["creation_date"] and creation["creation_date"] > observed_at[:10]:
        quality_flags.append("CREATION_AFTER_OBSERVATION")
    elif creation["creation_month"] and creation["creation_month"] > observed_at[:7]:
        quality_flags.append("CREATION_AFTER_OBSERVATION")
    elif creation["creation_year"] and creation["creation_year"] > observed_at[:4]:
        quality_flags.append("CREATION_AFTER_OBSERVATION")
    oci = _oci(row.get("oci"))
    if oci is None:
        quality_flags.append("MISSING_OCI")
    return {
        "schema_version": "citation-event-observation/0.2",
        "event_id": _event_id(row, cited_work_id, ordinal),
        "cited_work_id": cited_work_id,
        "cited_doi": cited_doi,
        "citing_pid": citing_pid,
        "citing_pids": citing_pids,
        "creation_date": creation["creation_date"],
        "creation_month": creation["creation_month"],
        "creation_year": creation["creation_year"],
        "creation_precision": creation["creation_precision"],
        "creation_values": creation["creation_values"],
        "observed_at": observed_at,
        "timespan": row.get("timespan"),
        "author_self_citation": _status(row.get("author_sc")),
        "journal_self_citation": _status(row.get("journal_sc")),
        "quality_flags": quality_flags,
        "source": {
            "provider": "OpenCitations",
            "oci": oci,
            "raw_response_ref": raw_response_ref,
        },
    }


def _reported_count(payload: list[dict[str, Any]], doi: str) -> int:
    if not payload:
        return 0
    if len(payload) != 1 or "count" not in payload[0]:
        raise OpenCitationsError(f"{doi}: invalid citation-count response")
    try:
        count = int(payload[0]["count"])
    except (TypeError, ValueError) as exc:
        raise OpenCitationsError(f"{doi}: invalid citation-count value") from exc
    if count < 0:
        raise OpenCitationsError(f"{doi}: negative citation-count value")
    return count


def _eligibility(
    observations: list[dict[str, Any]], latest_publication_date: date
) -> tuple[list[tuple[dict[str, Any], str]], list[dict[str, Any]], list[str]]:
    candidates: list[tuple[dict[str, Any], str]] = []
    coverage: list[dict[str, Any]] = []
    doi_to_work_ids: dict[str, list[str]] = defaultdict(list)
    normalized_by_work: dict[str, str | None] = {}
    for work in observations:
        doi = normalize_doi(work.get("doi"))
        normalized_by_work[work["work_id"]] = doi
        if doi:
            doi_to_work_ids[doi].append(work["work_id"])
    collisions = sorted(doi for doi, work_ids in doi_to_work_ids.items() if len(work_ids) > 1)

    for work in observations:
        doi = normalized_by_work[work["work_id"]]
        if not work.get("doi"):
            status = "NO_DOI"
        elif doi is None:
            status = "INVALID_DOI"
        elif doi in collisions:
            status = "DUPLICATE_DOI_MAPPING"
        elif date.fromisoformat(work["publication_date"]) > latest_publication_date:
            status = "TOO_RECENT"
        else:
            status = "ELIGIBLE"
            candidates.append((work, doi))
        coverage.append(
            {
                "schema_version": "citation-work-coverage/0.1",
                "work_id": work["work_id"],
                "doi": doi,
                "publication_date": work["publication_date"],
                "eligibility_status": status,
                "openalex_cited_by_count": work["citation_snapshot"][
                    "cited_by_count"
                ],
                "opencitations_citation_count": None,
                "opencitations_event_row_count": None,
                "dated_event_count": None,
                "monthly_usable_event_count": None,
                "year_only_event_count": None,
                "missing_or_conflicting_event_count": None,
                "cross_source_ratio": None,
                "count_matches_event_rows": None,
                "raw_response_refs": None,
                "quality_flags": [],
            }
        )
    return candidates, coverage, collisions


def run_ca01(
    config: RunConfig,
    client: OpenCitationsReader,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
    rebuild: bool = False,
) -> CA01Result:
    if resume and rebuild:
        raise InvariantError("CA-01 --resume and --rebuild are mutually exclusive")
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    store = RunStore(run_dir / scope_mode)
    required = [
        "query-manifest.json",
        "tm02-result.json",
        "quality/tm02-quality-report.json",
        "observations/work-observations.jsonl.gz",
    ]
    missing = [item for item in required if not store.path(item).exists()]
    if missing:
        raise InvariantError(f"CA-01 requires completed TM-02: {missing}")

    result_path = store.path("ca01-result.json")
    quality_path = store.path("quality/ca01-quality-report.json")
    if resume and result_path.exists() and quality_path.exists():
        completed = store.read_json("ca01-result.json")
        if completed.get("collector_version") != f"research-signal-instrument/{__version__}":
            raise InvariantError(
                "CA-01 result was produced by another collector version; use a new run.id"
            )
        return CA01Result(
            scope_mode=scope_mode,
            scope_dir=store.root,
            input_work_count=completed["input_work_count"],
            eligible_work_count=completed["eligible_work_count"],
            collected_work_count=completed["collected_work_count"],
            citation_event_count=completed["citation_event_count"],
            quality_report_path=quality_path,
        )
    if result_path.exists() and not rebuild:
        raise InvariantError("CA-01 result already exists; use --resume or --rebuild")

    source_manifest = store.read_json("query-manifest.json")
    observations = store.read_jsonl_gz("observations/work-observations.jsonl.gz")
    if not observations:
        raise InvariantError("CA-01 received no WorkObservation")
    if any(item.get("schema_version") != "work-observation/0.1" for item in observations):
        raise InvariantError("CA-01 requires work-observation/0.1 inputs")
    if any(
        item.get("source", {}).get("manifest_id") != source_manifest["manifest_id"]
        for item in observations
    ):
        raise InvariantError("CA-01 WorkObservations differ from the query manifest")

    latest_publication_date = add_months(
        config.collection.to_publication_date, -12
    )
    candidates, coverage, collisions = _eligibility(
        observations, latest_publication_date
    )
    eligible_dois = [doi for _, doi in candidates]
    manifest_stable = {
        "schema_version": "ca01-query-manifest/0.1",
        "run_id": source_manifest["run_id"],
        "scope_mode": scope_mode,
        "input_query_manifest_ref": source_manifest["manifest_id"],
        "input_work_observations_hash": sha256_json(observations),
        "eligible_doi_hash": sha256_json(eligible_dois),
        "api": {
            "provider": "OpenCitations",
            "base_url": config.opencitations.base_url.rstrip("/"),
            "citations_route": "/citations/{id}",
            "citation_count_route": "/citation-count/{id}",
            "api_key_env": config.opencitations.api_key_env,
            "requests_per_minute": config.opencitations.requests_per_minute,
        },
        "eligibility": {
            "minimum_age_months": 12,
            "latest_publication_date": latest_publication_date.isoformat(),
            "input_work_count": len(observations),
            "eligible_work_count": len(candidates),
        },
    }
    ca_manifest_path = "citations/ca01-query-manifest.json"
    if store.path(ca_manifest_path).exists():
        if not (resume or rebuild):
            raise InvariantError("CA-01 partial collection exists; use --resume")
        existing_manifest = store.read_json(ca_manifest_path)
        for key, expected in manifest_stable.items():
            if existing_manifest.get(key) != expected:
                raise InvariantError(
                    f"CA-01 resume configuration/input changed: {key}"
                )
        ca_manifest = existing_manifest
    else:
        ca_manifest = dict(manifest_stable)
        ca_manifest["manifest_id"] = (
            f"ca01:{source_manifest['run_id']}:{scope_mode}:opencitations-v2"
        )
        ca_manifest["collection_started_at"] = _now()
        store.write_json(ca_manifest_path, ca_manifest)

    coverage_by_work = {item["work_id"]: item for item in coverage}
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    api_request_count = 0
    cached_response_count = 0
    duplicate_event_count = 0
    count_mismatch_count = 0
    for work, doi in candidates:
        key = _raw_key(doi)
        citations_ref = f"raw/ca01/opencitations/{key}-citations.json.gz"
        count_ref = f"raw/ca01/opencitations/{key}-citation-count.json.gz"
        if store.path(citations_ref).exists():
            citations_raw = store.read_json_gz(citations_ref)
            cached_response_count += 1
        else:
            if rebuild:
                raise InvariantError(
                    f"CA-01 offline rebuild requires cached response: {citations_ref}"
                )
            fetched_at = _now()
            payload = client.citations(doi)
            api_request_count += 1
            citations_raw = {
                "schema_version": "opencitations-raw-response/0.1",
                "operation": "citations",
                "doi": doi,
                "fetched_at": fetched_at,
                "response": payload,
            }
            store.write_json_gz(citations_ref, citations_raw)
        if store.path(count_ref).exists():
            count_raw = store.read_json_gz(count_ref)
            cached_response_count += 1
        else:
            if rebuild:
                raise InvariantError(
                    f"CA-01 offline rebuild requires cached response: {count_ref}"
                )
            fetched_at = _now()
            payload = client.citation_count(doi)
            api_request_count += 1
            count_raw = {
                "schema_version": "opencitations-raw-response/0.1",
                "operation": "citation-count",
                "doi": doi,
                "fetched_at": fetched_at,
                "response": payload,
            }
            store.write_json_gz(count_ref, count_raw)

        citation_rows = citations_raw.get("response")
        count_rows = count_raw.get("response")
        if not isinstance(citation_rows, list) or not isinstance(count_rows, list):
            raise InvariantError(f"{doi}: cached OpenCitations response is invalid")
        reported_count = _reported_count(count_rows, doi)
        row_count = len(citation_rows)
        count_matches = reported_count == row_count
        if not count_matches:
            count_mismatch_count += 1
        precision_counts: Counter[str] = Counter()
        for ordinal, row in enumerate(citation_rows, 1):
            event = normalize_citation_event(
                row,
                cited_work_id=work["work_id"],
                cited_doi=doi,
                observed_at=citations_raw["fetched_at"],
                raw_response_ref=citations_ref,
                ordinal=ordinal,
            )
            precision_counts[event["creation_precision"]] += 1
            if event["event_id"] in seen_event_ids:
                duplicate_event_count += 1
                continue
            seen_event_ids.add(event["event_id"])
            events.append(event)

        item = coverage_by_work[work["work_id"]]
        openalex_count = item["openalex_cited_by_count"]
        item.update(
            {
                "eligibility_status": "COLLECTED",
                "opencitations_citation_count": reported_count,
                "opencitations_event_row_count": row_count,
                "dated_event_count": precision_counts["DAY"],
                "monthly_usable_event_count": (
                    precision_counts["DAY"] + precision_counts["MONTH"]
                ),
                "year_only_event_count": precision_counts["YEAR"],
                "missing_or_conflicting_event_count": (
                    precision_counts["MISSING"] + precision_counts["CONFLICTING"]
                ),
                "cross_source_ratio": (
                    round(reported_count / openalex_count, 12)
                    if openalex_count
                    else None
                ),
                "count_matches_event_rows": count_matches,
                "raw_response_refs": {
                    "citations": citations_ref,
                    "citation_count": count_ref,
                },
                "quality_flags": (
                    [] if count_matches else ["OPENCITATIONS_COUNT_ROW_MISMATCH"]
                ),
            }
        )

    events.sort(
        key=lambda item: (
            item["cited_work_id"],
            item["creation_month"] or "9999-12",
            item["creation_date"] or "9999-12-31",
            item["event_id"],
        )
    )
    coverage.sort(key=lambda item: item["work_id"])
    events_path = store.write_jsonl_gz(
        "citations/citation-events.jsonl.gz", events, overwrite=resume or rebuild
    )
    coverage_path = store.write_jsonl_gz(
        "citations/work-citation-coverage.jsonl.gz",
        coverage,
        overwrite=resume or rebuild,
    )
    status_counts = Counter(item["eligibility_status"] for item in coverage)
    creation_precision_counts = Counter(
        item["creation_precision"] for item in events
    )
    monthly_usable_creation_count = (
        creation_precision_counts["DAY"] + creation_precision_counts["MONTH"]
    )
    missing_creation_count = creation_precision_counts["MISSING"]
    conflicting_creation_count = creation_precision_counts["CONFLICTING"]
    missing_citing_pid_count = sum(
        "MISSING_CITING_PID" in item["quality_flags"] for item in events
    )
    collected_work_count = status_counts["COLLECTED"]
    warnings = []
    if count_mismatch_count:
        warnings.append("OPENCITATIONS_COUNT_ROW_MISMATCH_PRESENT")
    if creation_precision_counts["YEAR"] or creation_precision_counts["MONTH"]:
        warnings.append("PARTIAL_CREATION_DATES_PRESENT")
    if missing_creation_count:
        warnings.append("UNDATED_CITATION_EVENTS_PRESENT")
    if conflicting_creation_count:
        warnings.append("CONFLICTING_CREATION_VALUES_PRESENT")
    if missing_citing_pid_count:
        warnings.append("UNRESOLVED_CITING_PIDS_PRESENT")
    if collisions:
        warnings.append("DUPLICATE_DOI_MAPPINGS_EXCLUDED")
    quality = {
        "schema_version": "ca01-quality-report/0.2",
        "run_id": source_manifest["run_id"],
        "collector_version": f"research-signal-instrument/{__version__}",
        "scope_mode": scope_mode,
        "query_manifest_ref": ca_manifest["manifest_id"],
        "resumed": resume,
        "rebuilt": rebuild,
        "input_work_count": len(observations),
        "eligibility_status_counts": dict(sorted(status_counts.items())),
        "eligible_work_count": len(candidates),
        "collected_work_count": collected_work_count,
        "citation_event_count": len(events),
        "creation_precision_counts": {
            key: creation_precision_counts[key]
            for key in ["DAY", "MONTH", "YEAR", "MISSING", "CONFLICTING"]
        },
        "monthly_usable_creation_count": monthly_usable_creation_count,
        "monthly_usable_creation_ratio": (
            round(monthly_usable_creation_count / len(events), 12)
            if events
            else None
        ),
        "missing_creation_value_count": missing_creation_count,
        "conflicting_creation_value_count": conflicting_creation_count,
        "missing_citing_pid_count": missing_citing_pid_count,
        "duplicate_event_count": duplicate_event_count,
        "duplicate_doi_mapping_count": len(collisions),
        "count_row_mismatch_count": count_mismatch_count,
        "api_request_count_this_execution": api_request_count,
        "cached_response_count_this_execution": cached_response_count,
        "all_eligible_works_collected": collected_work_count == len(candidates),
        "warnings": warnings,
    }
    quality_path = store.write_json(
        "quality/ca01-quality-report.json", quality, overwrite=resume or rebuild
    )
    result = {
        "schema_version": "ca01-result/0.2",
        "scope_mode": scope_mode,
        "collector_version": f"research-signal-instrument/{__version__}",
        "input_work_count": len(observations),
        "eligible_work_count": len(candidates),
        "collected_work_count": collected_work_count,
        "citation_event_count": len(events),
        "monthly_usable_creation_count": monthly_usable_creation_count,
        "monthly_usable_creation_ratio": quality["monthly_usable_creation_ratio"],
        "outputs": {
            "query_manifest": ca_manifest_path,
            "citation_events": events_path.relative_to(store.root).as_posix(),
            "work_coverage": coverage_path.relative_to(store.root).as_posix(),
            "quality_report": quality_path.relative_to(store.root).as_posix(),
        },
    }
    store.write_json("ca01-result.json", result, overwrite=resume or rebuild)
    return CA01Result(
        scope_mode=scope_mode,
        scope_dir=store.root,
        input_work_count=len(observations),
        eligible_work_count=len(candidates),
        collected_work_count=collected_work_count,
        citation_event_count=len(events),
        quality_report_path=quality_path,
    )
