import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";
import type { PocBundle } from "./types";

const bundle: PocBundle = {
  schema_version: "research-signal-poc/0.1",
  source: {
    run_id: "run-1",
    manifest_id: "manifest-1",
    scope_mode: "lineage",
    portfolio_label: "Mines Paris–PSL",
    information_cutoff: "2026-06-30",
    observation_vintage: "2026-08-29T10:45:42Z",
    temporal_mode: "retrospective_reconstruction",
    retrospective_reconstruction: true,
  },
  detectors: [
    {
      key: "topic_momentum",
      title: "Topic Momentum",
      description: "Topics",
      signal_count: 1,
      headline_count: 1,
      watch_count: 0,
      exploration_count: 0,
    },
    {
      key: "citation_acceleration",
      title: "Citation Acceleration",
      description: "Works",
      signal_count: 1,
      headline_count: 0,
      watch_count: 1,
      exploration_count: 0,
    },
    {
      key: "actor_collaboration_novelty",
      title: "Actor/Collaboration Novelty",
      description: "Actors",
      signal_count: 1,
      headline_count: 0,
      watch_count: 0,
      exploration_count: 1,
    },
  ],
  signals: [
    {
      signal_id: "sig:tm:T1",
      detector: {
        key: "topic_momentum",
        title: "Topic Momentum",
        type: "topic_momentum",
        version: "topic-momentum/0.1",
      },
      subject: { kind: "topic", id: "T1", label: "Scientific Computing" },
      signal_label: "RISING",
      scale_corroboration: {
        concordance: "CONTRADICTED",
        subfield_direction: "FALLING",
        field_direction: null,
        note: "opposite_parent_direction",
      },
      priority: { score: 0.9 },
      confidence: { level: "HIGH", limitations: ["LIMIT_TM"] },
      editorial: {
        tier: "HEADLINE_CANDIDATE",
        review_status: "REQUIRED",
        review_reasons: [],
      },
      summary: {
        headline: "Scientific Computing progresse",
        why_unusual: "Le volume augmente nettement.",
      },
      why_unusual: "Le volume augmente nettement.",
      analysis_context: {
        current_window: { start: "2025-07-01", end: "2026-06-30" },
        reference: {
          kind: "historical_window",
          reference_id: "previous",
          window: { start: "2024-07-01", end: "2025-06-30" },
        },
      },
      temporal_context: {
        mode: "retrospective_reconstruction",
        emitted_at: "2026-08-31T09:46:36Z",
        information_cutoff: "2026-06-30T23:59:59Z",
        observation_vintage: "2026-08-29T10:45:42Z",
        cutoff_basis: "publication_date",
      },
      quality_flags: [],
      provenance: { code_version: "research-signal-instrument/0.5.0" },
      metrics: { current_count: 10, reference_count: 3, direction_streak: 3 },
      payload: {},
      evidence_refs: [
        {
          evidence_id: "proof-1",
          type: "observation",
          role: "current_window",
          observed_at: "2026-08-29T10:45:42Z",
          locator: { kind: "work_observation", id: "W1" },
          supports: "Work 1",
        },
      ],
      evidence_bundle_id: "bundle-tm",
      evidence_bundle_available: true,
      dossier_path: "dossiers/by-topic/T1-2026-06-30.md",
      limitations: ["LIMIT_TM"],
      feed_rank: 1,
    },
    {
      signal_id: "sig:ca:W1",
      detector: {
        key: "citation_acceleration",
        title: "Citation Acceleration",
        type: "citation_acceleration",
        version: "citation-acceleration/0.1",
      },
      subject: { kind: "work", id: "W1", label: "Anomaly detection" },
      signal_label: "BREAKOUT",
      priority: { score: 0.8 },
      confidence: { level: "MEDIUM", limitations: [] },
      editorial: { tier: "WATCH", review_status: "OPTIONAL", review_reasons: [] },
      summary: {
        headline: "Anomaly detection accélère",
        why_unusual: "24 citations contre 5.",
      },
      why_unusual: "24 citations contre 5.",
      analysis_context: {
        current_window: { start: "2025-07-01", end: "2026-06-30" },
        reference: {
          kind: "cohort",
          reference_id: "cohort",
          window: { start: "2024-07-01", end: "2025-06-30" },
        },
      },
      temporal_context: {
        mode: "retrospective_reconstruction",
        emitted_at: "2026-09-01T14:52:33Z",
        information_cutoff: "2026-06-30T23:59:59Z",
        observation_vintage: "2026-08-29T10:45:42Z",
        cutoff_basis: "publication_date",
      },
      quality_flags: [],
      provenance: { code_version: "research-signal-instrument/0.9.0" },
      metrics: {
        recent_citation_count: 24,
        previous_citation_count: 5,
        absolute_delta: 19,
        acceleration_ratio: 4.16,
        cohort: { percentile: 1, size: 26 },
      },
      payload: {},
      evidence_refs: [],
      evidence_bundle_id: "bundle-ca",
      evidence_bundle_available: true,
      dossier_path: null,
      limitations: [],
      feed_rank: 2,
    },
    {
      signal_id: "sig:acn:I1",
      detector: {
        key: "actor_collaboration_novelty",
        title: "Actor/Collaboration Novelty",
        type: "actor_collaboration_novelty",
        version: "actor-collaboration-novelty/0.1",
      },
      subject: { kind: "institution", id: "I1", label: "Université X" },
      signal_label: "NEW_EXTERNAL_ACTOR",
      priority: { score: 0.7 },
      confidence: { level: "HIGH", limitations: [] },
      editorial: { tier: "EXPLORATION", review_status: "OPTIONAL", review_reasons: [] },
      summary: {
        headline: "Université X apparaît",
        why_unusual: "Trois œuvres sur trois mois.",
      },
      why_unusual: "Trois œuvres sur trois mois.",
      analysis_context: {
        current_window: { start: "2025-07-01", end: "2026-06-30" },
        reference: {
          kind: "history",
          reference_id: "history",
          window: { start: "2022-07-01", end: "2025-06-30" },
        },
      },
      temporal_context: {
        mode: "retrospective_reconstruction",
        emitted_at: "2026-09-01T19:45:23Z",
        information_cutoff: "2026-06-30T23:59:59Z",
        observation_vintage: "2026-08-29T10:45:42Z",
        cutoff_basis: "publication_date",
      },
      quality_flags: [],
      provenance: { code_version: "research-signal-instrument/0.13.0" },
      metrics: {
        current_work_count: 3,
        current_active_months: 3,
        recent_baseline_work_count: 0,
        older_history_work_count: 0,
        distinct_topic_count: 2,
        distinct_author_pair_count_lower_bound: 4,
      },
      payload: {},
      evidence_refs: [],
      evidence_bundle_id: "bundle-acn",
      evidence_bundle_available: true,
      dossier_path: null,
      limitations: [],
      feed_rank: 3,
    },
  ],
  evidence_by_id: {
    "bundle-tm": { summary: "proof tm" },
    "bundle-ca": {
      monthly_timeline: [
        { month: "2025-07", primary_count: 2 },
        { month: "2025-08", primary_count: 5 },
      ],
    },
    "bundle-acn": {
      history: {
        windows: {
          current: {
            monthly_work_counts: [
              { month: "2025-07", work_count: 1 },
              { month: "2025-08", work_count: 2 },
            ],
          },
        },
      },
    },
  },
  backtests: {
    topic_momentum: {
      available: true,
      result: {},
      summary: { horizons: { "+12m": { overall: { observed: 10, strict_retention_rate: 0.5, directional_survival_rate: 0.7, non_reversal_rate: 0.8 } } } },
      quality: {},
      extra: {},
    },
    citation_acceleration: {
      available: false,
      result: null,
      summary: null,
      quality: null,
      extra: {},
    },
    actor_collaboration_novelty: {
      available: true,
      result: {},
      summary: { replayed_signal_count: 8, unique_subject_count: 6, observed_outcome_count: 5, continued_count: 2, continuation_rate: 0.4 },
      quality: {},
      extra: {},
    },
  },
  top_topics: [
    {
      topic_id: "T_BIG",
      label: "Big stable theme",
      subfield: "Materials",
      total_count: 150,
      current_count: 20,
      previous_count: 22,
      direction: "STABLE",
      presence: "PERSISTING",
    },
    {
      topic_id: "T1",
      label: "Scientific Computing",
      subfield: "Computer Science",
      total_count: 40,
      current_count: 10,
      previous_count: 3,
      direction: "RISING",
      presence: "PERSISTING",
    },
  ],
  warnings: ["RETROSPECTIVE_RECONSTRUCTION"],
};

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  it("applies combined filters and resets them", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    expect(screen.getByRole("button", { name: "Scientific Computing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anomaly detection" })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Détecteur"), "citation_acceleration");
    await user.selectOptions(screen.getByLabelText("Confiance"), "MEDIUM");
    await user.type(screen.getByLabelText("Recherche"), "anomaly");

    expect(screen.getByRole("button", { name: "Anomaly detection" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Scientific Computing" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Réinitialiser" }));
    expect(screen.getByRole("button", { name: "Scientific Computing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Université X" })).toBeInTheDocument();
  });

  it("adapts change-type choices to the selected detector", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    await user.selectOptions(screen.getByLabelText("Détecteur"), "citation_acceleration");

    expect(
      screen.getByRole("option", { name: "Décollage des citations" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Hausse inhabituelle du thème" }),
    ).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Type de changement"), "BREAKOUT");
    expect(screen.getByRole("button", { name: "Anomaly detection" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Scientific Computing" })).not.toBeInTheDocument();
  });

  it("shows a single non-redundant dossier and keeps the filtered feed", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    await user.selectOptions(screen.getByLabelText("Détecteur"), "topic_momentum");
    await user.click(screen.getByRole("button", { name: "Scientific Computing" }));

    expect(screen.getByRole("heading", { name: "Scientific Computing" })).toBeInTheDocument();
    expect(screen.getByText("Pourquoi c’est inhabituel")).toBeInTheDocument();
    // why_unusual must appear exactly once (no card/panel duplication)
    expect(screen.getAllByText("Le volume augmente nettement.")).toHaveLength(1);
    expect(screen.getByText("Publications par fenêtre")).toBeInTheDocument();
    // traceability codes live only inside the collapsible technical block
    expect(screen.getByText("Références techniques (traçabilité)")).toBeInTheDocument();
    expect(screen.getByText("bundle-tm")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anomaly detection" })).not.toBeInTheDocument();
  });

  it("surfaces scale corroboration as a badge and a filter", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    // The contradicted topic signal shows a "Contredit" badge (card + panel).
    expect(screen.getAllByText("Contredit").length).toBeGreaterThan(0);

    // Filtering by "Contredit par le sous-domaine" keeps only the topic signal.
    await user.selectOptions(
      screen.getByLabelText("Corroboration"),
      "CONTRADICTED",
    );
    expect(screen.getByRole("button", { name: "Scientific Computing" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anomaly detection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Université X" })).not.toBeInTheDocument();

    // The corroboration filter is dynamic: it disappears for a detector whose
    // signals carry no concordance (citation acceleration here).
    await user.selectOptions(screen.getByLabelText("Détecteur"), "citation_acceleration");
    expect(screen.queryByLabelText("Corroboration")).not.toBeInTheDocument();
  });

  it("shows the indicators help accordion and no reading-priority filter", () => {
    render(<App initialData={bundle} />);
    expect(screen.getByText("Comment lire les indicateurs")).toBeInTheDocument();
    expect(screen.getByText("Signal saillant")).toBeInTheDocument();
    // the reading-priority tier flag has been removed from the UI
    expect(screen.queryByLabelText("Priorité de lecture")).not.toBeInTheDocument();
    expect(screen.queryByText("À surveiller")).not.toBeInTheDocument();
  });

  it("switches the interface language to English and back", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    // Defaults to French.
    expect(screen.getByText("Comment lire les indicateurs")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByText("How to read the indicators")).toBeInTheDocument();
    expect(screen.getByLabelText("Detector")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "FR" }));
    expect(screen.getByText("Comment lire les indicateurs")).toBeInTheDocument();
  });

  it("switches to the stock view and links a theme back to the flux", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    await user.click(screen.getByRole("tab", { name: "Stock — plus gros thèmes" }));
    expect(screen.getByText("Plus gros thèmes du portefeuille")).toBeInTheDocument();
    // Ranked by total volume: the big theme comes first.
    expect(screen.getByText("Big stable theme")).toBeInTheDocument();

    // A theme that has a signal is a link; clicking it opens the flux dossier.
    await user.click(screen.getByRole("button", { name: "Scientific Computing" }));
    expect(screen.getByRole("heading", { name: "Scientific Computing" })).toBeInTheDocument();
  });

  it("translates raw quality flags into plain language", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    await user.click(screen.getByRole("button", { name: "Scientific Computing" }));
    // LIMIT_TM is an unknown code -> humanized, never shown raw in the main read
    expect(screen.getByText("Point technique : Limit tm")).toBeInTheDocument();
  });

  it("renders the context view from detector evidence", async () => {
    const user = userEvent.setup();
    render(<App initialData={bundle} />);

    await user.click(screen.getByRole("button", { name: "Anomaly detection" }));
    expect(screen.getByText("Citations observées par mois")).toBeInTheDocument();
    expect(screen.getByLabelText("Citations observées par mois")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Université X" }));
    expect(screen.getByLabelText("Relation institutionnelle observée")).toBeInTheDocument();
    expect(screen.getByText("Publications matérialisant la relation")).toBeInTheDocument();
  });
});
