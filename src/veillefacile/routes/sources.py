from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from ..ingestion import keywords_of
from ..keywords import effective
from ..search import SemanticUnavailable, search_sources

router = APIRouter(prefix="/sources")


def source_out(row: dict) -> dict:
    """Public JSON of a Source: no full_text (see /text), no embedding; adds effective `keywords`."""
    out = {k: v for k, v in row.items() if k != "full_text"}
    out["keywords"] = effective(keywords_of(row))
    return out


class SourceIn(BaseModel):
    url: str
    title: str | None = None
    full_text: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    keywords_mode: Literal["append", "replace"] = "append"


@router.post("", status_code=201)
async def create_source(body: SourceIn, request: Request, response: Response):
    row, created = await request.app.state.ingestion.ingest(**body.model_dump())
    response.status_code = 201 if created else 200
    return source_out(row)


@router.get("")
async def search(request: Request, q: str | None = None, mode: Literal["hybrid", "semantic", "text"] = "hybrid",
                 site: str | None = None, keywords: list[str] = Query(default=[]),
                 published_after: datetime | None = None, published_before: datetime | None = None,
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    s = request.app.state
    try:
        rows, degraded = await search_sources(
            s.repo, s.llm, s.settings.embedding_model, q=q, mode=mode, site=site, keywords=keywords,
            published_after=published_after, published_before=published_before, limit=limit, offset=offset)
    except SemanticUnavailable:
        raise HTTPException(503, "Embedding model unavailable")
    return {"results": [source_out(r) for r in rows], "degraded": degraded, "limit": limit, "offset": offset}


@router.get("/{source_id}")
def get_source(source_id: int, request: Request):
    row = request.app.state.repo.get(source_id)
    if row is None:
        raise HTTPException(404, "Source not found")
    return source_out(row)


class SourcePatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    add_keywords: list[str] = []
    remove_keywords: list[str] = []


@router.patch("/{source_id}")
async def patch_source(source_id: int, body: SourcePatch, request: Request):
    row = await request.app.state.ingestion.edit(source_id, **body.model_dump())
    if row is None:
        raise HTTPException(404, "Source not found")
    return source_out(row)


@router.get("/{source_id}/text")
def get_source_text(source_id: int, request: Request, start: int = Query(0, ge=0),
                    length: int | None = Query(None, ge=0)):
    out = request.app.state.repo.text_slice(source_id, start, length)
    if out is None:
        raise HTTPException(404, "Source not found")
    return out


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, request: Request):
    if not request.app.state.repo.delete(source_id):
        raise HTTPException(404, "Source not found")
