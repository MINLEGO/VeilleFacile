"""Hybrid search over Sources: exact pgvector similarity + Postgres full text, fused by RRF (k = 60).
Reused by the REST route, the MCP tool (#21) and the UI (#22) through `search_sources`."""
import asyncio
import re
from datetime import datetime
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from .errors import QuotaError, UpstreamError
from .repository import COLUMNS, vector_literal

RRF_K = 60
MAX_WORDS = 32  # bound the generated tsquery
Mode = Literal["hybrid", "semantic", "text"]


class SemanticUnavailable(Exception):
    """Query embedding failed in `semantic` mode -> 503."""


def _filters(site, keywords, published_after, published_before) -> tuple[str, list]:
    where, p = ["TRUE"], []
    if site:
        where.append("origin_site = %s")
        p.append(site)
    for k in keywords:  # effective keyword = manual, or generated and not rejected (case-insensitive)
        where.append("(lower(%s) = ANY (SELECT lower(x) FROM unnest(manual_keywords) x) OR "
                     "(lower(%s) = ANY (SELECT lower(x) FROM unnest(generated_keywords) x) AND "
                     "lower(%s) <> ALL (SELECT lower(x) FROM unnest(rejected_keywords) x)))")
        p += [k, k, k]
    if published_after:
        where.append("published_at >= %s")
        p.append(published_after)
    if published_before:
        where.append("published_at <= %s")
        p.append(published_before)
    return " AND ".join(where), p


def _fetch_sync(database_url: str, query: str, params: list) -> list[dict]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        return conn.execute(query, params).fetchall()


async def _fetch(repo, query: str, params: list) -> list[dict]:
    return await asyncio.to_thread(_fetch_sync, repo.database_url, query, params)  # keep psycopg off the loop


async def search_sources(repo, llm, embedding_model: str, *, q: str | None = None, mode: Mode = "hybrid",
                         site: str | None = None, keywords: list[str] = (), published_after: datetime | None = None,
                         published_before: datetime | None = None, limit: int = 20,
                         offset: int = 0) -> tuple[list[dict], bool]:
    """-> (rows, degraded). Rows are Source rows (no full_text stripping: callers use source_out) plus `score`
    when q is given. Without q: newest `updated_at` first. Raises SemanticUnavailable (mode=semantic, embedding failed)."""
    cond, p = _filters(site, keywords, published_after, published_before)
    q = (q or "").strip()
    if not q:
        return await _fetch(repo, f"SELECT {COLUMNS} FROM sources WHERE {cond} ORDER BY updated_at DESC, id DESC "
                                  f"LIMIT %s OFFSET %s", p + [limit, offset]), False
    # degraded exists for hybrid only: semantic fails (503) instead, text never uses embeddings
    degraded = mode == "hybrid" and bool((await _fetch(
        repo, "SELECT 1 FROM sources WHERE embedding_model IS DISTINCT FROM %s LIMIT 1", [embedding_model])))
    embedding = None
    if mode != "text":
        try:
            embedding = (await llm.embed([q]))[0]
        except (UpstreamError, QuotaError) as e:
            if mode == "semantic":
                raise SemanticUnavailable() from e
            degraded = True
    words = re.findall(r"\w+", q)[:MAX_WORDS] if mode != "semantic" else []
    lists, lp = [], []
    if embedding is not None:
        lists.append(f"SELECT id, row_number() OVER (ORDER BY embedding <=> %s::vector) AS r FROM sources "
                     f"WHERE {cond} AND embedding_model = %s")
        lp += [vector_literal(embedding)] + p + [embedding_model]
    if words:
        # any word matches (tsquery `||` is OR); plainto_tsquery per word never raises on odd input
        tq = "(" + " || ".join("plainto_tsquery('english', %s)" for _ in words) + ")"
        lists.append(f"SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search_text, {tq}) "
                     f"DESC) AS r FROM sources WHERE {cond} AND search_text @@ {tq}")
        lp += words + p + words
    if not lists:
        return [], degraded
    ranks = " UNION ALL ".join(f"({s})" for s in lists)
    rows = await _fetch(
        repo, f"WITH ranks AS ({ranks}), fused AS (SELECT id, sum(1.0 / (%s + r))::float8 AS score FROM ranks "
              f"GROUP BY id) SELECT {COLUMNS}, score FROM fused JOIN sources USING (id) "
              f"ORDER BY score DESC, id LIMIT %s OFFSET %s", lp + [RRF_K, limit, offset])
    return rows, degraded
