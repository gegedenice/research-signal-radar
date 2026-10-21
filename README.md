# Research Signal Radar

Research Signal Radar monitors an institution's research output in OpenAlex the way a situation room
monitors live sources. It **sweeps** the institution's works and compares the latest year with the
three years before (the **baseline**). It promotes statistically significant changes to **signals**, lets
you **drill down** to the works behind each signal on a semantic map, and writes a short **brief**.

The first universe is **IRD** (Institut de recherche pour le développement): non-retracted articles
published 2016–2025, about 78,000 works.

It answers one question per detector:

| Detector | Entity | Question |
|---|---|---|
| Topics | OpenAlex topic / subfield | Which research themes take a markedly larger or smaller share of the output than in the recent past? |
| Citations | Work | Which works are cited markedly faster than comparable works (same year and field)? |
| Collaborations | External institution / country | Which partners appear, return, intensify or fade in the co-publications? |

A **semantic map** (2-D or 3-D) places every work by its title and abstract, so signals can be seen in
the intellectual landscape and over time.

It is a prototype: correctness, traceability and simplicity come before completeness.

## How it works

```
OpenAlex ──radar sweep──▶ snapshot (Parquet) ──radar detect──▶ signals + brief.md
                                   │
                                   ├──radar embed──▶ title + abstract embeddings (Albert, BAAI/bge-m3)
                                   │                        │
                                   │                  radar map──▶ clusters, regions, 2-D / 3-D map
                                   │                        │
                                   └────────────radar export──▶ ui/public/data/ ──▶ web UI (React + deck.gl)
```

- **One statistical engine** for the three detectors. Each detector only counts works (or
  citations) per entity in a 12-month current window and the 36 months before. The engine then
  compares shares: exact conditional binomial test, Benjamini–Hochberg false-discovery control and a
  minimum effect size. Labels: `NEW`, `RISING`, `FALLING`, `GONE`.
- **Every signal resolves to works.** The UI shows them in the feed, the detail panel and on the map.
- **No generative model anywhere.** Embeddings are used for the map only. Cluster labels are c-TF-IDF
  terms. The brief is filled from a template.
- **Since last sweep.** Each new sweep is diffed against the previous one: works added and removed,
  reassigned topics, partners seen for the first time, citation jumps.

## Requirements

- Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 20 (for the UI)
- An OpenAlex API key and an [Albert](https://guides.ia.numerique.gouv.fr/albert-api/) API key (for embeddings)

```bash
cp .env.example .env     # then fill OPENALEX_API_KEY and ALBERT_API_KEY (never in config files)
uv sync
```

## Running a sweep

```bash
uv run radar sweep       # harvest the universe → data/sweeps/<date>/ (resumable the same day)
uv run radar detect      # all detectors, levels and cutoffs → derived/ + brief.md   (< 1 min)
uv run radar embed       # embeddings, cached: a later sweep only sends new or changed texts
uv run radar map         # clusters + 2-D/3-D map, offline (≈ 10 min on a laptop)
uv run radar export      # bundle for the UI → ui/public/data/
```

Other commands: `radar brief` rewrites the brief; `radar diff <old> <new>` compares two stored sweeps.
Every command takes `--config` (default `config/ird.toml`) and `--sweep latest|<id>`.

## Web UI

```bash
cd ui
npm install
npm run dev              # http://localhost:5173
npm run build            # production build in ui/dist/ (static files, no backend)
```

- **Map:** colour by cluster trend, region or presence of an abstract; 2-D or 3-D; zoom to a signal's works.
- **Time bar:** play 2016 → 2025, step by step, by window or cumulatively.
- **Feed:** signals per detector at the current cutoff, filterable by level, label and text.
- **Detail panels:** signals (why, share chart, yearly series, works, how it was computed), clusters and works.
- **Overview:** volcano plots, signals per cutoff, since last sweep, about the data, brief download.
- Works on desktop, tablet and phone.
- The URL keeps the view, so a link opens the same signal at the same year.

## Configuration

`config/ird.toml` holds the universe (one OpenAlex filter) and every parameter: periods, engine
thresholds, detector settings and map settings. Comments record the values measured on the IRD
sweep and the decisions taken during the build.

To monitor another institution, copy the file. Change `[universe]` (`root_institution`, `filter`,
years), then run the commands above with `--config`.

## Repository layout

```
config/ird.toml        universe and parameters
specs/                 specifications (source of truth for the design; read 01 first)
src/radar/             sweep, tables, diff, engine, detectors/, brief, semantic/ (embed, map), export, cli
tests/                 pytest, no network
ui/                    React + TypeScript + Vite app (vitest)
data/                  sweeps and caches (git-ignored)
```

The OpenAlex client lives in its own repository,
[gegedenice/openalex-api-client](https://github.com/gegedenice/openalex-api-client) (v1.0.1).

## Tests

```bash
uv run pytest            # Python (no network)
cd ui && npm test        # UI logic
```

## Known limits

- OpenAlex topics come from a classifier: topic signals inherit its errors. Drill down to the works
  to catch them.
- Citations use today's `counts_by_year`: detection at past cutoffs is a reconstruction.
- `NEW` means absent from this universe since 2016, not new to science. 2016–2018 are baseline only.
- Collaboration signals depend on affiliation disambiguation: a renamed or merged institution can
  look like a new partner.
- Works without an abstract (about 22% for IRD) are placed on the map from their title only.
