"""Real GitHub / Hugging Face clients against a stubbed transport, injected into the app (no live network)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.clients import GitHubClient, HuggingFaceClient

from .conftest import AUTH


@pytest.fixture(autouse=True)
def _empty_table(client):
    """Apps built here skip the truncation of the `client` fixture; depend on it for a clean table."""


def app_with(settings, fakes, *, gh=None, hf=None, gh_token="", hf_token=""):
    deps = {"llm": fakes["llm"]}
    if gh:
        deps["github"] = GitHubClient(gh_token, transport=httpx.MockTransport(gh))
    if hf:
        deps["hf"] = HuggingFaceClient(hf_token, transport=httpx.MockTransport(hf))
    return TestClient(create_app(settings, **deps), headers=AUTH, raise_server_exceptions=False)


def fetch(c, url):
    return c.post("/api/sources", json={"url": url})


def test_github_fetch_maps_readme_title_date_and_sends_headers(settings, fakes):
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path == "/repos/foo/bar":
            return httpx.Response(200, json={"full_name": "Foo/Bar", "description": "d",
                                             "created_at": "2024-01-02T03:04:05Z"})
        assert req.url.path == "/repos/foo/bar/readme"
        return httpx.Response(200, text="# README")

    with app_with(settings, fakes, gh=handler, gh_token="tok") as c:
        r = fetch(c, "https://github.com/Foo/Bar/tree/main")
        assert r.status_code == 201, r.text
        s = r.json()
        assert s["title"] == "Foo/Bar" and s["ingest_mode"] == "fetch" and s["published_at"].startswith("2024-01-02")
        assert c.get(f"/api/sources/{s['id']}/text").json()["text"] == "# README"
    assert all(r.headers["Authorization"] == "Bearer tok" and r.headers["User-Agent"] for r in seen)
    assert seen[1].headers["Accept"] == "application/vnd.github.raw+json"


def test_github_without_token_sends_no_auth_and_missing_readme_falls_back_to_description(settings, fakes):
    def handler(req):
        assert "Authorization" not in req.headers
        if req.url.path.endswith("/readme"):
            return httpx.Response(404)
        return httpx.Response(200, json={"full_name": "a/b", "description": "just a desc", "created_at": None})

    with app_with(settings, fakes, gh=handler) as c:
        s = fetch(c, "https://github.com/a/b").json()
        assert s["published_at"] is None
        assert c.get(f"/api/sources/{s['id']}/text").json()["text"] == "just a desc"


@pytest.mark.parametrize("status", [404, 500, 403])
def test_github_repo_errors_are_502_and_store_nothing(settings, fakes, status):
    with app_with(settings, fakes, gh=lambda req: httpx.Response(status)) as c:
        r = fetch(c, "https://github.com/a/b")
        assert r.status_code == 502 and ("not found" in r.json()["detail"]) == (status == 404)
        assert c.get("/api/sources").json()["results"] == []


@pytest.mark.parametrize("url, api, readme", [
    ("https://huggingface.co/ns/m", "/api/models/ns/m", "/ns/m/raw/main/README.md"),
    ("https://huggingface.co/datasets/ns/d", "/api/datasets/ns/d", "/datasets/ns/d/raw/main/README.md"),
    ("https://huggingface.co/spaces/ns/s", "/api/spaces/ns/s", "/spaces/ns/s/raw/main/README.md"),
])
def test_hf_fetch_maps_each_repo_type(settings, fakes, url, api, readme):
    ident = api.split("/", 3)[3]

    def handler(req):
        if req.url.path == api:
            return httpx.Response(200, json={"id": ident, "createdAt": "2023-05-06T00:00:00.000Z"})
        assert req.url.path == readme and req.headers["Authorization"] == "Bearer t"
        return httpx.Response(200, text="card")

    with app_with(settings, fakes, hf=handler, hf_token="t") as c:
        r = fetch(c, url)
        assert r.status_code == 201, r.text
        assert r.json()["title"] == ident and r.json()["published_at"].startswith("2023-05-06")
        assert c.get(f"/api/sources/{r.json()['id']}/text").json()["text"] == "card"


def test_hf_follows_redirects(settings, fakes):
    def handler(req):
        if req.url.path == "/api/models/bert":
            return httpx.Response(307, headers={"location": "/api/models/google/bert"})
        if req.url.path == "/api/models/google/bert":
            return httpx.Response(200, json={"id": "google/bert"})
        return httpx.Response(200, text="card")

    with app_with(settings, fakes, hf=handler) as c:
        r = fetch(c, "https://huggingface.co/bert")
        assert r.status_code == 201 and r.json()["title"] == "google/bert"


@pytest.mark.parametrize("status", [401, 404])  # HF answers 401 for unknown repos
def test_hf_missing_is_a_clear_502(settings, fakes, status):
    with app_with(settings, fakes, hf=lambda req: httpx.Response(status)) as c:
        r = fetch(c, "https://huggingface.co/ns/m")
        assert r.status_code == 502 and "not found or not accessible" in r.json()["detail"]


def test_hf_unreadable_readme_falls_back_to_title(settings, fakes):
    def handler(req):
        if req.url.path.startswith("/api/"):
            return httpx.Response(200, json={"id": "ns/m"})
        return httpx.Response(401)  # gated repo, README needs a token

    with app_with(settings, fakes, hf=handler) as c:
        s = fetch(c, "https://huggingface.co/ns/m").json()
        assert c.get(f"/api/sources/{s['id']}/text").json()["text"] == "ns/m"


def test_network_error_is_502(settings, fakes):
    def handler(req):
        raise httpx.ConnectTimeout("x")

    with app_with(settings, fakes, gh=handler) as c:
        assert fetch(c, "https://github.com/a/b").status_code == 502
