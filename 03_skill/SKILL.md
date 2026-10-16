---
name: claim-delta-radar
description: Monitor how an institution's or topic's research changes between two time windows with a two-tier instrument. TIER 1 (headline, no LLM) aggregates works along the OpenAlex topic taxonomy and diffs paper-counts into new / persisting / disappearing / rising / falling topics. TIER 2 (drill-down) extracts atomic claims from abstracts ONLY inside flagged moving topics, embeds them (Albert/bge-m3), and reads what is being claimed. Use for "what topics/claims are emerging/fading at institution X", "claim delta radar", "research-output monitoring", "track new vs disappearing findings", "scholarly trend surveillance". Inspired by the Crucix sweep->delta->signal->ideas OSINT loop, applied to research outputs.
---

# Claim Delta Mini-Radar

Turns two time windows of an institution's (or a topic's) publications into a
**new / persisting / disappearing** map of atomic research claims, plus a
grounded monitoring brief. The scholarly analog of the Crucix OSINT
sweep -> delta -> signal -> ideas loop.

## Pipeline (three-tier)

The radar runs at three resolutions matched to three questions. **Tier 1**
answers *which topics are moving* from OpenAlex metadata alone — no language
model, exact, reproducible, at full corpus scale. **Tier 2** answers *what is
being claimed* inside a moving topic, and runs the LLM ONLY on the topics Tier 1
flags, so language-model cost scales with the number of live signals, not the
size of the institution. **Tier 3** answers *where the institution sits vs the
world* on a moving topic — leading, following, niche-owner, wave-rider, or
diverging — from OpenAlex citation flow, timing, and prominence, again with no
new subscription. (On the Mines pilot the cheap Tier-1 count headline matches a
far more expensive claim-count headline: trajectory Spearman 0.99, delta 0.93 —
so Tier 1 loses nothing by skipping the LLM. See §Robustness.)

**Tier 1 — topic headline (no LLM):**
1. **Fetch metadata** — `fetch_topic_meta(inst_id, from, to, field_id=None)` pulls
   lightweight OpenAlex records (id, date, primary_topic, field) for EACH window;
   no abstract requirement, so it sees the full paper population.
2. **Headline** — `build_headline(windows, win_order, prior, recent)` builds the
   per-topic paper-count matrix and reads it as a **trajectory** (RISING/FALLING/
   STABLE per topic slope) and a two-window **delta** (NEW/PERSISTING/DISAPPEARING).
3. **Flag** — `flag_moving(headline, kinds=("RISING","FALLING","NEW"))` selects the
   topics worth a drill-down.

**Tier 2 — targeted claim drill-down (LLM, flagged topics only):**
4. **Fetch abstracts + extract** — `fetch_works(inst_id, from, to)` for the flagged
   window (carries abstracts + topic), then
   `drilldown_claims(flagged, works, host, window)` extracts 2–5 atomic claims per
   paper ONLY inside flagged topics, returning `{topic: [claims]}`.
5. **Embed (optional)** — `embed_claims(texts, api_key)` via Albert bge-m3 to
   separate genuinely new claims from restatements within a topic.
6. **Brief** — `make_brief(host, clusters, meta)` turns the flagged topics + claim
   evidence into a grounded monitoring brief with self-flagged caveats.

**Secondary signal — claim-level exploration (runs alongside Tier 1):** wherever
claims exist at corpus scale, `explore_claims(claims, emb, prior, recent)` clusters
them independent of the topic taxonomy to surface **cross-cutting themes** (spanning
many topics) and a **claim-theme delta** — movement the per-topic count is blind to.
Secondary and noisier (isolates a method-generic boilerplate cluster as a finding).
See §Secondary signal.

