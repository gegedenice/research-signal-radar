import { useMemo, useState } from "react";
import type { Bundle, Signal, Works } from "../types";
import type { Action } from "../logic/state";
import { effect, fmtQ, int, pct, ratio } from "../logic/format";
import { LABEL_RGB, rgb } from "../theme";
import { Chart, cssVar } from "./Chart";
import { LabelBadge } from "./Feed";
import { WorkList } from "./WorkList";

const DETECTOR_NAMES = { topics: "Topics", citations: "Citations", collaborations: "Collaborations" };

export function SignalDetail({ bundle, signal, works, cutoff, dispatch }: {
  bundle: Bundle; signal: Signal; works: Works | null; cutoff: string | null; dispatch: (a: Action) => void;
}) {
  const color = rgb(LABEL_RGB[signal.label]);
  const year = Number(signal.cutoff.slice(0, 4));
  const stale = cutoff !== signal.cutoff;
  const clusterLabel = useMemo(() => new Map(bundle.clusters.map((c) => [c.cluster, c.label])), [bundle]);
  const unit = signal.detector === "citations" ? "citations" : "works";

  const dumbbell = useMemo(() => ({
    grid: { left: 20, right: 20, top: 8, bottom: 22, containLabel: true },
    xAxis: { type: "value", min: 0, axisLabel: { formatter: (v: number) => pct(v) }, splitLine: { lineStyle: { color: cssVar("--border") } } },
    yAxis: { type: "category", data: [""], show: false },
    tooltip: { formatter: (p: any) => `${p.seriesName}: ${pct(p.value[0])}` },
    series: [
      { type: "line", data: [[signal.share_b, ""], [signal.share_c, ""]], symbol: "none", lineStyle: { color: cssVar("--muted"), width: 2 }, silent: true },
      { name: "Baseline share", type: "scatter", data: [[signal.share_b, ""]], symbolSize: 12, itemStyle: { color: cssVar("--none") } },
      { name: "Current share", type: "scatter", data: [[signal.share_c, ""]], symbolSize: 12, itemStyle: { color } },
    ],
  }), [signal, color]);

  const yearly = useMemo(() => {
    const years = signal.series.map((p) => String(p.period));
    const base = [String(year - 3), String(year - 1)];
    return {
      grid: { left: 8, right: 8, top: 24, bottom: 20, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: cssVar("--muted"), fontSize: 11 }, itemHeight: 8 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: years, axisLabel: { fontSize: 10 } },
      yAxis: [
        { type: "value", splitLine: { lineStyle: { color: cssVar("--border") } }, axisLabel: { fontSize: 10 } },
        { type: "value", axisLabel: { formatter: (v: number) => pct(v), fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: unit, type: "bar", itemStyle: { color: cssVar("--none") }, data: signal.series.map((p) => ({ value: p.n, itemStyle: { color: p.period === year ? color : cssVar("--none") } })),
          markArea: { silent: true, itemStyle: { color: "rgba(127,127,127,0.12)" }, data: [[{ xAxis: base[0] }, { xAxis: base[1] }]] } },
        { name: "share", type: "line", yAxisIndex: 1, data: signal.series.map((p) => (p.den ? p.n / p.den : 0)), symbolSize: 4,
          lineStyle: { color: cssVar("--text"), width: 1.5 }, itemStyle: { color: cssVar("--text") } },
      ],
    };
  }, [signal, year, color, unit]);

  const extra = signal.extra as Record<string, any>;
  return (
    <div className="signal-detail">
      <div className="detail-head">
        <LabelBadge label={signal.label} detector={signal.detector} />
        <button className="close" onClick={() => dispatch({ type: "select", selection: null })}>✕</button>
      </div>
      <h2>{signal.entity.label ?? signal.entity.id}</h2>
      {signal.entity.parent_label && <div className="muted">{signal.entity.parent_label}</div>}
      <div className="muted small">{DETECTOR_NAMES[signal.detector]} · {signal.level} · {signal.cutoff}</div>
      {stale && <p className="notice">No signal for this entity at {cutoff ?? "this step"} — showing {signal.cutoff}.</p>}

      <p className="why">{signal.why}</p>

      <h3>Share: baseline vs current</h3>
      <Chart option={dumbbell} height={70} caption={`Share of ${unit} — ${effect(signal.log2_sr, signal.ci_low, signal.ci_high)}, 95% interval`} />

      <h3>Per year</h3>
      <Chart option={yearly} height={170} caption={`Bars: ${unit} per year; line: share. Shaded: baseline (${year - 3}–${year - 1}); highlighted: ${year}.`} />

      {signal.clusters.length > 0 && (
        <>
          <h3>On the map</h3>
          <ul className="plain">
            {signal.clusters.map((c) => (
              <li key={c.cluster}>
                <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "select", selection: { kind: "cluster", id: c.cluster } }); }}>
                  {clusterLabel.get(c.cluster) ?? `cluster ${c.cluster}`}
                </a>{" "}
                <span className="muted num">{pct(c.share)}</span>
              </li>
            ))}
          </ul>
          <button onClick={() => dispatch({ type: "zoomToSelection" })}>Zoom to works</button>
        </>
      )}

      <h3>Works</h3>
      <WorkList works={works} top={signal.top_work_idx} all={signal.work_idx} dispatch={dispatch} />
      {signal.n_unmapped > 0 && <p className="muted small">{signal.n_unmapped} works of the window have no map position.</p>}

      {signal.detector === "citations" && (
        <>
          <h3>Cohort</h3>
          <p>{String(extra.cohort ?? "")} · {int(Number(extra.cohort_size ?? 0))} works ({String(extra.cohort_level ?? "")} level)</p>
          {Array.isArray(extra.citing_works) && extra.citing_works.length > 0 && (
            <ul className="plain">{extra.citing_works.map((w: any) => <li key={w.id}>{w.title}</li>)}</ul>
          )}
        </>
      )}
      {signal.detector === "collaborations" && (
        <>
          <h3>Partner</h3>
          <p>
            {extra.country ? `Country ${extra.country}` : ""}{extra.type ? ` · ${extra.type}` : ""}
            {extra.ror && <> · <a href={String(extra.ror)} target="_blank" rel="noreferrer">ROR</a></>}
          </p>
          {Array.isArray(extra.anchor_units) && extra.anchor_units.length > 0 && (
            <>
              <div className="muted small">Anchor units most involved</div>
              <ul className="plain">{extra.anchor_units.map((u: any) => <li key={u.institution_id}>{u.name} <span className="muted num">{u.works}</span></li>)}</ul>
            </>
          )}
        </>
      )}
      {signal.detector === "topics" && extra.primary_share !== undefined && extra.primary_share !== null && (
        <p className="muted small">Primary topic of {pct(Number(extra.primary_share))} of these works (counting: {String(extra.counting)}).</p>
      )}

      <Computed signal={signal} bundle={bundle} />
    </div>
  );
}

