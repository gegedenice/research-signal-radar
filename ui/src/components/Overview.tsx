import { useMemo } from "react";
import type { Bundle, Detector, Label, Works } from "../types";
import type { Action, State } from "../logic/state";
import { LABELS, labelName } from "../logic/feed";
import { fmtQ, int, pct, ratio } from "../logic/format";
import { LABEL_RGB, rgb } from "../theme";
import { S } from "../strings";
import { Chart, cssVar } from "./Chart";

const NAMES: Record<Detector, string> = { topics: "Topics", citations: "Citations", collaborations: "Collaborations" };

export function Overview({ bundle, works, state, dispatch, cutoff }: {
  bundle: Bundle; works: Works | null; state: State; dispatch: (a: Action) => void; cutoff: string | null;
}) {
  return (
    <div className="overview">
      <section>
        <h2>Volcano plots {cutoff ? `· ${cutoff}` : ""}</h2>
        {!cutoff && <p className="muted">Pick a cutoff (2019 or later) on the time bar to see the tested entities.</p>}
        <div className="volcano-grid">
          {cutoff && bundle.detectors.map((d) => <Volcano key={d.key} bundle={bundle} detector={d.key} state={state} dispatch={dispatch} cutoff={cutoff} />)}
        </div>
      </section>
      <section>
        <h2>Signals by cutoff</h2>
        <div className="volcano-grid">
          {bundle.detectors.map((d) => <ByCutoff key={d.key} bundle={bundle} detector={d.key} level={state.levels[d.key]} />)}
        </div>
      </section>
      <SinceLastSweep bundle={bundle} works={works} dispatch={dispatch} />
      <About bundle={bundle} />
    </div>
  );
}

function Volcano({ bundle, detector, state, dispatch, cutoff }: {
  bundle: Bundle; detector: Detector; state: State; dispatch: (a: Action) => void; cutoff: string;
}) {
  const levels = bundle.detectors.find((d) => d.key === detector)!.levels;
  const level = state.levels[detector];
  const v = bundle.volcano[`${detector}|${level}|${cutoff}`];
  const { alpha, min_log2_ratio } = bundle.meta.params;
  const option = useMemo(() => {
    if (!v) return {};
    const groups: Record<string, any[]> = { none: [] };
    v.log2_sr.forEach((x, i) => {
      const q = v.q[i];
      if (x === null || q === null) return;
      const idx = v.signal_idx[i];
      const label = idx >= 0 ? bundle.signals[idx].label : "none";
      (groups[label] ??= []).push({ value: [x, -Math.log10(Math.max(q, 1e-300))], i });
    });
    const line = (coord: any) => ({ lineStyle: { type: "dashed", color: cssVar("--muted") }, ...coord });
    return {
      grid: { left: 8, right: 12, top: 10, bottom: 26, containLabel: true },
      tooltip: {
        formatter: (p: any) => {
          const i = p.data.i, idx = v.signal_idx[i];
          const name = idx >= 0 ? bundle.signals[idx].entity.label ?? v.entity_id[i] : v.entity_id[i];
          return `${name}<br/>share ${ratio(v.log2_sr[i]!)} · q = ${fmtQ(v.q[i]!)}${idx >= 0 ? `<br/>${bundle.signals[idx].label}` : ""}`;
        },
      },
      xAxis: { type: "value", name: "log2 share ratio", nameLocation: "middle", nameGap: 20, splitLine: { lineStyle: { color: cssVar("--border") } } },
      yAxis: { type: "value", name: "−log10 q", splitLine: { lineStyle: { color: cssVar("--border") } } },
      series: Object.entries(groups).map(([label, data]) => ({
        name: label, type: "scatter", data, symbolSize: label === "none" ? 4 : 7, large: data.length > 2000,
        itemStyle: { color: label === "none" ? "rgba(130,140,155,0.45)" : rgb(LABEL_RGB[label as Label]) },
        markLine: label === "none" ? {
          silent: true, symbol: "none", label: { show: false },
          data: [line({ yAxis: -Math.log10(alpha) }), line({ xAxis: min_log2_ratio }), line({ xAxis: -min_log2_ratio })],
        } : undefined,
      })),
    };
  }, [v, bundle, alpha, min_log2_ratio]);
  const onClick = (p: any) => {
    const idx = v?.signal_idx[p.data?.i];
    if (idx !== undefined && idx >= 0) {
      dispatch({ type: "set", patch: { view: "map", tab: detector, selection: { kind: "signal", id: bundle.signals[idx].id } } });
    }
  };
  return (
    <div className="panel">
      <div className="panel-head">
        <strong>{NAMES[detector]}</strong>
        {levels.length > 1 && (
          <span className="seg">
            {levels.map((l) => (
              <button key={l} className={l === level ? "active" : ""} onClick={() => dispatch({ type: "set", patch: { levels: { ...state.levels, [detector]: l } } })}>{l}</button>
            ))}
          </span>
        )}
      </div>
      {v ? (
        <Chart option={option} height={230} onClick={onClick}
          caption={`${int(v.n_tested)} entities tested${v.sampled ? ` (plot shows ${int(v.q.length)}: all signals + lowest q)` : ""}. Dashed: q = ${alpha}, ±${ratio(min_log2_ratio)}. Click a signal to open it.`} />
      ) : (
        <p className="muted small">{bundle.detectors.find((d) => d.key === detector)?.skipped?.[cutoff] ?? "No tested entities at this cutoff."}</p>
      )}
    </div>
  );
}

