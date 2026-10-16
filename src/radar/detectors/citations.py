"""Citations detector: works cited markedly faster than their cohort (specs/04 §4.2)."""

import numpy as np
import pandas as pd

from ..config import Citations
from ..engine import Cutoff
from .common import OUTPUT_COLUMNS, SweepTables, cutoff_year


def citation_matrix(tables: SweepTables) -> pd.DataFrame:
    """Citations received per work (rows) and calendar year (columns), zero-filled."""
    key = ("citations", "matrix")
    if key not in tables.cache:
        cby = tables.counts_by_year
        matrix = cby.pivot_table(index="work_id", columns="year", values="cited_by_count", aggfunc="sum", fill_value=0)
        low, high = tables.citation_coverage
        years = range(low if low is not None else tables.first_year, (high if high is not None else tables.last_year) + 1)
        matrix = matrix.reindex(index=tables.works["work_id"], columns=list(years), fill_value=0).fillna(0).astype(int)
        tables.cache[key] = matrix
    return tables.cache[key]


def skip_reason(tables: SweepTables, cutoff: Cutoff, cfg: Citations) -> str | None:
    """Why the citation detector cannot run at this cutoff, or None."""
    if not cutoff.year_end:
        year = cutoff_year(tables, cutoff)
        return f"Citations are counted per calendar year — latest available: {year - 1}-H2"
    year = cutoff_year(tables, cutoff)
    low, high = tables.citation_coverage
    if low is None or high is None:
        return "no counts_by_year coverage measured"
    if year - 3 < low or year > high:
        return f"baseline years {year - 3}–{year - 1} or year {year} outside counts_by_year coverage {low}–{high}"
    return None


def assign_cohorts(works: pd.DataFrame, min_size: int) -> pd.DataFrame:
    """Cohort per work: same year + field, else year + domain, else year (first with ≥ min_size works)."""
    works = works.copy()
    year = works["publication_year"].astype(int).astype(str)
    works["cohort_level"] = None
    works["cohort_key"] = None
    works["cohort_label"] = None
    for level, id_col, label_col in [("field", "field_id", "field"), ("domain", "domain_id", "domain"),
                                     ("year", None, None)]:
        if id_col is None:
            key, label = year, pd.Series("all fields", index=works.index)
        else:
            key = (year + "|" + works[id_col].astype(str)).where(works[id_col].notna())
            label = works[label_col].astype(str)
        size = key.map(key.value_counts())
        ok = works["cohort_level"].isna() & key.notna()
        if level != "year":  # the last fallback is used whatever its size
            ok &= size >= min_size
        works.loc[ok, "cohort_level"] = level
        works.loc[ok, "cohort_key"] = key[ok]
        works.loc[ok, "cohort_label"] = year[ok] + " · " + label[ok]
    return works


def build(tables: SweepTables, cfg: Citations, cutoff: Cutoff, level: str = "work") -> pd.DataFrame:
    year = cutoff_year(tables, cutoff)
    works = tables.works[tables.works["publication_year"].notna()]
    works = works[works["publication_year"].astype(int) <= year - cfg.min_age_years]
    if works.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    works = assign_cohorts(works, cfg.min_cohort_size)
    matrix = citation_matrix(tables).reindex(works["work_id"]).fillna(0)
    pub = works["publication_year"].astype(int).to_numpy()
    cols = np.array(matrix.columns)
    m = matrix.to_numpy()

    # Baseline years: max(p, Y-3) … Y-1; history: p … Y-4. Citations before p are ignored.
    baseline_mask = (cols[None, :] >= np.maximum(pub, year - 3)[:, None]) & (cols[None, :] <= year - 1)
    history_mask = (cols[None, :] >= pub[:, None]) & (cols[None, :] < year - 3)
    c = m[:, list(cols).index(year)] if year in cols else np.zeros(len(works), dtype=int)
    b = (m * baseline_mask).sum(axis=1)
    history = (m * history_mask).sum(axis=1)

    frame = pd.DataFrame({
        "entity_id": works["work_id"].to_numpy(),
        "entity_label": works["title"].to_numpy(),
        "parent_id": works["field_id"].to_numpy(),
        "parent_label": works["field"].to_numpy(),
        "c": c.astype(int), "b": b.astype(int), "history_before": history.astype(int),
        "cohort_key": works["cohort_key"].to_numpy(),
    })
    # Leave-one-out cohort denominators: the work never dilutes its own reference.
    totals = frame.groupby("cohort_key")[["c", "b"]].transform("sum")
    frame["C"] = totals["c"] - frame["c"]
    frame["B"] = totals["b"] - frame["b"]

    # Display series per calendar year: the work's citations and the rest of its cohort's.
    years = [y for y in tables.years if y in cols]
    year_idx = [list(cols).index(y) for y in years]
    own = m[:, year_idx]
    cohort_sum = pd.DataFrame(own, index=frame["cohort_key"]).groupby(level=0).transform("sum").to_numpy()
    others = cohort_sum - own
    # Only works that will be tested get a series (display only; it dominates the run time).
    tested = frame["c"].to_numpy() >= cfg.min_current
    frame["series"] = [
        [{"period": y, "n": int(n), "den": int(d)} for y, n, d in zip(years, row_n, row_d)] if t else []
        for row_n, row_d, t in zip(own, others, tested)
    ]
    frame["work_ids_current"] = [[w] for w in frame["entity_id"]]
    frame["top_work_ids"] = frame["work_ids_current"]
    sizes = frame["cohort_key"].map(frame["cohort_key"].value_counts())
    frame["extra"] = [
        {"cohort": label, "cohort_level": lvl, "cohort_size": int(size), "publication_year": int(p)}
        for label, lvl, size, p in zip(works["cohort_label"], works["cohort_level"], sizes, pub)
    ]
    return frame[OUTPUT_COLUMNS]
