"""`radar embed`: title + abstract embeddings from the Albert API, with a cache (specs/05 §3)."""

import hashlib
import json
import logging
import os
import random
import re
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from ..config import Config

logger = logging.getLogger(__name__)

EMBEDDING_TYPE = "text-embeddings-inference"
RETRY_STATUSES = {429, 503}
MAX_ATTEMPTS = 6
SAVE_EVERY = 20  # batches per cache part: an interruption loses at most this much work


class AlbertError(RuntimeError):
    pass


class BatchTooLarge(AlbertError):
    pass


class AlbertClient:
    """Minimal OpenAI-compatible client for Albert: GET /models, POST /embeddings."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 120, transport=None):
        if not api_key:
            raise AlbertError("Albert API key missing: set it in .env (never in the config file)")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._sleep = time.sleep
        self.tokens = 0
        self.cost = 0.0

    def __repr__(self):
        return f"AlbertClient(base_url={str(self._client.base_url)!r}, api_key='***')"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise AlbertError(f"{type(exc).__name__} calling {path} after {attempt} attempts") from None
                self._sleep(min(60, 2 ** attempt) + random.uniform(0, 1))
                continue
            status = response.status_code
            if status < 400:
                return response.json()
            text = response.text[:300]
            if status in (401, 403):
                raise AlbertError(f"Albert refused the key (HTTP {status}): check ALBERT_API_KEY")
            if status == 400 and "budget" in text.lower():
                raise AlbertError(f"Albert budget exhausted (HTTP 400): {text}")
            if status in (413, 422):
                raise BatchTooLarge(f"HTTP {status}: {text}")
            if status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = min(60, 2 ** attempt) + random.uniform(0, 1)
                logger.warning("Albert HTTP %s on %s, retrying in %.1f s", status, path, delay)
                self._sleep(delay)
                continue
            raise AlbertError(f"Albert HTTP {status} on {path}: {text}")
        raise AssertionError("unreachable")

    def models(self) -> list[dict]:
        return self._request("GET", "/models").get("data", [])

    def resolve_model(self, wanted: str) -> dict:
        """The embedding model whose ID or alias is `wanted`; otherwise list what is available."""
        embedding = [m for m in self.models() if m.get("type") == EMBEDDING_TYPE]
        for model in embedding:
            if model.get("id") == wanted or wanted in (model.get("aliases") or []):
                return model
        available = ", ".join(
            m["id"] + (f" (aliases: {', '.join(m['aliases'])})" if m.get("aliases") else "") for m in embedding
        ) or "none"
        raise AlbertError(f"embedding model {wanted!r} not available on Albert; embedding models: {available}")

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        body = {"model": model, "input": texts, "encoding_format": "float"}
        data = self._request("POST", "/embeddings", json=body)
        usage = data.get("usage") or {}
        self.tokens += int(usage.get("total_tokens") or 0)
        self.cost += float(usage.get("cost") or 0)
        rows = sorted(data["data"], key=lambda d: d.get("index", 0))
        if len(rows) != len(texts):
            raise AlbertError(f"Albert returned {len(rows)} vectors for {len(texts)} texts")
        return [row["embedding"] for row in rows]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-").lower()


class EmbeddingCache:
    """`data/cache/embeddings/<model_slug>/part-*.parquet`: text_hash, model, vector (float32)."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, np.ndarray]:
        vectors = {}
        for part in sorted(self.directory.glob("part-*.parquet")):
            frame = pd.read_parquet(part)
            for h, v in zip(frame["text_hash"], frame["vector"]):
                vectors[h] = np.asarray(v, dtype=np.float32)
        return vectors

    def append(self, hashes: list[str], model: str, vectors: list) -> None:
        if not hashes:
            return
        n = len(list(self.directory.glob("part-*.parquet"))) + 1
        frame = pd.DataFrame({"text_hash": hashes, "model": model,
                              "vector": [np.asarray(v, dtype=np.float32) for v in vectors]})
        tmp = self.directory / f".part-{n:05d}.tmp"
        frame.to_parquet(tmp, index=False)
        tmp.replace(self.directory / f"part-{n:05d}.parquet")


def embed_texts(client: AlbertClient, texts: list[str], model: str, batch_size: int) -> list:
    """Embed in batches; a batch refused as too large (413/422) is halved and retried."""
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        try:
            vectors.extend(client.embed(batch, model))
        except BatchTooLarge:
            if len(batch) == 1:
                raise
            logger.warning("batch of %d refused as too large, halving", len(batch))
            vectors.extend(embed_texts(client, batch, model, max(1, len(batch) // 2)))
    return vectors


def run_embed(sweep_dir: Path, config: Config, client: AlbertClient | None = None) -> dict:
    started = time.monotonic()
    sweep_dir = Path(sweep_dir)
    sem = config.semantic
    client = client or AlbertClient(sem.base_url, os.environ.get(sem.api_key_env, ""))
    model = client.resolve_model(sem.model)
    model_id = model["id"]
    logger.info("embedding model %r resolved to %r", sem.model, model_id)

    works = pd.read_parquet(sweep_dir / "works.parquet", columns=["work_id", "text_for_embedding", "has_abstract"])
    texts = works["text_for_embedding"].fillna("").astype(str)
    mapped = works[texts.str.len() > 0].copy()
    mapped["text_hash"] = [text_hash(t) for t in texts[mapped.index]]

    cache = EmbeddingCache(config.data_dir / "cache" / "embeddings" / model_slug(model_id))
    known = cache.load()
    todo = mapped.drop_duplicates("text_hash")
    todo = todo[~todo["text_hash"].isin(known.keys())]
    logger.info("%d texts to embed (%d already cached)", len(todo), len(mapped) - len(todo))

    chunk = sem.batch_size * SAVE_EVERY
    for start in range(0, len(todo), chunk):
        part = todo.iloc[start:start + chunk]
        vectors = embed_texts(client, part["text_for_embedding"].tolist(), model_id, sem.batch_size)
        cache.append(part["text_hash"].tolist(), model_id, vectors)
        known.update({h: np.asarray(v, dtype=np.float32) for h, v in zip(part["text_hash"], vectors)})
        logger.info("embedded %d / %d (%s tokens so far)", start + len(part), len(todo), f"{client.tokens:,}")

    matrix = np.stack([known[h] for h in mapped["text_hash"]]) if len(mapped) else np.zeros((0, 0), np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) if len(mapped) else None
    if len(mapped):
        matrix = matrix / np.where(norms == 0, 1, norms)
    derived = sweep_dir / "derived"
    derived.mkdir(exist_ok=True)
    pd.DataFrame({
        "work_id": mapped["work_id"].to_numpy(),
        "text_hash": mapped["text_hash"].to_numpy(),
        "has_abstract": mapped["has_abstract"].to_numpy(),
        "vector": list(matrix.astype(np.float32)),
    }).to_parquet(derived / "embeddings.parquet", index=False)

    meta_path = derived / "semantic_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["embed"] = {
        "model_configured": sem.model,
        "model_id": model_id,
        "max_context_length": model.get("max_context_length"),
        "dimension": int(matrix.shape[1]) if len(mapped) else None,
        "works": int(len(works)),
        "mapped": int(len(mapped)),
        "unmapped_empty_text": int(len(works) - len(mapped)),
        "title_only": int((~mapped["has_abstract"].fillna(False).astype(bool)).sum()),
        "embedded_now": int(len(todo)),
        "from_cache": int(len(mapped["text_hash"].unique()) - len(todo)),
        "tokens": client.tokens,
        "cost": round(client.cost, 6),
        "seconds": round(time.monotonic() - started, 1),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta["embed"]
