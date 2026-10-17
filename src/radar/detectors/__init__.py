"""`radar detect`: every detector × level × cutoff through the engine (specs/04 §4, §6, §7)."""

import json
import logging
import time
from pathlib import Path

import pandas as pd

from ..config import Config
from ..engine import Cutoff, assess, cutoffs
from . import citations, collaborations, topics
from .common import SweepTables, cutoff_year

logger = logging.getLogger(__name__)

ASSESSMENT_COLUMNS = [
    "detector", "level", "cutoff", "cutoff_month", "entity_id", "entity_label", "parent_id", "parent_label",
    "c", "b", "C", "B", "share_c", "share_b", "log2_sr", "ci_low", "ci_high", "p", "q", "is_signal", "label",
    "returning", "rank",
]
SIGNAL_EXTRA_COLUMNS = ["signal_id", "series", "work_ids_current", "top_work_ids", "extra", "why"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def window_label(window: range, first_year: int, mode: str) -> str:
    """"2025" / "2022–2024" in year mode, "Jul 2024–Jun 2025" in semester mode."""
    start, end = window.start, window.stop - 1
    y0, y1 = first_year + start // 12, first_year + end // 12
    if mode == "year":
        return str(y0) if y0 == y1 else f"{y0}–{y1}"
    return f"{MONTHS[start % 12]} {y0}–{MONTHS[end % 12]} {y1}"


def _x(log2_value: float) -> str:
    """Share ratio with 2 significant digits, never in scientific notation (×110, not ×1.1e+02)."""
    value = 2 ** log2_value
    return f"×{float(f'{value:.2g}'):.0f}" if value >= 10 else f"×{value:.2g}"


def why(row, detector: str, cutoff: Cutoff, config: Config, tables: SweepTables) -> str:
    sr, lo, hi = _x(row.log2_sr), _x(row.ci_low), _x(row.ci_high)
    if detector == "citations":
        year = cutoff_year(tables, cutoff)
        start = max(row.extra["publication_year"], year - 3)
        base = str(start) if start == year - 1 else f"{start}–{year - 1}"
        verb = "rose" if row.log2_sr > 0 else "fell"
        return (f"{row.entity_label}: {row.c} citations in {year} vs {row.b} over {base}. "
                f"Its share of citations to {row.extra['cohort']} papers {verb} {sr} "
                f"(95% CI {lo}–{hi}), q = {row.q:.2g}.")
    mode = config.periods.mode
    current = window_label(cutoff.current, tables.first_year, mode)
    baseline = window_label(cutoff.baseline, tables.first_year, mode)
    return (f"{row.entity_label}: {row.c} of {row.C} works in {current} ({row.share_c:.1%}) "
            f"vs {row.b} of {row.B} in {baseline} ({row.share_b:.1%}). "
            f"Share {sr} (95% CI {lo}–{hi}), q = {row.q:.2g}.")


def plan(config: Config):
    """(detector name, module, its config, levels, directions, support filter)."""
    d = config.detectors
    return [
        ("topics", topics, d.topics, d.topics.levels, {"up", "down"},
         lambda f: (f.c + f.b) >= d.topics.min_support),
        ("citations", citations, d.citations, ["work"], set(d.citations.directions),
         # A cohort with no other citations in either window gives no reference share.
         lambda f: (f.c >= d.citations.min_current) & (f.C > 0) & (f.B > 0)),
        ("collaborations", collaborations, d.collaborations, d.collaborations.levels, {"up", "down"},
         lambda f: (f.c + f.b) >= d.collaborations.min_support),
    ]


def run_detect(sweep_dir: Path, config: Config) -> dict:
    started = time.monotonic()
    sweep_dir = Path(sweep_dir)
    u, periods = config.universe, config.periods
    tables = SweepTables.load(sweep_dir, u.first_year, u.last_year)
    cuts = cutoffs(u.first_year, u.last_year, periods.mode, periods.window_months, periods.baseline_months)

    assessed, signals, summary_rows, skipped = [], [], [], []
    for name, module, cfg, levels, directions, supported in plan(config):
        for level in levels:
            for cutoff in cuts:
                if name == "citations":
                    reason = citations.skip_reason(tables, cutoff, cfg)
                    if reason:
                        skipped.append({"detector": name, "cutoff": cutoff.label, "reason": reason})
                        continue
                built = module.build(tables, cfg, cutoff, level)
                tested = built[supported(built)] if len(built) else built
                row = {"detector": name, "level": level, "cutoff": cutoff.label,
                       "seen": int(len(built)), "tested": int(len(tested)), "signals": {}}
                if len(tested):
                    out = assess(tested, alpha=config.engine.alpha, min_log2_ratio=config.engine.min_log2_ratio,
                                 directions=directions)
                    out.insert(0, "cutoff_month", cutoff.month)
                    out.insert(0, "cutoff", cutoff.label)
                    out.insert(0, "level", level)
                    out.insert(0, "detector", name)
                    assessed.append(out[ASSESSMENT_COLUMNS])
                    hits = out[out["is_signal"]].copy()
                    if len(hits):
                        hits["signal_id"] = [f"{name}:{level}:{e}:{cutoff.label}" for e in hits["entity_id"]]
                        hits["why"] = [why(r, name, cutoff, config, tables) for r in hits.itertuples()]
                        hits["extra"] = [json.dumps(e, ensure_ascii=False, default=str) for e in hits["extra"]]
                        signals.append(hits[ASSESSMENT_COLUMNS + SIGNAL_EXTRA_COLUMNS])
                    row["signals"] = {k: int(v) for k, v in hits["label"].value_counts().sort_index().items()}
                summary_rows.append(row)

    derived = sweep_dir / "derived"
    derived.mkdir(exist_ok=True)
    assessments = pd.concat(assessed, ignore_index=True) if assessed else pd.DataFrame(columns=ASSESSMENT_COLUMNS)
    signal_table = (pd.concat(signals, ignore_index=True) if signals
                    else pd.DataFrame(columns=ASSESSMENT_COLUMNS + SIGNAL_EXTRA_COLUMNS))
    assessments.to_parquet(derived / "assessments.parquet", index=False)
    signal_table.to_parquet(derived / "signals.parquet", index=False)

    consortium = int((tables.works["n_authors"].fillna(0) > config.detectors.collaborations.max_authors).sum())
    summary = {
        "sweep_id": tables.sweep_id,
        "config_hash": config.config_hash,
        "period_mode": periods.mode,
        "cutoffs": [c.label for c in cuts],
        "parameters": {
            "engine": {"alpha": config.engine.alpha, "min_log2_ratio": config.engine.min_log2_ratio},
            "topics": {"levels": list(config.detectors.topics.levels),
                       "min_support": config.detectors.topics.min_support},
            "citations": {k: getattr(config.detectors.citations, k)
                          for k in ("min_age_years", "min_current", "min_cohort_size", "directions")},
            "collaborations": {k: getattr(config.detectors.collaborations, k)
                               for k in ("levels", "min_support", "max_authors", "exclude_countries")},
        },
        "consortium_works_excluded": consortium,
        "citation_cutoffs_skipped": skipped,
        "runs": summary_rows,
        "n_assessments": int(len(assessments)),
        "n_signals": int(len(signal_table)),
        "seconds": round(time.monotonic() - started, 1),
    }
    (derived / "detect_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    logger.info("detect %s: %d assessments, %d signals in %.1f s", tables.sweep_id, len(assessments),
                len(signal_table), summary["seconds"])
    return summary
