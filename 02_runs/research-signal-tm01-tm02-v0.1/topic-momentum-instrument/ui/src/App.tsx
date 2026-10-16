import { useEffect, useDeferredValue, useState } from "react";
import type {
  DetectorKey,
  PocBundle,
  SignalRecord,
  TopTopic,
} from "./types";
import { LangProvider, LanguageSwitch, useI18n } from "./i18n";
import type { Lang, Translate } from "./i18n";

const BUNDLE_URL = "/data/research-signal-poc.json";

interface AppProps {
  initialData?: PocBundle;
}

export function App({ initialData }: AppProps) {
  return (
    <LangProvider>
      <AppInner initialData={initialData} />
    </LangProvider>
  );
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: PocBundle };

type Filters = {
  detector: DetectorKey | "all";
  signalLabel: "all" | string;
  confidence: "all" | string;
  scale: "all" | string;
  query: string;
};

const DEFAULT_FILTERS: Filters = {
  detector: "all",
  signalLabel: "all",
  confidence: "all",
  scale: "all",
  query: "",
};

function AppInner({ initialData }: AppProps) {
  const { t, lang } = useI18n();
  const [state, setState] = useState<LoadState>(
    initialData ? { status: "ready", data: initialData } : { status: "loading" },
  );
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [view, setView] = useState<"flux" | "stock">("flux");
  const deferredQuery = useDeferredValue(filters.query.trim().toLowerCase());

  useEffect(() => {
    if (initialData) {
      return;
    }
    let cancelled = false;
    fetch(BUNDLE_URL)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(t("load.failed", { status: response.status }));
        }
        return (await response.json()) as PocBundle;
      })
      .then((data) => {
        if (!cancelled) {
          setState({ status: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : t("load.unknown"),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [initialData, t]);

  if (state.status === "loading") {
    return <StatusScreen title={t("status.loading.title")} body={t("status.loading.body")} />;
  }
  if (state.status === "error") {
    return <StatusScreen title={t("status.error.title")} body={state.message} />;
  }

  const { data } = state;
  const labelOptions = signalLabelOptions(data.signals, filters.detector, t);
  const scaleOptions = scaleConcordanceOptions(data.signals, filters.detector);
  const topTopics = data.top_topics ?? [];
  const topicSignalIds = new Set<string>(
    data.signals
      .filter((signal) => signal.detector.key === "topic_momentum")
      .map((signal) => signal.subject.id),
  );
  const openTopicSignal = (topicId: string) => {
    const match = data.signals.find(
      (signal) => signal.detector.key === "topic_momentum" && signal.subject.id === topicId,
    );
    if (match) {
      setSelectedSignalId(match.signal_id);
      setView("flux");
    }
  };

  const filteredSignals = data.signals.filter((signal) => {
    if (filters.detector !== "all" && signal.detector.key !== filters.detector) return false;
    if (filters.signalLabel !== "all" && signal.signal_label !== filters.signalLabel) return false;
    if (filters.confidence !== "all" && signal.confidence.level !== filters.confidence) return false;
    if (filters.scale !== "all" && concordanceOf(signal) !== filters.scale) return false;
    if (!deferredQuery) return true;
    const haystack = [
      signal.summary?.headline,
      signal.subject.label,
      signal.signal_label,
      signal.why_unusual,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(deferredQuery);
  });

  const selectedSignal =
    filteredSignals.find((signal) => signal.signal_id === selectedSignalId) ??
    data.signals.find((signal) => signal.signal_id === selectedSignalId) ??
    filteredSignals[0] ??
    null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{t("app.eyebrow")}</p>
          <h1>{data.source.portfolio_label}</h1>
          <p className="subhead">
            {t("header.scope")} : <strong>{scopeDescription(data.source.scope_mode, t)}</strong> ·{" "}
            {t("header.cutoff")}{" "}
            <strong>{formatDate(data.source.information_cutoff, lang)}</strong> ·{" "}
            {t("header.collected")}{" "}
            <strong>{formatDateTime(data.source.observation_vintage, lang)}</strong>
          </p>
        </div>
        <div className="topbar-side">
          <LanguageSwitch />
          <div className="signal-breakdown">
            <MetricCard
              label={t("header.themes")}
              value={String(countByDetector(data.signals, "topic_momentum"))}
              compact
            />
            <MetricCard
              label={t("header.works")}
              value={String(countByDetector(data.signals, "citation_acceleration"))}
              compact
            />
            <MetricCard
              label={t("header.actors")}
              value={String(countByDetector(data.signals, "actor_collaboration_novelty"))}
              compact
            />
          </div>
        </div>
      </header>

      <section className="warning-strip">
        <strong>{t("warning.title")}</strong> {t("warning.body")}
      </section>

      <IndicatorsHelp />

      <section className="detector-grid" aria-label="Cartes détecteur">
        {data.detectors.map((detector) => (
          <article key={detector.key} className="panel detector-card">
            <div className="panel-header">
              <h2>{detectorDisplayName(detector.key, t)}</h2>
            </div>
            <p className="detector-copy">{detectorDescription(detector.key, t)}</p>
            <DetectorConfidenceBar
              signals={data.signals.filter((signal) => signal.detector.key === detector.key)}
            />
          </article>
        ))}
      </section>

      <div className="view-tabs" role="tablist" aria-label="Vue">
        <button
          type="button"
          role="tab"
          aria-selected={view === "flux"}
          className={`view-tab ${view === "flux" ? "active" : ""}`}
          onClick={() => setView("flux")}
        >
          {t("tab.flux")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "stock"}
          className={`view-tab ${view === "stock" ? "active" : ""}`}
          onClick={() => setView("stock")}
        >
          {t("tab.stock")}
        </button>
      </div>

      {view === "stock" ? (
        <StockView topTopics={topTopics} signalTopicIds={topicSignalIds} onOpenTopic={openTopicSignal} />
      ) : (
        <section className="workspace">
          <div className="panel feed-panel">
            <div className="panel-header">
              <h2>{t("feed.title")}</h2>
              <span className="muted">{t("feed.subtitle")}</span>
            </div>
            <FilterBar
              filters={filters}
              labelOptions={labelOptions}
              scaleOptions={scaleOptions}
              onChange={setFilters}
            />
            {filteredSignals.length === 0 ? (
              <div className="empty-state">{t("feed.empty")}</div>
            ) : (
              <ul className="signal-list">
                {filteredSignals.map((signal) => (
                  <li key={signal.signal_id}>
                    <SignalCard
                      isSelected={selectedSignal?.signal_id === signal.signal_id}
                      onSelect={() => setSelectedSignalId(signal.signal_id)}
                      signal={signal}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>

          <aside className="panel context-panel">
            {selectedSignal ? (
              <SignalDetail
                evidence={data.evidence_by_id[selectedSignal.evidence_bundle_id ?? ""]}
                signal={selectedSignal}
              />
            ) : (
              <div className="empty-state">{t("feed.detail_empty")}</div>
            )}
          </aside>
        </section>
      )}
    </div>
  );
}

function StatusScreen({ title, body }: { title: string; body: string }) {
  return (
    <div className="status-screen">
      <div className="panel status-panel">
        <h1>{title}</h1>
        <p>{body}</p>
      </div>
    </div>
  );
}

function FilterBar({
  filters,
  labelOptions,
  scaleOptions,
  onChange,
}: {
  filters: Filters;
  labelOptions: Array<{ value: string; label: string }>;
  scaleOptions: string[];
  onChange: (value: Filters) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="filter-bar">
      <label>
        {t("filter.detector")}
        <select
          aria-label={t("filter.detector")}
          value={filters.detector}
          onChange={(event) =>
            onChange({
              ...filters,
              detector: event.target.value as Filters["detector"],
              signalLabel: "all",
              scale: "all",
            })
          }
        >
          <option value="all">{t("filter.detector.all")}</option>
          <option value="topic_momentum">{t("detector.topic_momentum.name")}</option>
          <option value="citation_acceleration">{t("detector.citation_acceleration.name")}</option>
          <option value="actor_collaboration_novelty">
            {t("detector.actor_collaboration_novelty.name")}
          </option>
        </select>
      </label>
      <label>
        {t("filter.change")}
        <select
          aria-label={t("filter.change")}
          value={filters.signalLabel}
          onChange={(event) => onChange({ ...filters, signalLabel: event.target.value })}
        >
          <option value="all">{t("filter.change.all")}</option>
          {labelOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("filter.confidence")}
        <select
          aria-label={t("filter.confidence")}
          value={filters.confidence}
          onChange={(event) => onChange({ ...filters, confidence: event.target.value })}
        >
          <option value="all">{t("filter.confidence.all")}</option>
          <option value="HIGH">{t("conf.HIGH")}</option>
          <option value="MEDIUM">{t("conf.MEDIUM")}</option>
          <option value="LOW">{t("conf.LOW")}</option>
        </select>
      </label>
      {scaleOptions.length > 0 ? (
        <label>
          {t("filter.corroboration")}
          <select
            aria-label={t("filter.corroboration")}
            value={filters.scale}
            onChange={(event) => onChange({ ...filters, scale: event.target.value })}
          >
            <option value="all">{t("filter.corroboration.all")}</option>
            {scaleOptions.map((value) => (
              <option key={value} value={value}>
                {t(`scale.opt.${value}`)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="search-field">
        {t("filter.search")}
        <input
          aria-label={t("filter.search")}
          value={filters.query}
          onChange={(event) => onChange({ ...filters, query: event.target.value })}
          placeholder={t("filter.search.placeholder")}
        />
      </label>
      <button type="button" className="reset-button" onClick={() => onChange(DEFAULT_FILTERS)}>
        {t("filter.reset")}
      </button>
    </div>
  );
}

function SignalCard({
  signal,
  isSelected,
  onSelect,
}: {
  signal: SignalRecord;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { t, lang } = useI18n();
  return (
    <article className={`signal-card ${isSelected ? "selected" : ""}`}>
      <button aria-label={signal.subject.label} type="button" className="signal-summary" onClick={onSelect}>
        <span className="signal-title">{signal.subject.label}</span>
        <span className="badge-group">
          <SignalLabelBadge label={signal.signal_label} />
          <ScaleBadge signal={signal} />
        </span>
      </button>
      <div className="signal-foot">
        <span>{detectorDisplayName(signal.detector.key, t)}</span>
        <span>
          {t("card.priority")} : {formatNumber(signal.priority.score, lang)}
        </span>
        <span>
          {t("card.confidence")} : {confidenceDescription(signal.confidence.level, t)}
        </span>
      </div>
    </article>
  );
}

function SignalDetail({
  signal,
  evidence,
}: {
  signal: SignalRecord;
  evidence: Record<string, unknown> | undefined;
}) {
  const { t, lang } = useI18n();
  return (
    <div className="context-content">
      <div className="detail-head">
        <p className="eyebrow">
          {t("dossier.eyebrow")} · {detectorDisplayName(signal.detector.key, t)}
        </p>
        <h2>{signal.subject.label}</h2>
        <div className="badge-group context-badges">
          <SignalLabelBadge label={signal.signal_label} />
          <ScaleBadge signal={signal} />
        </div>
      </div>

      <section className="detail-block">
        <h3>{t("dossier.why")}</h3>
        <p>{signal.why_unusual || signal.summary?.why_unusual || t("dossier.info_absent")}</p>
      </section>

      <div className="signal-essentials">
        <div>
          <span>{t("dossier.priority")}</span>
          <strong>{formatNumber(signal.priority.score, lang)}</strong>
        </div>
        <div>
          <span>{t("dossier.confidence")}</span>
          <strong>{confidenceDescription(signal.confidence.level, t)}</strong>
        </div>
        <div>
          <span>{t("dossier.change")}</span>
          <strong>{signalLabelDescription(signal.signal_label, t)}</strong>
        </div>
      </div>

      {signal.editorial.review_status === "REQUIRED" ? (
        <p className="review-callout">
          {t("dossier.review")}
          {reviewReasonSuffix(signal.editorial.review_reasons, t)}.
        </p>
      ) : null}

      <ScaleNote signal={signal} />

      {signal.detector.key === "topic_momentum" ? <TopicContext evidence={evidence} signal={signal} /> : null}
      {signal.detector.key === "citation_acceleration" ? (
        <CitationContext evidence={evidence} signal={signal} />
      ) : null}
      {signal.detector.key === "actor_collaboration_novelty" ? (
        <ActorContext evidence={evidence} signal={signal} />
      ) : null}

      <section className="detail-block">
        <h3>{t("dossier.metrics")}</h3>
        <dl className="metric-list">
          {detectorMetrics(signal, t).map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <ContextDocuments evidence={evidence} />

      <FlagList codes={[...signal.limitations, ...signal.quality_flags]} />

      <TechnicalRefs signal={signal} evidence={evidence} />
    </div>
  );
}

function TopicContext({
  signal,
  evidence,
}: {
  signal: SignalRecord;
  evidence: Record<string, unknown> | undefined;
}) {
  const { t } = useI18n();
  return (
    <>
      <p className="context-copy">{t("ctx.topic.copy")}</p>
      <ComparisonChart
        items={[
          { label: t("ctx.window.studied"), value: numberValue(signal.metrics.current_count) },
          { label: t("ctx.window.year_before"), value: numberValue(signal.metrics.reference_count) },
        ]}
        title={t("ctx.topic.chart_pub")}
      />
      <ComparisonChart
        rate
        items={[
          { label: t("ctx.window.studied"), value: numberValue(signal.metrics.current_share) },
          { label: t("ctx.window.year_before"), value: numberValue(signal.metrics.reference_share) },
        ]}
        title={t("ctx.topic.chart_share")}
      />
      <ContextCaption evidence={evidence} />
    </>
  );
}

function CitationContext({
  signal,
  evidence,
}: {
  signal: SignalRecord;
  evidence: Record<string, unknown> | undefined;
}) {
  const { t } = useI18n();
  const evidenceRecord = asRecord(evidence);
  return (
    <>
      <p className="context-copy">{t("ctx.citation.copy")}</p>
      <ComparisonChart
        items={[
          { label: t("ctx.window.studied"), value: numberValue(signal.metrics.recent_citation_count) },
          { label: t("ctx.window.previous"), value: numberValue(signal.metrics.previous_citation_count) },
        ]}
        title={t("ctx.citation.chart_win")}
      />
      <TimelineChart
        points={timelinePoints(evidenceRecord.monthly_timeline, "primary_count")}
        title={t("ctx.citation.chart_month")}
      />
    </>
  );
}

function ActorContext({
  signal,
  evidence,
}: {
  signal: SignalRecord;
  evidence: Record<string, unknown> | undefined;
}) {
  const { t } = useI18n();
  const evidenceRecord = asRecord(evidence);
  const history = asRecord(evidenceRecord.history);
  const windows = asRecord(history.windows);
  const currentWindow = asRecord(windows.current);
  const anchor = asRecord(signal.metrics.anchor_institution);
  const external = asRecord(signal.metrics.external_institution);
  return (
    <>
      <p className="context-copy">{t("ctx.actor.copy")}</p>
      <div className="relationship-diagram" aria-label={t("ctx.actor.relation")}>
        <div className="relationship-node anchor-node">
          <span>{t("ctx.actor.internal")}</span>
          <strong>{formatUnknown(anchor.label, t)}</strong>
        </div>
        <div className="relationship-link">
          <strong>{formatUnknown(signal.metrics.current_work_count, t)}</strong>
          <span>{t("ctx.actor.publications")}</span>
        </div>
        <div className="relationship-node external-node">
          <span>{t("ctx.actor.external")}</span>
          <strong>{formatUnknown(external.label, t)}</strong>
        </div>
      </div>
      <TimelineChart
        points={timelinePoints(currentWindow.monthly_work_counts, "work_count")}
        title={t("ctx.actor.chart_rel")}
      />
    </>
  );
}

function ComparisonChart({
  title,
  items,
  rate = false,
}: {
  title: string;
  items: Array<{ label: string; value: number | null }>;
  rate?: boolean;
}) {
  const { t, lang } = useI18n();
  const available = items.flatMap((item) => (item.value === null ? [] : [item.value]));
  const maximum = Math.max(...available, 1);
  const fmt = (value: number) => (rate ? formatRate(value, lang) : formatNumber(value, lang));
  return (
    <figure className="context-chart">
      <figcaption>{title}</figcaption>
      {available.length === 0 ? (
        <p className="muted">{t("ctx.data_absent")}</p>
      ) : (
        <div className="comparison-bars">
          {items.map((item) => (
            <div key={item.label} className="comparison-row">
              <span>{item.label}</span>
              <div className="bar-track">
                <span
                  className="bar-fill"
                  style={{ width: `${item.value === null ? 0 : Math.max((item.value / maximum) * 100, 3)}%` }}
                />
              </div>
              <strong>{item.value === null ? t("value.absent") : fmt(item.value)}</strong>
            </div>
          ))}
        </div>
      )}
    </figure>
  );
}

function TimelineChart({
  title,
  points,
}: {
  title: string;
  points: Array<{ label: string; value: number }>;
}) {
  const { t } = useI18n();
  const maximum = Math.max(...points.map((point) => point.value), 1);
  return (
    <figure className="context-chart">
      <figcaption>{title}</figcaption>
      {points.length === 0 ? (
        <p className="muted">{t("ctx.timeline_absent")}</p>
      ) : (
        <>
          <div className="timeline-bars" aria-label={title}>
            {points.map((point) => (
              <span
                key={point.label}
                aria-label={`${point.label} : ${point.value}`}
                className="timeline-bar"
                style={{ height: `${Math.max((point.value / maximum) * 100, 5)}%` }}
                title={`${point.label} : ${point.value}`}
              />
            ))}
          </div>
          <div className="timeline-labels">
            <span>{points[0].label}</span>
            <span>{points[points.length - 1].label}</span>
          </div>
        </>
      )}
    </figure>
  );
}

function ContextCaption({ evidence }: { evidence: Record<string, unknown> | undefined }) {
  const { t } = useI18n();
  const evaluationDate = formatUnknown(asRecord(evidence).evaluation_date, t);
  if (evaluationDate === t("value.absent")) {
    return null;
  }
  return (
    <p className="muted">
      {t("ctx.eval_date")} {evaluationDate}.
    </p>
  );
}

function ContextDocuments({ evidence }: { evidence: Record<string, unknown> | undefined }) {
  const { t, lang } = useI18n();
  const documents = asArray(asRecord(evidence).representative_works)
    .slice(0, 3)
    .map((item) => asRecord(item));
  return (
    <section className="detail-block context-documents">
      <h3>{t("dossier.docs")}</h3>
      {documents.length === 0 ? (
        <p className="muted">{t("dossier.docs_absent")}</p>
      ) : (
        <ul>
          {documents.map((document, index) => (
            <li key={String(document.work_id ?? document.observation_id ?? index)}>
              <strong>{formatUnknown(document.title, t)}</strong>
              <span>{formatDate(String(document.publication_date ?? ""), lang)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FlagList({ codes }: { codes: string[] }) {
  const { t } = useI18n();
  const unique = [...new Set(codes)];
  return (
    <section className="detail-block">
      <h3>{t("dossier.flags")}</h3>
      {unique.length === 0 ? (
        <p className="muted">{t("dossier.flags_none")}</p>
      ) : (
        <ul className="flag-list">
          {unique.map((code) => (
            <li key={code}>{flagDescription(code, t)}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TechnicalRefs({
  signal,
  evidence,
}: {
  signal: SignalRecord;
  evidence: Record<string, unknown> | undefined;
}) {
  const { t, lang } = useI18n();
  return (
    <details className="tech-refs">
      <summary>{t("dossier.tech")}</summary>
      <div className="detail-grid">
        <InfoLine label={t("tech.signal_id")} value={signal.signal_id} />
        <InfoLine label={t("tech.change_code")} value={signal.signal_label} />
        <InfoLine label={t("tech.detector_version")} value={signal.detector.version} />
        <InfoLine label={t("tech.code_version")} value={signal.provenance.code_version || t("value.absent")} />
        <InfoLine label={t("tech.cutoff")} value={formatDateTime(signal.temporal_context.information_cutoff, lang)} />
        <InfoLine label={t("tech.collected")} value={formatDateTime(signal.temporal_context.observation_vintage, lang)} />
        <InfoLine label={t("tech.method")} value={temporalModeDescription(signal.temporal_context.mode, t)} />
        <InfoLine label={t("tech.bundle")} value={signal.evidence_bundle_id || t("value.absent_m")} />
      </div>
      {signal.evidence_refs.length > 0 ? (
        <>
          <h4>{t("tech.evidence")}</h4>
          <ul className="evidence-list">
            {signal.evidence_refs.slice(0, 8).map((item) => (
              <li key={item.evidence_id}>
                <strong>{item.locator.id}</strong> · {item.role} · {item.supports}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {signal.evidence_bundle_available && evidence ? (
        <>
          <h4>{t("tech.bundle_full")}</h4>
          <pre className="evidence-bundle">{JSON.stringify(evidence, null, 2)}</pre>
        </>
      ) : null}
    </details>
  );
}

function IndicatorsHelp() {
  const { t } = useI18n();
  const entries: Array<[string, string]> = [
    [t("help.salient.term"), t("help.salient.def")],
    [t("help.priority.term"), t("help.priority.def")],
    [t("help.confidence.term"), t("help.confidence.def")],
    [t("help.corroboration.term"), t("help.corroboration.def")],
  ];
  return (
    <details className="indicators-help">
      <summary>{t("help.summary")}</summary>
      <dl className="indicators-help-body">
        {entries.map(([term, def]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{def}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function DetectorConfidenceBar({ signals }: { signals: SignalRecord[] }) {
  const { t } = useI18n();
  const total = signals.length;
  const high = signals.filter((signal) => signal.confidence.level === "HIGH").length;
  const medium = signals.filter((signal) => signal.confidence.level === "MEDIUM").length;
  const low = total - high - medium;
  const segments = [
    { key: "high", label: t("conf.compo.high"), value: high, cls: "high" },
    { key: "medium", label: t("conf.compo.medium"), value: medium, cls: "medium" },
    { key: "low", label: t("conf.compo.low"), value: low, cls: "low" },
  ];
  const barLabel = segments.map((segment) => `${segment.value} ${segment.label}`).join(", ");
  return (
    <div className="tier-overview">
      <div className="tier-total">
        <strong>{total}</strong>
        <span>{t("detector.signals")}</span>
      </div>
      <div className="tier-bar" role="img" aria-label={barLabel}>
        {segments
          .filter((segment) => segment.value > 0)
          .map((segment) => (
            <span
              key={segment.key}
              className={`tier-seg ${segment.cls}`}
              style={{ flexGrow: segment.value }}
              title={`${segment.label} : ${segment.value}`}
            />
          ))}
      </div>
      <ul className="tier-legend">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className={`tier-dot ${segment.cls}`} />
            {segment.label} <strong>{segment.value}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StockView({
  topTopics,
  signalTopicIds,
  onOpenTopic,
}: {
  topTopics: TopTopic[];
  signalTopicIds: Set<string>;
  onOpenTopic: (topicId: string) => void;
}) {
  const { t } = useI18n();
  if (topTopics.length === 0) {
    return (
      <section className="panel stock-panel">
        <div className="empty-state">{t("stock.unavailable")}</div>
      </section>
    );
  }
  const maximum = Math.max(...topTopics.map((topic) => topic.total_count), 1);
  const rising = topTopics.filter((topic) => topic.direction === "RISING").length;
  const falling = topTopics.filter((topic) => topic.direction === "FALLING").length;
  return (
    <section className="panel stock-panel">
      <div className="panel-header">
        <h2>{t("stock.title")}</h2>
        <span className="muted">
          {t("stock.summary", { count: topTopics.length, rising, falling })}
        </span>
      </div>
      <p className="muted stock-intro">{t("stock.intro")}</p>
      <ol className="stock-list">
        {topTopics.map((topic, index) => {
          const hasSignal = signalTopicIds.has(topic.topic_id);
          return (
            <li key={topic.topic_id} className="stock-row">
              <span className="stock-rank">{index + 1}</span>
              <div className="stock-main">
                <div className="stock-label">
                  {hasSignal ? (
                    <button type="button" className="stock-link" onClick={() => onOpenTopic(topic.topic_id)}>
                      {topic.label}
                    </button>
                  ) : (
                    <span>{topic.label}</span>
                  )}
                  <StockDirectionBadge direction={topic.direction} />
                </div>
                <div className="stock-bar" aria-hidden="true">
                  <span
                    className="stock-fill"
                    style={{ width: `${Math.max((topic.total_count / maximum) * 100, 2)}%` }}
                  />
                </div>
                <div className="stock-meta">
                  {topic.subfield ? `${topic.subfield} · ` : ""}
                  {t("stock.meta", { count: topic.total_count, current: topic.current_count })}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function StockDirectionBadge({ direction }: { direction?: string | null }) {
  const { t } = useI18n();
  if (!direction || direction === "UNDETERMINED") {
    return null;
  }
  const cls = direction === "RISING" ? "rising" : direction === "FALLING" ? "falling" : "stable";
  const text = t(`dir.${direction}`) === `dir.${direction}` ? direction : t(`dir.${direction}`);
  return <span className={`badge stock-dir ${cls}`}>{text}</span>;
}

function countByDetector(signals: SignalRecord[], key: DetectorKey): number {
  return signals.filter((signal) => signal.detector.key === key).length;
}

function MetricCard({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div className={`metric-card ${compact ? "compact" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SignalLabelBadge({ label }: { label: string }) {
  const { t } = useI18n();
  return <span className={`badge qualification ${signalLabelClass(label)}`}>{signalLabelBadgeText(label, t)}</span>;
}

function ScaleBadge({ signal }: { signal: SignalRecord }) {
  const { t } = useI18n();
  const concordance = concordanceOf(signal);
  if (!concordance || concordance === "NEUTRAL") {
    return null;
  }
  return (
    <span className={`badge scale ${scaleConcordanceClass(concordance)}`}>
      {t(`scale.badge.${concordance}`)}
    </span>
  );
}

function ScaleNote({ signal }: { signal: SignalRecord }) {
  const { t } = useI18n();
  const concordance = concordanceOf(signal);
  if (!concordance || concordance === "NEUTRAL") {
    return null;
  }
  const subfield = signal.scale_corroboration?.subfield_direction;
  const subfieldText = subfield ? ` (${t("scale.subfield")} ${directionText(subfield, t)})` : "";
  return (
    <p className={`scale-note ${scaleConcordanceClass(concordance)}`}>
      {t(`scale.sentence.${concordance}`)}
      {subfieldText}
    </p>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

// ---- helpers (pure) ----

function concordanceOf(signal: SignalRecord): string | null {
  return signal.scale_corroboration?.concordance ?? null;
}

function detectorDisplayName(key: string, t: Translate): string {
  const value = t(`detector.${key}.name`);
  return value === `detector.${key}.name` ? key : value;
}

function detectorDescription(key: DetectorKey, t: Translate): string {
  return t(`detector.${key}.desc`);
}

function signalLabelOptions(
  signals: SignalRecord[],
  detector: DetectorKey | "all",
  t: Translate,
): Array<{ value: string; label: string }> {
  const visible = detector === "all" ? signals : signals.filter((signal) => signal.detector.key === detector);
  return [...new Set(visible.map((signal) => signal.signal_label))]
    .sort()
    .map((value) => ({ value, label: signalLabelDescription(value, t) }));
}

function signalLabelDescription(label: string, t: Translate): string {
  const value = t(`labeldesc.${label}`);
  return value === `labeldesc.${label}` ? humanizeCode(label) : value;
}

function signalLabelBadgeText(label: string, t: Translate): string {
  const value = t(`label.${label}`);
  return value === `label.${label}` ? humanizeCode(label) : value;
}

function signalLabelClass(label: string): string {
  if (label === "FALLING") return "falling";
  if (label === "RISING" || label === "BREAKOUT" || label === "ACCELERATING") return "rising";
  return "novelty";
}

function confidenceDescription(level: string, t: Translate): string {
  const value = t(`conf.${level}`);
  return value === `conf.${level}` ? level || t("conf.absent") : value;
}

function scaleConcordanceClass(concordance: string): string {
  if (concordance === "CORROBORATED") return "corroborated";
  if (concordance === "CONTRADICTED") return "contradicted";
  return "isolated";
}

function scaleConcordanceOptions(signals: SignalRecord[], detector: DetectorKey | "all"): string[] {
  const visible = detector === "all" ? signals : signals.filter((signal) => signal.detector.key === detector);
  const present = new Set<string>();
  for (const signal of visible) {
    const concordance = concordanceOf(signal);
    if (concordance && concordance !== "NEUTRAL") present.add(concordance);
  }
  return ["CORROBORATED", "ISOLATED_WITHIN_PARENT", "CONTRADICTED"].filter((value) => present.has(value));
}

function directionText(direction: string, t: Translate): string {
  const value = t(`dir.${direction}.long`);
  return value === `dir.${direction}.long` ? direction : value;
}

function reviewReasonSuffix(reasons: string[], t: Translate): string {
  if (!reasons || reasons.length === 0) return "";
  return ` — ${reasons.map((code) => flagDescription(code, t)).join(" ; ")}`;
}

function flagDescription(code: string, t: Translate): string {
  const value = t(`flag.${code}`);
  if (value !== `flag.${code}`) return value;
  return t("flag.generic", { code: humanizeCode(code) });
}

function humanizeCode(code: string): string {
  if (!code) return "—";
  const words = code.toLowerCase().replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function scopeDescription(scope: string, t: Translate): string {
  const value = t(`scope.${scope}`);
  return value === `scope.${scope}` ? scope : value;
}

function temporalModeDescription(mode: string, t: Translate): string {
  const value = t(`temporal.${mode}`);
  return value === `temporal.${mode}` ? mode : value;
}

function detectorMetrics(signal: SignalRecord, t: Translate): Array<{ label: string; value: string }> {
  if (signal.detector.key === "topic_momentum") {
    return [
      metric(t("metric.topic.current"), signal.metrics.current_count, t),
      metric(t("metric.topic.reference"), signal.metrics.reference_count, t),
      metric(t("metric.topic.current_share"), signal.metrics.current_share, t),
      metric(t("metric.topic.reference_share"), signal.metrics.reference_share, t),
      metric(t("metric.topic.percentile"), signal.metrics.historical_percentile, t),
      metric(t("metric.topic.streak"), signal.metrics.direction_streak, t),
    ];
  }
  if (signal.detector.key === "citation_acceleration") {
    return [
      metric(t("metric.cit.current"), signal.metrics.recent_citation_count, t),
      metric(t("metric.cit.previous"), signal.metrics.previous_citation_count, t),
      metric(t("metric.cit.delta"), signal.metrics.absolute_delta, t),
      metric(t("metric.cit.ratio"), signal.metrics.acceleration_ratio, t),
      metric(t("metric.cit.cohort_pct"), asRecord(signal.metrics.cohort ?? signal.payload.cohort).percentile, t),
      metric(t("metric.cit.cohort_size"), asRecord(signal.metrics.cohort ?? signal.payload.cohort).size, t),
    ];
  }
  return [
    metric(t("metric.acn.works"), signal.metrics.current_work_count, t),
    metric(t("metric.acn.months"), signal.metrics.current_active_months, t),
    metric(t("metric.acn.recent"), signal.metrics.recent_baseline_work_count, t),
    metric(t("metric.acn.older"), signal.metrics.older_history_work_count, t),
    metric(t("metric.acn.topics"), signal.metrics.distinct_topic_count, t),
    metric(t("metric.acn.pairs"), signal.metrics.distinct_author_pair_count_lower_bound, t),
  ];
}

function metric(label: string, value: unknown, t: Translate) {
  return { label, value: formatUnknown(value, t) };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function timelinePoints(value: unknown, countKey: string): Array<{ label: string; value: number }> {
  return asArray(value).flatMap((item) => {
    const record = asRecord(item);
    const label = typeof record.month === "string" ? record.month : null;
    const count = numberValue(record[countKey]);
    return label && count !== null ? [{ label, value: count }] : [];
  });
}

function formatUnknown(value: unknown, t: Translate): string {
  if (value === null || value === undefined || value === "") return t("value.absent");
  if (typeof value === "number") return formatNumber(value, "fr");
  if (typeof value === "boolean") return value ? t("value.yes") : t("value.no");
  return String(value);
}

function locale(lang: Lang): string {
  return lang === "en" ? "en-US" : "fr-FR";
}

function formatNumber(value: number, lang: Lang): string {
  return new Intl.NumberFormat(locale(lang), { maximumFractionDigits: 3 }).format(value);
}

function formatRate(value: number, lang: Lang): string {
  return new Intl.NumberFormat(locale(lang), { style: "percent", maximumFractionDigits: 1 }).format(value);
}

function formatDate(value: string, lang: Lang): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "long" }).format(date);
}

function formatDateTime(value: string, lang: Lang): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "medium", timeStyle: "short" }).format(date);
}
