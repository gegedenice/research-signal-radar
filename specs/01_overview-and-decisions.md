# 01 — Overview and decisions

## 1. What Delta Radar is

Delta Radar monitors an institution's research output the way an OSINT situation room
monitors live sources: it **sweeps** the source on a schedule, compares the latest state
with a **baseline**, computes a **delta**, promotes statistically significant changes to
**signals**, lets the reader **drill down** to the works behind each signal, and produces a
short **brief**.

It answers one question per detector:

| Detector | Entity | Question |
|---|---|---|
| Topics | OpenAlex topic (and subfield) | Which research themes take a markedly larger or smaller share of the institution's output than in the recent past? |
| Citations | Work | Which works are being cited markedly faster than comparable works (same publication year and field)? |
| Collaborations | External institution (and country) | Which partners appear, return, intensify or fade in the institution's co-publications? |

A fourth, non-detector layer — the **semantic map** — places every work on a 2-D map built
from its title and abstract, so signals can be seen in the intellectual landscape and over time.

It is a prototype. Correctness, traceability and simplicity matter more than completeness.

## 2. The chain, made concrete

| Step | What it is in this project | Where it lives |
|---|---|---|
| Universe | One OpenAlex filter + a root institution ID, versioned in a TOML file | `config/ird.toml` (spec 03) |
| Sweep | One full harvest of the universe, stored as a dated snapshot of Parquet tables | `data/sweeps/<sweep_id>/` (spec 03) |
| Baseline | The 36 months before the current 12-month window | engine (spec 04) |
| Delta | Current-window share vs baseline share, with an exact test and a confidence interval. Windows are calendar years by default; an optional semester mode slides the 12-month window every 6 months (04 §2) | engine (spec 04) |
| Signal | An entity whose delta survives false-discovery control and a minimum effect size | `signals.parquet` (spec 04) |
| Drill-down | The works behind a signal, highlighted on the semantic map | UI (spec 06) |
| Brief | A Markdown summary generated from a template — no LLM | `brief.md` (spec 04 §8) |
| Since last sweep | What changed between two stored sweeps: new works, new partners, citation jumps | `diff.json` (spec 03 §6) |

## 3. Principles

1. **One engine, three feeds.** All three detectors reduce their data to the same shape —
   counts per entity and period plus a denominator — and go through the same statistical
   test. No detector has its own scoring formula.
2. **Statistics instead of rule stacks.** False positives from small samples are handled by an
   exact test plus Benjamini–Hochberg false-discovery control, not by additional confidence
   layers, sensitivity profiles or editorial tiers.
3. **Every signal resolves to works.** A signal carries the IDs of the works that produce it in
   the current window. The UI can always show them.
4. **No generative model in detection or labeling.** Embeddings are used for the semantic map
   only. Cluster labels come from c-TF-IDF terms. There is no LLM anywhere in the pipeline.
5. **Recompute rather than resume.** The whole detection pipeline runs in seconds to minutes
   on a snapshot. Only the two expensive, network-bound steps are cached: the OpenAlex harvest
   and the embeddings.
6. **Honest wording.** `NEW` means "absent from the observable history of this universe since
   2016", not new to science. A signal is "a significant change worth a look", not a
   discovery or a prediction.

## 4. What was removed from the prototype, and why

| Removed | Replaced by / reason |
|---|---|
| Stage split TM-01…08, CA-01…04, ACN-01…04 with per-stage result files, quality reports, `--resume`/`--rebuild` | One CLI (`radar sweep`, `detect`, `embed`, `map`, `export`, plus `diff` and `brief`). Detection is recomputed each time. |
| Census by `group_by` + separate detailed works sweep + cross-checks between them | One works harvest. Counts are computed locally from the works table. |
| Presence statuses (6), direction axes (4), growth modes (4), acceleration status | Four labels: `NEW`, `RISING`, `FALLING`, `GONE`. |
| Confidence guard (7 components), sensitivity profiles (lenient/default/strict), confidence levels | Exact test p-value → BH q-value, plus the confidence interval of the effect size. |
| Priority score combining magnitude/anomaly/persistence/support; editorial tiers; review status | Rank = conservative effect size (the CI bound closest to zero). |
| Multi-scale corroboration (topic vs subfield vs field) | The topic detector runs at two levels (topic, subfield) as two independent views. No concordance rules. |
| Monthly rolling windows with quarterly evaluation; January-date diagnostics | 12-month windows only: calendar years by default, or sliding every 6 months in semester mode, which is enabled only if the January-1 date share is low (04 §2). Never 6-month windows. |
| Retrospective backtest with episodes, +6/+12 outcomes, right-censoring, lag profiles | The engine is simply run at every cutoff (2019–2025). The resulting history drives the UI timer. |
| OpenCitations collection (≈ 11,700 raw files), dated citation events, self-citation handling | OpenAlex `counts_by_year` (citations received per calendar year). |
| `SignalEnvelope` with temporal sub-contract, JSON Schemas, dummy fixtures | One flat signal table with a documented column list (04 §6). |
| Platform vision: 150-feature registry, six scoring dimensions (magnitude, velocity, anomaly, convergence, strategic relevance, confidence), seven lifecycle states, SLM, contribution frames, claims | Out of scope. This is a prototype. |

