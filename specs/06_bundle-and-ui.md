# 06 — Data bundle and UI

## 1. Architecture

```
data/sweeps/<id>/ (tables + derived/)
        │  radar export
        ▼
ui/public/data/   bundle.json  points.json  works.json
        │
        ▼
React 19 + TypeScript + Vite   (static, read-only, no backend, no network calls except OpenAlex/DOI links)
  ├─ deck.gl   — semantic map (ScatterplotLayer, TextLayer, DataFilterExtension, OrthographicView)
  └─ ECharts   — every other chart (sparklines, bars, dumbbells, volcano)
```

Two chart libraries is the maximum: deck.gl because ~75k interactive points with per-point
highlighting and smooth transitions are its core use case; ECharts for everything else.
The UI only displays values computed in Python. It never recomputes a test, a label or a rank.

The UI is in English. All strings go through one dictionary file (`ui/src/strings.ts`) so French can be added later.

## 2. Bundle (`radar export`)

Written to `ui/public/data/`. Deterministic: same sweep and config → byte-identical files (except `generated_at`).

Counts in the examples below are illustrative.

### 2.1 `points.json` — the map, columnar

> **Amendment (October 2026, 3-D map):** `points.json` also carries `x3`, `y3`, `z3` (quantized like `x`, `y`), and clusters/regions carry their 3-D label positions. The map offers a **2-D / 3-D toggle**: 2-D uses `OrthographicView` as below; 3-D uses deck.gl `OrbitView` with the same layers and filters on `(x3, y3, z3)`. Everything else (colours, filters, selection, time bar) is identical in both views. Spec 05 §4.2 explains why the two layouts are independent. With the three extra columns the target for `points.json` becomes < 5 MB (measured: 3.9 MB for 78,000 works).

```json
{"n": 75000,
 "x": [0.1234, ...], "y": [...],          // 4 decimals
 "year": [2021, ...],
 "pub_month": [62, ...],                  // months since 2016-01, drives the time filter
 "cluster": [12, ...],                     // -1 = outlier
 "region": [3, ...],
 "has_abstract": [1, 0, ...]}
```
Point index `i` is the row order of `map_points.parquet` sorted by `work_id`. Every other file refers to works by this index.

### 2.2 `works.json` — tooltip and lists, columnar, loaded after first paint

`id, title, year, doi, cited_by_count, topic (index into a topics dictionary), subfield (index)` plus the dictionaries `topics: [label…]`, `subfields: [label…]`.

### 2.3 `bundle.json`

```json
{
  "schema_version": "research-signal-radar-bundle/0.1",
  "generated_at": "...",
  "meta": {"universe": {...}, "sweep_id": "...", "observed_at": "...", "n_works": 75000,
           "years": [2016, 2025], "period_mode": "year",
           "steps": [{"label": "2016", "start_month": 0, "end_month": 11, "is_cutoff": false}, ...],
           "cutoffs": ["2019", "2020", ..., "2025"],
           "params": {"alpha": 0.05, "min_log2_ratio": 0.585, "baseline_months": 36, ...},
           "config_hash": "..."},
  "quality": {...},                        // subset of quality.json
  "detectors": [{"key": "topics", "levels": ["topic", "subfield"],
                 "summary": {"2025": {"topic": {"seen": 0, "tested": 0, "NEW": 0, "RISING": 0, "FALLING": 0, "GONE": 0}}}}, ...],
  "signals": [ {signal}, ... ],            // all cutoffs
  "volcano": {"topics|topic|2025": {"entity_id": [...], "log2_sr": [...], "q": [...], "signal_idx": [...]}, ...},
  "clusters": [ {cluster}, ... ],
  "regions": [ {region}, ... ],
  "diff": {...} | null,
  "brief_md": "..."
}
```

**Signal object:**
```json
{"id": "topics:topic:T10101:2025", "detector": "topics", "level": "topic", "cutoff": "2025",
 "entity": {"id": "T10101", "label": "...", "parent_label": "..."},
 "label": "RISING", "returning": false,
 "c": 25, "b": 30, "C": 8500, "B": 24000, "share_c": 0.00294, "share_b": 0.00125,
 "log2_sr": 1.239, "ci_low": 0.48, "ci_high": 1.998, "p": 0.0031, "q": 0.012, "rank": 0.48,
 "why": "...",
 "series": [{"period": 2016, "n": 9, "den": 6100}, ...],
 "work_idx": [102, 5531, ...],            // works of the current window, as point indices
 "n_unmapped": 0,                         // works of the window without a map position (no title/abstract)
 "top_work_idx": [5531, ...],             // ≤ 10
 "clusters": [{"cluster": 12, "share": 0.44}, ...],   // ≤ 3, where the signal's works sit on the map
 "extra": {...}}
```
For citation signals, `work_idx` = the cited work only, and `extra` holds the yearly citation series, cohort label/size and, if fetched, citing works of year `Y` (`{id, title}` list — these are outside the universe and not on the map).

