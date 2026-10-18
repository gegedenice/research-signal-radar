// Shapes of the static bundle written by `radar export` (specs/06 §2).

export type Label = "NEW" | "RISING" | "FALLING" | "GONE";
export type Detector = "topics" | "citations" | "collaborations";

export interface Points {
  n: number;
  x: number[];
  y: number[];
  x3: number[];
  y3: number[];
  z3: number[];
  year: number[];
  pub_month: number[];
  cluster: number[];
  region: number[];
  has_abstract: number[];
}

export interface Works {
  id: string[];
  title: (string | null)[];
  year: (number | null)[];
  doi: (string | null)[];
  cited_by_count: number[];
  topic: number[];
  subfield: number[];
  topics: string[];
  subfields: string[];
}

export interface SeriesPoint {
  period: number;
  n: number;
  den: number;
}

export interface Signal {
  id: string;
  detector: Detector;
  level: string;
  cutoff: string;
  entity: { id: string; label: string | null; parent_id: string | null; parent_label: string | null };
  label: Label;
  returning: boolean;
  c: number;
  b: number;
  C: number;
  B: number;
  share_c: number;
  share_b: number;
  log2_sr: number;
  ci_low: number;
  ci_high: number;
  q: number;
  rank: number;
  why: string;
  series: SeriesPoint[];
  work_idx: number[];
  n_unmapped: number;
  top_work_idx: number[];
  clusters: { cluster: number; share: number }[];
  extra: Record<string, unknown>;
}

export interface Step {
  label: string;
  start_month: number;
  end_month: number;
  is_cutoff: boolean;
}

export interface TrendEntry {
  label: Label | null;
  log2_sr: number;
  ci_low: number;
  ci_high: number;
  q: number;
}

export interface Cluster {
  cluster: number;
  region_id: number;
  label: string;
  terms: string[];
  size: number;
  x: number;
  y: number;
  x3: number;
  y3: number;
  z3: number;
  counts_by_year: Record<string, number>;
  top_topics: { id: string; label: string; share: number }[];
  top_subfields: { id: string; label: string; share: number }[];
  trend: Record<string, TrendEntry>;
  title_only_share: number | null;
}

export interface Region {
  region_id: number;
  label: string;
  terms: string[];
  size: number | null;
  x: number | null;
  y: number | null;
  x3: number | null;
  y3: number | null;
  z3: number | null;
}

export interface DetectorSummary {
  key: Detector;
  levels: string[];
  summary: Record<string, Record<string, { seen: number; tested: number } & Record<Label, number>>>;
  skipped?: Record<string, string>;
}

export interface Volcano {
  n_tested: number;
  sampled: boolean;
  log2_sr: (number | null)[];
  q: (number | null)[];
  signal_idx: number[];
}

export interface Bundle {
  schema_version: string;
  generated_at: string;
  meta: {
    universe: { id: string; label: string; filter: string; root_institution: string };
    sweep_id: string;
    observed_at: string;
    n_works: number;
    n_mapped: number;
    years: [number, number];
    period_mode: "year" | "semester";
    steps: Step[];
    cutoffs: string[];
    params: Record<string, unknown> & { alpha: number; min_log2_ratio: number };
    config_hash: string;
  };
  quality: Record<string, unknown>;
  detectors: DetectorSummary[];
  signals: Signal[];
  volcano: Record<string, Volcano>;
  clusters: Cluster[];
  regions: Region[];
  diff: Record<string, any> | null;
  brief_md: string;
}

export interface Data {
  bundle: Bundle;
  points: Points;
  works: Works | null; // loaded after first paint
}
