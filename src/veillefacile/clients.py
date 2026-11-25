"""Narrow interfaces to external services. Tests inject fakes; real classes are filled in by later tickets."""
from typing import Protocol


class LLMClient(Protocol):
    async def summarize(self, text: str) -> tuple[str, list[str]]:
        """Full text -> (structured summary markdown, generated keywords)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Texts -> embeddings (batched by the caller)."""


class SourceFetcher(Protocol):
    """GitHub / Hugging Face retrieval by canonical URL."""

    async def fetch(self, canonical_url: str) -> dict:
        """-> {"title": str, "full_text": str, "published_at": datetime | None}"""


class OpenRouterClient:
    def __init__(self, api_key: str, summary_model: str, embedding_model: str):
        self.api_key, self.summary_model, self.embedding_model = api_key, summary_model, embedding_model

    async def summarize(self, text: str) -> tuple[str, list[str]]:
        raise NotImplementedError  # later ticket

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError  # later ticket


class GitHubClient:
    def __init__(self, token: str):
        self.token = token

    async def fetch(self, canonical_url: str) -> dict:
        raise NotImplementedError  # later ticket


class HuggingFaceClient:
    async def fetch(self, canonical_url: str) -> dict:
        raise NotImplementedError  # later ticket
