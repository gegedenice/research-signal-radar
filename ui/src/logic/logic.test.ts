import { describe, expect, it } from "vitest";
import { bundle, points, signal } from "./fixtures";
import { validateBundle } from "./load";
import { cutoffAt, labelName, sameEntityAt, selectFeed, tabCounts } from "./feed";
import { bounds, filterRange, highlightMask } from "./map";
import { fromHash, initialState, makeReducer, toHash } from "./state";
import { effect, pct } from "./format";

describe("bundle loader", () => {
  it("accepts a valid bundle", () => {
    expect(() => validateBundle(bundle([signal({ id: "T1", work_idx: [0, 3] })]), points(4))).not.toThrow();
  });
  it("rejects an unknown schema", () => {
    const b = bundle([]);
    b.schema_version = "other/9";
    expect(() => validateBundle(b, points())).toThrow(/schema/);
  });
  it("rejects a work index outside the map", () => {
    expect(() => validateBundle(bundle([signal({ id: "T1", work_idx: [0, 4] })]), points(4))).toThrow(/outside/);
  });
});

describe("feed selector", () => {
  const signals = [
    signal({ id: "T1", entity: { id: "T1", label: "Coral reefs", parent_id: null, parent_label: null }, rank: 0.5 }),
    signal({ id: "T2", entity: { id: "T2", label: "Malaria vectors", parent_id: null, parent_label: null }, rank: 0.9, label: "FALLING" }),
    signal({ id: "T3", label: "NEW", rank: 0.7 }),
    signal({ id: "S1", level: "subfield" }),
    signal({ id: "W1", detector: "citations", level: "work" }),
    signal({ id: "T4", cutoff: "2024" }),
  ];
  const b = bundle(signals);
  const q = { cutoff: "2025", tab: "topics" as const, level: "topic", labels: [], search: "" };

  it("filters by tab and level and sorts by rank", () => {
    expect(selectFeed(b, q).items.map((s) => s.id)).toEqual(["T2", "T3", "T1"]);
    expect(selectFeed(b, { ...q, level: "subfield" }).items.map((s) => s.id)).toEqual(["S1"]);
    expect(selectFeed(b, { ...q, tab: "citations" }).items.map((s) => s.id)).toEqual(["W1"]);
  });
  it("combines labels and search", () => {
    expect(selectFeed(b, { ...q, labels: ["RISING", "NEW"] }).items.map((s) => s.id)).toEqual(["T3", "T1"]);
    expect(selectFeed(b, { ...q, labels: ["RISING"], search: "coral" }).items.map((s) => s.id)).toEqual(["T1"]);
    expect(selectFeed(b, { ...q, search: "MALARIA" }).items.map((s) => s.id)).toEqual(["T2"]);
    expect(selectFeed(b, q).labelCounts).toEqual({ RISING: 1, FALLING: 1, NEW: 1 });
  });
  it("swaps the list when the cutoff changes", () => {
    expect(selectFeed(b, { ...q, cutoff: "2024" }).items.map((s) => s.id)).toEqual(["T4"]);
    expect(tabCounts(b, "2025", { topics: "topic", citations: "work", collaborations: "institution" }))
      .toEqual({ topics: 3, citations: 1, collaborations: 0 });
  });
  it("shows the baseline message before the first cutoff", () => {
    expect(cutoffAt(b, 1)).toBeNull();
    const r = selectFeed(b, { ...q, cutoff: cutoffAt(b, 1) });
    expect(r.status).toBe("baseline");
    expect(r.status === "baseline" && r.message).toBe("Baseline period (2016–2018) — signals start in 2019");
  });
  it("shows the yearly-only note for citations at -H1 cutoffs", () => {
    const sb = bundle(signals, "semester");
    const h1 = sb.meta.steps.findIndex((s) => s.label === "2021-H1");
    const r = selectFeed(sb, { ...q, tab: "citations", cutoff: cutoffAt(sb, h1) });
    expect(r.status === "note" && r.message).toBe("Citations are counted per calendar year — latest available: 2020-H2");
  });
  it("finds the same entity at another cutoff", () => {
    expect(sameEntityAt(bundle([signal({ id: "a", entity: { id: "T9", label: "", parent_id: null, parent_label: null } }),
      signal({ id: "b", cutoff: "2024", entity: { id: "T9", label: "", parent_id: null, parent_label: null } })]),
      signal({ id: "a", entity: { id: "T9", label: "", parent_id: null, parent_label: null } }), "2024")?.id).toBe("b");
  });
  it("names citation labels", () => {
    expect(labelName("NEW", "citations")).toBe("Breakout");
    expect(labelName("RISING", "topics")).toBe("Rising");
  });
});

describe("map selection", () => {
  it("produces the highlight mask of the selected signal", () => {
    expect(Array.from(highlightMask(5, [1, 3, 9]))).toEqual([0, 1, 0, 1, 0]);
    expect(Array.from(highlightMask(3, null))).toEqual([0, 0, 0]);
  });
  it("filters by window or cumulatively", () => {
    const step = { label: "2020", start_month: 48, end_month: 59, is_cutoff: true };
    expect(filterRange(step, "window")).toEqual([48, 59]);
    expect(filterRange(step, "cumulative")).toEqual([0, 59]);
  });
  it("computes padded bounds", () => {
    expect(bounds([0, 0.5, 1], [0, 0.2, 1], [1, 2], 0)).toEqual([0.5, 0.2, 1, 1]);
  });
});

describe("state and URL hash", () => {
  const b = bundle([signal({ id: "topics:topic:T1:2025" })]);
  it("restores the same view after a round trip", () => {
    const reducer = makeReducer(b.meta.steps.length);
    let s = initialState(b);
    s = reducer(s, { type: "step", step: 5 });
    s = reducer(s, { type: "set", patch: { timeMode: "cumulative", dim: "3d", colorMode: "region", tab: "collaborations",
      levels: { ...s.levels, collaborations: "country" } } });
    s = reducer(s, { type: "select", selection: { kind: "signal", id: "topics:topic:T1:2025" } });
    const restored = fromHash(toHash(s, b), b, initialState(b));
    for (const key of ["step", "timeMode", "dim", "colorMode", "tab", "selection"] as const) expect(restored[key]).toEqual(s[key]);
    expect(restored.levels.collaborations).toBe("country");
  });
  it("stops playing at the last step", () => {
    const reducer = makeReducer(3);
    const s = reducer({ ...initialState(b), step: 2, playing: true }, { type: "tick" });
    expect(s.playing).toBe(false);
  });
});

describe("format", () => {
  it("formats shares and effects", () => {
    expect(pct(0.0029)).toBe("0.29%");
    expect(pct(0.125)).toBe("12.5%");
    expect(effect(1.239, 0.48, 1.998)).toBe("share ×2.4 (1.4–4)");
  });
});
