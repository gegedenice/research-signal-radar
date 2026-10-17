# 04 — Delta engine and the three detectors

## 1. Design in one paragraph

Each detector turns a sweep's tables into the same small input: for every entity, a count in
the **current window** (`c`), a count in the **baseline window** (`b`), and the matching
**denominators** (`C`, `B`). The engine asks one question of every entity: *is its share of the
denominator different now from what it was in the baseline?* It answers with an exact test,
controls the false discovery rate across all entities, and reports an effect size with a
confidence interval. Everything a detector adds is how it counts.

Because the test compares **shares**, overall growth of the institution's output does not
create signals: if IRD publishes 20% more in total and a topic grows by 20%, nothing fires.

## 2. Periods, windows and cutoffs

### 2.1 Common rules

- All time arithmetic uses `works.pub_month` (months since January of `first_year`).
- The **current window** is always 12 months long (`periods.window_months`). The **baseline** is the 36 months immediately before it (`periods.baseline_months`). There are never 6-month current windows: halving the window halves the counts, and a simulation showed detection power dropping by about half for the same entities (see the power table in §3).
- A **cutoff** is the last month of a current window. Cutoffs start at the first month where a full baseline exists. The latest cutoff is the "current situation"; earlier cutoffs give the signal history behind the UI timer.
- `history_before` = the entity's count in all months before the baseline. NEW therefore means "absent since January 2016".

### 2.2 The two period modes (`periods.mode`)

| | `year` (default) | `semester` (option) |
|---|---|---|
| Current window | Calendar year Y (Jan–Dec) | 12 months ending 30 June or 31 December |
| Baseline | Y-3 … Y-1 | the 36 months before |
| Cutoff label | `2025` | `2025-H1` (window Jul 2024–Jun 2025), `2025-H2` (= calendar 2025) |
| Cutoffs for IRD (2016–2025) | 2019 … 2025 → **7** | 2019-H2, 2020-H1 … 2025-H2 → **13** |
| Successive windows overlap | no | by 6 months (consecutive cutoffs are not independent) |

Every `-H2` cutoff in semester mode is computed exactly as the same year in year mode. The semester mode only adds the `-H1` cutoffs in between.

The code handles both modes with one function, `windows(cutoff) -> (current_months, baseline_months)`, and the cutoff list. Nothing else in the engine or the detectors depends on the mode.

### 2.3 When to turn on semester mode (decision at build step 2)

When only the year is known, OpenAlex sets `publication_date` to January 1. In semester mode, a `-H1` window (Jul Y-1 – Jun Y) catches all of year Y's January-1 works but only half of the year's real output. This creates false rises in `-H1` windows for fields and journals that publish year-only dates. Year mode is immune, because January 1 is still in the right year.

Turn semester mode on only if `quality.json` shows **both**:
- January-1 share overall ≤ 5% of works, and
- January-1 share ≤ 15% in every OpenAlex field with ≥ 500 works.

Otherwise keep year mode and write the measured values in a comment in `config/ird.toml`. Even when it is on, the UI states on `-H1` cutoffs that windows overlap with the previous cutoff.

### 2.4 Citations are always yearly

`counts_by_year` only gives citations per calendar year. The citation detector therefore runs only at year-end cutoffs (`2019 … 2025`, or the `-H2` cutoffs in semester mode). At `-H1` cutoffs its feed shows "Citations are counted per calendar year — latest available: {Y-1}-H2".

## 3. The engine (`radar/engine.py`)

One vectorized function. No detector-specific code inside.

```python
def assess(df: pd.DataFrame, *, alpha: float, min_log2_ratio: float,
           directions: set[str] = {"up", "down"}) -> pd.DataFrame:
    """df columns: entity_id, c, b, C, B, history_before (+ any passthrough columns).
    Returns df with: share_c, share_b, log2_sr, ci_low, ci_high, p, q, is_signal, label, rank."""
```

For each row:

1. **Shares**: `share_c = c / C`, `share_b = b / B`.
2. **Exact conditional test.** If the entity's share did not change, then given the `n = c + b` works it has across both windows, the number falling in the current window follows `Binomial(n, p0)` with `p0 = C / (C + B)`. Two-sided p-value:
   `p = min(1, 2 · min(P[X ≤ c], P[X ≥ c]))`, computed with `scipy.stats.binom.cdf` and `.sf` (vectorized). This is the standard conditional test for comparing two Poisson rates.
