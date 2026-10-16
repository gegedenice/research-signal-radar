# 05 — Semantic map

## 1. Purpose

Give every work a position on a 2-D map built from what it says (title + abstract), group
nearby works into clusters with readable labels, and expose per-year counts so the map can be
played over time. The map is where signals are seen in context: selecting a signal lights up
its works on the map.

It is independent of the OpenAlex topic taxonomy. Where the two disagree, the UI shows both
(§6). No generative model is used: cluster labels are c-TF-IDF terms.

## 2. Pipeline

```
works.text_for_embedding
   │  radar embed  (Albert API, BAAI/bge-m3, cached)
   ▼
1024-d vectors (L2-normalized)
   │  radar map
   ├─ UMAP → 5-d ─ HDBSCAN → clusters ─ c-TF-IDF → labels      (BERTopic)
   ├─ UMAP → 2-d → map coordinates
   ├─ agglomerative grouping of cluster centroids → regions (coarse labels)
   └─ per-year counts + engine (04 §5) → cluster trend per cutoff
```

## 3. Embeddings (`radar embed`, `semantic/embed.py`)

- **Provider:** Albert API (`https://albert.api.etalab.gouv.fr/v1`), OpenAI-compatible `POST /embeddings`, header `Authorization: Bearer $ALBERT_API_KEY`, body `{"model": ..., "input": [texts], "encoding_format": "float"}`. Use `httpx` directly; no SDK.
- **Model check at start-up:** call `GET /v1/models`. Albert exposes models under IDs and sometimes aliases (its current guide mentions `openweight-embeddings`). The configured `semantic.model = "BAAI/bge-m3"` MUST resolve to an available model of type `text-embeddings-inference`. Otherwise stop and print the available embedding models. Record the resolved ID and `max_context_length` in the output metadata. **Verify** which ID currently serves bge-m3.
- **Input:** `works.text_for_embedding` (title + abstract, ≤ `max_chars` = 4,000 characters; bge-m3 accepts up to 8,192 tokens, so truncation only bounds cost). Empty strings are never sent.
- **Batching:** `batch_size = 64` texts per request; on HTTP 413/422 halve the batch and retry.
- **Errors:** retry 429 and 503 with exponential backoff (max 6 attempts, honour `Retry-After`); 400 "insufficient budget", 401 and 403 stop immediately with a clear message. Never log the key.
- **Cache:** `data/cache/embeddings/<model_slug>.parquet` with columns `text_hash` (SHA-256 of the exact text sent), `model`, `vector` (float32 list, 1,024 values). Before calling the API, look up every text hash. Only missing texts are embedded. A later sweep therefore only pays for new or modified works.
- **Output:** `derived/embeddings.parquet` = `work_id, text_hash, has_abstract` + vector (or a reference to the cache rows), L2-normalized locally.
- **Usage report:** sum `usage.total_tokens` and `usage.cost` from responses; print and store them in `derived/semantic_meta.json`. Rough order of magnitude for IRD 2016–2025: 70–80k texts × ~300 tokens ≈ 20–25M tokens for the first run.

## 4. Landscape (`radar map`, `semantic/landscape.py`)

All randomness seeded with `semantic.random_state = 42`.

### 4.1 Clustering with BERTopic

```python
umap_5d   = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42)
hdbscan_m = HDBSCAN(min_cluster_size=cfg.min_cluster_size,   # default 60
                    min_samples=10, metric="euclidean",
                    cluster_selection_method="eom", prediction_data=True)
vectorizer = CountVectorizer(stop_words=STOPWORDS, ngram_range=(1, 2),
                             min_df=5, max_df=0.5, token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
model = BERTopic(embedding_model=None, umap_model=umap_5d, hdbscan_model=hdbscan_m,
                 vectorizer_model=vectorizer,
                 ctfidf_model=ClassTfidfTransformer(reduce_frequent_words=True),
                 calculate_probabilities=False)
topics, _ = model.fit_transform(docs, embeddings=vectors)
```