function ByCutoff({ bundle, detector, level }: { bundle: Bundle; detector: Detector; level: string }) {
  const d = bundle.detectors.find((x) => x.key === detector)!;
  const cutoffs = bundle.meta.cutoffs;
  const labels = detector === "citations" ? (["NEW", "RISING"] as Label[]) : LABELS;
  const option = useMemo(() => ({
    grid: { left: 8, right: 8, top: 24, bottom: 20, containLabel: true },
    legend: { top: 0, textStyle: { color: cssVar("--muted"), fontSize: 11 }, itemHeight: 8 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: cutoffs },
    yAxis: { type: "value", splitLine: { lineStyle: { color: cssVar("--border") } } },
    series: labels.map((l) => ({
      name: labelName(l, detector), type: "bar", stack: "s", itemStyle: { color: rgb(LABEL_RGB[l]) },
      data: cutoffs.map((c) => d.summary[c]?.[level]?.[l] ?? 0),
    })),
  }), [d, cutoffs, labels, level, detector]);
  return (
    <div className="panel">
      <div className="panel-head"><strong>{NAMES[detector]}</strong><span className="muted small">{level}</span></div>
      <Chart option={option} height={180} caption="Number of signals per cutoff, by label." />
    </div>
  );
}

function SinceLastSweep({ bundle, works, dispatch }: { bundle: Bundle; works: Works | null; dispatch: (a: Action) => void }) {
  const diff = bundle.diff;
  const indexOf = useMemo(() => new Map((works?.id ?? []).map((id, i) => [id, i])), [works]);
  if (!diff) return (
    <section><h2>Since last sweep</h2><p className="muted">Only one sweep so far: this panel compares two stored sweeps.</p></section>
  );
  const totals = diff.totals as Record<string, Record<string, number>>;
  const workLink = (id: string, text?: string) => {
    const i = indexOf.get(id);
    return i === undefined ? <span>{text ?? id}</span> : (
      <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "set", patch: { view: "map", selection: { kind: "work", idx: i } } }); }}>{text ?? id}</a>
    );
  };
  return (
    <section>
      <h2>Since last sweep <span className="muted small">{diff.old_sweep} → {diff.new_sweep}</span></h2>
      <table className="kv compact">
        <thead><tr><td />{Object.keys(totals[diff.old_sweep]).map((k) => <td key={k} className="num">{k}</td>)}</tr></thead>
        <tbody>{Object.entries(totals).map(([sweep, t]) => (
          <tr key={sweep}><td>{sweep}</td>{Object.values(t).map((v, i) => <td key={i} className="num">{int(v)}</td>)}</tr>
        ))}</tbody>
      </table>
      <div className="diff-grid">
        <div>
          <h3>Works added: {int(diff.works_added.count)}</h3>
          <ul className="plain">{Object.entries(diff.works_added.by_publication_year as Record<string, any>).map(([y, v]) => (
            <li key={y}><span>{y}</span><span className="num">{int(v.count)}</span></li>))}</ul>
          <h3>Works removed: {int(diff.works_removed.count)}</h3>
          <ul className="plain">{(diff.works_removed.ids as string[]).slice(0, 10).map((id) => <li key={id}>{id}</li>)}</ul>
        </div>
        <div>
          <h3>Topic reassigned: {int(diff.topic_reassigned.count)}</h3>
          <ul className="plain">{(diff.topic_reassigned.examples as any[]).slice(0, 10).map((x) => (
            <li key={x.work_id}>{workLink(x.work_id)} <span className="muted small">{x.old_topic} → {x.new_topic}</span></li>))}</ul>
          <h3>Partners first seen: {diff.partners_first_seen.institutions.length}</h3>
          <ul className="plain">{(diff.partners_first_seen.institutions as any[]).slice(0, 10).map((p) => (
            <li key={p.institution_id}><span>{p.institution_name} <span className="muted">{p.country}</span></span><span className="num">{p.work_ids.length}</span></li>))}</ul>
        </div>
        <div>
          <h3>Citation jumps</h3>
          <ul className="plain">{(diff.citation_jumps as any[]).map((j) => (
            <li key={j.work_id}>{workLink(j.work_id, j.title ?? j.work_id)}<span className="num">+{int(j.delta)}</span></li>))}</ul>
        </div>
      </div>
    </section>
  );
}

