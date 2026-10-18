import { useMemo } from "react";
import type { Bundle, Points, Works } from "../types";
import type { Action } from "../logic/state";
import { fmtQ, int, pct, ratio } from "../logic/format";
import { LABEL_RGB, rgb } from "../theme";
import { Chart, cssVar } from "./Chart";
import { LabelBadge } from "./Feed";

const SIGNAL_SHARE_IN_CLUSTER = 0.2; // signals listed under a cluster hold ≥ 20% of their works in it (specs/06 §3.5)

export function ClusterDetail({ bundle, id, dispatch }: { bundle: Bundle; id: number; dispatch: (a: Action) => void }) {
  const cluster = bundle.clusters.find((c) => c.cluster === id);
  const option = useMemo(() => {
    if (!cluster) return {};
    const years = Object.keys(cluster.counts_by_year);
    return {
      grid: { left: 8, right: 8, top: 8, bottom: 20, containLabel: true },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: years, axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: cssVar("--border") } }, axisLabel: { fontSize: 10 } },
      series: [{ type: "bar", data: years.map((y) => cluster.counts_by_year[y]), itemStyle: { color: cssVar("--none") } }],
    };
  }, [cluster]);
  const related = useMemo(
    () => bundle.signals.filter((s) => s.clusters.some((c) => c.cluster === id && c.share >= SIGNAL_SHARE_IN_CLUSTER)),
    [bundle, id],
  );
  if (!cluster) return <p className="muted">Unknown cluster {id}.</p>;
  const close = () => dispatch({ type: "select", selection: null });
  return (
    <div>
      <div className="detail-head"><span className="muted small">Cluster {cluster.cluster} · {int(cluster.size)} works</span><button className="close" onClick={close}>✕</button></div>
      <h2>{cluster.label}</h2>
      <p className="muted small">{cluster.terms.join(" · ")}</p>
      {cluster.title_only_share !== null && cluster.title_only_share > 0.5 && (
        <p className="notice">{pct(cluster.title_only_share)} of these works have no abstract: their position is less reliable.</p>
      )}
      <h3>Works per year</h3>
      <Chart option={option} height={130} caption="Number of works of the cluster per publication year." />
      <h3>Trend per cutoff</h3>
      <table className="kv">
        <thead><tr><td>cutoff</td><td>label</td><td className="num">share</td><td className="num">95% CI</td><td className="num">q</td></tr></thead>
        <tbody>
          {Object.entries(cluster.trend).map(([cut, t]) => (
            <tr key={cut}>
              <td>{cut}</td>
              <td style={{ color: t.label ? rgb(LABEL_RGB[t.label]) : undefined }}>{t.label ?? "–"}</td>
              <td className="num">{ratio(t.log2_sr)}</td>
              <td className="num">{ratio(t.ci_low)}–{ratio(t.ci_high)}</td>
              <td className="num">{fmtQ(t.q)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>OpenAlex topics</h3>
      <ul className="plain">{cluster.top_topics.map((t) => <li key={t.id}>{t.label} <span className="muted num">{pct(t.share)}</span></li>)}</ul>
      {cluster.top_subfields.length > 0 && (
        <ul className="plain">{cluster.top_subfields.map((t) => <li key={t.id} className="muted">{t.label} <span className="num">{pct(t.share)}</span></li>)}</ul>
      )}
      <h3>Signals in this cluster</h3>
      {related.length === 0 && <p className="muted small">No signal has ≥ 20% of its works here.</p>}
      <ul className="plain">
        {related.slice(0, 30).map((s) => (
          <li key={s.id}>
            <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "select", selection: { kind: "signal", id: s.id } }); }}>
              {s.entity.label ?? s.entity.id}
            </a>
            <span><LabelBadge label={s.label} detector={s.detector} /> <span className="muted small">{s.cutoff}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WorkDetail({ bundle, points, works, idx, dispatch }: {
  bundle: Bundle; points: Points; works: Works | null; idx: number; dispatch: (a: Action) => void;
}) {
  const signals = useMemo(() => bundle.signals.filter((s) => s.work_idx.includes(idx)), [bundle, idx]);
  const cluster = bundle.clusters.find((c) => c.cluster === points.cluster[idx]);
  const close = () => dispatch({ type: "select", selection: null });
  return (
    <div>
      <div className="detail-head"><span className="muted small">Work</span><button className="close" onClick={close}>✕</button></div>
      <h2>{works?.title[idx] ?? "…"}</h2>
      <table className="kv">
        <tbody>
          <tr><td>Year</td><td>{points.year[idx]}</td></tr>
          <tr><td>OpenAlex topic</td><td>{works && works.topic[idx] >= 0 ? works.topics[works.topic[idx]] : "–"}</td></tr>
          <tr><td>Cluster</td><td>
            {cluster ? <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "select", selection: { kind: "cluster", id: cluster.cluster } }); }}>{cluster.label}</a> : "unassigned"}
          </td></tr>
          <tr><td>Citations</td><td className="num">{works ? int(works.cited_by_count[idx]) : "…"}</td></tr>
          <tr><td>Abstract</td><td>{points.has_abstract[idx] ? "yes" : "no (placed from its title)"}</td></tr>
        </tbody>
      </table>
      {works && (
        <p>
          <a href={`https://openalex.org/${works.id[idx]}`} target="_blank" rel="noreferrer">OpenAlex</a>
          {works.doi[idx] && <> · <a href={`https://doi.org/${works.doi[idx]}`} target="_blank" rel="noreferrer">DOI</a></>}
        </p>
      )}
      <h3>Signals including this work</h3>
      {signals.length === 0 && <p className="muted small">None.</p>}
      <ul className="plain">
        {signals.map((s) => (
          <li key={s.id}>
            <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "select", selection: { kind: "signal", id: s.id } }); }}>
              {s.entity.label ?? s.entity.id}
            </a>
            <span><LabelBadge label={s.label} detector={s.detector} /> <span className="muted small">{s.cutoff}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}
