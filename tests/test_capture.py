import asyncio
import json
from datetime import datetime, timezone

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from veillefacile.clients import OpenRouterClient
from veillefacile.errors import QuotaError, UpstreamError

from .fakes import fake_embedding


def post(client, **body):
    body.setdefault("url", "https://example.com/post")
    body.setdefault("full_text", "Some long text about Rust.")
    return client.post("/api/sources", json=body)


def test_capture_creates_then_updates(client):
    r = post(client, title="T")
    assert r.status_code == 201
    s = r.json()
    assert s["origin_site"] == "example.com" and s["title"] == "T" and s["keywords"] == ["fake"]
    assert s["summary"].startswith("## What it is") and s["ingest_mode"] == "capture"
    assert "full_text" not in s and "embedding" not in s
    r2 = post(client, url="https://www.example.com/post/?utm_source=x#frag", title="T2")
    assert r2.status_code == 200 and r2.json()["id"] == s["id"] and r2.json()["title"] == "T2"
    assert r2.json()["created_at"] == s["created_at"]


def test_get_source_and_404(client):
    sid = post(client).json()["id"]
    assert client.get(f"/api/sources/{sid}").json()["id"] == sid
    assert client.get("/api/sources/9999").status_code == 404


def test_requires_key(client):
    assert TestClient(client.app).post("/api/sources", json={"url": "https://a.b"}).status_code == 401


def test_caller_fields_respected_and_summary_skips_llm(client, fakes):
    r = post(client, title="Mine", summary="## What it is\nmine", published_at="2024-05-01T00:00:00Z",
             keywords=["Alpha"])
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["summary"] == "## What it is\nmine" and s["keywords"] == ["Alpha"]
    assert s["published_at"].startswith("2024-05-01") and fakes["llm"].summarize_calls == 0


def test_keywords_append_replace_and_reingest_keeps_manual_and_rejected(client):
    assert post(client, keywords=["Mine"]).json()["keywords"] == ["fake", "Mine"]
    s = post(client, keywords=["Only"], keywords_mode="replace").json()
    assert s["manual_keywords"] == ["Only"] and s["rejected_keywords"] == ["fake"] and s["keywords"] == ["Only"]
    s = post(client).json()  # reingest: generated keyword regenerated but stays rejected, manual kept
    assert s["keywords"] == ["Only"] and s["rejected_keywords"] == ["fake"]


def test_embedding_and_tsvector_cover_title_summary_keywords(client, settings):
    sid = post(client, title="Zebra", summary="## What it is\nquagga", keywords=["Okapi"]).json()["id"]
    with psycopg.connect(settings.database_url) as conn:
        emb, model = conn.execute("SELECT embedding::text, embedding_model FROM sources WHERE id=%s", (sid,)).fetchone()
        n = conn.execute("SELECT count(*) FROM sources WHERE search_text @@ "
                         "plainto_tsquery('english','zebra okapi quagga')").fetchone()[0]
    assert model == settings.embedding_model and n == 1
    assert len(emb.strip("[]").split(",")) == len(fake_embedding("x"))


@pytest.mark.parametrize("exc,status", [(UpstreamError("down"), 502), (QuotaError(30), 503)])
def test_all_or_nothing(client, fakes, settings, exc, status):
    fakes["llm"].fail = exc
    r = post(client)
    assert r.status_code == status
    if status == 503:
        assert r.headers["Retry-After"] == "30"
    with psycopg.connect(settings.database_url) as conn:
        assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


def test_capture_required_for_other_sites(client):
    r = client.post("/api/sources", json={"url": "https://example.com/x"})
    assert r.status_code == 422 and "Capture requise" in r.json()["detail"]


def test_github_without_full_text_uses_fetcher(client, fakes):
    fakes["github"].pages["https://github.com/foo/bar"] = {
        "title": "foo/bar", "full_text": "README", "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
    r = client.post("/api/sources", json={"url": "https://github.com/Foo/Bar/tree/x", "title": "Custom"})
    assert r.status_code == 201 and r.json()["title"] == "Custom" and r.json()["ingest_mode"] == "fetch"


# --- real OpenRouter client against a stubbed transport ---------------------------------------------------

LLM_OUT = ("## What it is\nA thing.\n\n## Why it matters\nIt does.\n\n## Key points\n- a\n\n"
           "## Who it's for\nYou.\n\n## Keywords\nRust, Tokio ,  ")


def _client(handler):
    return OpenRouterClient("k", "m1:free, m2", "emb", transport=httpx.MockTransport(handler))


def test_openrouter_summary_uses_models_list_and_parses_keywords(caplog):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"model": "m2", "choices": [{"message": {"content": LLM_OUT}}]})

    with caplog.at_level("INFO"):
        summary, kws = asyncio.run(_client(handler).summarize("x" * 200_000, title="T", url="u", site="s"))
    assert seen["body"]["models"] == ["m1:free", "m2"] and seen["body"]["temperature"] == 0.2
    assert len(seen["body"]["messages"][0]["content"]) < 103_000
    assert kws == ["Rust", "Tokio"] and summary.startswith("## What it is")
    assert "m2" in caplog.text


@pytest.mark.parametrize("resp,exc", [
    (httpx.Response(429, headers={"Retry-After": "12"}), QuotaError),
    (httpx.Response(500), UpstreamError),
    (httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "no sections"}}]}), UpstreamError),
])
def test_openrouter_error_mapping(resp, exc):
    with pytest.raises(exc) as e:
        asyncio.run(_client(lambda req: resp).summarize("t"))
    if exc is QuotaError:
        assert e.value.retry_after == 12


def test_openrouter_timeout_is_upstream_error():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(UpstreamError):
        asyncio.run(_client(handler).summarize("t"))


def test_openrouter_embeddings_batched_by_32_in_order():
    calls = []

    def handler(req):
        inp = json.loads(req.content)["input"]
        calls.append(len(inp))
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(t)]}
                                                  for i, t in reversed(list(enumerate(inp)))]})

    out = asyncio.run(_client(handler).embed([str(i) for i in range(70)]))
    assert calls == [32, 32, 6] and [v[0] for v in out] == list(range(70))


def test_fetch_404_is_502_and_creates_no_source(client, settings):
    r = client.post("/api/sources", json={"url": "https://github.com/foo/missing"})
    assert r.status_code == 502 and "not found" in r.json()["detail"]
    with psycopg.connect(settings.database_url) as conn:
        assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
