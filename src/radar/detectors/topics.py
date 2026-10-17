"""Topics detector: share of works by topic or subfield (specs/04 §4.1, with the counting amendment)."""

import pandas as pd

from ..config import Topics
from ..engine import Cutoff
from .common import OUTPUT_COLUMNS, SweepTables, top_by_citations, window_counts, yearly_series

PRIMARY = {"topic": "primary_topic_id", "subfield": "subfield_id"}


def _map(frame: pd.DataFrame | None, key: str, value: str) -> dict:
    if frame is None:
        return {}
    return frame.dropna(subset=[key]).drop_duplicates(key).set_index(key)[value].to_dict()


def _labels(tables: SweepTables) -> dict:
    """Display names and parents. The topics table also covers topics that are never primary."""
    if "labels" not in tables.cache:
        w, t = tables.works, tables.topics
        tables.cache["labels"] = {
            "topic": {**_map(t, "topic_id", "topic"), **_map(w, "primary_topic_id", "primary_topic")},
            "topic_parent": {**_map(t, "topic_id", "subfield_id"), **_map(w, "primary_topic_id", "subfield_id")},
            "subfield": _map(w, "subfield_id", "subfield"),
            "subfield_parent": {**_map(t, "subfield_id", "field_id"), **_map(w, "subfield_id", "field_id")},
            "field": _map(w, "field_id", "field"),
        }
    return tables.cache["labels"]


def topic_pairs(tables: SweepTables, cfg: Topics, level: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(denominator works, one row per work × entity with pub_month and is_primary)."""
    key = ("topics", "pairs", level, cfg.counting)
    if key in tables.cache:
        return tables.cache[key]
    works = tables.works[tables.works["primary_topic_id"].notna()]
    primary = works[["work_id", PRIMARY[level], "pub_month"]].rename(columns={PRIMARY[level]: "primary_entity"})
    if cfg.counting == "primary":
        pairs = primary.assign(entity_id=primary["primary_entity"])
    else:
        column = "topic_id" if level == "topic" else "subfield_id"
        assigned = tables.topics[["work_id", column]].rename(columns={column: "entity_id"})
        pairs = assigned.dropna().drop_duplicates().merge(primary, on="work_id")
    pairs = pairs.dropna(subset=["entity_id"]).assign(is_primary=lambda f: f["entity_id"] == f["primary_entity"])
    tables.cache[key] = (works, pairs[["work_id", "entity_id", "pub_month", "is_primary"]])
    return tables.cache[key]


def build(tables: SweepTables, cfg: Topics, cutoff: Cutoff, level: str) -> pd.DataFrame:
    if level not in PRIMARY:
        raise ValueError(f"unknown level {level!r}")
    works, pairs = topic_pairs(tables, cfg, level)
    out = window_counts(pairs[["work_id", "entity_id", "pub_month"]], works["pub_month"], cutoff)

    names = _labels(tables)
    parent_kind = "subfield" if level == "topic" else "field"
    out["entity_label"] = [names[level].get(e, f"{level.capitalize()} {e}") for e in out.index]
    out["parent_id"] = [names[f"{level}_parent"].get(e) for e in out.index]
    out["parent_label"] = [names[parent_kind].get(p) if p is not None else None for p in out["parent_id"]]

    current = pairs[pairs["pub_month"].between(cutoff.current.start, cutoff.current.stop - 1)]
    primary_share = current.groupby("entity_id")["is_primary"].mean()
    out["extra"] = [
        {"counting": cfg.counting,
         "primary_share": round(float(primary_share[e]), 3) if e in primary_share.index else None}
        for e in out.index
    ]

    key = ("topics", level, cfg.counting, "series")
    if key not in tables.cache:
        years = tables.first_year + works["pub_month"] // 12
        tables.cache[key] = yearly_series(pairs[["work_id", "entity_id", "pub_month"]], years, tables.years,
                                          tables.first_year)
    out["series"] = tables.cache[key].reindex(out.index)
    cited = tables.works.set_index("work_id")["cited_by_count"]
    out["top_work_ids"] = top_by_citations(out["work_ids_current"], cited)
    return out.reset_index()[OUTPUT_COLUMNS]
