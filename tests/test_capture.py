from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from veillefacile.errors import QuotaError, UpstreamError


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


def test_index_covers_title_summary_keywords(client, settings):
    sid = post(client, title="Zebra", summary="## What it is\nquagga", keywords=["Okapi"]).json()["id"]
    post(client, url="https://example.com/other", title="Other", summary="nothing")
    assert client.get(f"/api/sources/{sid}").json()["embedding_model"] == settings.embedding_model
    for word in ("zebra", "quagga", "okapi"):  # title, summary, keyword: full text search
        hits = client.get("/api/sources", params={"q": word, "mode": "text"}).json()["results"]
        assert [h["id"] for h in hits] == [sid], word
    sem = client.get("/api/sources", params={"q": "Zebra\n## What it is\nquagga\nfake, Okapi", "mode": "semantic"})
    assert sem.json()["results"][0]["id"] == sid


@pytest.mark.parametrize("exc,status", [(UpstreamError("down"), 502), (QuotaError(30), 503)])
def test_all_or_nothing(client, fakes, exc, status):
    fakes["llm"].fail = exc
    r = post(client)
    assert r.status_code == status
    if status == 503:
        assert r.headers["Retry-After"] == "30"
    assert client.get("/api/sources").json()["results"] == []


def test_capture_required_for_other_sites(client):
    r = client.post("/api/sources", json={"url": "https://example.com/x"})
    assert r.status_code == 422 and "Capture requise" in r.json()["detail"]


def test_github_without_full_text_uses_fetcher(client, fakes):
    fakes["github"].pages["https://github.com/foo/bar"] = {
        "title": "foo/bar", "full_text": "README", "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
    r = client.post("/api/sources", json={"url": "https://github.com/Foo/Bar/tree/x", "title": "Custom"})
    assert r.status_code == 201 and r.json()["title"] == "Custom" and r.json()["ingest_mode"] == "fetch"


def test_fetch_404_is_502_and_creates_no_source(client):
    r = client.post("/api/sources", json={"url": "https://github.com/foo/missing"})
    assert r.status_code == 502 and "not found" in r.json()["detail"]
    assert client.get("/api/sources").json()["results"] == []
