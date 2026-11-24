# Moteur de stockage pour la recherche hybride

Issue : [MINLEGO/VeilleFacile#3](https://github.com/MINLEGO/VeilleFacile/issues/3)
Statut : recherche, aucune décision technique prise dans ce document.

## Question

Quel moteur retenir pour stocker les Sources et faire une recherche hybride (vectorielle + plein texte, avec un bon score sur les noms propres) sur Coolify, en mono-utilisateur et à petite échelle (quelques milliers de Sources) ?

Hypothèses de dimensionnement (à confirmer) :

- quelques milliers de Sources, avec titre, URL, résumé structuré, mots-clés (souvent des noms propres : outils, modèles, auteurs) et texte intégral stocké mais non indexé ;
- embeddings possiblement en 4096 dimensions (modèle d'embedding de 8B paramètres) ;
- recherche = similarité vectorielle sur résumé + titre + mots-clés, et correspondance lexicale forte sur les noms propres.

## Résumé et recommandation

**Recommandation : PostgreSQL (image avec pgvector) pour tout stocker, recherche vectorielle exacte sans index, recherche lexicale via le plein texte natif de Postgres (`tsvector`, configuration `simple`, index GIN), fusion par RRF.**

Pourquoi :

1. **Une seule base, un seul service à sauvegarder.** Les Sources, leurs métadonnées, le texte intégral, les vecteurs et l'index plein texte vivent au même endroit, avec transactions. Coolify propose déjà PostgreSQL comme ressource de base de données.
2. **Pas besoin d'index vectoriel à cette échelle.** Un index HNSW pgvector refuse les vecteurs de plus de 2000 dimensions (4000 en `halfvec`). Un modèle à 4096 dimensions ne peut donc pas être indexé en HNSW, même en `halfvec`. Pour quelques milliers de lignes, la recherche exacte (comportement par défaut de pgvector) reste simple et parfaitement précise.
3. **Fusion simple.** RRF se calcule en SQL ou en Python sur deux listes de rangs, sans réglage de poids entre scores hétérogènes.
4. **Chemin d'évolution clair.** Si le plein texte natif de Postgres ne classe pas assez bien les noms propres (il ne pondère pas la rareté des termes, voir plus bas), on peut ajouter une extension BM25 (pg_textsearch ou ParadeDB) sans changer d'architecture.

Alternative sérieuse si l'on veut un moteur hybride dédié : **Qdrant** (fusion RRF/DBSF native, service Coolify disponible). Meilisearch est pertinent si la tolérance aux fautes de frappe compte, mais sa fusion est opaque. LanceDB et SQLite (sqlite-vec + FTS5) sont des options embarquées intéressantes, mais avec des points de maturité à surveiller.

## Contraintes chiffrées

### Taille des vecteurs

Calcul sur float32 (4 octets par dimension), hors surcharge d'index :

| Nombre de Sources | 1536 dims | 4096 dims (float32) | 4096 dims (float16) |
|---|---|---|---|
| 1 000 | 6 Mo | 16 Mo | 8 Mo |
| 5 000 | 31 Mo | 82 Mo | 41 Mo |
| 10 000 | 61 Mo | 164 Mo | 82 Mo |

Ce sont des estimations à partir des formules données par Qdrant (voir section RAM), pas des mesures.

Coût d'une recherche exacte : chaque requête parcourt tous les vecteurs, soit environ 41 millions de multiplications-additions pour 10 000 Sources à 4096 dimensions. C'est de l'ordre de la dizaine de millisecondes à quelques dizaines de millisecondes en mémoire, à valider par benchmark sur votre machine.

### Limites de dimension par moteur

| Moteur | Limite stockage | Limite index | Source |
|---|---|---|---|
| pgvector `vector` | 16 000 dims | HNSW et IVFFlat : 2 000 dims | [README pgvector](https://github.com/pgvector/pgvector) |
| pgvector `halfvec` | 16 000 dims | HNSW et IVFFlat : 4 000 dims | [README pgvector](https://github.com/pgvector/pgvector) |
| pgvector `bit` | n/a | HNSW et IVFFlat : 64 000 dims | [README pgvector](https://github.com/pgvector/pgvector) |
| pgvector `sparsevec` | 16 000 éléments non nuls | HNSW : 1 000 éléments non nuls | [README pgvector](https://github.com/pgvector/pgvector) |
| Qdrant (vecteurs denses) | 65 535 dims | n/a | [FAQ Qdrant](https://qdrant.tech/documentation/faq/qdrant-fundamentals/index.md) |
| Meilisearch (`userProvided`) | non documentée | n/a | [Vue d'ensemble Meilisearch](https://www.meilisearch.com/docs/capabilities/hybrid_search/overview) : `dimensions` est obligatoire pour ce type d'embedder |
| sqlite-vec | non documentée sur la page officielle | n/a | [Page sqlite-vec](https://alexgarcia.xyz/sqlite-vec/) |

Conséquence directe pour un modèle à 4096 dimensions :

- en `vector` ou `halfvec` avec index HNSW : impossible ;
- en recherche exacte : possible et suffisant à cette échelle ;
- avec troncature (Matryoshka, si le modèle la supporte) à 2000 dims (`vector` HNSW) ou 4000 dims (`halfvec` HNSW) : possible. À vérifier pour le modèle choisi, la troncature n'est pas une propriété universelle des modèles d'embedding.

Paramètres HNSW par défaut de pgvector, pour référence si l'index devient nécessaire : `m` = 16, `ef_construction` = 64, `ef_search` = 40 ([README pgvector](https://github.com/pgvector/pgvector)).

## Score de fusion

### Principe RRF

Reciprocal Rank Fusion : pour chaque document `d`, `score(d) = Σ_r 1 / (k + rang_r(d))`, où `r` parcourt les listes de résultats (vectoriel, lexical). Avantage : on ne fusionne que des rangs, donc pas besoin de normaliser des scores de natures différentes (distance cosinus d'un côté, BM25 ou `ts_rank` de l'autre).

- pgvector : la documentation mentionne RRF ou un cross-encoder pour combiner des résultats, sans fournir de code RRF ([README pgvector](https://github.com/pgvector/pgvector)).
- Qdrant : RRF avec `k` par défaut de 2 selon la documentation, configurable à partir de la v1.16 (`{"rrf": {"k": 60}}`). Qdrant propose aussi DBSF, qui normalise les distributions de scores (moyenne et écart-type, de μ−3σ à μ+3σ) ([Requêtes hybrides Qdrant](https://qdrant.tech/documentation/search/hybrid-queries/)).
- LanceDB : RRF est le reranker par défaut ; il se combine les positions dans les deux listes ([Recherche hybride LanceDB](https://docs.lancedb.com/search/hybrid-search)).
- Meilisearch : la fusion n'est pas RRF ; la documentation dit seulement que les résultats sont fusionnés par un « système de scoring intelligent » propre, sans formule publiée ([Recherche hybride Meilisearch](https://www.meilisearch.com/docs/learn/ai_powered_search/hybrid_search)). Le paramètre `semanticRatio` (défaut 0,5) règle l'équilibre.

Pour ce projet, RRF avec un `k` explicite (la valeur de 60 proposée dans la littérature d'origine, à Cormack, Clarke et Buettcher, 2009, est un point de départ, non vérifié sur la source primaire dans cette recherche) est le choix le plus simple et le plus reproductible.

### Point critique : les noms propres

Le classement lexical doit donner un poids élevé aux termes rares (un nom propre apparaît peu, donc il doit compter beaucoup). Cela relève de BM25 (pondération IDF) :

- `ts_rank` et `ts_rank_cd` de Postgres ordonnent « selon la fréquence des lexèmes correspondants » ([Fonctions de classement PostgreSQL](https://www.postgresql.org/docs/current/textsearch-controls.html)). Aucune pondération de rareté n'est documentée : un nom propre rare ne remonte pas automatiquement davantage qu'un mot banal. C'est la principale faiblesse du plein texte natif pour ce cas d'usage.
- Mitigation sans extension : mettre les mots-clés (noms propres) en poids `A`, le titre en `B`, le résumé en `C`, le texte intégral en `D`, et ajouter un bonus explicite si un mot-clé de la requête correspond exactement à un mot-clé de la Source.
- Mitigation avec extension : pg_textsearch (BM25, voir ci-dessous) ou ParadeDB pg_search.

## Comparatif

| Critère | Postgres + pgvector + FTS natif | Postgres + pgvector + pg_textsearch (BM25) | Postgres + pgvector + ParadeDB | Qdrant | Meilisearch | LanceDB (embarqué) | SQLite + sqlite-vec + FTS5 |
|---|---|---|---|---|---|---|---|
| Recherche hybride intégrée | Non (deux requêtes + fusion) | Non (deux requêtes + fusion) | Oui, documentée (« Hybrid Search ») sans RRF mentionné | Oui : prefetch + RRF ou DBSF | Oui : `semanticRatio`, fusion propriétaire | Oui : `query_type="hybrid"` + reranker RRF par défaut | Non (fusion côté application) |
| Lexical type BM25 | Non (`ts_rank` sans IDF) | Oui (`k1`, `b`, Block-Max WAND) | Oui (« BM25 Scoring ») | Lexical via sparse vectors ou index texte | Propriétaire (pertinence + tolérance aux fautes) | Oui via Tantivy (BM25) ou FTS natif | Oui : `bm25()` de FTS5 |
| Limite de dimension (4096) | Pas d'index HNSW ; recherche exacte OK | Idem | Idem | OK (limite 65 535) | Non documentée | Non documentée | Non documentée |
| RAM (ordre de grandeur, 10 000 Sources) | Quelques centaines de Mo pour Postgres et le cache | Idem + `memory_limit` (2 Go par défaut, budget de memtable) | Idem | ~200 Mo pour les vecteurs (calcul officiel) + surcharge du processus | Inconnue pour les vecteurs, à mesurer | Faible (embarqué) | Très faible |
| Déploiement Coolify | Ressource PostgreSQL native ; image pgvector disponible | Image personnalisée (PG 17/18/19 uniquement) | Image ParadeDB dédiée (à remplacer le Postgres Coolify) | Service one-click | Service one-click | Pas de service : bibliothèque dans le conteneur de l'app | Pas de service : fichier dans le conteneur de l'app |
| Licence | PostgreSQL / pgvector : MIT | pg_textsearch : licence PostgreSQL | ParadeDB Community : AGPL-3.0 | Qdrant : Apache-2.0 | Meilisearch : MIT (+ BSL pour certaines parties EE) | Apache-2.0 | SQLite : domaine public ; sqlite-vec : pré-v1 |
| Maturité | Élevée | GA v1.0.0 (version la plus récente listée : v1.6.0) | Actif | Élevée | Élevée | Contestée selon les sources (voir plus bas) | sqlite-vec : pré-v1, « expect breaking changes » |

### Postgres + pgvector + FTS natif

- **Points forts** : un seul service, sauvegarde `pg_dump` unique, transactions, jointures avec les Sources, filtres SQL classiques, aucun service supplémentaire.
- **Vecteurs** : `vector(4096)` ou `halfvec(4096)` (sans index HNSW), recherche exacte. Le stockage d'un `halfvec` de 4096 dims fait `2 × dims + 8` octets, soit 8 200 octets par ligne ([Référence pgvector](https://github.com/pgvector/pgvector)).
- **Plein texte** : `tsvector` avec pondération, index GIN. Un index GIN ne stocke que les lexèmes, pas leurs étiquettes de poids ([Index textuels PostgreSQL](https://www.postgresql.org/docs/current/textsearch-indexes.html)).
- **Configuration `simple`** : le dictionnaire `simple` convertit les jetons en minuscules et filtre des stop words selon un fichier. La documentation ne décrit pas de racinisation pour ce dictionnaire, donc les noms propres ne sont pas tronqués ([Dictionnaires PostgreSQL](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)). Les accents ne sont pas retirés par ce dictionnaire ; le faire demande le module `unaccent`, documenté séparément.
- **Limite** : pas d'IDF, donc classement lexical moins fin sur les noms propres (voir ci-dessus).

### Postgres + pgvector + pg_textsearch (BM25)

- Extension sous licence PostgreSQL, binaires Linux amd64 et arm64, BM25 avec `k1` et `b` configurables, opérateur `<@>` en `ORDER BY`, Block-Max WAND pour les requêtes top-k ([dépôt pg_textsearch](https://github.com/timescale/pg_textsearch)).
- Versions de PostgreSQL supportées : 17, 18 et 19. Coolify propose PostgreSQL 16, 17 et 18 pour ses bases ([choix d'une base dans Coolify](https://coolify.io/docs/databases/choose-a-database)) : il faudra une image personnalisée, donc un peu de maintenance.
- Mémoire : `pg_textsearch.memory_limit` contrôle le cache de memtable (budget partagé, 2 Go par défaut), pas la construction d'index, qui suit `maintenance_work_mem` ([dépôt pg_textsearch](https://github.com/timescale/pg_textsearch)).
- La page ne documente pas d'intégration hybride avec pgvector : la fusion reste côté requête.

### Postgres + pgvector + ParadeDB pg_search

- Extension « BM25 Scoring » et « Hybrid Search » listées dans le README ; licence AGPL-3.0 pour la Community Edition ; installation par image Docker ([dépôt ParadeDB](https://github.com/paradedb/paradedb)).
- Le README ne mentionne pas RRF et ne précise pas les versions de PostgreSQL supportées ; la page de documentation BM25 n'a pas pu être lue (erreur 404 puis redirection non suivie). À vérifier avant adoption.
- Contrainte : une image ParadeDB remplace le PostgreSQL de Coolify, donc une gestion de l'image à part. L'AGPL n'est pas un problème pour un usage personnel mono-utilisateur, mais à noter si le projet devient ouvert à d'autres.

### Qdrant

- **Hybride natif** : plusieurs `prefetch` (un par représentation, dense ou sparse) fusionnés par `rrf` ou `dbsf` en une seule requête ; disponible depuis la v1.10 ([Requêtes hybrides Qdrant](https://qdrant.tech/documentation/search/hybrid-queries/)).
- **Lexical** : passe par des vecteurs sparse (il faut produire les poids côté client), pas par un moteur BM25 pur. Le « built-in IDF » de Qdrant 1.10 existe, mais je ne l'ai pas consulté sur la page officielle dans cette recherche.
- **Dimensions** : jusqu'à 65 535 par vecteur dense ; 4096 passe ([FAQ Qdrant](https://qdrant.tech/documentation/faq/qdrant-fundamentals/index.md)).
- **RAM** : formule officielle ([Capacity Planning Qdrant](https://qdrant.tech/documentation/capacity-planning/index.md)) :
  - `base = nombre_de_points × facteur_de_réplication` ;
  - `dense_size = base × dimensions × octets_par_dimension` ;
  - `hnsw_size = base × m × 2 × 4 × 1.2` (m = 16 par défaut) ;
  - `id_tracker_size = base × 52` octets ;
  - RAM ≈ somme des trois, puis marge d'environ 20 %.

  Application à 10 000 Sources, 4096 dims, float32, réplication 1 : dense ≈ 164 Mo, HNSW ≈ 1,5 Mo, ID tracker ≈ 0,5 Mo, soit ≈ 166 Mo, ≈ 200 Mo avec la marge. Le processus Qdrant ajoute son propre surcoût, non mesuré ici.
- **Sauvegarde** : snapshots de collection, documentés dans le tutoriel officiel ([Sauvegarde et restauration par snapshots](https://qdrant.tech/documentation/tutorials/create-snapshot)). Un snapshot sur le même disque que Qdrant disparaît avec lui : il faut le copier ailleurs.
- **Points faibles pour ce cas** : un service supplémentaire à sauvegarder et à garder synchronisé avec la base des Sources (double écriture, risque de dérive).

### Meilisearch

- **Hybride** : `semanticRatio` par requête, défaut 0,5 ; keyword et sémantique sont lancés en parallèle puis fusionnés par un scoring propre ; `rankingScoreThreshold` permet de couper les faibles correspondances sémantiques ([Recherche hybride Meilisearch](https://www.meilisearch.com/docs/learn/ai_powered_search/hybrid_search), [Vue d'ensemble](https://www.meilisearch.com/docs/capabilities/hybrid_search/overview)).
- **Vecteurs fournis par l'application** : embedder `userProvided`, `dimensions` obligatoire ; aucune limite de dimension publiée.
- **Points forts** : tolérance aux fautes de frappe, bonne ergonomie de recherche, Coolify one-click.
- **Points faibles** : la formule de fusion n'est pas publiée, donc difficile de régler finement le comportement sur les noms propres ; la RAM des vecteurs n'est pas documentée pour l'auto-hébergement (la documentation RAM ne donne pas de formule vectorielle) ; deuxième base à synchroniser avec Postgres.
- **Sauvegarde** : snapshots (copie exacte, planifiable par `--schedule-snapshot`) et dumps (export pour migrer entre versions) ([Sauvegarde Meilisearch](https://www.meilisearch.com/docs/resources/self_hosting/data_backup/overview)).
- **RAM** : minimum 256 Mo, et la documentation recommande que le jeu de données tienne en RAM pendant l'indexation ([Performance Meilisearch](https://www.meilisearch.com/docs/resources/self_hosting/performance/ram_multithreading)).

### LanceDB (embarqué)

- **Hybride** : `table.search(..., query_type="hybrid")` avec `.rerank(...)` ; RRF par défaut ; résultat dans une colonne `_relevance_score` ([Recherche hybride LanceDB](https://docs.lancedb.com/search/hybrid-search)).
- **Plein texte** : index FTS à créer sur la colonne texte, avec Tantivy (BM25) ([Full-Text Search with Tantivy](https://lancedb.com/docs/search/full-text-search-tantivy)). Les sources se contredisent sur le moteur FTS par défaut selon la version du SDK Python : à vérifier pour la version installée.
- **Embarqué** : pas de serveur, connexion par chemin local ; la documentation indique que le reranking se fait dans l'application.
- **Licence** : Apache-2.0 pour le paquet Python (vérifié via les métadonnées de paquets, pas sur la page de dépôt).
- **Maturité** : les sources divergent. Un miroir classe la version 0.39.0 en « Alpha », tandis qu'un autre indique une maintenance saine ; la publication est annoncée environ toutes les deux semaines. Un point à valider avant adoption.
- **Filtres** : le filtrage plein texte est limité en post-filtrage sans index natif (indication tirée des docs Tantivy).
- **Sauvegarde** : copie du répertoire de données (non vérifié dans cette recherche).

### SQLite + sqlite-vec + FTS5

- **FTS5** : fonction `bm25()` native (les valeurs basses sont les meilleures correspondances) ; tokenizers `unicode61` (défaut, retire les diacritiques des lettres latines), `porter` (racinisation), `trigram` (sous-chaînes) ; index de préfixes ; tables à contenu externe avec `rebuild` ([Documentation FTS5](https://sqlite.org/fts5.html)). FTS5 offre donc un BM25 réel, avec IDF, mais n'a pas de racinisation pour `unicode61`, ce qui est bon pour les noms propres.
- **sqlite-vec** : extension pré-v1 (« expect breaking changes ») ; vecteurs float, int8 et binaires dans des tables `vec0`. La page officielle n'indique ni algorithme (exact ou approximatif), ni limite de dimension, et se déclare « work-in-progress » ([Page sqlite-vec](https://alexgarcia.xyz/sqlite-vec/)). Les exemples sont des recherches KNN ; l'exactitude de la recherche n'est pas formellement documentée sur cette page.
- **Hybride** : fusion à écrire dans l'application (RRF simple sur deux requêtes).
- **Déploiement** : un fichier SQLite dans un volume du conteneur de l'app ; pas de service séparé.
- **Sauvegarde** : copie cohérente du fichier (méthode d'API de sauvegarde ou `VACUUM INTO`, non vérifiées dans cette recherche).
- **Risque** : la dépendance pré-v1 pour la partie vectorielle.

## Déploiement sur Coolify

- **PostgreSQL** : Coolify propose des bases PostgreSQL 16, 17 et 18 ainsi que des images pgvector ([choix d'une base dans Coolify](https://coolify.io/docs/databases/choose-a-database)). Recommandé pour la solution retenue.
- **Qdrant et Meilisearch** : présents dans le catalogue one-click ([catalogue des services Coolify](https://coolify.io/docs/services/all)). Une fois déployés, le logiciel et ses sauvegardes restent à votre charge (versions d'image, planification).
- **LanceDB et SQLite** : pas de service ; la donnée vit dans un volume monté sur le conteneur de l'application FastAPI.

## Sauvegardes

| Moteur | Mécanisme officiel | Remarque |
|---|---|---|
| Postgres | `pg_dump` (non consulté dans cette recherche) | Une seule sauvegarde couvre Sources, texte et vecteurs. |
| Qdrant | Snapshots de collection ([tutoriel](https://qdrant.tech/documentation/tutorials/create-snapshot)) | Copier hors du disque de Qdrant ; tester une restauration. |
| Meilisearch | Snapshots planifiables et dumps ([doc](https://www.meilisearch.com/docs/resources/self_hosting/data_backup/overview)) | Un snapshot avant chaque mise à jour, selon la documentation de versioning. |
| LanceDB | Copie du répertoire (non vérifié) | Sauvegarde du volume. |
| SQLite | Copie cohérente du fichier (non vérifié) | Plus simple que les autres : un fichier. |

Dans tous les cas : la base des Sources reste la source de vérité. Les index vectoriels et lexicaux sont reconstructibles à partir de celle-ci, ce qui limite l'impact d'une perte d'index.

## Clients Python

- **psycopg / pgvector-python** : paquet `pgvector`, licence MIT, intégrations pour Django, SQLAlchemy, SQLModel, Psycopg 2 et 3, asyncpg, pg8000 et Peewee ([pgvector-python](https://github.com/pgvector/pgvector-python)). Client mature, léger.
- **qdrant-client** : client officiel, avec création de snapshots (vu dans une documentation miroir, non relue sur la page officielle).
- **meilisearch-python-sdk** : client de la communauté, non évalué en détail ici.
- **lancedb** : API Python riche, maturité contestée selon les sources (voir ci-dessus).
- **sqlite-vec** : paquet Python pour l'extension, pré-v1.

## Non vérifié et limites de cette recherche

- ParadeDB : page de documentation BM25 non lue (404, puis redirection non suivie). Les versions de PostgreSQL supportées par pg_search ne sont pas confirmées.
- Empreinte RAM de Meilisearch pour les vecteurs : aucune formule officielle trouvée.
- Empreinte RAM du processus Qdrant et de Postgres : non mesurée.
- Coûts de recherche exacte : estimation théorique, à valider par benchmark sur les vrais embeddings.
- Valeur `k = 2` par défaut pour RRF dans Qdrant : telle que lue dans la documentation consultée ; à confirmer dans la version déployée.
- `pg_dump`, sauvegarde LanceDB et SQLite : méthodes standard, non confirmées par une source primaire dans cette recherche.

## Étapes suivantes proposées (non engagées)

1. Choisir le modèle d'embedding et vérifier s'il supporte une troncature (Matryoshka) vers 2000 ou 4000 dimensions.
2. Prototype : table `sources` Postgres avec `halfvec(4096)` ou `vector(4096)`, colonne `tsvector` pondérée, requête RRF en SQL. Mesurer latence et qualité sur 50 à 100 requêtes réelles, dont des noms propres.
3. Si le classement des noms propres reste insuffisant, comparer pg_textsearch (BM25) et Qdrant sur le même jeu de test.

## Sources principales

- pgvector (README : limites d'index, HNSW, recherche exacte, RRF) : https://github.com/pgvector/pgvector
- pgvector-python : https://github.com/pgvector/pgvector-python
- ParadeDB : https://github.com/paradedb/paradedb
- pg_textsearch (Timescale) : https://github.com/timescale/pg_textsearch
- PostgreSQL, fonctions de classement : https://www.postgresql.org/docs/current/textsearch-controls.html
- PostgreSQL, index textuels : https://www.postgresql.org/docs/current/textsearch-indexes.html
- PostgreSQL, dictionnaires : https://www.postgresql.org/docs/current/textsearch-dictionaries.html
- Qdrant, requêtes hybrides : https://qdrant.tech/documentation/search/hybrid-queries/
- Qdrant, FAQ : https://qdrant.tech/documentation/faq/qdrant-fundamentals/index.md
- Qdrant, capacity planning : https://qdrant.tech/documentation/capacity-planning/index.md
- Qdrant, snapshots : https://qdrant.tech/documentation/tutorials/create-snapshot
- Meilisearch, recherche hybride : https://www.meilisearch.com/docs/learn/ai_powered_search/hybrid_search
- Meilisearch, vue d'ensemble hybride : https://www.meilisearch.com/docs/capabilities/hybrid_search/overview
- Meilisearch, sauvegardes : https://www.meilisearch.com/docs/resources/self_hosting/data_backup/overview
- Meilisearch, performance RAM : https://www.meilisearch.com/docs/resources/self_hosting/performance/ram_multithreading
- LanceDB, recherche hybride : https://docs.lancedb.com/search/hybrid-search
- LanceDB, FTS Tantivy : https://lancedb.com/docs/search/full-text-search-tantivy
- sqlite-vec : https://alexgarcia.xyz/sqlite-vec/
- SQLite FTS5 : https://sqlite.org/fts5.html
- Coolify, bases de données : https://coolify.io/docs/databases/choose-a-database
- Coolify, services : https://coolify.io/docs/services/all
