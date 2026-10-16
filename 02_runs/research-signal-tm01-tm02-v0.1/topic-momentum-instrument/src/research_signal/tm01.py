from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import __version__
from .config import RunConfig
from .errors import InvariantError, OpenAlexError
from .models import short_openalex_id
from .storage import RunStore, sha256_json


class OpenAlexReader(Protocol):
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def iter_cursor_pages(self, path: str, params: dict[str, Any]): ...


@dataclass(frozen=True)
class TM01Result:
    run_dir: Path
    root_institution_id: str
    hierarchy_snapshot_path: Path
    manifest_paths: dict[str, Path]


def _institution_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    identifier = short_openalex_id(record.get("id"))
    if not identifier:
        raise OpenAlexError("institution record has no OpenAlex ID")
    return {
        "id": identifier,
        "display_name": record.get("display_name") or identifier,
        "ror": record.get("ror"),
        "type": record.get("type"),
        "country_code": record.get("country_code"),
        "lineage": [short_openalex_id(item) for item in record.get("lineage") or []],
        "works_count": record.get("works_count"),
        "cited_by_count": record.get("cited_by_count"),
    }


def resolve_ror(client: OpenAlexReader, ror: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = client.get_json(
        "/institutions",
        {"filter": f"ror:{ror}", "per-page": 2},
    )
    results = raw.get("results") or []
    if len(results) != 1:
        raise OpenAlexError(f"ROR {ror} resolved to {len(results)} OpenAlex institutions")
    return results[0], raw


def resolve_lineage(
    client: OpenAlexReader,
    root_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    raw_pages: list[dict[str, Any]] = []
    params = {"filter": f"lineage:{root_id}", "per-page": 200}
    for _, page in client.iter_cursor_pages("/institutions", params):
        raw_pages.append(page)
        for item in page.get("results") or []:
            snapshot = _institution_snapshot(item)
            records[snapshot["id"]] = snapshot
    if root_id not in records:
        raise InvariantError(f"lineage query did not include root institution {root_id}")
    return [records[key] for key in sorted(records)], raw_pages


def scope_filter(
    scope_mode: str,
    root_id: str,
    included_ids: list[str],
    *,
    lineage_materialized: bool,
) -> str:
    if scope_mode == "exact":
        return f"authorships.institutions.id:{root_id}"
    if scope_mode == "lineage" and not lineage_materialized:
        return f"authorships.institutions.lineage:{root_id}"
    if scope_mode in {"lineage", "curated_set"}:
        if not included_ids:
            raise InvariantError(f"{scope_mode} has no institution IDs")
        return "authorships.institutions.id:" + "|".join(included_ids)
    raise InvariantError(f"unsupported scope mode: {scope_mode}")


def _included_ids(
    scope_mode: str,
    root_id: str,
    descendants: list[dict[str, Any]],
    curated_ids: tuple[str, ...],
    excluded_ids: tuple[str, ...],
) -> list[str]:
    excluded = set(excluded_ids)
    if scope_mode == "exact":
        values = {root_id}
    elif scope_mode == "lineage":
        values = {item["id"] for item in descendants}
    else:
        values = set(curated_ids)
    values -= excluded
    if not values:
        raise InvariantError(f"scope {scope_mode} is empty after exclusions")
    return sorted(values)


def build_manifest(
    config: RunConfig,
    *,
    root: dict[str, Any],
    descendants: list[dict[str, Any]],
    hierarchy_fingerprint: str,
    scope_mode: str,
) -> dict[str, Any]:
    root_id = root["id"]
    included = _included_ids(
        scope_mode,
        root_id,
        descendants,
        config.universe.curated_institution_ids,
        config.universe.excluded_institution_ids,
    )
    scope_run_id = f"{config.run_id}-{scope_mode}"
    scope_universe_id = f"{config.universe.id}@{config.universe.version}:{scope_mode}"
    lineage_materialized = scope_mode == "lineage" and bool(
        config.universe.excluded_institution_ids
    )
    institution_filter = scope_filter(
        scope_mode,
        root_id,
        included,
        lineage_materialized=lineage_materialized,
    )
    types_filter = "type:" + "|".join(config.stream.types)
    classic_filter = ",".join(
        [
            institution_filter,
            f"from_publication_date:{config.collection.from_publication_date.isoformat()}",
            f"to_publication_date:{config.collection.to_publication_date.isoformat()}",
            types_filter,
        ]
    )
    observed_at = config.data_vintage.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "query-manifest/0.1",
        "manifest_id": scope_run_id,
        "run_id": scope_run_id,
        "source": "openalex",
        "source_mode": "api-live",
        "data_vintage": observed_at,
        "temporal_semantics": config.temporal_semantics,
        "corpus": config.stream.corpus,
        "universe": {
            "id": scope_universe_id,
            "base_id": config.universe.id,
            "label": config.universe.label,
            "version": config.universe.version,
            "root_ror": config.universe.root_ror,
            "root_openalex_id": root_id,
            "root_display_name": root["display_name"],
            "scope_mode": scope_mode,
            "scope_filter_strategy": (
                "materialized_institution_set" if lineage_materialized else scope_mode
            ),
            "included_institution_ids": included,
            "excluded_institution_ids": sorted(config.universe.excluded_institution_ids),
            "hierarchy_resolved_at": observed_at,
            "hierarchy_fingerprint": hierarchy_fingerprint,
        },
        "stream": {
            "id": config.stream.id,
            "types": list(config.stream.types),
            "has_abstract_filter": False,
            "counting_method": config.stream.counting_method,
        },
        "topic_axis": "primary_topic.id",
        "bucket_granularity": "month",
        "from_publication_date": config.collection.from_publication_date.isoformat(),
        "to_publication_date": config.collection.to_publication_date.isoformat(),
        "scope_filter": institution_filter,
        "classic_filter": classic_filter,
        "openalex_query_interpretation": {
            "status": "pending_first_execution",
            "oql": None,
            "oqo": None,
        },
        "client_version": f"research-signal-instrument/{__version__}",
        "detector_version": "topic-momentum/0.1",
        "secrets_embedded": False,
    }


def run_tm01(config: RunConfig, client: OpenAlexReader) -> TM01Result:
    run_dir = config.output_root / config.run_id
    store = RunStore(run_dir)
    resolved, raw_resolution = resolve_ror(client, config.universe.root_ror)
    root = _institution_snapshot(resolved)
    descendants, raw_lineage_pages = resolve_lineage(client, root["id"])

    for index, page in enumerate(raw_lineage_pages, 1):
        store.write_json_gz(f"tm01/raw/lineage/page-{index:04d}.json.gz", page)
    store.write_json_gz("tm01/raw/ror-resolution.json.gz", raw_resolution)

    fingerprint_payload = {
        "root_id": root["id"],
        "institutions": [item["id"] for item in descendants],
        "excluded": sorted(config.universe.excluded_institution_ids),
    }
    hierarchy_fingerprint = sha256_json(fingerprint_payload)
    hierarchy = {
        "schema_version": "institution-hierarchy-snapshot/0.1",
        "universe_id": config.universe.id,
        "universe_version": config.universe.version,
        "resolved_at": config.data_vintage.isoformat().replace("+00:00", "Z"),
        "root": root,
        "institutions": descendants,
        "excluded_institution_ids": sorted(config.universe.excluded_institution_ids),
        "fingerprint": hierarchy_fingerprint,
    }
    hierarchy_path = store.write_json("tm01/hierarchy-snapshot.json", hierarchy)

    manifest_paths: dict[str, Path] = {}
    for mode in config.universe.scope_modes:
        manifest = build_manifest(
            config,
            root=root,
            descendants=descendants,
            hierarchy_fingerprint=hierarchy_fingerprint,
            scope_mode=mode,
        )
        manifest_paths[mode] = store.write_json(f"{mode}/query-manifest.json", manifest)

    store.write_json(
        "tm01/result.json",
        {
            "schema_version": "tm01-result/0.1",
            "run_id": config.run_id,
            "root_institution_id": root["id"],
            "hierarchy_snapshot": str(hierarchy_path.relative_to(run_dir)),
            "manifests": {
                mode: str(path.relative_to(run_dir)) for mode, path in manifest_paths.items()
            },
        },
    )
    return TM01Result(run_dir, root["id"], hierarchy_path, manifest_paths)
