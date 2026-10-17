"""What the three detectors share: the sweep tables and window counting (specs/04 §4)."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..engine import Cutoff

OUTPUT_COLUMNS = [
    "entity_id", "entity_label", "parent_id", "parent_label", "c", "b", "C", "B", "history_before",
    "series", "work_ids_current", "top_work_ids", "extra",
]


@dataclass
class SweepTables:
    sweep_id: str
    works: pd.DataFrame
    authorships: pd.DataFrame
    counts_by_year: pd.DataFrame
    first_year: int
    last_year: int
    citation_coverage: tuple[int | None, int | None] = (None, None)
    topics: pd.DataFrame | None = None  # work × topic (up to 3), for topics counting = "all"
    cache: dict = field(default_factory=dict)  # per-level values that do not depend on the cutoff

    @property
    def years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))

    @classmethod
    def load(cls, sweep_dir: Path, first_year: int, last_year: int) -> "SweepTables":
        sweep_dir = Path(sweep_dir)
        quality = json.loads((sweep_dir / "quality.json").read_text(encoding="utf-8"))
        coverage = quality.get("counts_by_year_coverage", {})
        return cls(
            sweep_id=sweep_dir.name,
            works=pd.read_parquet(sweep_dir / "works.parquet"),
            authorships=pd.read_parquet(sweep_dir / "authorships.parquet"),
            counts_by_year=pd.read_parquet(sweep_dir / "counts_by_year.parquet"),
            first_year=first_year,
            last_year=last_year,
            citation_coverage=(coverage.get("earliest_year"), coverage.get("latest_year")),
            topics=pd.read_parquet(sweep_dir / "topics.parquet"),
        )


def cutoff_year(tables: SweepTables, cutoff: Cutoff) -> int:
    return tables.first_year + cutoff.month // 12


def _in(months: pd.Series, window: range) -> pd.Series:
    return months.between(window.start, window.stop - 1)


def window_counts(pairs: pd.DataFrame, den_months: pd.Series, cutoff: Cutoff) -> pd.DataFrame:
    """Distinct works per entity in the current window, baseline and before it, plus denominators.

    pairs: one row per (work_id, entity_id) with the work's pub_month.
    den_months: pub_month of every work in the denominator.
    Returns one row per entity seen up to the cutoff, indexed by entity_id.
    """
    months = pairs["pub_month"]
    counts = pairs.assign(
        c=_in(months, cutoff.current), b=_in(months, cutoff.baseline), history_before=months < cutoff.baseline.start
    ).groupby("entity_id")[["c", "b", "history_before"]].sum().astype(int)
    counts = counts[(counts.c + counts.b + counts.history_before) > 0]
    counts["C"] = int(_in(den_months, cutoff.current).sum())
    counts["B"] = int(_in(den_months, cutoff.baseline).sum())
    current = pairs[_in(months, cutoff.current)].sort_values("work_id")
    counts["work_ids_current"] = current.groupby("entity_id")["work_id"].agg(list).reindex(counts.index)
    counts["work_ids_current"] = counts["work_ids_current"].apply(lambda v: v if isinstance(v, list) else [])
    return counts


def top_by_citations(work_ids: pd.Series, cited: pd.Series, n: int = 10) -> pd.Series:
    """For each list of work IDs, the `n` most cited (ties broken by ID)."""
    def pick(ids):
        ranked = sorted(ids, key=lambda w: (-int(cited.get(w, 0) or 0), w))
        return ranked[:n]
    return work_ids.apply(pick)


def yearly_series(pairs: pd.DataFrame, den_years: pd.Series, years: list[int], first_year: int) -> pd.Series:
    """Per entity, `[{"period": year, "n": works, "den": denominator}]` for each calendar year."""
    year = first_year + pairs["pub_month"] // 12
    table = pd.crosstab(pairs["entity_id"], year).reindex(columns=years, fill_value=0)
    den = den_years.value_counts().reindex(years, fill_value=0)
    den_list = [int(den[y]) for y in years]
    return pd.Series(
        [[{"period": y, "n": int(n), "den": d} for y, n, d in zip(years, row, den_list)] for row in table.to_numpy()],
        index=table.index,
    )
