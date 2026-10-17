"""`brief.md` for the latest cutoff, from a template — no LLM (specs/04 §8)."""

import json
from pathlib import Path

import pandas as pd

from .config import Config

TOP = 10
DIFF_ITEMS = 5
LABEL_ORDER = ["NEW", "RISING", "FALLING", "GONE"]
CITATION_LABELS = {"NEW": "Breakout", "RISING": "Accelerating"}


def openalex_link(detector: str, level: str, entity_id: str) -> str:
    if detector == "topics" and level == "subfield":
        return f"https://openalex.org/subfields/{entity_id}"
    if detector == "collaborations" and level == "country":
        return f"https://openalex.org/countries/{entity_id}"
    return f"https://openalex.org/{entity_id}"


def _since_last_sweep(diff: dict) -> list[str]:
    lines = [f"## Since last sweep ({diff['old_sweep']} → {diff['new_sweep']})", ""]
    totals = diff["totals"]
    old, new = totals[diff["old_sweep"]], totals[diff["new_sweep"]]
    lines.append("| | " + " | ".join(old) + " |")
    lines.append("|---|" + "---|" * len(old))
    lines.append(f"| {diff['old_sweep']} | " + " | ".join(str(v) for v in old.values()) + " |")
    lines.append(f"| {diff['new_sweep']} | " + " | ".join(str(v) for v in new.values()) + " |")
    lines.append("")
    added = diff["works_added"]
    by_year = ", ".join(f"{y}: {v['count']}" for y, v in sorted(added["by_publication_year"].items()))
    lines.append(f"- Works added: {added['count']}" + (f" (by publication year — {by_year})" if by_year else ""))
    removed = diff["works_removed"]
    lines.append(f"- Works removed: {removed['count']}" +
                 (f" — e.g. {', '.join(removed['ids'][:DIFF_ITEMS])}" if removed["ids"] else ""))
    reassigned = diff["topic_reassigned"]
    lines.append(f"- Primary topic reassigned: {reassigned['count']}")
    for ex in reassigned["examples"][:DIFF_ITEMS]:
        lines.append(f"  - {ex['work_id']}: {ex['old_topic']} → {ex['new_topic']}")
    partners = diff["partners_first_seen"]
    lines.append(f"- Partners first seen: {len(partners['institutions'])} institutions, "
                 f"{len(partners['countries'])} countries")
    for p in partners["institutions"][:DIFF_ITEMS]:
        lines.append(f"  - {p['institution_name']} ({p['country']}), {len(p['work_ids'])} works")
    if diff["citation_jumps"]:
        lines.append("- Largest citation increases:")
        for j in diff["citation_jumps"][:DIFF_ITEMS]:
            lines.append(f"  - {j['title']} ({j['work_id']}): {j['old']} → {j['new']} (+{j['delta']})")
    return lines + [""]


def make_brief(sweep_dir: Path, config: Config) -> str:
    sweep_dir = Path(sweep_dir)
    manifest = json.loads((sweep_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((sweep_dir / "derived" / "detect_summary.json").read_text(encoding="utf-8"))
    signals = pd.read_parquet(sweep_dir / "derived" / "signals.parquet")
    cutoff = summary["cutoffs"][-1]

    lines = [
        f"# {config.universe.label} — brief",
        "",
        f"Sweep {manifest['sweep_id']} (observed {manifest['observed_at']}) · cutoff **{cutoff}** · "
        f"{manifest['harvested_count']:,} works",
        "",
    ]
    diff_path = sweep_dir / "diff.json"
    if diff_path.exists():
        lines += _since_last_sweep(json.loads(diff_path.read_text(encoding="utf-8")))

    skipped = {s["cutoff"]: s["reason"] for s in summary["citation_cutoffs_skipped"]}
    for run in summary["runs"]:
        if run["cutoff"] != cutoff:
            continue
        detector, level = run["detector"], run["level"]
        title = detector.capitalize() + ("" if detector == "citations" else f" — {level}")
        lines += [f"## {title}", ""]
        names = CITATION_LABELS if detector == "citations" else {}
        counts = ", ".join(f"{names.get(k, k)} {run['signals'].get(k, 0)}" for k in LABEL_ORDER
                           if k in run["signals"])
        lines.append(f"{run['tested']:,} tested of {run['seen']:,} seen · signals: {counts or 'none'}")
        lines.append("")
        top = signals[(signals.detector == detector) & (signals.level == level) & (signals.cutoff == cutoff)]
        top = top.sort_values(["rank", "q"], ascending=[False, True]).head(TOP)
        for s in top.itertuples():
            label = names.get(s.label, s.label)
            lines.append(f"- **{label}** — {s.why} [OpenAlex]({openalex_link(detector, level, s.entity_id)})")
        lines.append("")
    if cutoff in skipped:
        lines += [f"Citations: {skipped[cutoff]}", ""]

    e = config.engine
    lines += [
        "## Method",
        "",
        f"- Windows: the current window is 12 months ending at the cutoff; the baseline is the 36 months before "
        f"({config.periods.mode} mode). Observable history starts in January {config.universe.first_year}: "
        f"NEW means absent since then, not new to science.",
        "- Test: exact conditional binomial test of the entity's share in the current window vs the baseline.",
        f"- False discoveries: Benjamini–Hochberg q ≤ {e.alpha} within each detector × level × cutoff.",
        f"- Effect-size floor: share ratio ≥ ×{2 ** e.min_log2_ratio:.2g} or ≤ ÷{2 ** e.min_log2_ratio:.2g}; "
        "ranked by the confidence bound closest to zero.",
        ("- Topics: each work counts for each of its OpenAlex topics (up to 3; shares are of works)."
         if config.detectors.topics.counting == "all" else "- Topics: each work counts for its primary topic only."),
        "- Limits: topics come from the OpenAlex classifier; citations use today's counts_by_year "
        "(past cutoffs are reconstructions); collaborations depend on affiliation disambiguation.",
        "",
    ]
    return "\n".join(lines)


def write_brief(sweep_dir: Path, config: Config) -> Path:
    path = Path(sweep_dir) / "derived" / "brief.md"
    path.write_text(make_brief(sweep_dir, config), encoding="utf-8")
    return path
