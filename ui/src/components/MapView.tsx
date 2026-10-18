import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { OrbitView, OrthographicView } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Bundle, Cluster, Points, Works } from "../types";
import type { Action, State } from "../logic/state";
import { bounds, filterRange, highlightMask } from "../logic/map";
import { LABEL_RGB, REGION_RGB } from "../theme";
import { S } from "../strings";

const SCALE = 1000; // map coordinates are in [0, 1]; deck works better with a larger extent
const LABEL_ZOOM = 1.2; // above this zoom (2-D), cluster labels replace region labels

type RGB = [number, number, number];

function fitZoom(width: number, height: number): number {
  return Math.log2(Math.max(1, Math.min(width, height)) / SCALE) - 0.05;
}

export function MapView({ bundle, points, works, state, dispatch, cutoff, selectedIdx, previewIdx }: {
  bundle: Bundle; points: Points; works: Works | null; state: State; dispatch: (a: Action) => void;
  cutoff: string | null; selectedIdx: number[] | null; previewIdx: number[] | null;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const is3d = state.dim === "3d";
  const n = points.n;
  const step = bundle.meta.steps[state.step];

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const home2d = useMemo(() => ({ target: [SCALE / 2, SCALE / 2, 0] as [number, number, number], zoom: fitZoom(size.width, size.height) }), [size]);
  const home3d = useMemo(() => ({ target: [SCALE / 2, SCALE / 2, SCALE / 2] as [number, number, number], zoom: fitZoom(size.width, size.height) - 0.4, rotationX: 25, rotationOrbit: 30 }), [size]);
  const [viewState, setViewState] = useState<Record<string, any>>(home2d);
  const fitted = useRef(false);
  useEffect(() => {
    if (size.width > 0 && !fitted.current) { setViewState(is3d ? home3d : home2d); fitted.current = true; }
  }, [size, home2d, home3d, is3d]);
  useEffect(() => { setViewState(is3d ? home3d : home2d); }, [is3d]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Zoom to works": fit the 2-D view to the selected points (3-D: re-centre on them).
  useEffect(() => {
    if (!state.zoomToken || !selectedIdx?.length) return;
    if (!is3d) {
      const b = bounds(points.x, points.y, selectedIdx, 0.03);
      if (!b) return;
      const [x0, y0, x1, y1] = b;
      const span = Math.max(x1 - x0, y1 - y0, 0.01) * SCALE;
      setViewState({ target: [((x0 + x1) / 2) * SCALE, ((y0 + y1) / 2) * SCALE, 0], zoom: Math.log2(Math.min(size.width, size.height) / span), transitionDuration: 600 });
    } else {
      const c = [0, 0, 0];
      for (const i of selectedIdx) { c[0] += points.x3[i]; c[1] += points.y3[i]; c[2] += points.z3[i]; }
      setViewState((v) => ({ ...v, target: c.map((v2) => (v2 / selectedIdx.length) * SCALE), zoom: (v.zoom ?? 0) + 1, transitionDuration: 600 }));
    }
  }, [state.zoomToken]); // eslint-disable-line react-hooks/exhaustive-deps

  const positions = useMemo(() => {
    const size3 = is3d ? 3 : 2;
    const arr = new Float32Array(n * size3);
    for (let i = 0; i < n; i++) {
      arr[i * size3] = (is3d ? points.x3[i] : points.x[i]) * SCALE;
      arr[i * size3 + 1] = (is3d ? points.y3[i] : points.y[i]) * SCALE;
      if (is3d) arr[i * 3 + 2] = points.z3[i] * SCALE;
    }
    return { value: arr, size: size3 };
  }, [points, is3d, n]);

  const clusterById = useMemo(() => new Map(bundle.clusters.map((c) => [c.cluster, c])), [bundle]);

  const baseColors = useMemo(() => {
    const trendColor = new Map<number, RGB>();
    for (const c of bundle.clusters) {
      const t = cutoff ? c.trend[cutoff] : undefined;
      trendColor.set(c.cluster, c.cluster === -1 ? LABEL_RGB.OUTLIER : t?.label ? LABEL_RGB[t.label] : LABEL_RGB.NONE);
    }
    const out = new Uint8Array(n * 3);
    for (let i = 0; i < n; i++) {
      let col: RGB;
      if (state.colorMode === "region") col = points.region[i] < 0 ? LABEL_RGB.OUTLIER : REGION_RGB[points.region[i] % REGION_RGB.length];
      else if (state.colorMode === "abstract") col = points.has_abstract[i] ? LABEL_RGB.RISING : LABEL_RGB.FALLING;
      else col = trendColor.get(points.cluster[i]) ?? LABEL_RGB.NONE;
      out.set(col, i * 3);
    }
    return out;
  }, [bundle, points, cutoff, state.colorMode, n]);

  const focusIdx = previewIdx ?? selectedIdx;
  const focus = useMemo(() => (focusIdx ? highlightMask(n, focusIdx) : null), [focusIdx, n]);

  const range = filterRange(step, state.timeMode);
  // One layer for all points: those in the time-bar window are drawn fully, the others stay as a faint
  // background (cheaper than two layers of 78k points, same picture as specs/06 §3.4).
  const inWindow = useMemo(() => {
    const out = new Uint8Array(n);
    for (let i = 0; i < n; i++) out[i] = points.pub_month[i] >= range[0] && points.pub_month[i] <= range[1] ? 1 : 0;
    return out;
  }, [points, n, range[0], range[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  const fgColors = useMemo(() => {
    const out = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) {
      const bright = inWindow[i] === 1;
      out[i * 4] = bright ? baseColors[i * 3] : 150;
      out[i * 4 + 1] = bright ? baseColors[i * 3 + 1] : 160;
      out[i * 4 + 2] = bright ? baseColors[i * 3 + 2] : 175;
      out[i * 4 + 3] = focus ? (focus[i] ? 255 : bright ? 40 : 10) : bright ? 200 : 22;
    }
    return out;
  }, [baseColors, focus, inWindow, n]);

  // A single selected work (citation signal) pulses.
  const [pulse, setPulse] = useState(0);
  const single = focusIdx && focusIdx.length === 1 ? focusIdx[0] : null;
  useEffect(() => {
    if (single === null) return;
    const id = window.setInterval(() => setPulse((p) => (p + 1) % 2), 600);
    return () => window.clearInterval(id);
  }, [single]);

  const radii = useMemo(() => {
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = focus && focus[i] ? (single === i ? 7 + pulse * 4 : 4) : inWindow[i] ? 2 : 1.5;
    return out;
  }, [focus, n, single, pulse, inWindow]);

  const zoom = viewState.zoom ?? 0;
  const relZoom = zoom - home2d.zoom;
  const showClusters = is3d || relZoom > LABEL_ZOOM;
  const view = useMemo(() => (is3d ? new OrbitView({ id: "orbit" }) : new OrthographicView({ id: "ortho" })), [is3d]);

  // Greedy label placement in screen space: biggest first, skip any label overlapping one already placed.
  const labels = useMemo(() => {
    const items: any[] = showClusters ? bundle.clusters.filter((c) => c.cluster !== -1) : bundle.regions.filter((r) => r.x !== null);
    const viewport = view.makeViewport({ width: size.width, height: size.height, viewState: viewState as any });
    if (!viewport) return items;
    const fontPx = showClusters ? 12 : 14;
    const placed: [number, number, number, number][] = [];
    const out: any[] = [];
    for (const d of [...items].sort((a, b) => (b.size ?? 0) - (a.size ?? 0))) {
      const pos = is3d ? [d.x3 * SCALE, d.y3 * SCALE, d.z3 * SCALE] : [d.x * SCALE, d.y * SCALE, 0];
      const [px, py] = viewport.project(pos);
      if (px < 0 || py < 0 || px > size.width || py > size.height) continue;
      const w = d.label.length * fontPx * 0.55 + 6, h = fontPx + 4;
      const box: [number, number, number, number] = [px - w / 2, py - h / 2, px + w / 2, py + h / 2];
      if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      placed.push(box);
      out.push(d);
    }
    return out;
  }, [bundle, showClusters, is3d, view, viewState, size]);

  const layers = [
    new ScatterplotLayer({
      id: "foreground",
      data: {
        length: n,
        attributes: {
          getPosition: positions,
          getFillColor: { value: fgColors, size: 4, normalized: true },
          getRadius: { value: radii, size: 1 },
        },
      },
      radiusUnits: "pixels",
      billboard: true,
      stroked: !!focus,
      getLineColor: [255, 255, 255, 220],
      lineWidthUnits: "pixels",
      getLineWidth: 0,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 120],
      onClick: ({ index }) => index >= 0 && dispatch({ type: "select", selection: { kind: "work", idx: index } }),
    }),
    focus &&
      new ScatterplotLayer({
        id: "focus-outline",
        data: focusIdx!,
        getPosition: (i: number) => (is3d ? [points.x3[i] * SCALE, points.y3[i] * SCALE, points.z3[i] * SCALE] : [points.x[i] * SCALE, points.y[i] * SCALE]),
        radiusUnits: "pixels",
        billboard: true,
        getRadius: (i: number) => (single === i ? 8 + pulse * 4 : 4.5),
        filled: false,
        stroked: true,
        lineWidthUnits: "pixels",
        getLineWidth: 1.2,
        getLineColor: [255, 255, 255, 230],
        updateTriggers: { getPosition: [is3d], getRadius: [single, pulse] },
      }),
    new TextLayer<any>({
      id: showClusters ? "cluster-labels" : "region-labels",
      data: labels,
      getPosition: (d: any) => (is3d ? [d.x3 * SCALE, d.y3 * SCALE, d.z3 * SCALE] : [d.x * SCALE, d.y * SCALE]),
      getText: (d: any) => d.label,
      getSize: showClusters ? 12 : 14,
      getColor: [230, 237, 243, 230],
      outlineWidth: 3,
      outlineColor: [11, 17, 24, 255],
      fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
      characterSet: "auto",
      parameters: { depthCompare: "always" }, // labels stay readable in 3-D
      fontSettings: { sdf: true },
      fontWeight: showClusters ? 500 : 700,
      pickable: showClusters,
      onClick: ({ object }: any) => object && dispatch({ type: "select", selection: { kind: "cluster", id: object.cluster } }),
      updateTriggers: { getPosition: [is3d] },
    }),
  ].filter(Boolean);

  const tooltip = ({ index, layer, object }: any) => {
    if (layer?.id === "cluster-labels" && object) return { text: `${object.label}\n${object.size} works` };
    if (layer?.id !== "foreground" || index < 0) return null;
    const cluster: Cluster | undefined = clusterById.get(points.cluster[index]);
    const title = works?.title[index] ?? "…";
    const topic = works && works.topic[index] >= 0 ? works.topics[works.topic[index]] : "";
    return { text: `${title}\n${points.year[index]} · ${cluster?.label ?? "unassigned"}${topic ? `\nOpenAlex: ${topic}` : ""}` };
  };

  return (
    <div className="mapwrap" ref={wrap}>
      <DeckGL
        views={view}
        viewState={viewState}
        onViewStateChange={({ viewState: v }) => setViewState(v)}
        controller={true}
        layers={layers}
        getTooltip={tooltip}
        style={{ position: "absolute", inset: "0" }}
      />
      <div className="map-controls">
        <span className="seg">
          {(["trend", "region", "abstract"] as const).map((m) => (
            <button key={m} className={state.colorMode === m ? "active" : ""} onClick={() => dispatch({ type: "set", patch: { colorMode: m } })}>
              {S.colorModes[m]}
            </button>
          ))}
        </span>
        <span className="seg">
          {(["2d", "3d"] as const).map((d) => (
            <button key={d} className={state.dim === d ? "active" : ""} onClick={() => dispatch({ type: "set", patch: { dim: d } })}>
              {S.dims[d]}
            </button>
          ))}
        </span>
        <button title="Fit to data" onClick={() => setViewState({ ...(is3d ? home3d : home2d), transitionDuration: 400 })}>⤢</button>
        {selectedIdx && selectedIdx.length > 0 && (
          <button onClick={() => dispatch({ type: "zoomToSelection" })}>{S.zoomToWorks}</button>
        )}
      </div>
      <MapLegend mode={state.colorMode} cutoff={cutoff} />
    </div>
  );
}

function MapLegend({ mode, cutoff }: { mode: State["colorMode"]; cutoff: string | null }) {
  const item = (rgbv: RGB, text: string) => (
    <span key={text}><i style={{ background: `rgb(${rgbv.join(",")})` }} />{text}</span>
  );
  return (
    <div className="map-legend small">
      {mode === "trend" && (
        <>
          <span className="muted">Cluster trend {cutoff ? `at ${cutoff}` : "(baseline: none)"}</span>
          {item(LABEL_RGB.RISING, "rising")}{item(LABEL_RGB.FALLING, "falling")}{item(LABEL_RGB.NEW, "new")}
          {item(LABEL_RGB.NONE, "no signal")}{item(LABEL_RGB.OUTLIER, "unassigned")}
        </>
      )}
      {mode === "region" && <span className="muted">Colour = region (coarse groups of clusters)</span>}
      {mode === "abstract" && (<>{item(LABEL_RGB.RISING, "with abstract")}{item(LABEL_RGB.FALLING, "title only")}</>)}
    </div>
  );
}