**Tier 3 — global positioning (OpenAlex citation structure, flagged topics only):**
7. **Position** — `position_topic(topic_id, from, to, inst_id)` (or
   `position_flagged(flagged, from, to, inst_id, topics=headline["topics"])` for a
   batch) computes, for each moving topic, three sub-signals with three
   confidence levels: **timing** (median-date lead/lag + citation-flow direction,
   HIGH, free), **prominence** (institution share of global papers + trend, HIGH,
   free), and an optional **stance** read (LLM, LOW). It returns one *positioning
   card* per topic — `LEADING / EARLY-MOVER / FOLLOWING / WAVE-RIDER /
   DIVERGING-ABSENT` — each with the evidence attached and a confidence tier, never
   a bare arrow. Because Tier 1 identifies topics by exact `primary_topic.id`, the
   global set and institution subset are exact taxonomy filters — no fuzzy label
   search, so membership is auditable by construction.

Every adapter returns the same work-dict `{id,title,date,abstract,topic,...}` so
the source is swappable: **OpenAlex** (global, has topics), **HAL**
(`fetch_hal(...)`), **theses.fr** (`fetch_theses(...)`). Tier 1's topic axis needs
OpenAlex topics; HAL/theses sources use the claim-cluster path (§Claim-cluster path).

## Minimal use — three-tier (python tool)

```python
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
env = load_env()                                   # reads .env (ALBERT_API_KEY)
try: email = host.get_user_email()
except Exception: email = None

inst = resolve_institution("04y8cs423", email)     # Mines Paris – PSL (any ROR)
win_order = ["2020","2021","2022","2023","2024","2025","2026-H1"]
spans = {"2020":("2020-01-01","2020-12-31"), "2021":("2021-01-01","2021-12-31"),
         "2022":("2022-01-01","2022-12-31"), "2023":("2023-01-01","2023-12-31"),
         "2024":("2024-01-01","2024-12-31"), "2025":("2025-01-01","2025-12-31"),
         "2026-H1":("2026-01-01","2026-06-30")}

# --- TIER 1: topic headline, no LLM, full population ---
windows = {w: fetch_topic_meta(inst["id"], *spans[w], email=email) for w in win_order}
headline = build_headline(windows, win_order, prior="2025", recent="2026-H1")
print(headline["delta_counts"])                    # {'NEW':..,'PERSISTING':..,'DISAPPEARING':..}
flagged = flag_moving(headline, kinds=("RISING","NEW"))   # topics worth a drill-down

# --- TIER 2: claims ONLY inside flagged topics ---
recent = fetch_works(inst["id"], *spans["2026-H1"], email=email)   # abstracts + topic
by_topic = drilldown_claims(flagged, recent, host, "2026-H1")      # {topic: [claims]}

# optional: embed within a flagged topic to split new claims from restatements
# emb = embed_claims([c["claim"] for c in by_topic["Solar Radiation and Photovoltaics"]],
#                    env["ALBERT_API_KEY"])

# --- TIER 3: where does the institution sit vs the world, per flagged topic ---
cards = position_flagged(flagged, "2020-01-01", "2026-06-30", inst["id"],
                         topics=headline["topics"], email=email)
for c in cards:
    print(c["verdict"], f'[{c["confidence"]}]', c["topic"],
          f'{c["n_inst"]}/{c["n_global"]}')
```

The headline is metadata-only and cheap; extraction touches only the handful of
flagged topics. To scope to one field, pass `field_id="fields/17"` (Computer
Science) to both `fetch_topic_meta` and `fetch_works`.

## Claim-cluster path (HAL, theses.fr, or OpenAlex without topics)

Use this path when the source has **no topic taxonomy** (HAL, theses.fr) or when
you want a topic-agnostic claim delta. Instead of the Tier-1 topic headline, it
clusters the atomic claims themselves by embedding similarity and diffs the
clusters. It is the original single-tier engine; the two-tier path above is
preferred for OpenAlex because the topic headline is cheaper and coherent by
construction.

