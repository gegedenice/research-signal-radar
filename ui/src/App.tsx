import { useEffect, useMemo, useReducer, useState } from "react";
import type { Bundle, Points, Works } from "./types";
import { loadCore, loadWorks } from "./logic/load";
import { fromHash, initialState, makeReducer, toHash, type State } from "./logic/state";
import { Header } from "./components/Header";
import { TimeBar, stepCounts } from "./components/TimeBar";
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
      <div className="body">
        <aside className="feed"><div className="placeholder">Signal feed</div></aside>
        <main className="center">
          <div className="mapwrap"><div className="placeholder">Map — {points.n} points{works ? "" : ` · ${S.loadingWorks}`}</div></div>
          <TimeBar bundle={bundle} state={state} dispatch={dispatch} counts={counts} />
        </main>
        <Detail state={state} />
      </div>
    </div>
  );
}

function Detail({ state }: { state: State }) {
  if (!state.selection) return null;
  return <aside className="detail">{JSON.stringify(state.selection)}</aside>;
}
