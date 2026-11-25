"""Ingestion service: orchestrates canonicalisation, fetch seam, LLM, keywords, embedding and persistence.
All external calls happen before the single write, so a failure leaves nothing behind (all-or-nothing)."""
import asyncio
from datetime import datetime
from typing import Literal

from . import keywords as kw
from .clients import LLMClient, SourceFetcher
from .errors import CaptureRequired
from .repository import SourceRepository
from .urls import canonicalize


def index_text(title: str, summary: str, keywords: list[str]) -> str:
    """The text that is embedded and fed to the tsvector: title + summary + effective keywords."""
    return "\n".join([title, summary, ", ".join(keywords)])


def keywords_of(row: dict) -> kw.Keywords:
    return kw.Keywords(row["generated_keywords"], row["manual_keywords"], row["rejected_keywords"])


class IngestionService:
    def __init__(self, repo: SourceRepository, llm: LLMClient, fetchers: dict[str, SourceFetcher],
                 embedding_model: str):
        """fetchers: origin site -> fetcher, e.g. {"github.com": ..., "huggingface.co": ...} (#18)."""
        self.repo, self.llm, self.fetchers, self.embedding_model = repo, llm, fetchers, embedding_model

    async def embed_index(self, title: str, summary: str, k: kw.Keywords) -> tuple[str, list[float]]:
        """-> (index text, embedding). Reuse after any change of title/summary/keywords (PATCH, #20)."""
        text = index_text(title, summary, kw.effective(k))
        return text, (await self.llm.embed([text]))[0]

    async def ingest(self, url: str, *, title: str | None = None, full_text: str | None = None,
                     published_at: datetime | None = None, summary: str | None = None,
                     keywords: list[str] | None = None,
                     keywords_mode: Literal["append", "replace"] = "append") -> tuple[dict, bool]:
        """-> (source row, created). Raises CaptureRequired, UpstreamError, QuotaError."""
        canonical, site = canonicalize(url)
        existing = await asyncio.to_thread(self.repo.get_by_canonical, canonical)  # psycopg blocks: off the loop
        mode = "capture"
        if full_text is None:
            fetcher = self.fetchers.get(site)
            if fetcher is None:
                raise CaptureRequired("Capture requise : ce site ne peut pas être récupéré par URL, "
                                      "envoyez le texte intégral (full_text).")
            fetched = await fetcher.fetch(canonical)
            full_text, mode = fetched["full_text"], "fetch"
            title = title or fetched.get("title")
            published_at = published_at or fetched.get("published_at")
        title = title or (existing and existing["title"]) or canonical
        published_at = published_at or (existing and existing["published_at"])

        k = keywords_of(existing) if existing else kw.Keywords()
        if summary is None:
            summary, generated = await self.llm.summarize(full_text, title=title, url=canonical, site=site)
            k = kw.regenerate(k, generated)
        if keywords is not None and keywords_mode == "replace":
            k = kw.replace(k, keywords)
        else:
            for word in keywords or []:
                k = kw.add(k, word)

        text, embedding = await self.embed_index(title, summary, k)
        row = {"url": url, "canonical_url": canonical, "origin_site": site, "title": title, "summary": summary,
               "generated_keywords": k.generated, "manual_keywords": k.manual, "rejected_keywords": k.rejected,
               "full_text": full_text, "ingest_mode": mode, "published_at": published_at}
        return await asyncio.to_thread(self.repo.upsert, row, text, embedding, self.embedding_model)

    async def edit(self, source_id: int, *, title: str | None = None, summary: str | None = None,
                   keywords: list[str] | None = None, add_keywords: list[str] = (),
                   remove_keywords: list[str] = ()) -> dict | None:
        """Manual correction (PATCH, no summary LLM call): applies keywords replace, then add, then remove;
        re-embeds and re-indexes only if title, summary or effective keywords changed. -> updated row, None if absent."""
        row = await asyncio.to_thread(self.repo.get, source_id)
        if row is None:
            return None
        title = title or row["title"]
        summary = summary if summary is not None else row["summary"]
        old = keywords_of(row)
        k = old
        if keywords is not None:
            k = kw.replace(k, keywords)
        for word in add_keywords:
            k = kw.add(k, word)
        for word in remove_keywords:
            k = kw.remove(k, word)
        fields = {"title": title, "summary": summary, "generated_keywords": k.generated,
                  "manual_keywords": k.manual, "rejected_keywords": k.rejected}
        text = embedding = None
        if (title, summary, kw.effective(k)) != (row["title"], row["summary"], kw.effective(old)):
            text, embedding = await self.embed_index(title, summary, k)
        return await asyncio.to_thread(self.repo.update, source_id, fields, text, embedding, self.embedding_model)