```python
env = load_env()
# HAL articles, same half-year windows as an OpenAlex run (comparable):
hal_recent = fetch_hal("UNIV-COTEDAZUR", "2026-01-01", "2026-06-30")
hal_prior  = fetch_hal("UNIV-COTEDAZUR", "2025-07-01", "2025-12-31")
# theses.fr PhD theses, full-year windows (annual rhythm):
th_recent  = fetch_theses("2025-01-01", "2025-12-31")
th_prior   = fetch_theses("2024-01-01", "2024-12-31")

for recent, prior, tag in [(hal_recent, hal_prior, "HAL"), (th_recent, th_prior, "theses")]:
    claims = extract_claims(host, recent, "recent") + extract_claims(host, prior, "prior")
    emb = embed_claims([c["claim"] for c in claims], env["ALBERT_API_KEY"])
    clusters = cluster_delta(claims, emb)
    brief = make_brief(host, clusters, {"institution": "Université Côte d'Azur",
        "field": "Computer Science", "source": tag,
        "prior_window": "...", "recent_window": "...", "counts": {}})
```

Same delta engine, three sources. Different indexing coverage surfaces different
signals — a topic receding in OpenAlex can be emerging in HAL — which is itself
an argument for reading sources side by side rather than trusting one.

## Robustness — why Tier 1 skips the LLM

A natural worry: are paper counts too blunt for the headline? On the Mines Paris
– PSL pilot (1,119 works, 520 topics, 7 windows) the topic-count headline was
checked against a claim-count headline built by extracting all 4,704 claims and
aggregating to the same topic axis. They are the same signal: the per-topic
claims-per-paper ratio is nearly constant (mean 4.5, CV 0.07), trajectory-slope
Spearman is **0.99** (97% sign agreement, 9/10 top rising topics identical), and
the two-window delta Spearman is **0.93** (98% sign agreement). The count
headline loses nothing relative to a ~10× more expensive claim headline — so
Tier 1 uses metadata directly and Tier 2 spends the LLM only where it adds what
counts cannot: the actual assertions inside a moving topic.

## Secondary signal — claim-level exploration (`explore_claims`)

The topic headline can only report movement **within** the taxonomy's buckets.
Wherever claims have been extracted at corpus scale (e.g. for the robustness
check above), `explore_claims(claims, emb, ...)` reads structure directly from
what is asserted, independent of the topic axis — a lens that runs **alongside**
Tier 1, not in place of it.

```python
# claims: list of dicts, each with an OpenAlex-topic key and a window key
# emb:    (n, 1024) bge-m3 embeddings, row-aligned to claims
res = explore_claims(claims, emb,
                     topic_key="oa_topic", window_key="window",
                     prior="2024", recent="2025", threshold=0.55)

res["cross_cutting"]   # themes spanning many topics: {n_claims, spans_topics, top_topics, exemplar}
res["delta"]["counts"] # {"NEW": .., "PERSISTING": .., "DISAPPEARING": ..} at the CLAIM-theme level
res["delta"]["emerging"], res["delta"]["receding"]  # ranked by signed delta
res["boilerplate"]     # the largest cluster (method-generic assertions), reported + excluded from delta
```

Two readings it yields that a per-topic count cannot:

- **Cross-cutting themes** — claim-clusters whose members come from many distinct
  OpenAlex topics (a shared method or framing diffusing across the taxonomy).
  `spans_topics` measures that breadth directly.
- **Claim-theme delta** — the NEW/PERSISTING/DISAPPEARING logic applied to
  claim-themes between two windows, flagging emerging and receding *assertions*
  regardless of which bucket their papers fall in.

Secondary by design: heavier (needs corpus-wide claims, not just flagged topics)
and noisier. A large fraction of abstract claims are method-generic boilerplate
("numerical simulations illustrate the merits of the proposed approach"); these
form the single biggest cluster, which the function returns as `boilerplate` and
excludes from the delta — its size is itself a finding. On the Mines pilot:
4,704 claims → 324 themes; a 740-claim boilerplate cluster; ~121 cross-cutting
themes (top spans 62 topics); claim-theme delta 2024→2025 = 10 NEW / 47
PERSISTING / 2 DISAPPEARING. Needs `scikit-learn` (agglomerative cosine
clustering, `threshold` is the cosine *distance* cut).

## Tier 3 — positioning method & confidence guard

Positioning is **computed, not fetched**: no tool returns a turnkey
leading/following label, so the verdict is decomposed into three sub-signals with
three honest confidence levels, all from OpenAlex REST (the source every sweep
already uses):

