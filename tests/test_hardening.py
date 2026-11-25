"""Review fixes, observed through the HTTP / MCP API."""
from dataclasses import replace

from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.errors import QuotaError, UpstreamError
from veillefacile.settings import Settings

from .conftest import API_KEY, AUTH
from .test_capture import post
from .test_edit import patch
from .test_mcp import HDR, call, rpc


def test_empty_env_vars_are_unset(monkeypatch, database_url, fakes):
    env = {"API_KEY": API_KEY, "DATABASE_URL": database_url, "MCP_DISABLED_TOOLS": "", "EMBEDDING_MODEL": "",
           "SUMMARY_MODEL": "", "OPENROUTER_API_KEY": ""}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    with TestClient(create_app(replace(s, skip_model_check=True), **fakes), headers=AUTH) as c:
        names = {t["name"] for t in rpc(c, "tools/list").json()["result"]["tools"]}
    assert names == {"search_sources", "get_source", "get_full_text", "add_source"}
    assert s.embedding_model and s.summary_model


def test_noop_patch_does_not_embed(client, fakes):
    sid = post(client, keywords=["Mine"]).json()["id"]
    fakes["llm"].fail = UpstreamError("down")
    assert patch(client, sid).status_code == 200
    assert patch(client, sid, title=client.get(f"/api/sources/{sid}").json()["title"]).status_code == 200
    assert patch(client, sid, remove_keywords=["never-there"]).json()["rejected_keywords"] == ["never-there"]
    assert patch(client, sid, title="New").status_code == 502


def test_remove_keyword_always_rejects_even_manual(client):
    sid = post(client, keywords=["Mine"]).json()["id"]
    s = patch(client, sid, remove_keywords=["mine"]).json()
    assert s["manual_keywords"] == [] and s["rejected_keywords"] == ["mine"]


def test_degraded_only_for_hybrid_with_query(client, settings, fakes):
    post(client, title="alpha", summary="alpha")
    with TestClient(create_app(replace(settings, embedding_model="newer"), **fakes), headers=AUTH) as other:
        assert other.get("/api/sources").json()["degraded"] is False
        assert other.get("/api/sources", params={"q": "alpha", "mode": "semantic"}).json()["degraded"] is False
        assert other.get("/api/sources", params={"q": "alpha", "mode": "text"}).json()["degraded"] is False
        assert other.get("/api/sources", params={"q": "alpha"}).json()["degraded"] is True


def test_weird_text_queries_never_500(client):
    post(client, title="Rust", summary="rust tokio")
    for q in ["a:* & !b | (c <-> d)", "'\\ \"", "the", "tokio'; DROP TABLE sources;--", "é_à ² ⅷ", "((("]:
        for mode in ("text", "hybrid"):
            assert client.get("/api/sources", params={"q": q, "mode": mode}).status_code == 200, q
    r = client.get("/api/sources", params={"q": "rust: tokio!", "mode": "text"})
    assert len(r.json()["results"]) == 1


def test_non_ascii_key_is_401_not_500(client):
    anon = TestClient(client.app, raise_server_exceptions=False)
    h = {"Authorization": "Bearer é".encode()}
    assert anon.get("/api/sources", headers=h).status_code == 401
    assert anon.post("/mcp", headers={**HDR, **h}, json={}).status_code == 401


def test_ping_is_gone(client):
    assert client.get("/api/ping").status_code == 404


# --- MCP ---------------------------------------------------------------------------------------------------

def full(settings, fakes):
    return TestClient(create_app(replace(settings, mcp_disabled_tools=""), **fakes), headers=AUTH)


def test_mcp_full_text_rejects_negative_slice(settings, fakes):
    with full(settings, fakes) as c:
        sid = call(c, "add_source", url="https://e.com/a", full_text="0123")[1]["id"]
        assert call(c, "get_full_text", source_id=sid, start=-1)[0] is True
        assert call(c, "get_full_text", source_id=sid, length=-1)[0] is True


def test_mcp_tools_surface_service_errors_clearly(settings, fakes):
    with full(settings, fakes) as c:
        err, text = call(c, "add_source", url="https://e.com/nope")
        assert err and "Capture requise" in text
        sid = call(c, "add_source", url="https://e.com/a", full_text="0123")[1]["id"]
        fakes["llm"].fail = QuotaError(30)
        err, text = call(c, "add_source", url="https://e.com/b", full_text="x")
        assert err and "30" in text and "uota" in text
        err, text = call(c, "update_source", source_id=sid, title="Other")
        assert err and "uota" in text
        fakes["llm"].fail = UpstreamError("boom")
        err, text = call(c, "update_source", source_id=sid, title="Other2")
        assert err and "boom" in text


# --- startup check covers summary models -------------------------------------------------------------------

def test_startup_check_warns_for_missing_summary_models(settings, fakes):
    listing = [{"id": settings.embedding_model}, {"id": "nvidia/nemotron-3.5-lightning:free"}]

    async def models():
        return listing

    with TestClient(create_app(settings, **fakes, models=models)) as c:
        w = c.get("/api/health").json()["warnings"]
    assert len(w) == 3 and not any("nemotron-3.5-lightning:free" in x for x in w)
    assert any("gemma-4-26b-a4b-it:free" in x for x in w)
