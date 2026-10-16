"""Collaborations detector: external institutions and countries in co-publications (specs/04 §4.3)."""

import pandas as pd

from ..config import Collaborations
from ..engine import Cutoff
from .common import OUTPUT_COLUMNS, SweepTables, top_by_citations, window_counts, yearly_series


def eligible_works(tables: SweepTables, cfg: Collaborations) -> pd.DataFrame:
    """Works kept after the consortium guard (n_authors > max_authors excluded)."""
    works = tables.works
    return works[~(works["n_authors"].fillna(0) > cfg.max_authors)]


def copublication_pairs(tables: SweepTables, cfg: Collaborations) -> pd.DataFrame:
    """(work, external institution) pairs where another author position holds the anchor side."""
    key = ("collaborations", "pairs", cfg.max_authors, tuple(cfg.exclude_countries))
    if key in tables.cache:
        return tables.cache[key]
    works = eligible_works(tables, cfg)
    auth = tables.authorships[tables.authorships["work_id"].isin(works["work_id"])]
    anchor = auth["is_anchor"].fillna(False).astype(bool)

    anchor_positions = auth[anchor].drop_duplicates(["work_id", "author_position_idx"])
    n_anchor = anchor_positions.groupby("work_id").size()
    is_anchor_position = set(zip(anchor_positions["work_id"], anchor_positions["author_position_idx"]))

    ext = auth[~anchor & auth["institution_id"].notna()].copy()
    own = [(w, p) in is_anchor_position for w, p in zip(ext["work_id"], ext["author_position_idx"])]
    # The anchor side must come from a different author position than the external one.
    ext = ext[(ext["work_id"].map(n_anchor).fillna(0).to_numpy() - pd.Series(own, dtype=int).to_numpy()) >= 1]
    if cfg.exclude_countries:
        ext = ext[~ext["institution_country"].isin(cfg.exclude_countries)]
    ext = ext.merge(works[["work_id", "pub_month"]], on="work_id")
    tables.cache[key] = ext
    return ext


def _anchor_units(tables: SweepTables, work_ids: pd.Series, n: int = 5) -> dict:
    """Per entity, the `n` anchor institutions most involved in its current works."""
    auth = tables.authorships
    anchors = auth[auth["is_anchor"].fillna(False).astype(bool)][["work_id", "institution_id", "institution_name"]]
    anchors = anchors.drop_duplicates(["work_id", "institution_id"])
    exploded = work_ids.explode().dropna().rename("work_id").reset_index()
    joined = exploded.merge(anchors, on="work_id")
    counts = joined.groupby(["entity_id", "institution_id", "institution_name"]).size().rename("works").reset_index()
    counts = counts.sort_values(["entity_id", "works", "institution_id"], ascending=[True, False, True])
    units: dict = {}
    for entity, iid, name, works in counts.groupby("entity_id").head(n).itertuples(index=False):
        units.setdefault(entity, []).append({"institution_id": iid, "name": name, "works": int(works)})
    return units


def build(tables: SweepTables, cfg: Collaborations, cutoff: Cutoff, level: str) -> pd.DataFrame:
    works = eligible_works(tables, cfg)
    ext = copublication_pairs(tables, cfg)
    if level == "institution":
        pairs = ext[["work_id", "institution_id", "pub_month"]].rename(columns={"institution_id": "entity_id"})
    elif level == "country":
        pairs = ext[["work_id", "institution_country", "pub_month"]].rename(
            columns={"institution_country": "entity_id"}).dropna(subset=["entity_id"])
    else:
        raise ValueError(f"unknown level {level!r}")
    pairs = pairs.drop_duplicates(["work_id", "entity_id"])

    out = window_counts(pairs, works["pub_month"], cutoff)
    if level == "institution":
        info = ext.drop_duplicates("institution_id").set_index("institution_id")
        out["entity_label"] = info["institution_name"].reindex(out.index)
        out["parent_id"] = info["institution_country"].reindex(out.index)
        out["parent_label"] = out["parent_id"]
        out["extra"] = [
            {"type": t, "country": c, "ror": r}
            for t, c, r in zip(info["institution_type"].reindex(out.index),
                               info["institution_country"].reindex(out.index),
                               info["institution_ror"].reindex(out.index))
        ]
    else:
        out["entity_label"] = out.index
        out["parent_id"] = None
        out["parent_label"] = None
        out["extra"] = [{} for _ in range(len(out))]
    # Evidence only matters for entities that will be tested.
    supported = out[(out["c"] + out["b"]) >= cfg.min_support]
    units = _anchor_units(tables, supported["work_ids_current"])
    out["extra"] = [{**e, "anchor_units": units.get(i, [])} for i, e in zip(out.index, out["extra"])]

    key = ("collaborations", level, "series", cfg.max_authors, tuple(cfg.exclude_countries))
    if key not in tables.cache:
        years = tables.first_year + works["pub_month"] // 12
        tables.cache[key] = yearly_series(pairs, years, tables.years, tables.first_year)
    out["series"] = tables.cache[key].reindex(out.index)
    cited = tables.works.set_index("work_id")["cited_by_count"]
    out["top_work_ids"] = top_by_citations(out["work_ids_current"], cited)
    return out.reset_index()[OUTPUT_COLUMNS]
