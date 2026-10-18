import type { Bundle, Detector, Label, Signal, Step } from "../types";

export const LABELS: Label[] = ["NEW", "RISING", "FALLING", "GONE"];
export const CITATION_LABELS: Label[] = ["NEW", "RISING"];

/** Display names: citations use Breakout / Accelerating (specs/04 §4.2). */
export function labelName(label: Label, detector: Detector): string {
  if (detector === "citations") return label === "NEW" ? "Breakout" : label === "RISING" ? "Accelerating" : label;
  return { NEW: "New", RISING: "Rising", FALLING: "Falling", GONE: "Gone" }[label];
}

export function labelGlyph(label: Label, detector: Detector): string {
  if (detector === "citations" && label === "NEW") return "✦";
  return { NEW: "▲", RISING: "▲", FALLING: "▼", GONE: "✕" }[label];
}

export function cutoffAt(bundle: Bundle, step: number): string | null {
  const s = bundle.meta.steps[step];
  return s && s.is_cutoff ? s.label : null;
}

export function baselineMessage(steps: Step[]): string {
  const base = steps.filter((s) => !s.is_cutoff);
  const first = steps.find((s) => s.is_cutoff);
  const span = base.length ? `${base[0].label.slice(0, 4)}–${base[base.length - 1].label.slice(0, 4)}` : "";
  return `Baseline period (${span}) — signals start in ${first?.label.slice(0, 4) ?? "the first cutoff"}`;
}

export interface FeedQuery {
  cutoff: string | null;
  tab: Detector;
  level: string;
  labels: Label[];
  search: string;
}

export type FeedResult =
  | { status: "baseline"; message: string; items: Signal[]; labelCounts: Record<string, number> }
  | { status: "note"; message: string; items: Signal[]; labelCounts: Record<string, number> }
  | { status: "ok"; items: Signal[]; labelCounts: Record<string, number> };

export function bySignalOrder(a: Signal, b: Signal): number {
  return b.rank - a.rank || a.q - b.q || a.id.localeCompare(b.id);
}

/** Signals of one cutoff / tab / level, filtered by labels and search, sorted by rank. */
export function selectFeed(bundle: Bundle, query: FeedQuery): FeedResult {
  const empty = {};
  if (query.cutoff === null) {
    return { status: "baseline", message: baselineMessage(bundle.meta.steps), items: [], labelCounts: empty };
  }
  if (query.tab === "citations" && query.cutoff.endsWith("-H1")) {
    const year = Number(query.cutoff.slice(0, 4));
    return {
      status: "note",
      message: `Citations are counted per calendar year — latest available: ${year - 1}-H2`,
      items: [],
      labelCounts: empty,
    };
  }
  const level = query.tab === "citations" ? "work" : query.level;
  const pool = bundle.signals.filter((s) => s.cutoff === query.cutoff && s.detector === query.tab && s.level === level);
  const labelCounts: Record<string, number> = {};
  for (const s of pool) labelCounts[s.label] = (labelCounts[s.label] ?? 0) + 1;
  const needle = query.search.trim().toLowerCase();
  const items = pool
    .filter((s) => query.labels.length === 0 || query.labels.includes(s.label))
    .filter((s) => !needle || (s.entity.label ?? s.entity.id).toLowerCase().includes(needle))
    .sort(bySignalOrder);
  return { status: "ok", items, labelCounts };
}

export function tabCounts(bundle: Bundle, cutoff: string | null, levels: Record<Detector, string>): Record<Detector, number> {
  const counts = { topics: 0, citations: 0, collaborations: 0 };
  if (!cutoff) return counts;
  for (const s of bundle.signals) {
    const level = s.detector === "citations" ? "work" : levels[s.detector];
    if (s.cutoff === cutoff && s.level === level) counts[s.detector] += 1;
  }
  return counts;
}

/** The signal with the same entity at another cutoff (detail panel keeps it when the time bar moves). */
export function sameEntityAt(bundle: Bundle, signal: Signal, cutoff: string | null): Signal | null {
  if (!cutoff) return null;
  return (
    bundle.signals.find(
      (s) => s.cutoff === cutoff && s.detector === signal.detector && s.level === signal.level && s.entity.id === signal.entity.id,
    ) ?? null
  );
}