| Sub-signal | Question | Evidence | Confidence |
|---|---|---|---|
| **Timing** | Did the institution publish before or after the world? | median-date lead/lag + citation-flow net (inbound cites − outbound refs, within the topic set) | HIGH — free, reproducible |
| **Prominence** | Does it own a niche or ride a crowded wave? | institution share of the global topic count + global trend | HIGH — a recomputable count |
| **Stance** | Does its claim align with or contradict the consensus? | LLM read of the exemplar claim vs top global abstracts, evidence quoted | LOW–MEDIUM — a judgment |

**Confidence guard (non-negotiable).** Every card carries a tier as a function of
*(institution sample size × global set size × how many sub-signals fired)*:
`high` needs n_inst≥4, n_global≥30, both structural sub-signals; it degrades to
`medium`/`low`/`very-low` otherwise. A citation-flow verdict on an 8-paper spine
is trustworthy; a stance-only read on a 1-paper topic is a whisper — render them
differently, never a single undifferentiated arrow. **Only position topics that
survived the trajectory/flag layer** — positioning a 1-window topic against the
global consensus is noise.

**Two honesty flags built into the card.** `flow_basis` states the citation flow
is computed on the downloaded page sample (`"sampled N of M global"`), while the
denominator `n_global` is the true `meta.count`; and a `NO-GLOBAL-MATCH` /
`DIVERGING-ABSENT` verdict says *the world is active and the institution silent*
rather than hiding a zero. Verdicts on the Mines pilot (2020→2026-H1): the three
largest topics — Phase Equilibria, Solar/Photovoltaics, Carbon Capture — all read
**FOLLOWING** at high confidence (share 0.2–0.7% of very large global topics,
median date lagging the world), which is the honest reading for a mid-size
institution on mature topics. The instrument reserves `LEADING`/`EARLY-MOVER` for
topics where the institution owns a niche and the field cites it more than it
cites out.

## Consuming the generalist connectors (`client.py`)

The built-in `fetch_hal` / `fetch_theses` in `kernel.py` are self-contained. To
instead source records from the **generalist agentic-stack connectors**
(`search-records-hal`, `search-theses-fr`, `search-works-openalex` - reusable
outside this radar), use `client.py`. It keeps the radar a *consumer*: the
connectors own each source's quirks (HAL Solr fields, theses.fr hydration,
OpenAlex abstract inversion) and emit one normalized record shape; `client.py`
maps those into the pipeline work-dict.

```python
import client
import os; os.environ["AGENTIC_STACK_ROOT"] = "/path/to/agentic-stack"  # repo clone

# CLI runners (subprocess -> skill cli.py):
hal_recent = client.fetch_hal("UNIV-COTEDAZUR", "2026-01-01", "2026-06-30")
th_recent  = client.fetch_theses("2025-01-01", "2025-12-31")           # auto --hydrate

# Pure mappers, when records already came from an MCP tool call:
works = client.map_records(mcp_results["results"], "hal")   # or "theses-fr" / "openalex"
```

`map_records(records, source, min_abstract=200)` filters to records whose
abstract meets the length floor - the same gate the built-in fetchers apply.
Both paths yield the identical `{id,title,date,abstract,lang,...}` work-dict, so
stages 2-5 are unchanged.

## Per-topic Markdown KB (`kb_emitter.py`)

Turn a delta run into a browsable, Quarto-searchable knowledge base - one `.md`
per claim-cluster with QMD/YAML front-matter, plus a linked `index.md`.

```python
import kb_emitter
meta = {"title": "UCA CS - HAL Claim KB", "source": "HAL", "field": "Computer Science",
        "institution": "Universite Cote d'Azur",
        "window_from": "2025-07-01", "window_to": "2026-06-30"}
paths = kb_emitter.emit_kb(clusters, "kb_hal", meta=meta,
                           top=25, statuses={"NEW", "PERSISTING"})
```

