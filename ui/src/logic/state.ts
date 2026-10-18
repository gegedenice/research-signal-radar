import type { Bundle, Detector, Label } from "../types";

export type Selection =
  | { kind: "signal"; id: string }
  | { kind: "cluster"; id: number }
  | { kind: "work"; idx: number }
  | null;

export interface State {
  view: "map" | "overview";
  step: number;
  timeMode: "window" | "cumulative";
  playing: boolean;
  tab: Detector;
  levels: Record<Detector, string>;
  labels: Label[]; // empty = all labels
  search: string;
  selection: Selection;
  hoverSignal: string | null;
  colorMode: "trend" | "region" | "abstract";
  dim: "2d" | "3d";
  zoomToken: number; // bumped to ask the map to fit the selection
}

export type Action =
  | { type: "set"; patch: Partial<State> }
  | { type: "step"; step: number }
  | { type: "tick" }
  | { type: "select"; selection: Selection }
  | { type: "toggleLabel"; label: Label }
  | { type: "zoomToSelection" };

export function initialState(bundle: Bundle): State {
  const levels: Record<Detector, string> = { topics: "topic", citations: "work", collaborations: "institution" };
  for (const d of bundle.detectors) levels[d.key] = d.levels[0];
  return {
    view: "map",
    step: bundle.meta.steps.length - 1,
    timeMode: "window",
    playing: false,
    tab: "topics",
    levels,
    labels: [],
    search: "",
    selection: null,
    hoverSignal: null,
    colorMode: "trend",
    dim: "2d",
    zoomToken: 0,
  };
}

export function makeReducer(nSteps: number) {
  return function reducer(state: State, action: Action): State {
    switch (action.type) {
      case "set":
        return { ...state, ...action.patch };
      case "step":
        return { ...state, step: Math.max(0, Math.min(nSteps - 1, action.step)) };
      case "tick":
        if (state.step >= nSteps - 1) return { ...state, playing: false };
        return { ...state, step: state.step + 1 };
      case "select":
        return { ...state, selection: action.selection };
      case "toggleLabel": {
        const has = state.labels.includes(action.label);
        return { ...state, labels: has ? state.labels.filter((l) => l !== action.label) : [...state.labels, action.label] };
      }
      case "zoomToSelection":
        return { ...state, zoomToken: state.zoomToken + 1 };
    }
  };
}

/** URL hash: `#signal=…&year=…&mode=…` plus view options (specs/06 §5). */
export function toHash(state: State, bundle: Bundle): string {
  const p = new URLSearchParams();
  p.set("year", bundle.meta.steps[state.step]?.label ?? "");
  p.set("mode", state.timeMode);
  if (state.view !== "map") p.set("view", state.view);
  p.set("tab", state.tab);
  p.set("level", state.levels[state.tab]);
  if (state.colorMode !== "trend") p.set("color", state.colorMode);
  if (state.dim !== "2d") p.set("dim", state.dim);
  const s = state.selection;
  if (s?.kind === "signal") p.set("signal", s.id);
  if (s?.kind === "cluster") p.set("cluster", String(s.id));
  if (s?.kind === "work") p.set("work", String(s.idx));
  return "#" + p.toString();
}

export function fromHash(hash: string, bundle: Bundle, base: State): State {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const state = { ...base, levels: { ...base.levels } };
  const step = bundle.meta.steps.findIndex((s) => s.label === p.get("year"));
  if (step >= 0) state.step = step;
  if (p.get("mode") === "cumulative") state.timeMode = "cumulative";
  if (p.get("view") === "overview") state.view = "overview";
  const tab = p.get("tab") as Detector | null;
  if (tab && bundle.detectors.some((d) => d.key === tab)) {
    state.tab = tab;
    const level = p.get("level");
    if (level && bundle.detectors.find((d) => d.key === tab)!.levels.includes(level)) state.levels[tab] = level;
  }
  const color = p.get("color");
  if (color === "region" || color === "abstract") state.colorMode = color;
  if (p.get("dim") === "3d") state.dim = "3d";
  const signal = p.get("signal");
  if (signal && bundle.signals.some((s) => s.id === signal)) state.selection = { kind: "signal", id: signal };
  else if (p.get("cluster") !== null) state.selection = { kind: "cluster", id: Number(p.get("cluster")) };
  else if (p.get("work") !== null) state.selection = { kind: "work", idx: Number(p.get("work")) };
  return state;
}
