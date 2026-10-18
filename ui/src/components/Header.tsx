import type { Bundle } from "../types";
import type { Action, State } from "../logic/state";
import { S } from "../strings";
import { int } from "../logic/format";

export function Header({ bundle, state, dispatch, theme, setTheme }: {
  bundle: Bundle; state: State; dispatch: (a: Action) => void; theme: string; setTheme: (t: string) => void;
}) {
  const m = bundle.meta;
  return (
    <header className="header">
      <h1>{m.universe.label}</h1>
      <span className="muted">· {S.sweep} {m.sweep_id} · {int(m.n_works)} {S.works}</span>
      <span className="spacer" />
      <span className="seg">
        {(["map", "overview"] as const).map((v) => (
          <button key={v} className={state.view === v ? "active" : ""} onClick={() => dispatch({ type: "set", patch: { view: v } })}>
            {v === "map" ? S.map : S.overview}
          </button>
        ))}
      </span>
      <button title={S.theme} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "☀" : "☾"}</button>
    </header>
  );
}
