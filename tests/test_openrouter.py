"""The real OpenRouter client (stubbed transport), injected into the app and driven through the API."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.clients import OpenRouterClient
from veillefacile.reembed import main

from .conftest import AUTH
from .fakes import fake_embedding


@pytest.fixture(autouse=True)
def _empty_table(client):
    """Apps built here skip the truncation of the `client` fixture; depend on it for a clean table."""

LLM_OUT = ("## What it is\nA thing.\n\n## Why it matters\nIt does.\n\n## Key points\n- a\n\n"
           "## Who it's for\nYou.\n\n## Keywords\nRust, Tokio ,  ")
BODY = {"url": "https://e.com/x", "full_text": "x" * 200_000, "title": "T"}


def embeddings(req):
    inp = json.loads(req.content)["input"]
    return httpx.Response(200, json={"data": [{"index": i, "embedding": fake_embedding(t)}
                                              for i, t in reversed(list(enumerate(inp)))]})  # out of order


def app_with(settings, handler, fakes=None, **kw):
    llm = OpenRouterClient("k", "m1:free, m2", "emb", transport=httpx.MockTransport(handler), **kw)
    return TestClient(create_app(settings, llm=llm, **(fakes or {})), headers=AUTH, raise_server_exceptions=False)


def test_summary_uses_models_list_and_parses_keywords(settings, caplog):
    seen = []

    def handler(req):
        if req.url.path.endswith("/embeddings"):
            return embeddings(req)
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"model": "m2", "choices": [{"message": {"content": LLM_OUT}}]})

    with caplog.at_level("INFO"), app_with(settings, handler) as c:
        r = c.post("/api/sources", json=BODY)
    assert r.status_code == 201, r.text
    assert seen[0]["models"] == ["m1:free", "m2"] and seen[0]["temperature"] == 0.2
    assert len(seen[0]["messages"][0]["content"]) < 103_000  # full text truncated
    assert r.json()["keywords"] == ["Rust", "Tokio"] and r.json()["summary"].startswith("## What it is")
    assert "m2" in caplog.text


@pytest.mark.parametrize("resp,status,retry", [
    (httpx.Response(429, headers={"Retry-After": "12"}), 503, "12"),
    (httpx.Response(402, headers={"Retry-After": "7"}), 503, "7"),  # credits exhausted
    (httpx.Response(429), 503, "60"),
    (httpx.Response(500), 502, None),
    (httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "no sections"}}]}), 502, None),
    (httpx.Response(200, text="not json"), 502, None),
])
def test_error_mapping(settings, resp, status, retry):
    with app_with(settings, lambda req: resp) as c:
        r = c.post("/api/sources", json=BODY)
        assert r.status_code == status and r.headers.get("Retry-After") == retry
        assert c.get("/api/sources").json()["results"] == []


def test_network_error_is_502(settings):
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with app_with(settings, handler) as c:
        assert c.post("/api/sources", json=BODY).status_code == 502


def test_timeout_is_a_total_cap(settings):
    async def slow(req):  # httpx's per-phase timeouts never fire here: only a total cap can
        await asyncio.sleep(5)
        return httpx.Response(200, json={})

    with app_with(settings, slow, timeout=0.2) as c:
        assert c.post("/api/sources", json=BODY).status_code == 502


def test_embeddings_batched_by_32_and_kept_in_order(client, settings, fakes):
    for i in range(40):
        r = client.post("/api/sources", json={"url": f"https://a.com/{i}", "title": f"Item{i}", "summary": "s",
                                              "full_text": "x"})
        assert r.status_code == 201
    calls = []

    def handler(req):
        calls.append(len(json.loads(req.content)["input"]))
        return embeddings(req)

    s = replace(settings, embedding_model="new/model")
    llm = OpenRouterClient("k", "m", "new/model", transport=httpx.MockTransport(handler))
    assert main(s, llm, confirm=lambda p: "o", out=lambda m: None) == 0
    assert calls == [1, 32, 8]
    with TestClient(create_app(s, **fakes), headers=AUTH) as c:
        top = c.get("/api/sources", params={"q": "Item17 s", "mode": "semantic", "limit": 1}).json()
    assert top["results"][0]["title"] == "Item17"  # vectors stayed attached to their own Source
