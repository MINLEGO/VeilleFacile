from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.errors import UpstreamError

from .conftest import AUTH


def add(client, url, title, summary, **kw):
    r = client.post("/api/sources", json={"url": url, "title": title, "summary": summary, "full_text": "x", **kw})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def ids(r):
    assert r.status_code == 200, r.text
    return [s["id"] for s in r.json()["results"]]


def test_no_query_orders_by_updated_at_desc_without_score(client):
    a, b = add(client, "https://a.com/1", "A", "alpha"), add(client, "https://a.com/2", "B", "beta")
    add(client, "https://a.com/1", "A again", "alpha")  # update bumps a
    r = client.get("/api/sources")
    assert ids(r) == [a, b] and "score" not in r.json()["results"][0] and r.json()["degraded"] is False


def test_pagination(client):
    made = [add(client, f"https://a.com/{i}", f"T{i}", "s") for i in range(5)]
    assert ids(client.get("/api/sources", params={"limit": 2, "offset": 1})) == [made[3], made[2]]
    assert client.get("/api/sources", params={"limit": 101}).status_code == 422


@pytest.fixture
def corpus(client):
    return {
        "rust": add(client, "https://a.com/rust", "Rust ownership", "borrow checker lifetimes", keywords=["Ferris"]),
        "py": add(client, "https://b.org/py", "Python asyncio", "event loop coroutines",
                  published_at="2024-01-10T00:00:00Z"),
        "zig": add(client, "https://a.com/zig", "Zig comptime", "borrow memory arenas",
                   published_at="2025-06-01T00:00:00Z"),
    }


def test_text_mode_matches_words_and_scores_descending(client, corpus):
    r = client.get("/api/sources", params={"q": "borrow", "mode": "text"})
    assert set(ids(r)) == {corpus["rust"], corpus["zig"]}
    scores = [s["score"] for s in r.json()["results"]]
    assert scores == sorted(scores, reverse=True) and all(s > 0 for s in scores)
    assert ids(client.get("/api/sources", params={"q": "nomatchword", "mode": "text"})) == []


def test_semantic_mode_ranks_by_similarity(client, corpus):
    r = client.get("/api/sources", params={"q": "Python asyncio event loop coroutines", "mode": "semantic"})
    assert ids(r)[0] == corpus["py"] and len(ids(r)) == 3


def test_hybrid_uses_rrf_k60(client, corpus):
    r = client.get("/api/sources", params={"q": "Rust ownership borrow checker lifetimes"})
    top = r.json()["results"][0]
    assert top["id"] == corpus["rust"]
    assert top["score"] == pytest.approx(2 / 61)  # rank 1 in both lists: 1/(60+1) twice


def test_text_mode_finds_keywords(client, corpus):
    assert corpus["rust"] in ids(client.get("/api/sources", params={"q": "ferris", "mode": "text"}))


def test_filters(client, corpus):
    assert set(ids(client.get("/api/sources", params={"site": "a.com"}))) == {corpus["rust"], corpus["zig"]}
    assert ids(client.get("/api/sources", params={"keywords": ["FERRIS"]})) == [corpus["rust"]]
    assert ids(client.get("/api/sources", params={"keywords": ["ferris", "nope"]})) == []
    assert ids(client.get("/api/sources", params={"published_after": "2025-01-01T00:00:00Z"})) == [corpus["zig"]]
    assert ids(client.get("/api/sources", params={"published_before": "2025-01-01T00:00:00Z"})) == [corpus["py"]]
    r = client.get("/api/sources", params={"q": "borrow", "site": "b.org"})
    assert ids(r) == [corpus["py"]]  # semantic still returns it; filters apply to both lists


def test_embedding_failure_degrades_hybrid_and_503s_semantic(client, corpus, fakes):
    fakes["llm"].fail = UpstreamError("down")
    r = client.get("/api/sources", params={"q": "borrow"})
    assert r.status_code == 200 and r.json()["degraded"] is True
    assert set(ids(r)) == {corpus["rust"], corpus["zig"]}
    assert client.get("/api/sources", params={"q": "borrow", "mode": "semantic"}).status_code == 503
    assert client.get("/api/sources", params={"q": "borrow", "mode": "text"}).json()["degraded"] is False


def test_semantic_ignores_other_model_and_flags_degraded(client, corpus, settings, fakes):
    with TestClient(create_app(replace(settings, embedding_model="other"), **fakes), headers=AUTH) as other:
        new = add(other, "https://c.com/new", "Brand new", "borrow fresh")
        r = other.get("/api/sources", params={"q": "borrow", "mode": "semantic"})
        assert ids(r) == [new] and r.json()["degraded"] is True
        assert other.get("/api/sources", params={"q": "borrow", "mode": "text"}).json()["degraded"] is False
    assert client.get("/api/sources", params={"q": "borrow"}).json()["degraded"] is True  # new is stale for client
