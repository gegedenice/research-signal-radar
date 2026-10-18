import { useEffect, useMemo, useReducer, useState } from "react";
import type { Bundle, Points, Works } from "./types";
import { loadCore, loadWorks } from "./logic/load";
import { fromHash, initialState, makeReducer, toHash } from "./logic/state";
import { Header } from "./components/Header";
import { TimeBar, stepCounts } from "./components/TimeBar";
import { MapView } from "./components/MapView";
import { Feed } from "./components/Feed";
import { Detail } from "./components/Detail";
import { Overview } from "./components/Overview";
import { cutoffAt } from "./logic/feed";
import { S } from "./strings";

export default function App() {
  const [core, setCore] = useState<{ bundle: Bundle; points: Points } | null>(null);
  const [works, setWorks] = useState<Works | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCore().then(setCore, (e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    if (core) loadWorks().then(setWorks, (e: Error) => setError(e.message));
  }, [core]);

  if (error) return <div className="centered"><div><p className="error">{S.loadError}</p><p className="muted">{error}</p></div></div>;
  if (!core) return <div className="centered">{S.loading}</div>;
  return <Radar bundle={core.bundle} points={core.points} works={works} />;
}

function Radar({ bundle, points, works }: { bundle: Bundle; points: Points; works: Works | null }) {
  const reducer = useMemo(() => makeReducer(bundle.meta.steps.length), [bundle]);
  const [state, dispatch] = useReducer(reducer, bundle, (b) => fromHash(window.location.hash, b, initialState(b)));
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? "dark");
  const counts = useMemo(() => stepCounts(bundle, points.pub_month), [bundle, points]);

  const cutoff = cutoffAt(bundle, state.step);
  const signalById = useMemo(() => new Map(bundle.signals.map((s) => [s.id, s])), [bundle]);
  const selectedIdx = useMemo(() => {
    const sel = state.selection;
    if (!sel) return null;
    if (sel.kind === "signal") return signalById.get(sel.id)?.work_idx ?? null;
    if (sel.kind === "work") return [sel.idx];
    const idx: number[] = [];
    points.cluster.forEach((c, i) => c === sel.id && idx.push(i));
    return idx;
  }, [state.selection, signalById, points]);
  const previewIdx = state.hoverSignal ? signalById.get(state.hoverSignal)?.work_idx ?? null : null;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    const hash = toHash(state, bundle);
    if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
  }, [state, bundle]);

  return (
    <div className="app">
      <Header bundle={bundle} state={state} dispatch={dispatch} theme={theme} setTheme={setTheme} />
      <div className={`body${state.view === "overview" ? " body-overview" : ""}`}>
        {state.view === "map" && <Feed bundle={bundle} state={state} dispatch={dispatch} cutoff={cutoff} />}
        <main className="center">
          {state.view === "map" ? (
            <MapView bundle={bundle} points={points} works={works} state={state} dispatch={dispatch} cutoff={cutoff}
              selectedIdx={selectedIdx} previewIdx={previewIdx} />
          ) : (
            <Overview bundle={bundle} works={works} state={state} dispatch={dispatch} cutoff={cutoff} />
          )}
          <TimeBar bundle={bundle} state={state} dispatch={dispatch} counts={counts} />
        </main>
        <Detail bundle={bundle} points={points} works={works} state={state} dispatch={dispatch} cutoff={cutoff} signalById={signalById} />
      </div>
    </div>
  );
}
