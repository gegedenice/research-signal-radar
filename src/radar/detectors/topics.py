"""Topics detector: share of works by primary topic or subfield (specs/04 §4.1)."""

import pandas as pd

from ..config import Topics
from ..engine import Cutoff
from .common import OUTPUT_COLUMNS, SweepTables, top_by_citations, window_counts, yearly_series

LEVEL_COLUMNS = {
    "topic": ("primary_topic_id", "primary_topic"),
    "subfield": ("subfield_id", "subfield"),
}


def build(tables: SweepTables, cfg: Topics, cutoff: Cutoff, level: str) -> pd.DataFrame:
    id_col, label_col = LEVEL_COLUMNS[level]
    works = tables.works[tables.works["primary_topic_id"].notna()]
    pairs = works[["work_id", id_col, "pub_month"]].rename(columns={id_col: "entity_id"}).dropna(subset=["entity_id"])

    out = window_counts(pairs, works["pub_month"], cutoff)
    labels = works.drop_duplicates(id_col).set_index(id_col)
    out["entity_label"] = labels[label_col].reindex(out.index)
    if level == "topic":
        out["parent_id"] = labels["subfield_id"].reindex(out.index)
        out["parent_label"] = labels["subfield"].reindex(out.index)
    else:
        out["parent_id"] = labels["field_id"].reindex(out.index)
        out["parent_label"] = labels["field"].reindex(out.index)

    key = ("topics", level, "series")
    if key not in tables.cache:
        years = tables.first_year + works["pub_month"] // 12
        tables.cache[key] = yearly_series(pairs, years, tables.years, tables.first_year)
    out["series"] = tables.cache[key].reindex(out.index)
    cited = tables.works.set_index("work_id")["cited_by_count"]
    out["top_work_ids"] = top_by_citations(out["work_ids_current"], cited)
    out["extra"] = [{} for _ in range(len(out))]
    return out.reset_index()[OUTPUT_COLUMNS]
