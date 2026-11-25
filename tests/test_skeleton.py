from dataclasses import replace

import psycopg
import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app

INSERT = ("INSERT INTO sources (url, canonical_url, origin_site, title, summary, full_text, ingest_mode) "
          "VALUES ('u', %s, 's', 't', 's', 'f', 'capture')")


def test_health_ok_without_key(client):
    assert TestClient(client.app).get("/api/health").status_code == 200


def test_health_503_when_db_unreachable(settings, fakes):
    bad = replace(settings, database_url="postgresql://x:x@localhost:1/x", skip_migrations=True)
    with TestClient(create_app(bad, **fakes)) as c:
        assert c.get("/api/health").status_code == 503


def test_protected_route_requires_key(client):
    anon = TestClient(client.app)
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        r = anon.get("/api/sources", headers=headers)
        assert r.status_code == 401
        assert "detail" in r.json()
    assert client.get("/api/sources").status_code == 200


def test_migrations_recorded_and_sources_schema(client, settings):
    with psycopg.connect(settings.database_url) as conn:
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
        cols = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='sources'")}
        conn.execute(INSERT, ("c",))
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(INSERT, ("c",))
    assert "0001_create_sources" in versions
    assert {"embedding", "embedding_model", "search_text", "generated_keywords", "manual_keywords",
            "rejected_keywords", "published_at", "created_at", "updated_at"} <= cols


def test_failing_migration_prevents_startup(settings, fakes, tmp_path):
    (tmp_path / "0001_bad.sql").write_text("SELECT * FROM does_not_exist;")
    bad = replace(settings, migrations_dir=str(tmp_path))
    with pytest.raises(Exception):
        with TestClient(create_app(bad, **fakes)):
            pass


def test_ui_served_at_root_without_key(client):
    r = TestClient(client.app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "VeilleFacile" in r.text


READ_KEY = "read-key"


def test_read_only_key(settings, fakes):
    from .conftest import AUTH
    with TestClient(create_app(replace(settings, read_api_key=READ_KEY), **fakes)) as c:
        sid = c.post("/api/sources", headers=AUTH, json={"url": "https://blog.example/a", "title": "A",
                                                          "full_text": "hello"}).json()["id"]
        ro = {"Authorization": f"Bearer {READ_KEY}"}
        assert c.get("/api/sources", headers=ro).status_code == 200
        assert c.get(f"/api/sources/{sid}", headers=ro).status_code == 200
        assert c.get(f"/api/sources/{sid}/text", headers=ro).status_code == 200
        assert c.post("/api/sources", headers=ro, json={"url": "https://blog.example/b"}).status_code == 403
        assert c.patch(f"/api/sources/{sid}", headers=ro, json={"title": "B"}).status_code == 403
        assert c.delete(f"/api/sources/{sid}", headers=ro).status_code == 403
        assert c.post("/mcp", headers=ro, json={}).status_code == 401  # MCP stays admin-only


def test_no_read_key_by_default(client):
    anon = TestClient(client.app)
    for token in (READ_KEY, ""):
        assert anon.get("/api/sources", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_cors_only_when_configured(settings, fakes):
    origin = {"Origin": "https://public.example"}
    with TestClient(create_app(settings, **fakes)) as c:
        assert "access-control-allow-origin" not in c.get("/api/health", headers=origin).headers
    with TestClient(create_app(replace(settings, cors_origins="https://public.example"), **fakes)) as c:
        r = c.options("/api/sources", headers={**origin, "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "Authorization"})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "https://public.example"
