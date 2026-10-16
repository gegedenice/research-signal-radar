# Delta Radar — fresh-start specifications

These documents specify a simplified rebuild of the Research Signal Radar prototype.
They replace, for implementation purposes, everything in `01_documentation/` and the
code in `02_runs/research-signal-tm01-tm02-v0.1/`. Those remain as history only.

The universe changes from Mines Paris–PSL to **IRD (Institut de recherche pour le
développement), non-retracted articles published 2016–2025**. 2020–2025 alone returned
47,851 works in October 2026; the 2016–2025 total, roughly 70–80k, is measured at build step 2.
Starting in 2016 gives a three-year baseline before the first cutoff (2019), so there are
seven yearly cutoffs (2019–2025), or thirteen half-year cutoffs in the optional semester mode.

## Reading order

| # | File | What it specifies | Hand to Claude when… |
|---|---|---|---|
| 01 | `01_overview-and-decisions.md` | Purpose, the signal chain, what was cut and why, glossary, repo layout | Always — every session starts here |
| 02 | `02_openalex-api-client-v1.md` | Rewrite of `gegedenice/openalex-api-client` as a generic v1 (also used by the IRD study) | Working on the client repo |
| 03 | `03_universe-and-sweep.md` | Universe config, harvest, normalized tables, snapshot storage, sweep-to-sweep diff | Building ingestion |
| 04 | `04_delta-engine-and-detectors.md` | The single statistical engine and the three detectors (topics, citations, collaborations) | Building detection |
| 05 | `05_semantic-map.md` | Embeddings (Albert / BAAI/bge-m3), UMAP, HDBSCAN, BERTopic, cluster series | Building the semantic layer |
| 06 | `06_bundle-and-ui.md` | Static data bundle, screens, interactions, dataviz | Building the UI |
| 07 | `07_build-plan.md` | Ordered steps, one Claude session each, with acceptance criteria | Planning / starting each step |

## How to use these with Claude

1. Create the new repository (`delta-radar`, see 01 §6) and copy this folder into it as `specs/`.
2. Add a `CLAUDE.md` at the repo root with the content given in 07 §1.
3. Run one step of `07_build-plan.md` per session: give Claude the step, plus 01 and the spec(s) the step names.
4. Each step ends when its acceptance criteria pass. Do not let a session start the next step.

## Conventions used in the specs

- **MUST / SHOULD / MAY** have their usual meaning. Anything not marked MUST is negotiable.
- Parameter defaults are given in `code` and are all configurable in `config/ird.toml`.
- "Verify" marks a fact about an external API that the implementer must check against the live API before relying on it.
