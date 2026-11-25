"""Hybrid search over Sources: exact pgvector similarity + Postgres full text, fused by RRF (k = 60).
Reused by the REST route, the MCP tool (#21) and the UI (#22) through `search_sources`."""
import re
from datetime import datetime
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from .errors import QuotaError, UpstreamError
from .repository import COLUMNS, vector_literal

RRF_K = 60
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


async def search_sources(repo, llm, embedding_model: str, *, q: str | None = None, mode: Mode = "hybrid",
                         site: str | None = None, keywords: list[str] = (), published_after: datetime | None = None,
                         published_before: datetime | None = None, limit: int = 20,
                         offset: int = 0) -> tuple[list[dict], bool]:
    """-> (rows, degraded). Rows are Source rows (no full_text stripping: callers use source_out) plus `score`
    when q is given. Without q: newest `updated_at` first. Raises SemanticUnavailable (mode=semantic, embedding failed)."""
    cond, p = _filters(site, keywords, published_after, published_before)
    q = (q or "").strip()
    with psycopg.connect(repo.database_url, row_factory=dict_row) as conn:
        stale = conn.execute("SELECT EXISTS (SELECT 1 FROM sources WHERE embedding_model IS DISTINCT FROM %s) AS x",
                             (embedding_model,)).fetchone()["x"]
        if not q:
            rows = conn.execute(f"SELECT {COLUMNS} FROM sources WHERE {cond} ORDER BY updated_at DESC, id DESC "
                                f"LIMIT %s OFFSET %s", p + [limit, offset]).fetchall()
            return rows, stale and mode != "text"
        embedding, degraded = None, stale and mode != "text"
        if mode != "text":
            try:
                embedding = (await llm.embed([q]))[0]
            except (UpstreamError, QuotaError) as e:
                if mode == "semantic":
                    raise SemanticUnavailable() from e
                degraded = True
        words = re.findall(r"\w+", q) if mode != "semantic" else []
        lists, lp = [], []
        if embedding is not None:
            lists.append(f"SELECT id, row_number() OVER (ORDER BY embedding <=> %s::vector) AS r FROM sources "
                         f"WHERE {cond} AND embedding_model = %s")
            lp += [vector_literal(embedding)] + p + [embedding_model]
        if words:
            tq = " | ".join(words)  # any word matches; ts_rank_cd orders by how many
            lists.append("SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search_text, to_tsquery('english', %s)) "
                         f"DESC) AS r FROM sources WHERE {cond} AND search_text @@ to_tsquery('english', %s)")
            lp += [tq] + p + [tq]
        if not lists:
            return [], degraded
        ranks = " UNION ALL ".join(f"({s})" for s in lists)
        rows = conn.execute(
            f"WITH ranks AS ({ranks}), fused AS (SELECT id, sum(1.0 / (%s + r))::float8 AS score FROM ranks "
            f"GROUP BY id) SELECT {COLUMNS}, score FROM fused JOIN sources USING (id) "
            f"ORDER BY score DESC, id LIMIT %s OFFSET %s", lp + [RRF_K, limit, offset]).fetchall()
        return rows, degraded
