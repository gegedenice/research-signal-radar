import { useEffect } from "react";
import type { Bundle, Points, Signal, Works } from "../types";
import type { Action, State } from "../logic/state";
import { sameEntityAt } from "../logic/feed";
import { SignalDetail } from "./SignalDetail";
import { ClusterDetail, WorkDetail } from "./ClusterWorkDetail";

export function Detail({ bundle, points, works, state, dispatch, cutoff, signalById }: {
  bundle: Bundle; points: Points; works: Works | null; state: State; dispatch: (a: Action) => void;
  cutoff: string | null; signalById: Map<string, Signal>;
}) {
  const sel = state.selection;
  const signal = sel?.kind === "signal" ? signalById.get(sel.id) ?? null : null;

  // Moving the time bar keeps an open signal when the same entity has a signal at the new cutoff.
  useEffect(() => {
    if (!signal || signal.cutoff === cutoff) return;
    const same = sameEntityAt(bundle, signal, cutoff);
    if (same) dispatch({ type: "select", selection: { kind: "signal", id: same.id } });
  }, [cutoff]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!sel) return null;
  return (
    <aside className="detail">
      {signal && <SignalDetail bundle={bundle} signal={signal} works={works} cutoff={cutoff} dispatch={dispatch} />}
      {sel.kind === "cluster" && <ClusterDetail bundle={bundle} id={sel.id} dispatch={dispatch} />}
      {sel.kind === "work" && <WorkDetail bundle={bundle} points={points} works={works} idx={sel.idx} dispatch={dispatch} />}
    </aside>
  );
}