3. **Effect size.** Share ratio with a +0.5 continuity correction (so zero counts are defined):
   `SR = ((c + 0.5) / C) / ((b + 0.5) / B)`, reported as `log2_sr = log2(SR)`.
   95% interval: `ln SR ± 1.96 · sqrt(1/(c+0.5) + 1/(b+0.5))`, converted to log2 → `ci_low`, `ci_high`.
4. **False discovery control.** Benjamini–Hochberg over all rows passed in one call → `q`. The caller passes exactly one detector × level × cutoff per call. Implement BH directly (10 lines) rather than adding statsmodels.
5. **Signal rule.** `is_signal = (q ≤ alpha) and (|log2_sr| ≥ min_log2_ratio) and direction allowed`, where direction is `up` if `log2_sr > 0`, else `down`. Defaults: `alpha = 0.05`, `min_log2_ratio = 0.585` (share ×1.5 or ÷1.5). The effect-size floor stops very large entities from signalling trivially small but significant changes.
6. **Label** (signals only):

   | Label | Condition |
   |---|---|
   | `NEW` | up, `b == 0` and `history_before == 0` |
   | `RISING` | up, otherwise. Add boolean `returning = (b == 0 and history_before > 0)` |
   | `FALLING` | down, `c > 0` |
   | `GONE` | down, `c == 0` |

7. **Rank** (sort key within a detector × level × cutoff): the conservative effect size, i.e. the CI bound closest to zero: `rank = max(0, ci_low)` for up, `max(0, -ci_high)` for down. Sort by `rank` descending, then `q` ascending. Rank is never shown as a score, only used for ordering.

### Worked example (MUST be a unit test)

A topic has `b = 30` works out of `B = 24,000` in 2022–2024 and `c = 25` out of `C = 8,500` in 2025.
`p0 = 8,500 / 32,500 = 0.2615`; expected current count = `55 × 0.2615 = 14.4`; observed 25.

| Quantity | Value |
|---|---|
| p (two-sided) | 0.0031 |
| log2 SR | 1.239 (share ×2.36) |
| 95% CI (log2) | [0.480, 1.998] (×1.39 to ×3.99) |
| rank | 0.480 |

Other reference cases with the same denominators (also tests): `c=6, b=0` → p = 0.00064, log2 SR = 5.198; `c=3, b=0` → p = 0.036 (does not survive FDR in a realistic run — three works are not enough to call something new); `c=2, b=40` → p = 0.00073, log2 SR = −2.520, CI [−4.363, −0.678].

### Statistical power — what to expect

FDR control makes the engine conservative when many entities are tested. A simulation with
2,000 tested entities and the denominators above gave:

| Baseline works per entity (3 years) | Share ×2 recovered | Share ×3 recovered |
|---|---|---|
| ≈ 10 | 0 / 20 | 0–1 / 20 |
| ≈ 30 | 0–2 / 20 | 15–18 / 20 |
| ≈ 60 | 2–12 / 20 | 20 / 20 |

with 0–2 false signals in every run. The same simulation with a 6-month current window
(semester counts) recovered about half as much: ×3 effects on entities with ~30 baseline works
were found 4–10 times out of 20 instead of 15–18. This is why windows stay 12 months long in
both period modes. Consequences:
- Small topics will rarely signal. That is the intended correction of the prototype's main weakness (on Mines, 66% of raw topic-level RISING onsets had reversed a year later). The subfield level exists to catch broader movements made of many small topics.
- `min_support` matters twice: it removes untestable entities and, by reducing the number of tests, increases power for the others.
- If the feed is too quiet in practice, raise `alpha` to 0.10 before touching anything else, and say so in the UI.

### What the engine deliberately does not do

No priority formula, no confidence levels, no persistence requirement, no multi-scale
concordance, no sensitivity profiles. If a signal is fragile, its q-value and its interval say so.

## 4. The three detectors

Each detector module exposes one function:

```python
def build(tables: SweepTables, cfg: DetectorConfig, cutoff: Cutoff, level: str) -> pd.DataFrame
    # Cutoff = (label, current_months, baseline_months) from windows() in §2.2
    # returns engine input rows + passthrough columns:
    # entity_id, entity_label, parent_id, parent_label, c, b, C, B, history_before,
    # series (list[{"period", "n", "den"}] per calendar year 2016–2025, both modes; display only), work_ids_current (list[str]), extra (dict)
```

and the orchestrator (`radar detect`) loops over detectors × levels × cutoffs, calls `build`, filters by minimum support, calls `assess`, and writes the outputs (§6).

### 4.1 Topics (`detectors/topics.py`)

