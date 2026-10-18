import { useEffect, useMemo, useRef, useState } from "react";
import type { Bundle, Detector, Label, Signal } from "../types";
import type { Action, State } from "../logic/state";
import { CITATION_LABELS, LABELS, labelGlyph, labelName, selectFeed, tabCounts } from "../logic/feed";
import { effect, int, pct } from "../logic/format";
import { LABEL_RGB, rgb } from "../theme";
import { S } from "../strings";
import { Sparkline } from "./Sparkline";

export function LabelBadge({ label, detector }: { label: Label; detector: Detector }) {
  return (
    <span className="badge" style={{ color: rgb(LABEL_RGB[label]), borderColor: rgb(LABEL_RGB[label]) }}>
      {labelGlyph(label, detector)} {labelName(label, detector)}
    </span>
  );
}

function counts(s: Signal): string {
  const unit = s.detector === "citations" ? "citations" : "works";
  return `${int(s.b)} → ${int(s.c)} ${unit}, ${pct(s.share_b)} → ${pct(s.share_c)}`;
}

export function Feed({ bundle, state, dispatch, cutoff }: {
  bundle: Bundle; state: State; dispatch: (a: Action) => void; cutoff: string | null;
}) {
  const tab = state.tab;
  const detector = bundle.detectors.find((d) => d.key === tab);
  const level = state.levels[tab];
  const result = useMemo(
    () => selectFeed(bundle, { cutoff, tab, level, labels: state.labels, search: state.search }),
    [bundle, cutoff, tab, level, state.labels, state.search],
  );
  const perTab = useMemo(() => tabCounts(bundle, cutoff, state.levels), [bundle, cutoff, state.levels]);
  const labels = tab === "citations" ? CITATION_LABELS : LABELS;
  const [focus, setFocus] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const selectedId = state.selection?.kind === "signal" ? state.selection.id : null;
  const cutoffYear = cutoff ? Number(cutoff.slice(0, 4)) : 0;

  useEffect(() => setFocus(0), [cutoff, tab, level, state.labels, state.search]);
  useEffect(() => {
    list.current?.querySelector(`[data-i="${focus}"]`)?.scrollIntoView({ block: "nearest" });
  }, [focus]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setFocus((f) => Math.min(result.items.length - 1, f + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setFocus((f) => Math.max(0, f - 1)); }
    else if (e.key === "Enter" && result.items[focus]) dispatch({ type: "select", selection: { kind: "signal", id: result.items[focus].id } });
    else if (e.key === "Escape") dispatch({ type: "select", selection: null });
  };

  return (
    <aside className="feed" onKeyDown={onKey}>
      <div className="feed-controls">
        <div className="seg tabs">
          {bundle.detectors.map((d) => (
            <button key={d.key} className={tab === d.key ? "active" : ""}
              onClick={() => dispatch({ type: "set", patch: { tab: d.key, labels: [] } })}>
              {S.tabs[d.key]} <span className="count">{perTab[d.key]}</span>
            </button>
          ))}
        </div>
        {detector && detector.levels.length > 1 && (
          <div className="seg">
            {detector.levels.map((l) => (
              <button key={l} className={level === l ? "active" : ""}
                onClick={() => dispatch({ type: "set", patch: { levels: { ...state.levels, [tab]: l } } })}>
                {S.levels[l] ?? l}
              </button>
            ))}
          </div>
        )}
        <div className="chips">
          {labels.map((l) => (
            <button key={l} className={`chip${state.labels.includes(l) ? " on" : ""}`} style={{ "--c": rgb(LABEL_RGB[l]) } as React.CSSProperties}
              onClick={() => dispatch({ type: "toggleLabel", label: l })}>
              {labelGlyph(l, tab)} {labelName(l, tab)} <span className="count">{result.labelCounts[l] ?? 0}</span>
            </button>
          ))}
        </div>
        <input type="search" placeholder={S.search} value={state.search}
          onChange={(e) => dispatch({ type: "set", patch: { search: e.target.value } })} />
      </div>
      <div className="cards" ref={list} tabIndex={0}>
        {result.status !== "ok" && <p className="note">{result.message}</p>}
        {result.status === "ok" && result.items.length === 0 && <p className="note">{S.noSignals}</p>}
        {result.items.map((s, i) => (
          <div key={s.id} data-i={i}
            className={`card${s.id === selectedId ? " selected" : ""}${i === focus ? " focused" : ""}`}
            onMouseEnter={() => dispatch({ type: "set", patch: { hoverSignal: s.id } })}
            onMouseLeave={() => dispatch({ type: "set", patch: { hoverSignal: null } })}
            onClick={() => { setFocus(i); dispatch({ type: "select", selection: { kind: "signal", id: s.id } }); }}>
            <div className="card-top">
              <LabelBadge label={s.label} detector={s.detector} />
              {s.returning && <span className="muted small">returning</span>}
            </div>
            <div className="card-title">{s.entity.label ?? s.entity.id}</div>
            {s.entity.parent_label && <div className="muted small">{s.entity.parent_label}</div>}
            <div className="card-bottom">
              <div>
                <div className="num-line">{counts(s)}</div>
                <div className="num-line">{effect(s.log2_sr, s.ci_low, s.ci_high)}</div>
              </div>
              <Sparkline series={s.series} cutoffYear={cutoffYear} color={rgb(LABEL_RGB[s.label])} />
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