Kept from the prototype: the chain; computing both count and share; zero-filling of missing
periods; the "two distinct authors" rule for collaborations; a raw-response cache;
React + Vite with a static JSON bundle and no backend.

## 5. Glossary

| Term | Meaning here |
|---|---|
| Universe | The set of works returned by the universe filter in `config/ird.toml`. |
| Anchor institution | An institution whose OpenAlex `lineage` contains the root institution (IRD, `I4210166444`). |
| Sweep | One complete harvest of the universe at a given date (`observed_at`). Immutable once written. |
| Period mode | `year` (default): windows are calendar years. `semester`: 12-month windows ending every 30 June and 31 December. |
| Cutoff | End of the current window, labelled `2025` in year mode or `2025-H1` / `2025-H2` in semester mode. Current window = the 12 months ending at the cutoff. Baseline = the 36 months before it. |
| Share | Entity count ÷ the detector's denominator for the same window. |
| Share ratio (SR) | Current share ÷ baseline share, with +0.5 added to both counts. Reported as log2. |
| q-value | Benjamini–Hochberg adjusted p-value within one detector × level × cutoff. |
| Signal | A tested entity with q ≤ `alpha` and \|log2 SR\| ≥ `min_log2_ratio`. |
| Assessment | Any tested entity, signal or not. Kept so the UI can plot the full distribution. |

## 6. Repository layout

Two repositories:

1. **`gegedenice/openalex-api-client`** — rewritten as v1 (spec 02). Generic. Used by Delta Radar and by the IRD study.
2. **`delta-radar`** — new repository:

```
delta-radar/
├── CLAUDE.md                 # see 07 §1
├── pyproject.toml            # uv-managed; Python ≥ 3.11
├── config/
│   └── ird.toml              # the universe and all parameters
├── specs/                    # this folder
├── src/radar/
│   ├── config.py             # load + validate TOML (pydantic or dataclasses)
│   ├── sweep.py              # harvest → snapshot (uses openalex-api-client)
│   ├── tables.py             # raw works → normalized tables
│   ├── diff.py               # sweep-to-sweep diff
│   ├── engine.py             # the single statistical engine
│   ├── detectors/
│   │   ├── topics.py
│   │   ├── citations.py
│   │   └── collaborations.py
│   ├── brief.py              # Markdown brief from template
│   ├── semantic/
│   │   ├── embed.py          # Albert client + cache
│   │   └── landscape.py      # UMAP + HDBSCAN + BERTopic
│   ├── export.py             # bundle for the UI
│   └── cli.py                # `radar` command (typer)
├── tests/
├── data/                     # git-ignored
│   ├── cache/                # raw OpenAlex pages, embeddings
│   └── sweeps/<sweep_id>/    # snapshot tables + derived outputs
└── ui/                       # React + TypeScript + Vite
```

Python dependencies: `openalex-api-client` (git), `pandas`, `pyarrow`, `numpy`, `scipy`,
`typer`, `httpx` (Albert calls), `umap-learn`, `hdbscan`, `bertopic`, `scikit-learn`.
Nothing else without a reason written in the PR.

## 7. Known limits to state in the UI and any talk

- OpenAlex topics are assigned by a classifier. Topic signals inherit its errors. The drill-down to works is how a reader catches them.
- `counts_by_year` is read from today's snapshot. Past years include citations indexed late. Detection at past cutoffs is a reconstruction, not what one would have seen at the time. OpenAlex documents `counts_by_year` as covering the last ten years only, so the earliest citation years may be missing (04 §4.2).
- The first three years (2016–2018) are baseline only, with no signals. 2020–2021 (COVID) sit inside several baselines; a share-based test absorbs the global dip, but not field-specific effects.
- Collaboration signals depend on OpenAlex affiliation disambiguation.
- Some works have no abstract in OpenAlex (the share is measured and reported in build step 2). Those works are placed on the map from their title only, and are marked as such.
