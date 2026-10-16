from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from . import __version__
from .config import RunConfig
from .dates import iter_month_buckets
from .errors import InvariantError
from .models import (
    normalize_topic_catalog_entry,
    normalize_work_observation,
    short_openalex_id,
)
from .storage import RunStore


class OpenAlexReader(Protocol):
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def iter_cursor_pages(
        self,
        path: str,
        params: dict[str, Any],
        *,
        start_cursor: str | None = "*",
        start_page_number: int = 1,
    ): ...


@dataclass(frozen=True)
class TM02Result:
    scope_mode: str
    scope_dir: Path
    bucket_count: int
    topic_row_count: int
    observation_count: int
    quality_report_path: Path


def _is_unknown_group(group: dict[str, Any]) -> bool:
    key = group.get("key")
    if key is None:
        return True
    normalized = str(key).strip().lower()
    return normalized in {"", "null", "none", "unknown"}


def _topic_id(group: dict[str, Any]) -> str:
    identifier = short_openalex_id(str(group.get("key") or ""))
    if not identifier:
        raise InvariantError(f"topic group has no key: {group}")
    return identifier


def _work_filter(manifest: dict[str, Any], start: date, end: date) -> str:
    types = "|".join(manifest["stream"]["types"])
    return ",".join(
        [
            manifest["scope_filter"],
            f"from_publication_date:{start.isoformat()}",
            f"to_publication_date:{end.isoformat()}",
            f"type:{types}",
        ]
    )


def _extract_x_query(page: dict[str, Any]) -> dict[str, Any]:
    x_query = (page.get("meta") or {}).get("x_query") or {}
    return {
        "oql": x_query.get("oql"),
        "oqo": x_query.get("oqo"),
    }