- **Entity:** an OpenAlex topic (`level = "topic"`) or subfield (`level = "subfield"`). The two levels are independent views; no rule links them. The topic level carries `parent_id/parent_label` = its subfield for display.
- **Counting** (`counting`, amendment of October 2026, see below):
  - `"all"` (default): a work counts for **each of its topics** (OpenAlex assigns up to 3: the primary topic and two secondary ones), and at subfield level for each distinct subfield among them. A work counts at most once per entity.
  - `"primary"`: a work counts only for its primary topic and the primary topic's subfield (the original rule).
- **Count:** number of distinct works with that topic/subfield in the window.
- **Denominator:** works in the window with at least one topic (in practice, a non-null primary topic). It stays a number of **works**, not of topic assignments, so a share still reads "x% of the institution's works touch this topic". In `"all"` mode shares across entities sum to more than 100%; this does not affect the test, which looks at one entity at a time and counts each work once for it.
- **Tested if:** `c + b ≥ min_support` (default 10).
- **Evidence:** `work_ids_current`; `top_work_ids` = up to 10 by `cited_by_count`; `extra.counting`; `extra.primary_share` = share of the current works for which the entity is the primary topic (or the primary topic's subfield), so a reader can tell a core theme from a secondary one.

**Why the amendment.** With primary-topic counting, the IRD sweep (77,831 works, ≈ 7,450 per year over ≈ 2,900 topics) gave a topic level where almost no entity reaches the ≈ 30 baseline works per entity needed to detect a ×3 change (power table, §3): 515 topics tested and 1–2 signals at the 2025 cutoff. Counting the three topics multiplies the evidence per topic by up to 3 without changing the test, and matters even more for smaller institutions. The secondary topics come from the same OpenAlex classifier, with lower scores: the classifier caveat of 01 §7 applies a fortiori, and `extra.primary_share` keeps it visible.

### 4.2 Citations (`detectors/citations.py`)

Source: `counts_by_year` (citations received per calendar year, by year of the citing work), zero-filled for missing years.

- **Entity:** a work `w` with publication year `p ≤ Y - min_age_years` (default 2, so there is at least a two-year baseline).
- **Count:** `c` = citations received in year `Y`; `b` = citations received over the baseline years that are ≥ `p`, i.e. `max(p, Y-3) … Y-1`.
- **Coverage:** OpenAlex documents `counts_by_year` as covering the last ten years. A citation cutoff is evaluated only if every baseline year is within the coverage measured in `quality.json`. Otherwise it is skipped and recorded in `detect_summary.json`. With a 2026 harvest this probably drops the 2019 cutoff (it needs 2016) — **verify**.
- **Denominator (cohort):** works with the same publication year and the same field (`field_id`). If that cohort has fewer than `min_cohort_size` works (default 20), fall back to same year + domain, then same year only. Record the cohort used in `extra.cohort`.
  `C` = citations received in `Y` by the cohort **excluding w**; `B` = same for the baseline years. (Leave-one-out stops a highly cited work from diluting its own reference.)
  Because all cohort members share the publication year, they share the same baseline years, so the shares are comparable.
- **Tested if:** `c ≥ min_current` (default 5). Only `up` direction (`directions = ["up"]`): fading citations of ageing papers are expected and not monitored.
- **Labels in the UI:** `NEW` is shown as **Breakout** (no citations before `Y`), `RISING` as **Accelerating**.
- **Evidence:** the work itself, its yearly citation series, cohort label and size. Optional (export step, top 50 signals only): the citing works of year `Y` via `oa.list("works", filter=f"cites:{w},publication_year:{Y}", select="id,title,publication_year")` — 50 cheap calls.

### 4.3 Collaborations (`detectors/collaborations.py`)

- **Co-publication rule** (kept from the prototype): work `w` counts for external institution `e` if `w` has an author position affiliated to `e` and a **different** author position affiliated to an anchor institution. One author holding both an IRD unit and `e` is a dual affiliation, not a collaboration, unless another author provides the anchor side. Author positions are compared by index, so authors without an OpenAlex ID still count as distinct people.
- **Consortium guard:** works with `n_authors > max_authors` (default 50) are excluded from this detector (numerator and denominator), and their number is reported in `detect_summary.json`.
- **Entity:** external institution ID (`level = "institution"`) or its country code (`level = "country"`; institutions without a country are skipped). An institution is external if it is not an anchor. Institutions/countries in `exclude_countries` are dropped before testing.
- **Count:** distinct works per entity per window. **Denominator:** works in the window (after the consortium guard).
- **Tested if:** `c + b ≥ min_support` (default 5).
- **Evidence:** `work_ids_current`; `extra` = institution type, country, ROR, and the anchor units most involved in the current works (top 5 anchor institutions by work count).
- **Note for the UI:** for the first cutoff (2019), `NEW` means "absent in 2016–2018". The label tooltip always states that observable history starts in January 2016.

## 5. Reuse by the semantic layer

Spec 05 calls `assess` once per cutoff with entity = semantic cluster, count = works in the cluster, denominator = all mapped works. The result colours clusters on the map by trend. It is not a fourth detector: it has no signal feed of its own.

## 6. Outputs (`data/sweeps/<id>/derived/`)

**`assessments.parquet`** — every tested entity, all detectors, levels and cutoffs:
`detector, level, cutoff, cutoff_month, entity_id, entity_label, parent_id, parent_label, c, b, C, B, share_c, share_b, log2_sr, ci_low, ci_high, p, q, is_signal, label, returning, rank`.
`cutoff` is the label string (`2025` or `2025-H1`); `cutoff_month` is the `pub_month` index of its last month.

**`signals.parquet`** — rows of `assessments` with `is_signal`, plus:
`signal_id` (= `f"{detector}:{level}:{entity_id}:{cutoff}"`), `series`, `work_ids_current`, `top_work_ids`, `extra` (JSON string), `why` (sentence, §7).

**`detect_summary.json`** — per detector × level × cutoff: number of entities seen, tested, signals per label; consortium works excluded; parameters and `config_hash`.

## 7. The "why" sentence (template, no LLM)

- Topics / collaborations: `"{label}: {c} of {C} works in {current_window} ({share_c:.1%}) vs {b} of {B} in {baseline_window} ({share_b:.1%}). Share ×{SR:.2g} (95% CI ×{lo:.2g}–×{hi:.2g}), q = {q:.2g}."`
- Citations: `"{title}: {c} citations in {Y} vs {b} over {baseline years}. Its share of citations to {cohort} papers rose ×{SR:.2g} (95% CI ×{lo:.2g}–×{hi:.2g}), q = {q:.2g}."`
- `{current_window}` / `{baseline_window}` read "2025" / "2022–2024" in year mode and "Jul 2024–Jun 2025" / "Jul 2021–Jun 2024" in semester mode.

## 8. Brief (`radar brief`, also run at the end of `radar detect`)

`brief.md` for the latest cutoff, built from a template:
1. Header: universe label, sweep date, cutoff, number of works.
2. Since last sweep: the `diff.json` totals and up to 5 notable items per section.
3. For each detector (and level): counts of signals by label, then the top 10 signals by rank, each with its `why` sentence and an OpenAlex link.
4. Method note (5 lines): windows, test, FDR, effect-size floor, known limits (01 §7).

## 9. CLI

```
radar detect [--sweep latest|<id>] [--config config/ird.toml]   # all detectors, levels, cutoffs + brief
radar brief  [--sweep latest|<id>]
```

`detect` runs from scratch every time and overwrites `derived/assessments.parquet`, `signals.parquet`, `detect_summary.json` and `brief.md`. It must finish in under a minute on the IRD sweep.

## 10. Tests

1. Worked example and reference cases of §3 (to 3 decimals).
2. **Null calibration:** 2,000 synthetic entities with constant share, Poisson counts, fixed seed → at most 2 signals.
3. **Planted effects:** 2,000 entities with baseline mean 60 (denominators as in §3), 20 of them with share ×3 → at least 18 recovered and at most 3 false signals, over 5 seeds. (Simulation while writing this spec: 20/20 recovered, 0–2 false.)
4. **Growth invariance:** multiplying all current counts and `C` by 1.5 leaves the signal set unchanged (up to rounding at the boundary).
5. Labels: NEW, RISING with `returning`, FALLING, GONE each produced by a hand-built case.
6. Citations: leave-one-out denominators; cohort fallback order; baseline years start at the publication year.
7. Collaborations: single dual-affiliated author → not counted; two distinct authors → counted; work above `max_authors` → excluded; country level aggregates institutions.
8. `windows()`: year mode gives cutoffs 2019…2025 for 2016–2025 data; semester mode gives 13 cutoffs; each `-H2` window equals the year-mode window; baseline always 36 months, ending just before the current window.
9. Citations run only at year-end cutoffs; a cutoff whose baseline years fall outside the measured `counts_by_year` coverage is skipped and reported.
10. `detect` on a small fixture sweep produces the three files with the documented columns.
11. Topics counting: in `"all"` mode a work with three topics counts once for each of them (and once per distinct subfield), the denominator counts works not assignments, and `extra.primary_share` is right; `"primary"` mode reproduces the original rule.
