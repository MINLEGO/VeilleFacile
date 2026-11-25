"""Sources persistence (psycopg, raw SQL). Rows are plain dicts; `embedding` and `search_text` are never returned."""
import psycopg
from psycopg.rows import dict_row

COLUMNS = ("id, url, canonical_url, origin_site, title, summary, generated_keywords, manual_keywords, "
           "rejected_keywords, full_text, ingest_mode, published_at, created_at, updated_at, embedding_model")


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


class SourceRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _one(self, query: str, params) -> dict | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            return conn.execute(query, params).fetchone()

    def get(self, source_id: int) -> dict | None:
        return self._one(f"SELECT {COLUMNS} FROM sources WHERE id = %s", (source_id,))

    def get_by_canonical(self, canonical_url: str) -> dict | None:
        return self._one(f"SELECT {COLUMNS} FROM sources WHERE canonical_url = %s", (canonical_url,))

    def upsert(self, row: dict, index_text: str, embedding: list[float], embedding_model: str) -> tuple[dict, bool]:
        """Insert or update by canonical_url in one statement -> (stored row, created). `row` holds the plain columns
        (url, canonical_url, origin_site, title, summary, *_keywords, full_text, ingest_mode, published_at);
        index_text feeds the tsvector (title + summary + effective keywords)."""
        cols = ["url", "canonical_url", "origin_site", "title", "summary", "generated_keywords", "manual_keywords",
                "rejected_keywords", "full_text", "ingest_mode", "published_at"]
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "canonical_url")
        q = (f"INSERT INTO sources ({', '.join(cols)}, embedding, embedding_model, search_text) "
             f"VALUES ({', '.join('%s' for _ in cols)}, %s::vector, %s, to_tsvector('english', %s)) "
             f"ON CONFLICT (canonical_url) DO UPDATE SET {update}, embedding = EXCLUDED.embedding, "
             f"embedding_model = EXCLUDED.embedding_model, search_text = EXCLUDED.search_text, updated_at = now() "
             f"RETURNING {COLUMNS}, (xmax = 0) AS created")
        stored = self._one(q, [row[c] for c in cols] + [vector_literal(embedding), embedding_model, index_text])
        return stored, stored.pop("created")

    def update(self, source_id: int, fields: dict, index_text: str | None = None, embedding: list[float] | None = None,
               embedding_model: str | None = None) -> dict | None:
        """Update plain columns (title, summary, *_keywords); with index_text+embedding also refreshes tsvector and
        embedding. Returns the row, or None if absent."""
        sets, params = [f"{c} = %s" for c in fields], list(fields.values())
        if index_text is not None:
            sets += ["search_text = to_tsvector('english', %s)", "embedding = %s::vector", "embedding_model = %s"]
            params += [index_text, vector_literal(embedding), embedding_model]
        return self._one(f"UPDATE sources SET {', '.join(sets)}, updated_at = now() WHERE id = %s "
                         f"RETURNING {COLUMNS}", params + [source_id])

    def count_stale(self, embedding_model: str) -> int:
        return self._one("SELECT count(*) AS n FROM sources WHERE embedding_model IS DISTINCT FROM %s",
                         (embedding_model,))["n"]

    def stale_batch(self, embedding_model: str, limit: int) -> list[dict]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            return conn.execute(f"SELECT {COLUMNS} FROM sources WHERE embedding_model IS DISTINCT FROM %s "
                                f"ORDER BY id LIMIT %s", (embedding_model, limit)).fetchall()

    def text_slice(self, source_id: int, start: int, length: int | None) -> dict | None:
        """-> {"text", "start", "total_length"} (length None = to the end)."""
        return self._one("SELECT substr(full_text, %s, coalesce(%s, length(full_text))) AS text, %s::int AS start, length(full_text) AS total_length "
                         "FROM sources WHERE id = %s", (start + 1, length, start, source_id))

    def delete(self, source_id: int) -> bool:
        with psycopg.connect(self.database_url) as conn:
            return conn.execute("DELETE FROM sources WHERE id = %s", (source_id,)).rowcount > 0
