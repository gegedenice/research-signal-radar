import type { Bundle, Points, Signal, Step } from "../types";

export function signal(partial: Partial<Signal> & { id: string }): Signal {
  return {
    detector: "topics", level: "topic", cutoff: "2025", label: "RISING", returning: false,
    entity: { id: partial.id, label: partial.id, parent_id: null, parent_label: null },
    c: 10, b: 5, C: 100, B: 300, share_c: 0.1, share_b: 0.0167, log2_sr: 2, ci_low: 1, ci_high: 3, p: 0.001, q: 0.01,
    rank: 1, why: "", series: [], work_idx: [0, 1], n_unmapped: 0, top_work_idx: [0], clusters: [], extra: {},
    ...partial,
  };
}

export function steps(mode: "year" | "semester" = "year"): Step[] {
  const out: Step[] = [];
  const size = mode === "year" ? 12 : 6;
  for (let start = 0; start < 120; start += size) {
    const year = 2016 + Math.floor(start / 12);
    const end = start + size - 1;
    const label = mode === "year" ? String(year) : `${year}-H${1 + Math.floor((start % 12) / 6)}`;
    out.push({ label, start_month: start, end_month: end, is_cutoff: end >= 47 });
  }
  return out;
}

export function bundle(signals: Signal[], mode: "year" | "semester" = "year"): Bundle {
  const st = steps(mode);
  return {
    schema_version: "research-signal-radar-bundle/0.1", generated_at: "",
    meta: {
      universe: { id: "u", label: "U", filter: "", root_institution: "I1" }, sweep_id: "2026-10-16",
      observed_at: "", n_works: 4, n_mapped: 4, years: [2016, 2025], period_mode: mode, steps: st,
      cutoffs: st.filter((s) => s.is_cutoff).map((s) => s.label), params: { alpha: 0.1, min_log2_ratio: 0.585 },
      config_hash: "h",
    },
    quality: {},
    detectors: [
      { key: "topics", levels: ["topic", "subfield"], summary: {} },
      { key: "citations", levels: ["work"], summary: {} },
      { key: "collaborations", levels: ["institution", "country"], summary: {} },
    ],
    signals, volcano: {}, clusters: [], regions: [], diff: null, brief_md: "",
  };
}

export function points(n = 4): Points {
  const col = (v: number) => Array.from({ length: n }, () => v);
  return { n, x: col(0.5), y: col(0.5), x3: col(0.5), y3: col(0.5), z3: col(0.5), year: col(2025),
           pub_month: col(110), cluster: col(0), region: col(0), has_abstract: col(1) };
}
