"""Real GitHub / Hugging Face clients against a stubbed transport (no live network)."""
import asyncio

import httpx
import pytest

from veillefacile.clients import GitHubClient, HuggingFaceClient
from veillefacile.errors import UpstreamError


run = asyncio.run


def gh(handler, token=""):
    return GitHubClient(token, transport=httpx.MockTransport(handler))


def hf(handler, token=""):
    return HuggingFaceClient(token, transport=httpx.MockTransport(handler))


def test_github_fetch_maps_readme_title_date_and_sends_headers():
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path == "/repos/foo/bar":
            return httpx.Response(200, json={"full_name": "Foo/Bar", "description": "d",
                                             "created_at": "2024-01-02T03:04:05Z"})
        assert req.url.path == "/repos/foo/bar/readme"
        return httpx.Response(200, text="# README")

    out = run(gh(handler, "tok").fetch("https://github.com/foo/bar"))
    assert out["title"] == "Foo/Bar" and out["full_text"] == "# README"
    assert out["published_at"].year == 2024
    assert all(r.headers["Authorization"] == "Bearer tok" and r.headers["User-Agent"] for r in seen)
    assert seen[1].headers["Accept"] == "application/vnd.github.raw+json"


def test_github_without_token_sends_no_auth_and_missing_readme_falls_back_to_description():
    def handler(req):
        assert "Authorization" not in req.headers
        if req.url.path.endswith("/readme"):
            return httpx.Response(404)
        return httpx.Response(200, json={"full_name": "a/b", "description": "just a desc", "created_at": None})

    out = run(gh(handler).fetch("https://github.com/a/b"))
    assert out["full_text"] == "just a desc" and out["published_at"] is None


@pytest.mark.parametrize("status", [404, 500, 403])
def test_github_repo_errors_are_upstream_errors(status):
    with pytest.raises(UpstreamError) as e:
        run(gh(lambda req: httpx.Response(status)).fetch("https://github.com/a/b"))
    assert ("not found" in str(e.value)) == (status == 404)


@pytest.mark.parametrize("url, api, readme", [
    ("https://huggingface.co/ns/m", "/api/models/ns/m", "/ns/m/raw/main/README.md"),
    ("https://huggingface.co/datasets/ns/d", "/api/datasets/ns/d", "/datasets/ns/d/raw/main/README.md"),
    ("https://huggingface.co/spaces/ns/s", "/api/spaces/ns/s", "/spaces/ns/s/raw/main/README.md"),
])
def test_hf_fetch_maps_each_repo_type(url, api, readme):
    def handler(req):
        if req.url.path == api:
            return httpx.Response(200, json={"id": api.split("/api/")[0] or api.split("/", 3)[3], "createdAt": "2023-05-06T00:00:00.000Z"})
        assert req.url.path == readme and req.headers["Authorization"] == "Bearer t"
        return httpx.Response(200, text="card")

    out = run(hf(handler, "t").fetch(url))
    assert out["full_text"] == "card" and out["published_at"].year == 2023


def test_hf_follows_redirects_and_missing_is_clear_error():
    def ok(req):
        if req.url.path == "/api/models/bert":
            return httpx.Response(307, headers={"location": "/api/models/google/bert"})
        if req.url.path == "/api/models/google/bert":
            return httpx.Response(200, json={"id": "google/bert"})
        return httpx.Response(200, text="card")

    out = run(hf(ok).fetch("https://huggingface.co/bert"))
    assert out["title"] == "google/bert"

    # HF answers 401 for unknown repos (private or missing are indistinguishable)
    for status in (401, 404):
        with pytest.raises(UpstreamError, match="not found or not accessible"):
            run(hf(lambda req, s=status: httpx.Response(s)).fetch("https://huggingface.co/ns/m"))


def test_hf_unreadable_readme_falls_back_to_title():
    def handler(req):
        if req.url.path.startswith("/api/"):
            return httpx.Response(200, json={"id": "ns/m"})
        return httpx.Response(401)  # gated repo, README needs a token

    assert (run(hf(handler).fetch("https://huggingface.co/ns/m"))["full_text"] == "ns/m")


def test_network_error_is_upstream_error():
    def handler(req):
        raise httpx.ConnectTimeout("x")

    with pytest.raises(UpstreamError):
        run(gh(handler).fetch("https://github.com/a/b"))
