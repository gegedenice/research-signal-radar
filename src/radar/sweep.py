"""One complete harvest of the universe -> an immutable dated snapshot (specs/03 §2, §4)."""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import openalex_api_client
from openalex_api_client import OpenAlex
from openalex_api_client.tidy import LIST_AUTHORS_CAP, works_tables, write_parquet

from . import __version__
from .config import Config
from .diff import diff_sweeps, previous_sweep
from .tables import add_radar_columns, quality_report

logger = logging.getLogger(__name__)

SNAPSHOT_TABLES = ["works", "authorships", "topics", "counts_by_year", "sdgs"]


def sweeps_dir(config: Config) -> Path:
    return config.data_dir / "sweeps"


def new_sweep_id(root: Path, observed_at: datetime) -> str:
    """`YYYY-MM-DD`, then `-2`, `-3`… if a sweep with that id already exists."""
    base = observed_at.strftime("%Y-%m-%d")
    sweep_id, n = base, 1
    while (root / sweep_id).exists():
        n += 1
        sweep_id = f"{base}-{n}"
    return sweep_id


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _may_be_truncated(work: dict) -> bool:
    if work.get("is_authors_truncated"):
        return True
    return len(work.get("authorships") or []) >= LIST_AUTHORS_CAP


def harvest(oa: OpenAlex, config: Config, sweep_id: str, refetched: set):
    """Yield raw works; re-read the full author list of works whose list may be cut (free gets)."""
    works = oa.iter(
        "works",
        filter=config.universe.filter,
        select=config.sweep.select,
        per_page=100,
        checkpoint=f"sweep-{sweep_id}",
    )
    for n, work in enumerate(works, start=1):
        if config.sweep.refetch_truncated_authors and _may_be_truncated(work):
            full = oa.get("works", work["id"], select="id,authorships")
            work = {**work, "authorships": full.get("authorships") or work.get("authorships")}
            refetched.add(openalex_api_client.short_id(work["id"]))
        if n % 5000 == 0:
            logger.info("harvested %d works (%d author lists re-read)", n, len(refetched))
        yield work


def run_sweep(config: Config, oa: OpenAlex | None = None, now: datetime | None = None) -> Path:
    observed_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    root = sweeps_dir(config)
    root.mkdir(parents=True, exist_ok=True)
    sweep_id = new_sweep_id(root, observed_at)
    oa = oa or OpenAlex(cache_dir=config.data_dir / "cache" / "openalex")

    expected = oa.count("works", filter=config.universe.filter)
    logger.info("sweep %s: %d works expected", sweep_id, expected)

    refetched: set[str] = set()
    tables = works_tables(harvest(oa, config, sweep_id, refetched), root_institution=config.universe.root_institution)
    # A re-read author list is complete, whatever its length.
    works = tables["works"]
    works.loc[works["work_id"].isin(refetched), "authors_truncated"] = False
    tables = add_radar_columns(tables, config)

    harvested = len(tables["works"])
    if harvested != expected:
        logger.warning("harvested %d works, expected %d (%.2f%%)", harvested, expected,
                       100 * (harvested - expected) / expected if expected else 0)

    # Written to a partial directory first: an interrupted sweep leaves no snapshot, so re-running
    # the same day reuses the same sweep_id and the client's checkpoint replays the cached pages.
    partial = root / f".{sweep_id}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    write_parquet({name: tables[name] for name in SNAPSHOT_TABLES}, partial)
    manifest = {
        "sweep_id": sweep_id,
        "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe": {
            "id": config.universe.id,
            "label": config.universe.label,
            "filter": config.universe.filter,
            "root_institution": config.universe.root_institution,
        },
        "expected_count": expected,
        "harvested_count": harvested,
        "select": list(config.sweep.select),
        "client_version": openalex_api_client.__version__,
        "radar_version": __version__,
        "config_hash": config.config_hash,
        "openalex_credits_used": oa.usage.credits_used_total,
    }
    write_json(partial / "manifest.json", manifest)
    write_json(partial / "quality.json", quality_report(tables, config, authors_refetched=len(refetched)))
    final = root / sweep_id
    partial.rename(final)
    logger.info("sweep %s written: %d works", sweep_id, harvested)

    previous = previous_sweep(root, sweep_id)
    if previous is not None:
        write_json(final / "diff.json", diff_sweeps(previous, final))
        logger.info("diff against %s written", previous.name)
    return final
