"""The single statistical engine (specs/04 §2–§3). No detector-specific code here."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import binom

Z95 = 1.959964


@dataclass(frozen=True)
class Cutoff:
    """End of a 12-month current window. `month` is the `pub_month` index of its last month."""

    label: str
    month: int
    current: range
    baseline: range

    @property
    def year_end(self) -> bool:
        return self.month % 12 == 11


def windows(month: int, window_months: int = 12, baseline_months: int = 36) -> tuple[range, range]:
    """(current_months, baseline_months) for a cutoff ending at `pub_month` index `month`."""
    start = month - window_months + 1
    return range(start, month + 1), range(start - baseline_months, start)


def cutoffs(first_year: int, last_year: int, mode: str = "year",
            window_months: int = 12, baseline_months: int = 36) -> list[Cutoff]:
    """All cutoffs with a full baseline: Decembers in year mode, Junes and Decembers in semester mode."""
    if mode not in {"year", "semester"}:
        raise ValueError(f"unknown period mode {mode!r}")
    step = 12 if mode == "year" else 6
    first = window_months + baseline_months - 1  # earliest month with a full baseline
    last = (last_year - first_year) * 12 + 11
    result = []
    for month in range(11 if mode == "year" else 5, last + 1, step):
        if month < first:
            continue
        year = first_year + month // 12
        if mode == "year":
            label = str(year)
        else:
            label = f"{year}-H2" if month % 12 == 11 else f"{year}-H1"
        current, baseline = windows(month, window_months, baseline_months)
        result.append(Cutoff(label, month, current, baseline))
    return result


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (q-values)."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    scaled = p[order] * m / np.arange(1, m + 1)
    q_sorted = np.minimum.accumulate(scaled[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(q_sorted, 1.0)
    return q


def assess(df: pd.DataFrame, *, alpha: float, min_log2_ratio: float,
           directions: set[str] | frozenset[str] = frozenset({"up", "down"})) -> pd.DataFrame:
    """Test every entity of one detector × level × cutoff.

    df columns: entity_id, c, b, C, B, history_before (+ any passthrough columns).
    Returns df with: share_c, share_b, log2_sr, ci_low, ci_high, p, q, is_signal, label, returning,
    rank — sorted by rank (descending) then q (ascending).
    """
    out = df.copy()
    c = out["c"].to_numpy(dtype=float)
    b = out["b"].to_numpy(dtype=float)
    C = out["C"].to_numpy(dtype=float)
    B = out["B"].to_numpy(dtype=float)
    hist = out["history_before"].to_numpy(dtype=float)

    out["share_c"] = c / C
    out["share_b"] = b / B

    # Exact conditional test: given n = c + b, c ~ Binomial(n, C / (C + B)) under no change.
    n = c + b
    p0 = C / (C + B)
    lower = binom.cdf(c, n, p0)
    upper = binom.sf(c - 1, n, p0)
    p = np.minimum(1.0, 2 * np.minimum(lower, upper))
    p[n == 0] = 1.0
    out["p"] = p

    # Share ratio with +0.5 continuity correction, CI on the log scale.
    ln_sr = np.log(((c + 0.5) / C) / ((b + 0.5) / B))
    half = Z95 * np.sqrt(1 / (c + 0.5) + 1 / (b + 0.5))
    out["log2_sr"] = ln_sr / np.log(2)
    out["ci_low"] = (ln_sr - half) / np.log(2)
    out["ci_high"] = (ln_sr + half) / np.log(2)

    out["q"] = bh(p)

    up = out["log2_sr"].to_numpy() > 0
    allowed = np.where(up, "up" in directions, "down" in directions)
    is_signal = (out["q"].to_numpy() <= alpha) & (np.abs(out["log2_sr"].to_numpy()) >= min_log2_ratio) & allowed
    out["is_signal"] = is_signal

    label = np.select(
        [up & (b == 0) & (hist == 0), up, ~up & (c > 0), ~up],
        ["NEW", "RISING", "FALLING", "GONE"],
        default="",
    ).astype(object)
    label[~is_signal] = None
    out["label"] = label
    out["returning"] = is_signal & up & (b == 0) & (hist > 0)

    out["rank"] = np.where(up, np.maximum(0, out["ci_low"]), np.maximum(0, -out["ci_high"]))
    return out.sort_values(["rank", "q"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
