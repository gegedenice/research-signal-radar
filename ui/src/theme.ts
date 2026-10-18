import type { Label } from "./types";

// Same semantic mapping everywhere (specs/06 §4): rising teal, falling orange, new violet, gone muted red.
export const LABEL_RGB: Record<Label | "NONE" | "OUTLIER", [number, number, number]> = {
  RISING: [45, 190, 170],
  FALLING: [240, 140, 50],
  NEW: [160, 120, 240],
  GONE: [200, 90, 90],
  NONE: [130, 140, 155],
  OUTLIER: [80, 88, 100],
};

export const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

// ~20 distinguishable hues for region colouring.
export const REGION_RGB: [number, number, number][] = [
  [78, 121, 167], [242, 142, 43], [225, 87, 89], [118, 183, 178], [89, 161, 79], [237, 201, 72], [176, 122, 161],
  [255, 157, 167], [156, 117, 95], [186, 176, 172], [31, 119, 180], [174, 199, 232], [255, 187, 120], [152, 223, 138],
  [197, 176, 213], [196, 156, 148], [247, 182, 210], [219, 219, 141], [158, 218, 229], [127, 127, 127],
];
