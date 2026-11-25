"""Deterministic fakes for external clients, shared by all tests."""
import hashlib
import re

from veillefacile.errors import UpstreamError

DIM = 64


def fake_embedding(text: str) -> list[float]:
    """Hash-based bag-of-words vector: texts sharing words are close (cosine)."""
    vec = [0.0] * DIM
    for word in re.findall(r"\w+", text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    return vec


class FakeLLM:
    def __init__(self):
        self.fail: Exception | None = None  # set to simulate outages (timeout, quota...)
        self.summarize_calls = 0
        self.embedded: list[str] = []  # every text sent to embed
        self.keywords = ["fake"]  # what summarize "generates"

    async def summarize(self, text: str, *, title: str = "", url: str = "", site: str = "") -> tuple[str, list[str]]:
        """Returns (summary markdown, generated keywords)."""
        self.summarize_calls += 1
        if self.fail:
            raise self.fail
        return f"## What it is\n{text[:100]}\n## Keywords\nfake", list(self.keywords)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise self.fail
        self.embedded += texts
        return [fake_embedding(t) for t in texts]


class FakeGitHub:
    def __init__(self):
        self.pages: dict[str, dict] = {}  # canonical_url -> {"title", "full_text", "published_at"}

    async def fetch(self, canonical_url: str) -> dict:
        if canonical_url not in self.pages:  # same contract as the real clients on a 404
            raise UpstreamError(f"not found: {canonical_url}")
        return self.pages[canonical_url]


class FakeHuggingFace(FakeGitHub):
    pass
