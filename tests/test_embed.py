import json
import logging

import httpx
import numpy as np
import pandas as pd
import pytest

from radar.semantic.embed import AlbertClient, AlbertError, embed_texts, run_embed, text_hash

KEY = "albert-secret-key-123"
MODELS = {"data": [
    {"id": "BAAI/bge-m3", "type": "text-embeddings-inference", "aliases": ["openweight-embeddings"],
     "max_context_length": 8192},
    {"id": "mistral-small", "type": "text-generation", "aliases": []},
]}


class FakeAlbert:
    """Answers /models and /embeddings; `script` forces statuses for the next embedding calls."""

    def __init__(self, models=MODELS, script=(), max_batch=None):
        self.models = models
        self.script = list(script)
        self.max_batch = max_batch
        self.batches = []
        self.headers = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.headers.append(request.headers.get("authorization"))
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=self.models)
        body = json.loads(request.content)
        if self.script:
            status, headers, payload = self.script.pop(0)
            return httpx.Response(status, headers=headers, json=payload)
        texts = body["input"]
        if self.max_batch and len(texts) > self.max_batch:
            return httpx.Response(413, json={"detail": "too large"})
        self.batches.append(len(texts))
        data = [{"index": i, "embedding": [float(len(t)), 1.0, 0.0]} for i, t in enumerate(texts)]
        return httpx.Response(200, json={"data": data, "usage": {"total_tokens": 10 * len(texts), "cost": 0.001}})


def client(fake):
    c = AlbertClient("https://albert.test/v1", KEY, transport=httpx.MockTransport(fake))
    c._sleep = lambda s: None
    return c


def test_batching_and_halving_on_413():
    fake = FakeAlbert(max_batch=2)
    vectors = embed_texts(client(fake), ["a", "bb", "ccc", "dddd", "eeeee"], "BAAI/bge-m3", batch_size=4)
    assert [v[0] for v in vectors] == [1, 2, 3, 4, 5]
    assert fake.batches == [2, 2, 1]


def test_retry_on_429_and_503_then_success():
    fake = FakeAlbert(script=[(429, {"Retry-After": "2"}, {}), (503, {}, {})])
    c = client(fake)
    sleeps = []
    c._sleep = sleeps.append
    assert len(c.embed(["x"], "BAAI/bge-m3")) == 1
    assert sleeps[0] == 2 and len(sleeps) == 2


@pytest.mark.parametrize("status,payload,message", [
    (401, {"detail": "unauthorized"}, "refused the key"),
    (403, {"detail": "forbidden"}, "refused the key"),
    (400, {"detail": "Insufficient budget"}, "budget"),
])
def test_stops_immediately(status, payload, message):
    fake = FakeAlbert(script=[(status, {}, payload), (200, {}, {})])
    with pytest.raises(AlbertError, match=message):
        client(fake).embed(["x"], "BAAI/bge-m3")
    assert len(fake.script) == 1  # no retry


def test_model_resolution():
    c = client(FakeAlbert())
    assert c.resolve_model("BAAI/bge-m3")["id"] == "BAAI/bge-m3"
    assert c.resolve_model("openweight-embeddings")["max_context_length"] == 8192
    with pytest.raises(AlbertError, match="embedding models: BAAI/bge-m3 \\(aliases: openweight-embeddings\\)"):
        c.resolve_model("mistral-small")


def test_key_never_logged_or_shown(caplog):
    fake = FakeAlbert(script=[(503, {}, {})] * 5 + [(500, {}, {"detail": "boom"})])
    c = client(fake)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AlbertError) as info:
            c.embed(["x"], "BAAI/bge-m3")
    assert fake.headers[0] == f"Bearer {KEY}"  # sent...
    for text in [str(info.value), repr(c)] + [r.getMessage() for r in caplog.records]:
        assert KEY not in text  # ...never shown


def write_sweep(path, texts):
    path.mkdir(parents=True)
    pd.DataFrame({"work_id": [f"W{i}" for i in range(len(texts))], "text_for_embedding": texts,
                  "has_abstract": [bool(t) and "\n\n" in t for t in texts]}).to_parquet(path / "works.parquet")


def test_run_embed_caches_and_second_run_makes_no_call(config, monkeypatch):
    sweep = config.data_dir / "sweeps" / "2026-10-20"
    write_sweep(sweep, ["Title A\n\nAbstract", "Title B", "", "Title A\n\nAbstract"])
    fake = FakeAlbert()
    meta = run_embed(sweep, config, client=client(fake))
    assert fake.batches == [2]  # the duplicate text and the empty one are not sent
    assert meta["mapped"] == 3 and meta["unmapped_empty_text"] == 1 and meta["embedded_now"] == 2
    assert meta["tokens"] == 20 and meta["model_id"] == "BAAI/bge-m3" and meta["dimension"] == 3

    out = pd.read_parquet(sweep / "derived" / "embeddings.parquet")
    assert list(out.work_id) == ["W0", "W1", "W3"]
    assert out.text_hash[0] == text_hash("Title A\n\nAbstract") and out.text_hash[0] == out.text_hash[2]
    assert np.allclose([np.linalg.norm(v) for v in out.vector], 1.0)

    fake2 = FakeAlbert()
    meta2 = run_embed(sweep, config, client=client(fake2))
    assert fake2.batches == [] and meta2["embedded_now"] == 0 and meta2["from_cache"] == 2
    saved = json.loads((sweep / "derived" / "semantic_meta.json").read_text())
    assert saved["embed"]["embedded_now"] == 0


def test_missing_key_is_a_clear_error():
    with pytest.raises(AlbertError, match="key missing"):
        AlbertClient("https://albert.test/v1", "")
