-- Cache of search query embeddings (LRU, bounded in search.py), so repeated queries skip the embedding API.
CREATE TABLE query_embeddings (
    model     text NOT NULL,
    query     text NOT NULL,
    embedding vector NOT NULL,
    used_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model, query)
);