def _manifest_vintage(manifest: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(manifest["data_vintage"].replace("Z", "+00:00"))


def _validate_manifest_config(config: RunConfig, manifest: dict[str, Any]) -> None:
    checks = {
        "from_publication_date": config.collection.from_publication_date.isoformat(),
        "to_publication_date": config.collection.to_publication_date.isoformat(),
        "corpus": config.stream.corpus,
    }
    for field, expected in checks.items():
        if manifest.get(field) != expected:
            raise InvariantError(
                f"configuration changed since TM-01: {field}={expected!r}, manifest={manifest.get(field)!r}"
            )
    if manifest["stream"]["types"] != list(config.stream.types):
        raise InvariantError("configuration changed since TM-01: stream types differ")


def collect_monthly_census(
    config: RunConfig,
    client: OpenAlexReader,
    store: RunStore,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    snapshots: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    topic_labels: dict[str, str] = {}
    observed_at = manifest["data_vintage"]

    for start, end, is_complete in iter_month_buckets(
        config.collection.from_publication_date,
        config.collection.to_publication_date,
    ):
        bucket_id = start.strftime("%Y-%m")
        params = {
            "filter": _work_filter(manifest, start, end),
            "group_by": "primary_topic.id",
            "per-page": config.collection.group_page_size,
            "corpus": manifest["corpus"],
        }
        counts: Counter[str] = Counter()
        explicit_unknown = 0
        page_count = 0
        included_count: int | None = None
        first_x_query: dict[str, Any] = {"oql": None, "oqo": None}

        for page_number, page in client.iter_cursor_pages("/works", params):
            page_count = page_number
            store.write_json_gz(
                f"raw/tm02/census/{bucket_id}/page-{page_number:04d}.json.gz",
                page,
            )
            meta_count = int((page.get("meta") or {}).get("count") or 0)
            if included_count is None:
                included_count = meta_count
                first_x_query = _extract_x_query(page)
            elif included_count != meta_count:
                raise InvariantError(f"{bucket_id}: meta.count changed during pagination")
            for group in page.get("group_by") or []:
                count = int(group.get("count") or 0)
                if _is_unknown_group(group):
                    explicit_unknown += count
                    continue
                topic_id = _topic_id(group)
                counts[topic_id] += count
                label = group.get("key_display_name") or topic_id
                existing = topic_labels.get(topic_id)
                if existing and existing != label:
                    # Labels may evolve across buckets; identity remains the ID.
                    topic_labels[topic_id] = label
                else:
                    topic_labels.setdefault(topic_id, label)

        if included_count is None:
            raise InvariantError(f"{bucket_id}: no census page returned")
        classified_count = sum(counts.values())
        residual = included_count - classified_count - explicit_unknown
        if residual < 0:
            raise InvariantError(
                f"{bucket_id}: grouped sum exceeds meta.count ({classified_count}+{explicit_unknown}>{included_count})"
            )
        if explicit_unknown and residual:
            raise InvariantError(
                f"{bucket_id}: explicit unknown group still leaves residual count {residual}"
            )
        inferred_unknown = residual if not explicit_unknown else 0
        unclassified_count = explicit_unknown + inferred_unknown
        if config.collection.strict_group_totals and (
            classified_count + unclassified_count != included_count
        ):
            raise InvariantError(f"{bucket_id}: census total invariant failed")
        coverage = classified_count / included_count if included_count else 1.0

        summary = {
            "schema_version": "topic-bucket-summary/0.1",
            "run_id": manifest["run_id"],
            "query_manifest_ref": manifest["manifest_id"],
            "universe_id": manifest["universe"]["id"],
            "universe_version": manifest["universe"]["version"],
            "scope_mode": manifest["universe"]["scope_mode"],
            "stream_id": manifest["stream"]["id"],
            "bucket": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": "month",
                "is_complete": is_complete,
            },
            "included_works_count": included_count,
            "classified_works_count": classified_count,
            "unclassified_count": unclassified_count,
            "topic_coverage": round(coverage, 12),
            "group_count": len(counts),
            "pages_fetched": page_count,
            "pagination_complete": True,
            "unknown_count_source": (
                "explicit"
                if explicit_unknown
                else "inferred_residual"
                if inferred_unknown
                else "none"
            ),
            "openalex_query": first_x_query,
        }
        summaries.append(summary)

        for topic_id, topic_count in sorted(counts.items()):
            snapshots.append(
                {
                    "schema_version": "topic-bucket/0.1",
                    "run_id": manifest["run_id"],
                    "universe_id": manifest["universe"]["id"],
                    "universe_version": manifest["universe"]["version"],
                    "scope_mode": manifest["universe"]["scope_mode"],
                    "stream_id": manifest["stream"]["id"],
                    "bucket": summary["bucket"],
                    "topic": {
                        "id": topic_id,
                        "display_name": topic_labels[topic_id],
                        "topic_metadata_observed_at": observed_at,
                    },
                    "topic_count": topic_count,
                    "classified_works_count": classified_count,
                    "included_works_count": included_count,
                    "unclassified_count": unclassified_count,
                    "topic_share": round(topic_count / classified_count, 12)
                    if classified_count
                    else 0.0,
                    "topic_coverage": round(coverage, 12),
                    "query_manifest_ref": manifest["manifest_id"],
                }
            )

    return snapshots, summaries, topic_labels


def build_topic_catalog(
    config: RunConfig,
    client: OpenAlexReader,
    store: RunStore,
    topic_labels: dict[str, str],
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    catalog: list[dict[str, Any]] = []
    warnings: list[str] = []
    for topic_id, label in sorted(topic_labels.items()):
        raw_topic: dict[str, Any] | None = None
        if config.collection.enrich_topics:
            try:
                raw_topic = client.get_json(f"/topics/{topic_id}")
                store.write_json_gz(f"raw/tm02/topics/{topic_id}.json.gz", raw_topic)
            except Exception as exc:  # enrichment must not erase a valid census
                warnings.append(f"{topic_id}: topic enrichment failed: {exc}")
        catalog.append(
            normalize_topic_catalog_entry(topic_id, label, observed_at, raw_topic)
        )
    return catalog, warnings


def collect_work_observations(
    config: RunConfig,
    client: OpenAlexReader,
    store: RunStore,
    manifest: dict[str, Any],
    *,
    resume: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    params = {
        "filter": _work_filter(
            manifest,
            config.collection.from_publication_date,
            config.collection.to_publication_date,
        ),
        "select": (
            "id,doi,display_name,publication_date,type,primary_topic,authorships,"
            "cited_by_count,referenced_works,updated_date"
        ),
        "per-page": config.collection.work_page_size,
        "corpus": manifest["corpus"],
    }
    observations: list[dict[str, Any]] = []
    seen_work_ids: set[str] = set()
    expected_count: int | None = None
    included_ids = set(manifest["universe"]["included_institution_ids"])
    observed_at = _manifest_vintage(manifest)

    def consume_page(page: dict[str, Any]) -> None:
        nonlocal expected_count
        meta_count = int((page.get("meta") or {}).get("count") or 0)
        if expected_count is None:
            expected_count = meta_count
        elif expected_count != meta_count:
            raise InvariantError("work meta.count changed during pagination")
        for work in page.get("results") or []:
            work_id = short_openalex_id(work.get("id"))
            if not work_id:
                raise InvariantError("work page contains a record without ID")
            if work_id in seen_work_ids:
                raise InvariantError(f"duplicate work across cursor pages: {work_id}")
            seen_work_ids.add(work_id)
            observations.append(
                normalize_work_observation(
                    work,
                    observed_at=observed_at,
                    manifest_id=manifest["manifest_id"],
                    universe_id=manifest["universe"]["id"],
                    scope_mode=manifest["universe"]["scope_mode"],
                    included_institution_ids=included_ids,
                )
            )

    next_cursor: str | None = "*"
    next_page_number = 1
    if resume:
        raw_dir = store.path("raw/tm02/works")
        cached_pages = sorted(raw_dir.glob("page-*.json.gz")) if raw_dir.exists() else []
        for expected_page_number, path in enumerate(cached_pages, 1):
            if path.name != f"page-{expected_page_number:04d}.json.gz":
                raise InvariantError("cached work pages are not contiguous from page 1")
            page = store.read_json_gz(path.relative_to(store.root))
            consume_page(page)
            next_cursor = (page.get("meta") or {}).get("next_cursor")
            if next_cursor is None and expected_page_number != len(cached_pages):
                raise InvariantError("cached work page sequence continues after terminal cursor")
        next_page_number = len(cached_pages) + 1

    if next_cursor is not None:
        page_iterator = client.iter_cursor_pages(
            "/works",
            params,
            start_cursor=next_cursor,
            start_page_number=next_page_number,
        )
    else:
        page_iterator = iter(())

    for page_number, page in page_iterator:
        store.write_json_gz(f"raw/tm02/works/page-{page_number:04d}.json.gz", page)
        consume_page(page)
    if expected_count is None:
        raise InvariantError("no work page returned")
    if len(observations) != expected_count:
        raise InvariantError(
            f"work pagination incomplete: normalized {len(observations)} of {expected_count}"
        )
    return observations, expected_count


def _crosscheck(
    observations: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed_by_month: Counter[str] = Counter(
        item["publication_date"][:7] for item in observations
    )
    findings: list[dict[str, Any]] = []
    for summary in summaries:
        month = summary["bucket"]["start"][:7]
        census = summary["included_works_count"]
        observed = observed_by_month[month]
        findings.append(
            {
                "month": month,
                "census_count": census,
                "observation_count": observed,
                "matches": census == observed,
            }
        )
    return findings


def run_tm02(
    config: RunConfig,
    client: OpenAlexReader,
    run_dir: Path,
    scope_mode: str,
    *,
    resume: bool = False,
) -> TM02Result:
    if scope_mode not in config.universe.scope_modes:
        raise InvariantError(f"scope {scope_mode} is not configured")
    manifest_path = run_dir / scope_mode / "query-manifest.json"
    if not manifest_path.exists():
        raise InvariantError(f"TM-01 manifest not found: {manifest_path}")
    scope_store = RunStore(run_dir / scope_mode)
    manifest = scope_store.read_json("query-manifest.json")
    _validate_manifest_config(config, manifest)

    completed_result_path = scope_store.path("tm02-result.json")
    completed_quality_path = scope_store.path("quality/tm02-quality-report.json")
    if resume and completed_result_path.exists() and completed_quality_path.exists():
        completed = scope_store.read_json("tm02-result.json")
        return TM02Result(
            scope_mode=scope_mode,
            scope_dir=scope_store.root,
            bucket_count=completed["bucket_count"],
            topic_row_count=completed["topic_row_count"],
            observation_count=completed["observation_count"],
            quality_report_path=completed_quality_path,
        )

    census_paths = [
        scope_store.path("census/topic-buckets.jsonl.gz"),
        scope_store.path("census/bucket-summaries.json"),
        scope_store.path("topics/topic-catalog.json"),
    ]
    if resume and all(path.exists() for path in census_paths):
        snapshots = scope_store.read_jsonl_gz("census/topic-buckets.jsonl.gz")
        summaries = scope_store.read_json("census/bucket-summaries.json")
        catalog = scope_store.read_json("topics/topic-catalog.json")
        topic_labels = {item["id"]: item["display_name"] for item in catalog}
        topic_warnings = [
            f"{item['id']}: topic enrichment unavailable in cached catalog"
            for item in catalog
            if item.get("metadata_status") != "resolved"
        ]
    elif resume and any(path.exists() for path in census_paths):
        raise InvariantError(
            "partial census outputs cannot be resumed safely; use a new run.id"
        )
    else:
        snapshots, summaries, topic_labels = collect_monthly_census(
            config, client, scope_store, manifest
        )
        catalog, topic_warnings = build_topic_catalog(
            config,
            client,
            scope_store,
            topic_labels,
            _manifest_vintage(manifest),
        )
        scope_store.write_jsonl_gz("census/topic-buckets.jsonl.gz", snapshots)
        scope_store.write_json("census/bucket-summaries.json", summaries)
        scope_store.write_json("topics/topic-catalog.json", catalog)

    observations: list[dict[str, Any]] = []
    expected_work_count = 0
    if config.collection.include_work_observations:
        observations, expected_work_count = collect_work_observations(
            config, client, scope_store, manifest, resume=resume
        )
        scope_store.write_jsonl_gz(
            "observations/work-observations.jsonl.gz", observations
        )

    crosscheck = _crosscheck(observations, summaries) if observations else []
    mismatches = [item for item in crosscheck if not item["matches"]]
    if mismatches and config.collection.strict_work_crosscheck:
        raise InvariantError(f"work/census monthly crosscheck failed: {mismatches[:3]}")

    incomplete_buckets = [
        item["bucket"]["start"] for item in summaries if not item["bucket"]["is_complete"]
    ]
    unresolved_authorship_count = sum(
        1
        for observation in observations
        for authorship in observation["authorships"]
        if authorship["identity_status"] == "unresolved"
    )
    observations_with_unresolved_authors = sum(
        1 for observation in observations if "UNRESOLVED_AUTHOR_ID" in observation["quality_flags"]
    )
    unmaterialized_institution_match_count = sum(
        1
        for observation in observations
        if "INSTITUTION_MATCH_NOT_MATERIALIZED" in observation["quality_flags"]
    )
    quality = {
        "schema_version": "tm02-quality-report/0.1",
        "run_id": manifest["run_id"],
        "collector_version": f"research-signal-instrument/{__version__}",
        "resumed": resume,
        "scope_mode": scope_mode,
        "query_manifest_ref": manifest["manifest_id"],
        "bucket_count": len(summaries),
        "topic_row_count": len(snapshots),
        "unique_topic_count": len(topic_labels),
        "observation_count": len(observations),
        "expected_work_count": expected_work_count,
        "unresolved_authorship_count": unresolved_authorship_count,
        "observations_with_unresolved_authors": observations_with_unresolved_authors,
        "unmaterialized_institution_match_count": unmaterialized_institution_match_count,
        "all_group_pages_complete": all(item["pagination_complete"] for item in summaries),
        "all_group_totals_valid": all(
            item["classified_works_count"] + item["unclassified_count"]
            == item["included_works_count"]
            for item in summaries
        ),
        "has_abstract_filter_used": False,
        "corpus": manifest["corpus"],
        "incomplete_buckets": incomplete_buckets,
        "topic_enrichment_warnings": topic_warnings,
        "work_census_crosscheck": crosscheck,
        "work_census_mismatch_count": len(mismatches),
        "warnings": (
            (["LIVE_API_DRIFT_OR_NORMALIZATION_MISMATCH"] if mismatches else [])
            + (["UNRESOLVED_AUTHOR_IDENTITIES_PRESENT"] if unresolved_authorship_count else [])
            + (
                ["INSTITUTION_MATCH_NOT_MATERIALIZED_PRESENT"]
                if unmaterialized_institution_match_count
                else []
            )
        ),
    }
    quality_path = scope_store.write_json("quality/tm02-quality-report.json", quality)
    scope_store.write_json(
        "tm02-result.json",
        {
            "schema_version": "tm02-result/0.1",
            "scope_mode": scope_mode,
            "collector_version": f"research-signal-instrument/{__version__}",
            "resumed": resume,
            "bucket_count": len(summaries),
            "topic_row_count": len(snapshots),
            "observation_count": len(observations),
            "outputs": {
                "topic_buckets": "census/topic-buckets.jsonl.gz",
                "bucket_summaries": "census/bucket-summaries.json",
                "topic_catalog": "topics/topic-catalog.json",
                "work_observations": (
                    "observations/work-observations.jsonl.gz"
                    if observations
                    else None
                ),
                "quality_report": "quality/tm02-quality-report.json",
            },
        },
    )
    return TM02Result(
        scope_mode=scope_mode,
        scope_dir=scope_store.root,
        bucket_count=len(summaries),
        topic_row_count=len(snapshots),
        observation_count=len(observations),
        quality_report_path=quality_path,
    )