function About({ bundle }: { bundle: Bundle }) {
  const m = bundle.meta, q = bundle.quality as Record<string, any>;
  const perYear = (q.abstract_share_per_year ?? {}) as Record<string, number>;
  const option = useMemo(() => ({
    grid: { left: 8, right: 8, top: 8, bottom: 20, containLabel: true },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => pct(v) },
    xAxis: { type: "category", data: Object.keys(perYear) },
    yAxis: { type: "value", max: 1, axisLabel: { formatter: (v: number) => pct(v) }, splitLine: { lineStyle: { color: cssVar("--border") } } },
    series: [{ type: "bar", data: Object.values(perYear), itemStyle: { color: cssVar("--none") } }],
  }), [perYear]);
  const download = () => {
    const url = URL.createObjectURL(new Blob([bundle.brief_md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url; a.download = `brief-${m.sweep_id}.md`; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section>
      <h2>{S.about}</h2>
      <div className="diff-grid">
        <div>
          <table className="kv">
            <tbody>
              <tr><td>Universe</td><td>{m.universe.label}</td></tr>
              <tr><td>Filter</td><td className="small"><code>{m.universe.filter}</code></td></tr>
              <tr><td>Sweep</td><td>{m.sweep_id} (observed {m.observed_at})</td></tr>
              <tr><td>Works</td><td className="num">{int(m.n_works)} ({int(m.n_mapped)} on the map)</td></tr>
              <tr><td>Abstract coverage</td><td className="num">{pct(q.abstract_share)}</td></tr>
              <tr><td>January-1 dates</td><td className="num">{pct(q.jan1_share)}</td></tr>
              <tr><td>Anchor materialized</td><td className="num">{pct(q.anchor_materialized_share)}</td></tr>
              <tr><td>Period mode</td><td>{m.period_mode} · cutoffs {m.cutoffs[0]}–{m.cutoffs[m.cutoffs.length - 1]}</td></tr>
            </tbody>
          </table>
          <button onClick={download}>Download brief (.md)</button>
        </div>
        <div>
          <Chart option={option} height={150} caption="Share of works with an abstract, per publication year." />
        </div>
        <div className="small">
          <h3>Method</h3>
          <ol className="method">
            <li>One OpenAlex harvest of the universe per sweep (a dated snapshot).</li>
            <li>Each detector counts works (or citations) per entity in a 12-month current window and the 36 months before.</li>
            <li>The question is always the same: did the entity's share change?</li>
            <li>Exact conditional binomial test, then Benjamini–Hochberg (q ≤ {m.params.alpha}).</li>
            <li>A signal also needs a share ratio of at least ×{(2 ** m.params.min_log2_ratio).toFixed(2)} (or ÷).</li>
            <li>Ranked by the confidence bound closest to zero.</li>
            <li>The map places works by their title and abstract (embeddings, UMAP, HDBSCAN); labels are c-TF-IDF terms.</li>
            <li>No generative model anywhere.</li>
          </ol>
          <h3>Known limits</h3>
          <ul className="method">
            <li>Topics come from the OpenAlex classifier; drill down to the works to catch its errors.</li>
            <li>Citations use today's counts_by_year: past cutoffs are reconstructions.</li>
            <li>The first three years are baseline only; NEW means absent since {m.years[0]}, not new to science.</li>
            <li>Collaborations depend on affiliation disambiguation (renamed institutions look new).</li>
            <li>Works without an abstract are placed from their title only.</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
