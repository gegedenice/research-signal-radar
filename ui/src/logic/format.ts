export function pct(share: number | null | undefined): string {
  if (share === null || share === undefined) return "–";
  const v = share * 100;
  return `${v < 1 ? v.toFixed(2) : v.toFixed(1)}%`;
}

export function ratio(log2: number): string {
  const v = 2 ** log2;
  return v >= 10 ? `×${Math.round(v)}` : `×${v.toPrecision(2).replace(/\.0+$/, "")}`;
}

export function effect(log2: number, low: number, high: number): string {
  return `share ${ratio(log2)} (${ratio(low).slice(1)}–${ratio(high).slice(1)})`;
}

export function fmtQ(q: number): string {
  return q < 0.001 ? q.toExponential(1) : q.toPrecision(2);
}

export function int(n: number): string {
  return n.toLocaleString("en-US");
}