- `STOPWORDS` = English + French + Spanish + Portuguese lists stored as text files in `semantic/stopwords/` (IRD publishes in all four), plus `semantic.extra_stopwords` from config for generic academic words (`study`, `results`, `using`, `based`, `analysis`, `data`, `paper`, `approach`, `effect`, `effects`, …).
- **Outliers:** HDBSCAN leaves many works unassigned (`-1`). Keep the raw assignment as `cluster_raw`. Then compute `cluster = model.reduce_outliers(docs, topics, strategy="embeddings", embeddings=vectors, threshold=0.5)` and `model.update_topics(docs, topics=cluster, vectorizer_model=vectorizer)` so labels reflect the final membership. Works still unassigned stay `-1` and are drawn grey. Report the outlier share before and after.
- **Labels:** `terms` = top 10 c-TF-IDF terms; `label` = top 3 joined with " · ".
- Expect roughly 100–250 clusters for 70–80k works with `min_cluster_size = 60`. Adjust `min_cluster_size` rather than forcing `nr_topics`.

### 4.2 Map coordinates

`UMAP(n_neighbors=15, n_components=2, min_dist=0.1, metric="cosine", random_state=42)` fitted on the same vectors. Rescale x and y to [0, 1] for the bundle.

### 4.3 Regions (coarse level, for zoomed-out labels)

- Centroid of each cluster in embedding space (mean of normalized vectors, re-normalized).
- `AgglomerativeClustering(n_clusters=cfg.n_regions [default 20], metric="cosine", linkage="average")` on centroids → `region_id` per cluster.
- Region terms: fit `CountVectorizer` + BERTopic's `ClassTfidfTransformer` on documents concatenated per region; label = top 3 terms.

### 4.4 Link to OpenAlex taxonomy

For each cluster: the 3 most frequent primary topics and subfields with their share of the cluster (`top_topics`). The UI shows them; a low top-1 share is itself informative (the cluster cuts across the taxonomy).

### 4.5 Counts over time and trend

- `counts_by_year` per cluster for 2016–2025.
- For each cutoff (04 §2, same `windows()` and period mode as the detectors): call the engine `assess` with entity = cluster, `c/b` = works of the cluster in the current/baseline window, `C/B` = all mapped works (including outliers) in those windows, same `alpha` and `min_log2_ratio`. Store `trend[cutoff] = {label, log2_sr, ci_low, ci_high, q}` (label `null` if not a signal). This colours clusters by trend in the UI. It is not a detector feed.

### 4.6 Model persistence

Save the BERTopic model (`model.save(path, serialization="safetensors", save_ctfidf=True)`) and the 2-d UMAP reducer (pickle) under `derived/semantic_model/`. They are refitted at each sweep (v1). Projecting a new sweep onto a previous map is out of scope.

## 5. Outputs

**`derived/map_points.parquet`** — one row per work that has a non-empty `text_for_embedding` (works with neither title nor abstract are not mapped; their number is in `semantic_meta.json`):
`work_id, x, y, cluster, cluster_raw, region_id, year, pub_month, has_abstract, primary_topic_id, subfield_id`.

**`derived/clusters.parquet`** — one row per cluster (including `-1`):
`cluster, region_id, label, terms (list), size, x, y` (median of member coordinates, for label placement)`, counts_by_year (dict), top_topics (list of {id, label, share}), trend (dict cutoff → {label, log2_sr, ci_low, ci_high, q})`.

**`derived/regions.parquet`** — `region_id, label, terms, size, x, y`.

**`derived/semantic_meta.json`** — resolved model ID, embedding dimension, number embedded vs cached, tokens/cost, outlier share before/after reduction, number of clusters and regions, parameters, runtime.

## 6. Quality checks printed at the end of `radar map`

- Outlier share after reduction (warn if > 25%).
- Share of title-only works per cluster (warn for clusters where > 50% are title-only: their position is less reliable).
- Largest cluster share (warn if > 10% of works: probably a "generic" cluster; adjust stop words).
- Top-1 OpenAlex topic share distribution across clusters (median), as a sanity check on coherence.

## 7. CLI

```
radar embed [--sweep latest|<id>]   # network: Albert; idempotent thanks to the cache
radar map   [--sweep latest|<id>]   # offline; ≈ 10–25 min CPU for 70–80k works (UMAP dominates)
```

## 8. Tests

- Embedding client against a fake server: batching, halving on 413, retry on 429/503, stop on 401, cache hit avoids the call, key absent from logs.
- Model resolution: configured ID present → OK; absent → error listing available embedding models.
- Landscape on synthetic data (fake vectors = 5 well-separated Gaussian blobs of 300 points, docs with blob-specific vocabulary): 5 clusters recovered, labels contain the blob vocabulary, coordinates in [0, 1], `counts_by_year` sums to the number of points.
- Determinism: two runs with the same seed give identical cluster assignments on the synthetic data.
