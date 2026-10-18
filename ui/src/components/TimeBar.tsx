import { useEffect } from "react";
import type { Bundle, Detector } from "../types";
import type { Action, State } from "../logic/state";
import { S } from "../strings";
import { LABEL_RGB, rgb } from "../theme";

const DETECTOR_RGB: Record<Detector, [number, number, number]> = {
  topics: LABEL_RGB.RISING, citations: LABEL_RGB.NEW, collaborations: LABEL_RGB.FALLING,
};

/** Works per step and signals per detector, computed once from the bundle (display only, no statistics). */
export function stepCounts(bundle: Bundle, pubMonth: number[]) {
  const steps = bundle.meta.steps;
  const works = steps.map((s) => {
    let n = 0;
    for (const m of pubMonth) if (m >= s.start_month && m <= s.end_month) n++;
    return n;
  });
  const signals = steps.map((s) => {
    const c: Record<Detector, number> = { topics: 0, citations: 0, collaborations: 0 };
    if (s.is_cutoff) for (const sig of bundle.signals) if (sig.cutoff === s.label) c[sig.detector]++;
    return c;
  });
  return { works, signals };
}

export function TimeBar({ bundle, state, dispatch, counts }: {
  bundle: Bundle; state: State; dispatch: (a: Action) => void; counts: ReturnType<typeof stepCounts>;
}) {
  const steps = bundle.meta.steps;
  const semester = bundle.meta.period_mode === "semester";
  const maxWorks = Math.max(1, ...counts.works);
  const maxSignals = Math.max(1, ...counts.signals.map((c) => c.topics + c.citations + c.collaborations));

  useEffect(() => {
    if (!state.playing) return;
    const id = window.setTimeout(() => dispatch({ type: "tick" }), semester ? 1000 : 1500);
    return () => window.clearTimeout(id);
  }, [state.playing, state.step, semester, dispatch]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        dispatch({ type: "set", patch: { playing: !state.playing, step: !state.playing && state.step >= steps.length - 1 ? 0 : state.step } });
      } else if (e.key === "ArrowLeft") dispatch({ type: "step", step: state.step - 1 });
      else if (e.key === "ArrowRight") dispatch({ type: "step", step: state.step + 1 });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.playing, state.step, steps.length, dispatch]);

  const firstCutoff = steps.findIndex((s) => s.is_cutoff);
  return (
    <div className="timebar">
      <button
        title={state.playing ? S.pause : S.play}
        onClick={() => dispatch({ type: "set", patch: { playing: !state.playing, step: !state.playing && state.step >= steps.length - 1 ? 0 : state.step } })}
      >
        {state.playing ? "❚❚" : "▶"}
      </button>
      <div className="ticks">
        {steps.map((s, i) => {
          const c = counts.signals[i];
          const h1 = semester && s.label.endsWith("-H1");
          return (
            <div key={s.label} style={{ display: "contents" }}>
              {i === firstCutoff && <span className="divider" />}
              <div
                className={`tick${i === state.step ? " current" : ""}${h1 ? " h1" : ""}`}
                title={`${s.label}: ${counts.works[i]} works` + (s.is_cutoff ? `, ${c.topics + c.citations + c.collaborations} signals` : " (baseline)")}
                onClick={() => dispatch({ type: "step", step: i })}
              >
                <div className="tick-bars" style={{ height: h1 ? 24 : 34 }}>
                  <div style={{ height: `${(counts.works[i] / maxWorks) * 45}%`, background: "var(--none)", opacity: 0.5 }} />
                  {(["topics", "citations", "collaborations"] as Detector[]).map((d) => (
                    <div key={d} style={{ height: `${(c[d] / maxSignals) * 55}%`, background: rgb(DETECTOR_RGB[d]) }} />
                  ))}
                </div>
                <span className="tick-label">{semester ? s.label.replace("-", " ") : s.label}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
        {semester && <span className="muted small">{S.semesterNote}</span>}
        <span className="seg">
          {(["window", "cumulative"] as const).map((m) => (
            <button key={m} className={state.timeMode === m ? "active" : ""} onClick={() => dispatch({ type: "set", patch: { timeMode: m } })}>
              {S[m]}
            </button>
          ))}
        </span>
      </div>
    </div>
  );
}