**Volcano arrays** hold all tested entities when ≤ 3,000; otherwise all signals plus the 3,000 − n_signals lowest-q non-signals (state the sampling in the chart caption).

Target sizes: `points.json` < 3 MB, `works.json` < 15 MB, `bundle.json` < 8 MB.

## 3. Screens

### 3.1 Layout (desktop first, ≥ 1280 px)

> **Amendment (October 2026, responsive):** CSS only, the desktop layout is unchanged. Below 1,280 px the side columns narrow; below 1,024 px the detail panel becomes a drawer over the map; below 760 px everything stacks (map and time bar first, then the feed), the detail opens full screen and the time bar stays pinned in the Overview.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ IRD — articles 2016–2025 · sweep 2026-10-20 · 75,000 works   [Map|Overview] ⓘ│
├──────────────┬───────────────────────────────────────────┬────────────────────┤
│ SIGNAL FEED  │                                           │ DETAIL             │
│ [Topics|Cit.|│            SEMANTIC MAP                   │ (signal, cluster   │
│  Collab.]    │                                           │  or work)          │
│ level ▾      │                                           │                    │
│ ▲New ▲Rising │                                           │                    │
│ ▼Fall ✕Gone  │                                           │                    │
│ search…      │                                           │                    │
│ ─ cards ─    ├───────────────────────────────────────────┤                    │
│              │ ▶ 2016 17 18 │2019 20 21 22 23 24 25   window|cumulative     │
└──────────────┴───────────────────────────────────────────┴────────────────────┘
   360 px                       flexible                          420 px (closable)
