import type { Step } from "../types";

/** 1 for points of the selection, 0 elsewhere (used for size, outline and dimming). */
export function highlightMask(n: number, workIdx: number[] | null): Uint8Array {
  const mask = new Uint8Array(n);
  if (workIdx) for (const i of workIdx) if (i >= 0 && i < n) mask[i] = 1;
  return mask;
}

/** DataFilterExtension range on pub_month for a time-bar step. */
export function filterRange(step: Step, mode: "window" | "cumulative"): [number, number] {
  return mode === "cumulative" ? [0, step.end_month] : [step.start_month, step.end_month];
}

/** Bounding box of a set of points, padded, for "Zoom to works". */
export function bounds(xs: number[], ys: number[], idx: number[], pad = 0.02): [number, number, number, number] | null {
  if (!idx.length) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const i of idx) {
    minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i]);
    minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i]);
  }
  return [minX - pad, minY - pad, maxX + pad, maxY + pad];
}
