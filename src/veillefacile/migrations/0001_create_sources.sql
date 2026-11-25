CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE sources (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url                text NOT NULL,
    canonical_url      text NOT NULL UNIQUE,
    origin_site        text NOT NULL,
    title              text NOT NULL,
    summary            text NOT NULL,
    generated_keywords text[] NOT NULL DEFAULT '{}',
    manual_keywords    text[] NOT NULL DEFAULT '{}',
    rejected_keywords  text[] NOT NULL DEFAULT '{}',
    full_text          text NOT NULL,
    ingest_mode        text NOT NULL CHECK (ingest_mode IN ('capture', 'fetch')),
    published_at       timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    embedding          vector,
    embedding_model    text,
    search_text        tsvector
);

CREATE INDEX sources_search_text_idx ON sources USING gin (search_text);
