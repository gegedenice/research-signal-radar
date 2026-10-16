export type DetectorKey =
  | "topic_momentum"
  | "citation_acceleration"
  | "actor_collaboration_novelty";

export type EditorialTier = "HEADLINE_CANDIDATE" | "WATCH" | "EXPLORATION";
export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW" | string;

export interface PocBundle {
  schema_version: string;
  generated_at?: string;
  source: {
    run_id: string;
    manifest_id: string;
    scope_mode: string;
    portfolio_label: string;
    information_cutoff: string;
    observation_vintage: string;
    temporal_mode: string;
    retrospective_reconstruction: boolean;
  };
  detectors: DetectorSummary[];
  signals: SignalRecord[];
  top_topics?: TopTopic[];
  evidence_by_id: Record<string, EvidenceBundle>;
  backtests: Record<string, BacktestPayload>;
  warnings: string[];
}

export interface TopTopic {
  topic_id: string;
  label: string;
  subfield?: string | null;
  total_count: number;
  current_count: number;
  previous_count: number;
  current_share?: number | null;
  direction?: string | null;
  presence?: string | null;
}

export interface DetectorSummary {
  key: DetectorKey;
  title: string;
  description: string;
  signal_count: number;
  headline_count: number;
  watch_count: number;
  exploration_count: number;
}

export interface SignalRecord {
  signal_id: string;
  detector: {
    key: DetectorKey;
    title: string;
    type: string;
    version: string;
  };
  subject: {
    kind: string;
    id: string;
    label: string;
    member_ids?: string[];
  };
  signal_label: string;
  scale_corroboration?: {
    subfield_direction?: string | null;
    field_direction?: string | null;
    concordance?: string | null;
    note?: string | null;
  } | null;
  priority: {
    score: number;
    components?: Record<string, number>;
  };
  confidence: {
    level: ConfidenceLevel;
    score?: number;
    factors?: string[];
    limitations?: string[];
    components?: Record<string, number>;
  };
  editorial: {
    tier: EditorialTier;
    review_status: string;
    review_reasons: string[];
  };
  summary?: {
    headline?: string;
    why_unusual?: string;
  };
  why_unusual?: string;
  analysis_context?: {
    current_window?: { start: string; end: string };
    reference?: {
      kind?: string;
      reference_id?: string;
      window?: { start: string; end: string };
    };
  };
  temporal_context: {
    mode: string;
    emitted_at: string;
    information_cutoff: string;
    observation_vintage: string;
    cutoff_basis: string;
  };
  quality_flags: string[];
  provenance: {
    code_version?: string;
    run_id?: string;
    query_manifest_id?: string;
  };
  metrics: Record<string, unknown>;
  payload: Record<string, unknown>;
  evidence_refs: EvidenceReference[];
  evidence_bundle_id: string | null;
  evidence_bundle_available: boolean;
  dossier_path: string | null;
  limitations: string[];
  feed_rank: number;
}

export interface EvidenceReference {
  evidence_id: string;
  type: string;
  role: string;
  observed_at: string;
  locator: {
    kind: string;
    id: string;
  };
  supports: string;
}

export type EvidenceBundle = Record<string, unknown>;

export interface BacktestPayload {
  available: boolean;
  result: Record<string, unknown> | null;
  summary: Record<string, unknown> | null;
  quality: Record<string, unknown> | null;
  extra: Record<string, unknown>;
}