```

### 3.2 Time bar (the interactive timer)

- **Steps** come from `meta.steps`, computed at export. Year mode: one step per year, 2016 … 2025 (10 steps). Semester mode: one step per half-year end, 2016-H2 … 2025-H2 (19 steps). Each step is a 12-month window: the calendar year, or the 12 months ending at that half-year. Steps before the first cutoff (2016–2018) are baseline-only. The others are the cutoffs (`meta.cutoffs`).
- One global state: `step` (index into `meta.steps`) and `mode ∈ {window, cumulative}`.
- Each tick shows a mini stacked bar: works in that step's window (grey) and, for cutoffs, the number of signals per detector.
- A vertical divider separates the baseline-only steps from the cutoffs. In semester mode, `-H1` ticks are drawn smaller, and a note says that consecutive windows overlap by 6 months.
- ▶ plays from the first to the last step (~1.5 s per year step, ~1 s per semester step), then stops. Space toggles play; ← → step.
- Effects:
  - **Map:** points whose `pub_month` falls in the step's 12-month window (window mode), or at or before its end (cumulative mode), are drawn fully; the others stay as a faint background. In trend colour mode, clusters use the trend at that cutoff.
  - **Feed:** shows the signals of that cutoff. For baseline-only steps it shows "Baseline period (2016–2018) — signals start in 2019" instead of an empty list. At `-H1` cutoffs the Citations tab shows the yearly-only note (04 §2.4).
  - **Detail:** an open signal is kept if the same entity has a signal at the new cutoff. Otherwise the panel shows "No signal for this entity at {cutoff}", with its series still visible.

### 3.3 Signal feed

- Tabs: Topics · Citations · Collaborations, each with its signal count at the current cutoff.
- Level toggle: topic / subfield; institution / country (not shown for citations).
- Label chips with counts (`▲ New`, `▲ Rising`, `▼ Falling`, `✕ Gone`; for citations `✦ Breakout`, `▲ Accelerating`). Multi-select. Glyph and text, never colour alone.
- Text search on entity label.
- Sorted by `rank` (never displayed as a number).
- **Card:** label badge · entity label (parent label in small text) · `b → c` with shares ("30 → 25 works, 0.13% → 0.29%") · effect "share ×2.4 (1.4–4.0)" · a 2016–2025 yearly share sparkline with the baseline shaded and the current window marked.
- Hovering a card previews its works on the map (highlight without selecting). Clicking selects it.
- Keyboard: ↑ ↓ move, Enter selects, Esc clears.

### 3.4 Semantic map

- `OrthographicView`, pan and zoom, fit to data on load.
- Background layer: all points, radius 1.5 px, alpha ~0.08. Foreground layer: the same points filtered by year with `DataFilterExtension` on `pub_month` (`filterRange` = the step's `[start_month, end_month]`, or `[0, end_month]` in cumulative mode), with radius transitions.
- **Colour modes** (selector in the map corner):
  - *Trend* (default): cluster trend at the current cutoff — rising teal, falling orange, new violet, no signal neutral grey; outliers light grey.
  - *Region*: ~20 categorical hues.
  - *Abstract*: works with or without abstract (diagnostic).
- **Labels:** region labels when zoomed out; cluster labels above a zoom threshold; collision-avoided (TextLayer with `collisionEnabled` or simple greedy placement).
- **Implementation note (October 2026):** the background and foreground layers are merged into one ScatterplotLayer whose alpha and radius are recomputed per time-bar step (points outside the window drawn faint), instead of two layers + `DataFilterExtension`: same picture, half the points to draw (78k instead of 156k), measured 2× faster on a software renderer. Labels use the greedy screen-space placement (biggest first), which does not depend on GPU picking.
- **Selection:** when a signal is selected, its `work_idx` points become large and outlined, everything else dims, and a "Zoom to works" button fits the view to them. For a citation signal (one work), the point pulses and its cluster outline is shown.
- **Hover tooltip:** title, year, cluster label, OpenAlex topic. Click a point → work detail. Click a cluster label → cluster detail.

### 3.5 Detail panel

**Signal detail**
1. Header: label badge, entity, parent, detector · level · cutoff.
2. The `why` sentence.
3. **Dumbbell chart:** baseline share and current share on one axis (two dots and a connector), plus the ratio and its 95% interval written beside it.
4. **Yearly series:** bars = count per year, line = share; baseline years shaded, current year highlighted.
5. **On the map:** the top 3 clusters holding its works, with shares (clickable).
6. **Works:** top 10 (title, year, citations, OpenAlex and DOI links), then "Show all N" expanding to the full `work_idx` list.
7. Detector-specific block:
   - *Citations:* yearly citation bars, cohort ("2019 · Environmental Science · 1,240 works"), citing works of year Y if present.
   - *Collaborations:* country, institution type, ROR link, anchor units most involved.
8. "How this was computed" (collapsed): `c, b, C, B`, p, q, test name, parameters, link to the method text.

**Cluster detail:** label and top 10 terms; works per year (bars); trend at each cutoff (small table: label, ×ratio, CI, q); top OpenAlex topics with shares; signals whose works fall mostly in this cluster (≥ 20% of their works).

**Work detail:** title, year, topic, cluster, citations, DOI/OpenAlex links, and the signals that include this work.

### 3.6 Overview view

- **Volcano plot per detector** (level toggle, cutoff from the time bar): x = log2 share ratio, y = −log10 q. Non-signals grey, signals coloured by label. Dashed guides at q = alpha and at ±`min_log2_ratio`. Hover → entity and numbers; click → switch to Map view with that signal selected. Caption states how many entities were tested and whether the plot is sampled.
- **Signals by cutoff:** for each detector, stacked bars of signal counts by label for each cutoff (7 bars in year mode, 13 in semester mode).
- **Since last sweep:** totals (works added/removed, reassigned topics, new partners), the lists from `diff.json`, each work clickable to the map. Hidden with a short note when there is only one sweep.
- **About the data:** universe filter, sweep date, quality highlights (abstract coverage per year, January-1 date share, materialized anchor share), the method in 8 lines, known limits (01 §7), and a **Download brief (.md)** button (`brief_md` → Blob).

## 4. Visual direction

- Dark "situation room" theme by default (slate background, high-contrast text), with a light theme toggle. Colours defined as CSS variables.
- Semantic colours: rising teal, falling orange, new violet, gone muted red; neutral grey for "no signal". The same mapping everywhere (feed, map, charts).
- Numbers right-aligned with tabular figures. No decorative gradients and no 3-D.
- Every chart has a one-line caption saying what is plotted and in which unit.

## 5. Explicit non-goals for the UI

No login, no persistence of user state besides the URL hash (`#signal=…&year=…&mode=…`), no editing, no live API calls, no LLM, no network graph, no geographic map.

## 6. Tests and acceptance

Vitest:
- Bundle loader validates `schema_version` and that every `work_idx` < `points.n`.
- Feed selector: filters by tab, level, labels and search combine correctly; a cutoff change swaps the list; baseline steps show the message; `-H1` cutoffs show the citations note.
- Selecting a signal produces the expected highlight mask.

Acceptance (manual, on the real IRD bundle):
1. First paint of the map < 3 s on a laptop; panning and the time-bar animation stay smooth (no visible stutter).
2. Playing the timer from 2016 to 2025 visibly moves the bright points, shows the baseline message for 2016–2018, and switches feed contents at every cutoff from 2019.
3. For one signal of each detector: the card, the detail panel and the map highlight agree on the same works; for topics and collaborations, `c` equals `len(work_idx) + n_unmapped`.
4. Clicking a point in a volcano plot opens the corresponding signal on the map.
5. The URL hash restores the same view after reload.
6. No console errors on the nominal path. `npm run build` passes.
