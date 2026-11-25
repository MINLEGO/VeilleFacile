# VeilleFacile

## Outils MCP

Le serveur MCP (`/mcp`) expose six outils. Pour en désactiver certains, lister leurs noms séparés par des virgules
dans `MCP_DISABLED_TOOLS` (les espaces autour des virgules sont ignorés) :

| Outil            | Rôle                                                  |
|------------------|-------------------------------------------------------|
| `search_sources` | Recherche hybride, sémantique ou textuelle des Sources |
| `get_source`     | Résumé, mots-clés et métadonnées d une Source          |
| `get_full_text`  | Tranche du texte intégral d une Source                 |
| `add_source`     | Ajoute une Source par URL                              |
| `update_source`  | Modifie titre, résumé ou mots-clés                     |
| `delete_source`  | Supprime définitivement une Source                     |

Exemple : `MCP_DISABLED_TOOLS=update_source,delete_source,add_source` ne laisse que la lecture.

Attention : une valeur vide prend le défaut `update_source,delete_source`. Pour tout activer, mettre une valeur qui ne
correspond à aucun outil, par exemple `MCP_DISABLED_TOOLS=none`.

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
