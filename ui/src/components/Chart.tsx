import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, ScatterChart, CustomChart } from "echarts/charts";
import { GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, LineChart, ScatterChart, CustomChart, GridComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, LegendComponent, CanvasRenderer]);

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

/** Small ECharts wrapper: one instance per element, option replaced on change, resized with its box. */
export function Chart({ option, height = 160, onClick, caption }: {
  option: echarts.EChartsCoreOption; height?: number; onClick?: (params: any) => void; caption?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const click = useRef(onClick);
  click.current = onClick;

  useEffect(() => {
    if (!el.current) return;
    chart.current = echarts.init(el.current, undefined, { renderer: "canvas" });
    chart.current.on("click", (p) => click.current?.(p));
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); chart.current?.dispose(); chart.current = null; };
  }, []);
  useEffect(() => {
    const text = cssVar("--muted");
    chart.current?.setOption({ textStyle: { color: text, fontFamily: "system-ui, sans-serif" }, animation: false, ...option }, true);
  }, [option]);

  return (
    <figure className="chart">
      <div ref={el} style={{ height }} />
      {caption && <figcaption className="muted small">{caption}</figcaption>}
    </figure>
  );
}
