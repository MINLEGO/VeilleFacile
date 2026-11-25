"""MCP adapter (Streamable HTTP, stateless, JSON): the 6 tools are thin wrappers over the REST logic."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import valid_key
from .errors import CaptureRequired, QuotaError, UpstreamError
from .routes.sources import source_out
from .search import SemanticUnavailable, search_sources


@asynccontextmanager
async def _tool_errors():
    """Service errors as clear tool errors (the REST handlers' counterpart)."""
    try:
        yield
    except CaptureRequired as e:
        raise ValueError(str(e)) from e
    except UpstreamError as e:
        raise ValueError(f"Upstream service failed: {e}") from e
    except QuotaError as e:
        raise ValueError(f"Quota exhausted, retry in {e.retry_after}s") from e


def build_mcp(app) -> FastMCP:
    """`app` is the FastAPI app; services are read from app.state at call time."""
    s = app.state
    # Bearer key guards /mcp, so DNS-rebinding host checks (localhost-only by default) are off.
    mcp = FastMCP("VeilleFacile", stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    async def search_sources_tool(q: str | None = None, mode: Literal["hybrid", "semantic", "text"] = "hybrid",
                                  site: str | None = None, keywords: list[str] = [],
                                  published_after: datetime | None = None, published_before: datetime | None = None,
                                  limit: int = 20, offset: int = 0) -> dict:
        """Hybrid search over saved Sources (no q: newest first). Returns summaries, not full text."""
        try:
            rows, degraded = await search_sources(
                s.repo, s.llm, s.settings.embedding_model, q=q, mode=mode, site=site, keywords=keywords,
                published_after=published_after, published_before=published_before,
                limit=max(1, min(limit, 100)), offset=max(0, offset))
        except SemanticUnavailable:
            raise ValueError("Embedding model unavailable")
        return {"results": [source_out(r) for r in rows], "degraded": degraded}

    async def get_source(source_id: int) -> dict:
        """One Source (summary, keywords, metadata; no full text)."""
        row = await asyncio.to_thread(s.repo.get, source_id)
        if row is None:
            raise ValueError("Source not found")
        return source_out(row)

    async def get_full_text(source_id: int, start: int = 0, length: int | None = None) -> dict:
        """A slice of a Source's full text: {text, start, total_length}."""
        if start < 0 or (length is not None and length < 0):
            raise ValueError("start and length must be >= 0")
        out = await asyncio.to_thread(s.repo.text_slice, source_id, start, length)
        if out is None:
            raise ValueError("Source not found")
        return out

    async def add_source(url: str, title: str | None = None, full_text: str | None = None,
                         published_at: datetime | None = None, summary: str | None = None,
                         keywords: list[str] | None = None,
                         keywords_mode: Literal["append", "replace"] = "append") -> dict:
        """Save a Source by URL (GitHub/Hugging Face are fetched; other sites need full_text)."""
        async with _tool_errors():
            row, _ = await s.ingestion.ingest(url, title=title, full_text=full_text, published_at=published_at,
                                              summary=summary, keywords=keywords, keywords_mode=keywords_mode)
        return source_out(row)

    async def update_source(source_id: int, title: str | None = None, summary: str | None = None,
                            keywords: list[str] | None = None, add_keywords: list[str] = [],
                            remove_keywords: list[str] = []) -> dict:
        """Edit a Source's title, summary or keywords."""
        async with _tool_errors():
            row = await s.ingestion.edit(source_id, title=title, summary=summary, keywords=keywords,
                                         add_keywords=add_keywords, remove_keywords=remove_keywords)
        if row is None:
            raise ValueError("Source not found")
        return source_out(row)

    async def delete_source(source_id: int) -> dict:
        """Permanently delete a Source."""
        if not await asyncio.to_thread(s.repo.delete, source_id):
            raise ValueError("Source not found")
        return {"deleted": source_id}

    disabled = {t.strip() for t in s.settings.mcp_disabled_tools.split(",")}
    for name, fn in {"search_sources": search_sources_tool, "get_source": get_source, "get_full_text": get_full_text,
                     "add_source": add_source, "update_source": update_source,
                     "delete_source": delete_source}.items():
        if name not in disabled:
            mcp.add_tool(fn, name=name)
    return mcp


def mount_mcp(app, mcp: FastMCP) -> None:
    """Serve `mcp` at exactly /mcp behind the same Bearer key (a Mount would redirect /mcp -> /mcp/)."""
    endpoint = mcp.streamable_http_app().routes[0].endpoint

    class Guarded:  # a class, so Route treats it as a raw ASGI app, not a request handler
        async def __call__(self, scope, receive, send):
            auth = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() != "bearer" or not valid_key(token, app.state.settings.api_key):
                resp = JSONResponse({"detail": "Invalid or missing API key"}, 401, {"WWW-Authenticate": "Bearer"})
                return await resp(scope, receive, send)
            await endpoint(scope, receive, send)

    app.router.routes.append(Route("/mcp", Guarded(), methods=["GET", "POST", "DELETE"]))