function Computed({ signal, bundle }: { signal: Signal; bundle: Bundle }) {
  const [open, setOpen] = useState(false);
  const p = bundle.meta.params;
  return (
    <details className="computed" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>How this was computed</summary>
      <table className="kv">
        <tbody>
          <tr><td>c (current)</td><td className="num">{int(signal.c)}</td><td>C</td><td className="num">{int(signal.C)}</td></tr>
          <tr><td>b (baseline)</td><td className="num">{int(signal.b)}</td><td>B</td><td className="num">{int(signal.B)}</td></tr>
          <tr><td>share ratio</td><td className="num">{ratio(signal.log2_sr)}</td><td>95% CI</td><td className="num">{ratio(signal.ci_low)}–{ratio(signal.ci_high)}</td></tr>
          <tr><td>p</td><td className="num">{fmtQ(signal.p)}</td><td>q (BH)</td><td className="num">{fmtQ(signal.q)}</td></tr>
        </tbody>
      </table>
      <p className="small muted">
        Exact conditional binomial test of the current share against the baseline share (given c + b, c ~ Binomial(c + b, C / (C + B))),
        Benjamini–Hochberg within detector × level × cutoff; signal if q ≤ {p.alpha} and the share changes by at least
        ×{(2 ** p.min_log2_ratio).toFixed(2)}. Current window: 12 months; baseline: the {String(p.baseline_months ?? 36)} months before.
      </p>
    </details>
  );
}