Each topic file carries front-matter (`title`, `status`, `signal`
emerging/persisting/receding, `claim_count`, `categories`, `window_*`) and lists
its member claims with `[window]`, paper title, `paper_id`, and date. `index.md`
records the run's NEW/PERSISTING/DISAPPEARING counts and a linked topic table.
`emit_kb(..., top=, statuses=)` caps and filters; member-key access is tolerant
(`claim`/`text`, `paper_id`/`work_id`, `paper_date`/`date`).

## Signal persistence & trajectory across >=3 sweeps (`persist.py`)

`cluster_delta` compares TWO windows. `persist.py` lifts that to a running series:
record each sweep, thread topics across sweeps by claim-centroid similarity, and
read each topic's *trajectory* - direction plus acceleration - not just its
one-pair direction.

```python
import persist
STORE = "signal_store"

# After each sweep's cluster_delta(claims, emb) run, persist its topics + centroids:
persist.record_sweep(clusters, emb, claims,
                     window={"label": "H1-2026", "from": "2026-01-01", "to": "2026-06-30"},
                     store_dir=STORE, meta={"institution": "...", "source": "OpenAlex"})

# Once >=2 sweeps are recorded, thread and read trajectories:
lineages = persist.thread_topics(STORE, sim_threshold=0.60)   # chains topics into lineages
rows     = persist.trajectories(lineages)                     # per-lineage series + direction
persist.emit_trajectory(rows, "traj_out", meta={"title": "..."})  # -> .md + .json + .png
```

`persist.trajectory_html(rows, fig_src=..., meta=...)` returns a dark-theme HTML
fragment (grouped rising/falling/intermittent/persistent lists + a lineage table)
ready to splice into the multi-source dashboard, so the >=3-sweep view sits beside
the two-window panels.

**Threading.** `thread_topics` processes sweeps oldest->newest and greedily chains
each topic onto the open lineage with the highest centroid cosine (>= `sim_threshold`,
default 0.60; one topic per lineage per sweep), else opens a new lineage. Centroids
are recomputed by `record_sweep` from the SAME embedding matrix `cluster_delta`
consumed - members are mapped back to embedding rows by object identity, so pass
the same `claims`/`emb`.

**Trajectory.** `trajectories` aligns each lineage to the global ordered window
axis (0 where absent), trims to its present span, and classifies:
`RISING`/`FALLING`/`STABLE`/`INTERMITTENT` (a mid-span 0 = disappeared-then-returned)
/`NEW` (one sweep). Acceleration is direction-aware: positive 2nd-difference on a
falling series reads as *slowing*, not accelerating. Each row also carries the
`current_status`/`current_signal` from its latest window.

`emit_trajectory` writes `trajectory.md` (table + rising/falling/intermittent
groupings), `trajectory.json`, and a multi-line `trajectory.png`. This is the
bridge from a pipeline you *run* to a platform that *runs*: a topic's
acceleration across three sweeps is a signal a two-window diff cannot see.

## Notes & tuning

- **Threshold** `0.62` (bge-m3 cosine) groups paraphrases; raise toward 0.72 for stricter "same claim". A separate cross-window max-similarity >= 0.72 marks a claim as a *restatement*.
- **Small samples churn.** One small institution + one field + adjacent half-years often yields near-total turnover (few PERSISTING clusters). That is a real property of the data, not a failure — say so, and lean on cluster-level trends (multiple papers) over single-paper topics.
- **Grounding.** The brief cites only the topic labels and counts passed in; it does not invent papers. Always surface its caveats to the user.
- **Tier-1 tuning.** `build_headline(min_total=4)` sets the "substantial topic" floor for the trajectory; `flag_moving(kinds=..., min_recent=1, top=N)` controls which topics reach Tier 2 — widen `kinds` or raise `top` for more drill-down, narrow for a tighter, cheaper run. `direction` uses a slope cut of ±0.15 papers/window.
- **Half-year windows read with care.** A recent half-year against full prior years inflates NEW/DISAPPEARING counts and puts emergers on very few papers; trust the multi-window trajectory over a single half-year delta, and say so in the brief.
- **Deps:** `requests`, `numpy` (base `python` env). No local ML model — embeddings are remote via Albert.
