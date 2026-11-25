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
