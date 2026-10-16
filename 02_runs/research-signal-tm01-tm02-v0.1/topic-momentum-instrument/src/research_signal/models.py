from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import InvariantError


def short_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1]


def nested_ref(value: dict[str, Any] | None) -> dict[str, str] | None:
    if not value:
        return None
    identifier = short_openalex_id(value.get("id"))
    label = value.get("display_name") or value.get("label")
    if not identifier:
        return None
    return {"id": identifier, "display_name": label or identifier}


def normalize_institution(value: dict[str, Any]) -> dict[str, Any]:
    identifier = short_openalex_id(value.get("id"))
    if not identifier:
        raise InvariantError("authorship institution has no OpenAlex ID")
    return {
        "id": identifier,
        "ror": value.get("ror"),
        "label": value.get("display_name") or identifier,
    }


def normalize_authorship(value: dict[str, Any]) -> dict[str, Any]:
    author = value.get("author") or {}
    author_id = short_openalex_id(author.get("id"))
    return {
        "author_id": author_id,
        "author_label": author.get("display_name") or author_id or "[unresolved author]",
        "identity_status": "resolved" if author_id else "unresolved",
        "position": value.get("author_position") or "unknown",
        "institutions": [normalize_institution(item) for item in value.get("institutions") or []],
    }


def normalize_work_observation(
    work: dict[str, Any],
    *,
    observed_at: datetime,
    manifest_id: str,
    universe_id: str,
    scope_mode: str,
    included_institution_ids: set[str],
) -> dict[str, Any]:
    work_id = short_openalex_id(work.get("id"))
    if not work_id:
        raise InvariantError("OpenAlex work has no ID")
    publication_date = work.get("publication_date")
    if not publication_date:
        raise InvariantError(f"{work_id}: missing publication_date")

    authorships = [normalize_authorship(item) for item in work.get("authorships") or []]
    observed_institution_ids = {
        institution["id"]
        for authorship in authorships
        for institution in authorship["institutions"]
    }
    matched = sorted(observed_institution_ids & included_institution_ids)
    match_status = "verified_local" if matched else "asserted_by_source_filter"

    primary_topic = work.get("primary_topic")
    topic = None
    if primary_topic and primary_topic.get("id"):
        topic = {
            "id": short_openalex_id(primary_topic["id"]),
            "label": primary_topic.get("display_name")
            or short_openalex_id(primary_topic["id"]),
        }

    observed_iso = observed_at.isoformat().replace("+00:00", "Z")
    source_updated_at = work.get("updated_date")
    if source_updated_at:
        parsed_updated_at = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
        if parsed_updated_at.tzinfo is None:
            parsed_updated_at = parsed_updated_at.replace(tzinfo=timezone.utc)
        source_updated_at = parsed_updated_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    quality_flags = {
        "UNRESOLVED_AUTHOR_ID"
        for authorship in authorships
        if authorship["identity_status"] == "unresolved"
    }
    if not matched:
        quality_flags.add("INSTITUTION_MATCH_NOT_MATERIALIZED")
    return {
        "schema_version": "work-observation/0.1",
        "observation_id": f"obs-{manifest_id}-{work_id}-{observed_at.date().isoformat()}",
        "work_id": work_id,
        "observed_at": observed_iso,
        "publication_date": publication_date,
        "work_type": work.get("type") or "unknown",
        "title": work.get("display_name") or work.get("title") or work_id,
        "doi": work.get("doi"),
        "primary_topic": topic,
        "authorships": authorships,
        "citation_snapshot": {
            "cited_by_count": int(work.get("cited_by_count") or 0),
            "provider": "OpenAlex",
        },
        "referenced_work_ids": [
            short_openalex_id(item) for item in work.get("referenced_works") or [] if item
        ],
        "source_updated_at": source_updated_at,
        "quality_flags": sorted(quality_flags),
        "inclusion": {
            "universe_id": universe_id,
            "reason": (
                f"OpenAlex authorship matched versioned {scope_mode} institution scope"
                if matched
                else f"OpenAlex server-side {scope_mode} filter included work; "
                "included institution was not materialized in returned authorships"
            ),
            "match_status": match_status,
            "matched_entity_ids": matched,
        },
        "source": {
            "provider": "OpenAlex",
            "record_id": work_id,
            "manifest_id": manifest_id,
        },
    }


def normalize_topic_catalog_entry(
    topic_id: str,
    display_name: str,
    observed_at: datetime,
    raw_topic: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_topic = raw_topic or {}
    return {
        "schema_version": "topic-catalog-entry/0.1",
        "id": topic_id,
        "display_name": raw_topic.get("display_name") or display_name or topic_id,
        "description": raw_topic.get("description"),
        "subfield": nested_ref(raw_topic.get("subfield")),
        "field": nested_ref(raw_topic.get("field")),
        "domain": nested_ref(raw_topic.get("domain")),
        "created_date": raw_topic.get("created_date"),
        "updated_date": raw_topic.get("updated_date"),
        "metadata_observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "metadata_status": "resolved" if raw_topic else "group_only",
    }
