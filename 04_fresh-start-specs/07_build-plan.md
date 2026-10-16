# 07 — Build plan

One step = one Claude session. Give Claude: this file (the step), `01_overview-and-decisions.md`,
and the specs listed for the step. A step is done when its acceptance criteria pass; the
session stops there.

## 1. `CLAUDE.md` for the `research-signal-radar` repository

```markdown
# Research Signal Radar

Read specs/01_overview-and-decisions.md before any change. The spec for the current step is
named in the request. Specs are the source of truth; if code and spec disagree, ask.

Rules
- Keep it simple. This is a prototype. Do not add stages, scores, confidence layers, schemas
  or abstractions that the specs do not ask for. If something seems missing, propose it in one
  sentence and wait.
- One statistical engine (src/radar/engine.py). Detectors only build counts and denominators.
- No LLM anywhere. Embeddings only for the semantic map.
- The UI never recomputes statistics, labels or ranks.
- Secrets only from environment variables (.env, git-ignored). Never log keys or URLs with keys.
- Tests: pytest (Python), vitest (UI). No network in tests.
- Python ≥ 3.11, managed with uv. New dependencies need a one-line justification in the PR.

Commands
- uv run radar sweep | detect | embed | map | export
- uv run pytest
- cd ui && npm run dev | npm run build | npm test
```

## 2. Steps

### Step 1 — `openalex-api-client` v1 (repo: openalex-api-client) · spec 02

Deliver: new client, `F` filter builder, retry and budget handling, cursor iteration, `group_by`, page cache with resume, `tidy` tables, deprecated v0 wrapper, README with the §10 examples, tests §9.
Accept when:
- all tests in 02 §9 pass with no network;
- one manual live run (by Géraldine) of the §10 examples succeeds, and `oa.count` on the Research Signal Radar filter returns the expected order of magnitude (≈ 47–48k for 2020–2025; the 2016–2025 total is recorded);
- `pip install "openalex-api-client[tables] @ git+https://github.com/gegedenice/openalex-api-client@v1.0.0"` works in a clean venv.

### Step 2 — Repository scaffold, config, sweep, quality, diff · specs 03

Deliver: `research-signal-radar` skeleton (01 §6), config loader, `radar sweep`, radar columns, snapshot layout, `quality.json`, `radar diff`, tests 03 §7.
Accept when:
- tests pass;
- a real sweep produces all tables; `harvested_count` is within 0.5% of `expected_count`;
- `quality.json` is reviewed with Géraldine: abstract coverage per year, January-1 share, materialized anchor share, `n_authors` distribution. **Decision points:** confirm `max_authors` and whether to set `exclude_countries = ["FR"]`; set `periods.mode` with the rule in 04 §2.3 (January-1 share ≤ 5% overall and ≤ 15% in every field with ≥ 500 works → `semester` allowed, otherwise `year`), and record the measured values in `config/ird.toml`; note the `counts_by_year` coverage, which tells which citation cutoffs exist.

### Step 3 — Engine · spec 04 §2–§3, §10 (tests 1–5 and 8)

Deliver: `windows()` for both period modes, `engine.assess` and BH, with tests on the worked example, reference cases, null calibration, planted effects, growth invariance, labels.
Accept when: all engine tests pass, and the function has no detector-specific code.

### Step 4 — Detectors, outputs, brief · spec 04 §4–§9

Deliver: the three detectors, `radar detect`, `assessments.parquet`, `signals.parquet`, `detect_summary.json`, `brief.md`.
Accept when:
- tests 04 §10 (6, 7, 9, 10) pass;
- on the real sweep, `radar detect` runs in < 1 minute;
- Géraldine reads `brief.md` and 10 signals per detector, checking each against its works. **Decision point:** adjust `alpha`, `min_support`, `min_log2_ratio` if the feed is unreadable (too many or too few signals). Record the decision in `config/ird.toml` comments.

### Step 5 — Embeddings · spec 05 §3

Deliver: Albert client with model resolution, batching, retries, cache; `radar embed`; tests.
Accept when: tests pass; a real run embeds every work with text; a second run makes zero API calls; tokens/cost are reported.

### Step 6 — Landscape · spec 05 §4–§8

Deliver: `radar map` (BERTopic clusters, 2-D coordinates, regions, taxonomy link, cluster trend), outputs and quality checks; tests.
Accept when:
- tests pass;
- on real data: outlier share ≤ 25% after reduction, no cluster > 10% of works, and Géraldine judges a sample of 15 cluster labels readable. **Decision point:** tune `min_cluster_size`, stop words, `n_regions`.

### Step 7 — Export · spec 06 §2

Deliver: `radar export` writing `bundle.json`, `points.json`, `works.json`; determinism test; size check.
Accept when: two exports of the same sweep are identical except `generated_at`; sizes within targets; every `work_idx` resolves.

### Step 8 — UI · spec 06 §3–§6

Suggested order inside the step (commit after each):
1. Load bundle, layout shell, time bar state.
2. Map (deck.gl) with year filter, colour modes, labels.
3. Feed with filters and sparklines.
4. Signal detail and map highlighting.
5. Cluster and work detail.
6. Overview: volcano, signals by cutoff, since last sweep, about the data, brief download.

Accept when the six acceptance checks of 06 §6 pass.

### Step 9 — Review pass (fresh session, no code written in steps 1–8)

Ask a separate Claude session to read specs 01–06 and the repository, and report only:
places where code contradicts the specs, any statistic computed in the UI, any secret logged,
and any element that adds complexity without a spec reference. Fix or consciously accept each item.

## 3. Repeating a sweep later

```
uv run radar sweep && uv run radar detect && uv run radar embed && uv run radar map && uv run radar export
```

The diff against the previous sweep is produced automatically. Only new or changed works are embedded.

## 4. Out of scope for v1 (do not build)

Scheduling, more institutions in the UI, a backend or API, MCP exposure, user accounts,
annotations, alerts, network graphs, geographic maps, LLM summaries, projecting new sweeps onto
a frozen map, French UI strings.
