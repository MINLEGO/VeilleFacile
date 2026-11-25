"""Embedding model change (#23): `python -m veillefacile.reembed` recomputes stale embeddings by hand,
and the startup check of the configured model against OpenRouter's public model list."""
import asyncio
import logging
import sys

import httpx

from . import keywords as kw
from .clients import EMBED_BATCH, OPENROUTER, OpenRouterClient
from .errors import QuotaError, UpstreamError
from .ingestion import index_text, keywords_of
from .repository import SourceRepository
from .settings import Settings

log = logging.getLogger("veillefacile.reembed")


async def reembed(repo: SourceRepository, llm, model: str, *, confirm=input, out=print) -> int:
    """Recompute Sources whose embedding_model differs from `model`, one committed batch at a time.
    Stale = not yet on `model`, so a rerun after an interruption resumes by itself. -> exit code."""
    total = repo.count_stale(model)
    if total == 0:
        out("Aucune Source à recalculer.")
        return 0
    try:
        dim = len((await llm.embed(["test"]))[0])
        calls = -(-total // EMBED_BATCH)
        out(f"Appel de test : modèle {model}, dimension {dim}.")
        out(f"{total} Source(s) à recalculer, {calls} appels prévus (lots de {EMBED_BATCH}).")
        if confirm("Continuer ? [o/N] ").strip().lower() not in ("o", "oui"):
            out("Annulé.")
            return 1
        done = 0
        while rows := repo.stale_batch(model, EMBED_BATCH):
            texts = [index_text(r["title"], r["summary"], kw.effective(keywords_of(r))) for r in rows]
            for r, text, emb in zip(rows, texts, await llm.embed(texts)):
                repo.update(r["id"], {}, text, emb, model, touch=False)  # committed per Source; whole batch only after embed
            done += len(rows)
            out(f"{done}/{total}")
    except (UpstreamError, QuotaError) as e:
        out(f"Interrompu ({e}) : relancer la commande pour reprendre.")
        return 1
    out("Terminé.")
    return 0


async def fetch_models() -> list[dict]:
    """OpenRouter public model list (no key needed). Raises UpstreamError when unreachable."""
    try:
        async with httpx.AsyncClient(base_url=OPENROUTER, timeout=10) as http:
            r = await http.get("/models")
            r.raise_for_status()
            return r.json()["data"]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        raise UpstreamError("OpenRouter model list unavailable") from e


async def check_models(fetch, models: list[str]) -> list[str]:
    """-> warnings: configured models (embedding and summary) absent from the list, or with an expiration_date.
    Unreachable list: ignored."""
    try:
        listing = await fetch()
    except UpstreamError:
        return []
    by_id = {m.get("id"): m for m in listing}
    warnings = []
    for model in models:
        found = by_id.get(model)
        if found is None:
            warnings.append(f"Model {model} is absent from the OpenRouter model list")
        elif found.get("expiration_date"):
            warnings.append(f"Model {model} expires on {found['expiration_date']}")
    for w in warnings:
        log.warning(w)
    return warnings


def main(settings: Settings | None = None, llm=None, *, confirm=input, out=print) -> int:
    """Command entry point; settings / llm / confirm / out are injectable for tests."""
    s = settings or Settings.from_env()
    llm = llm or OpenRouterClient(s.openrouter_api_key, s.summary_model, s.embedding_model)
    return asyncio.run(reembed(SourceRepository(s.database_url), llm, s.embedding_model, confirm=confirm, out=out))


if __name__ == "__main__":
    sys.exit(main())
