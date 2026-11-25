# VeilleFacile

## Tests

```
uv run pytest
```

Tests need a Postgres with pgvector (`pgvector/pgvector:pg18`). The server URL is read from `TEST_DATABASE_URL`
(default `postgresql://postgres:postgres@localhost:55432/postgres`). Each test session creates its own uniquely
named database, runs the migrations on it and drops it at the end.
