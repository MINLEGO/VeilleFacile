# VeilleFacile

## Tests

```
uv run pytest
```

Tests need a Postgres with pgvector (`pgvector/pgvector:pg18`). The server URL is read from `TEST_DATABASE_URL`
(default `postgresql://postgres:postgres@localhost:55432/postgres`). Each test session creates its own uniquely
named database, runs the migrations on it and drops it at the end.

## Changer le modèle d embedding

Changer `EMBEDDING_MODEL`, redémarrer, puis lancer à la main dans le conteneur :

```
python -m veillefacile.reembed
```

La commande fait un appel de test (modèle, dimension), affiche le nombre de Sources à recalculer et d appels prévus
(lots de 32), demande `[o/N]`, puis recalcule lot par lot en enregistrant au fil de l eau. Relancée après une
interruption, elle reprend où elle s était arrêtée. Tant que des Sources sont périmées, `mode=hybrid` répond
`degraded: true` et `/api/health` donne `stale_sources`. Au démarrage, `warnings` de `/api/health` signale un modèle
configuré absent de la liste publique OpenRouter ou avec une `expiration_date`.
