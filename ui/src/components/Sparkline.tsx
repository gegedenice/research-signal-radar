import type { SeriesPoint } from "../types";

/** Yearly share sparkline: baseline years shaded, the cutoff year marked (display only). */
export function Sparkline({ series, cutoffYear, color, width = 120, height = 28 }: {
  series: SeriesPoint[]; cutoffYear: number; color: string; width?: number; height?: number;
}) {
  if (!series.length) return null;
  const shares = series.map((p) => (p.den > 0 ? p.n / p.den : 0));
  const max = Math.max(...shares, 1e-9);
  const step = width / Math.max(1, series.length - 1);
  const x = (i: number) => i * step;
  const y = (v: number) => height - 2 - (v / max) * (height - 4);
  const idx = (year: number) => series.findIndex((p) => p.period === year);
  const b0 = idx(cutoffYear - 3), b1 = idx(cutoffYear - 1), cur = idx(cutoffYear);
  const path = shares.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <svg width={width} height={height} className="sparkline" aria-label="Yearly share">
      {b0 >= 0 && b1 >= 0 && <rect x={x(b0) - step / 2} width={x(b1) - x(b0) + step} y={0} height={height} fill="var(--panel-2)" />}
      {cur >= 0 && <line x1={x(cur)} x2={x(cur)} y1={0} y2={height} stroke="var(--muted)" strokeDasharray="2,2" />}
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} />
      {cur >= 0 && <circle cx={x(cur)} cy={y(shares[cur])} r={2.5} fill={color} />}
    </svg>
  );
}
