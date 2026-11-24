# Récupération par URL : GitHub et Hugging Face

Issue : MINLEGO/VeilleFacile#4 (`wayfinder:research`)

## Question

À partir d'une seule URL (dépôt GitHub, ou modèle / dataset / space Hugging Face), comment récupérer le titre, la description, le site d'origine et le README intégral, pour résumer et indexer le contenu ? Quelles APIs, quelle authentification, quelles limites de débit, et quels cas particuliers (README absent, model card, sous-chemins d'URL) ?

## Résumé

- **GitHub** : `GET /repos/{owner}/{repo}` donne `name`, `full_name`, `description`, `homepage`, `html_url`. `GET /repos/{owner}/{repo}/readme` donne le README. Sans token, la limite est de 60 requêtes par heure et par IP ; avec un token, de 5 000 par heure. Un dépôt sans README renvoie 404.
- **Hugging Face** : `GET /api/{models|datasets|spaces}/{namespace}/{name}` donne les métadonnées (pas de champ `description` au niveau racine). Le README s'obtient par `https://huggingface.co/{id}/raw/main/README.md`, avec le même chemin pour datasets et spaces via le préfixe `/datasets/` ou `/spaces/`. Les dépôts publics ne demandent aucun token. Les dépôts privés ou inexistants renvoient 401 sans token. Les dépôts gated gardent leurs métadonnées lisibles, mais leur README en `/raw/` renvoie 401 sans token.
- **Piège observé** : la doc GitHub indique que le README est renvoyé en raw par défaut ; le test live renvoie du JSON en base64. Il faut donc envoyer explicitement l'en-tête `Accept` (voir section GitHub).
- **Recommandation** : envoyer un token (`GITHUB_TOKEN`, `HF_TOKEN`) dès que possible, normaliser l'URL avant l'appel, et traiter 401/403/404 comme des états normaux (métadonnées partielles plutôt qu'échec).

## Méthode

Sources primaires : documentation officielle GitHub REST et Hugging Face Hub. Les points de comportement ont été vérifiés en direct avec `curl` le 2026-11-24 (sans token) ; chaque point est marqué **(vérifié live)** ou **(doc)**. La doc a été lue via un outil de résumé ; les citations entre guillemets sont donc à reprendre avec précaution et à recouper avec la page source avant implémentation.

---

## 1. GitHub

### 1.1 Normalisation de l'URL

Formes d'URL à accepter :

| Entrée | Dépôt à retenir |
|---|---|
| `https://github.com/{o}/{r}` | `{o}/{r}` |
| `https://github.com/{o}/{r}/` | `{o}/{r}` |
| `https://github.com/{o}/{r}.git` | `{o}/{r}` (le `.git` doit être retiré : `GET /repos/{o}/{r}.git` renvoie 404 **(vérifié live)**) |
| `https://github.com/{o}/{r}/tree/main/...`, `/blob/main/...`, `/issues/...`, `/pull/...` | `{o}/{r}` (sous-chemins ignorés) |
| `https://www.github.com/...` | à traiter comme `github.com` |

Le parsing est une règle de notre côté : la doc GitHub ne la définit pas. Les noms d'owner et de repo sont insensibles à la casse pour l'API **(doc, `repos/repos`: "Matching is case-insensitive")**.

Les sous-chemins `/tree/<branche>` ne changent que la branche de lecture. Si le besoin est de lire le README d'une autre branche, passer `ref` à l'endpoint README (voir 1.3).

### 1.2 Métadonnées du dépôt

`GET https://api.github.com/repos/{owner}/{repo}` **(doc : [repos/repos#get-a-repository](https://docs.github.com/en/rest/repos/repos#get-a-repository))**

- Pas de paramètre de requête. Accepte `application/vnd.github+json` (recommandé).
- Champs utiles : `name`, `full_name`, `description` (string ou `null`), `homepage` (URL ou `null`), `html_url`, `private`, `default_branch`, `fork`, `parent` et `source` (présents si c'est un fork).
- Statuts documentés : 200, 301 (déplacé), 403, 404.
- Live : `huggingface/transformers` renvoie 200 avec `name` et `full_name` **(vérifié live)**.

**Titre** : GitHub n'a pas de champ « titre » séparé. Utiliser `full_name` (ou `name`). **Site d'origine** : `html_url` pour l'origine, `homepage` si le dépôt en renseigne un.

### 1.3 README

`GET https://api.github.com/repos/{owner}/{repo}/readme` **(doc : [contents#get-a-repository-readme](https://docs.github.com/en/rest/repos/contents#get-a-repository-readme))**

- Paramètre `ref` (optionnel) : commit, branche ou tag ; par défaut la branche par défaut du dépôt.
- Variante `GET /repos/{owner}/{repo}/readme/{dir}` pour un README situé dans un dossier.
- En-tête `Accept: application/vnd.github.raw+json` : renvoie le contenu brut **(doc: "Returns the raw file contents")**. **Vérifié live** : retourne le Markdown directement.
- Sans cet en-tête : **réponse JSON**, avec `content` en base64 et `encoding: "base64"` **(vérifié live)**. La doc, résumée par l'outil, indique que le raw est le défaut ; le test live contredit ce point. Ne pas s'y fier : **toujours envoyer l'en-tête `Accept` explicitement**.
- Le README est renvoyé tel quel, y compris le front matter éventuel.

**README absent** : statut 404 **(doc: "404: Resource not found")**. Ce cas n'a pas été reproduit live (aucun dépôt sans README trouvé pendant ce test). Traiter 404 comme « pas de README » et conserver titre et description.

### 1.4 Authentification

- **Dépôts publics** : pas de token requis. Vérifié live : `huggingface/transformers` renvoie 200 sans authentification.
- **Dépôts privés** : token requis. Un token sans accès au dépôt renvoie 404 (non vérifié live ; cohérent avec le comportement GitHub habituel, à confirmer avec un dépôt privé de test).
- **En-tête `User-Agent`** : la doc indique qu'il est obligatoire et qu'une valeur invalide renvoie 403 **(doc : [getting-started-with-the-rest-api](https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api))**. Envoyer un UA explicite (par ex. `VeilleFacile/1.0`), même si `curl` par défaut a fonctionné en test.
- Token : PAT (`Authorization: Bearer <token>`) ; un token en lecture seule suffit.

### 1.5 Limites de débit

**(doc : [rate-limits-for-the-rest-api](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api))**

- Sans authentification : **60 requêtes par heure**, par IP d'origine.
- Avec token (PAT) : **5 000 requêtes par heure**.
- Limites secondaires : 900 points par minute pour les endpoints REST (une requête GET coûte 1 point), concurrence de 100 requêtes, 80 requêtes de création de contenu par minute.
- **Vérifié live** : en-tête `X-RateLimit-Limit: 60` sur appel anonyme.

Un pipeline qui indexe plusieurs dépôts sans token est vite limité. Par dépôt, il faut 2 appels (repo + readme) ; soit 30 dépôts par heure sans token.

### 1.6 Renommage, redirections, forks

- Renommage : la doc indique que les anciennes URL web redirigent vers le nouveau nom, et que `git clone/fetch/push` vers l'ancien emplacement continuent de fonctionner **(doc : [renaming-a-repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository))**. La doc ne dit pas explicitement que l'API REST redirige ; le statut 301 de `GET /repos/{o}/{r}` le suggère. **Conséquence** : suivre la redirection et normaliser la clé d'indexation sur `full_name` renvoyé, pas sur l'URL saisie.
- Fork : les champs `parent` et `source` sont présents ; le README du fork peut être identique à l'amont.

---

## 2. Hugging Face Hub

### 2.1 Formes d'URL et normalisation

Sur le web, la forme générique est `https://huggingface.co/{namespace}/{name}` pour les modèles, `https://huggingface.co/datasets/{namespace}/{name}` pour les datasets et `https://huggingface.co/spaces/{namespace}/{name}` pour les spaces **(doc : [repositories-getting-started](https://huggingface.co/docs/hub/repositories-getting-started) pour le clone ; la forme web est observée live)**.

| Entrée | Identifiant à retenir | Type |
|---|---|---|
| `huggingface.co/{ns}/{name}` | `{ns}/{name}` | model |
| `huggingface.co/datasets/{ns}/{name}` | `{ns}/{name}` | dataset |
| `huggingface.co/spaces/{ns}/{name}` | `{ns}/{name}` | space |
| `huggingface.co/{ns}/{name}/tree/main`, `/blob/main/README.md`, `/resolve/...`, `/raw/...` | `{ns}/{name}` (sous-chemin ignoré) | selon préfixe |
| `huggingface.co/bert-base-uncased` (sans organisation) | `bert-base-uncased` | model |

Points vérifiés live :

- **Sans organisation** : `GET /api/models/bert-base-uncased` renvoie **307** vers `/api/models/google-bert/bert-base-uncased` **(vérifié live)**. Un client qui ne suit pas les redirections échoue. Suivre la redirection et utiliser `id` de la réponse comme identifiant canonique.
- Les datasets sans organisation (ex. `squad`) suivent le même schéma : 307 vers `rajpurkar/squad` **(vérifié live)**.
- Le type (model, dataset, space) doit être déduit du préfixe de l'URL. Sans préfixe, c'est un model. Un identifiant de model appelé sur `/api/datasets/` renvoie 401 (non-existence, voir 2.5).

### 2.2 Métadonnées

Endpoints (doc : [hub/api](https://huggingface.co/docs/hub/api) renvoie vers l'OpenAPI ; le détail est dans [openapi.md](https://huggingface.co/.well-known/openapi.md)) :

- `GET /api/models/{namespace}/{name}`
- `GET /api/datasets/{namespace}/{name}`
- `GET /api/spaces/{namespace}/{name}`

Paramètres : `?full=true` et `?cardData=true` sont des options disponibles sur les endpoints d'information. La doc résumée par l'outil ne les décrit pas pour ces trois endpoints ; ils ont été acceptés sans erreur live sur le modèle (`bert-base-uncased?full=true&cardData=true` renvoie 200 après redirection).

Champs observés live :

- **Model** (`bert-base-uncased` ; et `meta-llama/Llama-3.1-8B`) : `id`, `author`, `cardData` (métadonnées YAML du README, objet), `gated` (`false`, `"auto"` ou `"manual"`), `private`, `pipeline_tag`, `library_name`, `tags`, `siblings` (liste des fichiers), `sha`, `lastModified`, `likes`, `downloads`. **Pas de `description` au niveau racine.**
- **Dataset** (`squad`) : `id`, `author`, `cardData`, `description` (présent ici, à la différence des models), `gated`, `private`, `tags`, `siblings`, `sha`, `lastModified`, `likes`, `downloads`, `paperswithcode_id`, `pretty_name`, `license`, `language`.
- **Space** (`gradio/hello_world`) : `id`, `author`, `sdk`, `title`, `emoji`, `cardData` (objet avec `title`, `emoji`, `sdk`...), `private`, `gated`, `tags`, `sha`, `siblings`, `likes`, `hardware`, `runtime`, `visibility`. **Pas de `description` au niveau racine.**

**Titre** : model et space -> `id` (ou `cardData.title` pour les spaces) ; dataset -> `cardData.pretty_name` ou `id`. **Description** : dataset -> `description` ; model et space -> pas de champ dédié, utiliser le premier paragraphe du README, ou `cardData` quand il en contient un (non vérifié pour tous les cas).

### 2.3 README (model card / dataset card / space card)

Le README est le fichier `README.md` à la racine du dépôt. Plusieurs URL donnent le même contenu **(vérifié live)** :

- `https://huggingface.co/{id}/raw/main/README.md` : `200 text/plain` (model, dataset, space). **Recommandé** : URL explicite, contenu brut.
- `https://huggingface.co/{id}/resolve/main/README.md` : `200` (mêmes contenus).
- `https://huggingface.co/datasets/{id}/raw/main/README.md` et `https://huggingface.co/spaces/{id}/raw/main/README.md` : `200`.

Le README contient le front matter YAML (`---`) suivi du Markdown. Le front matter correspond à `cardData` ; pour l'indexation, séparer les deux ou garder le tout.

Alternative côté Python : `huggingface_hub` **(doc : [package_reference/hf_api](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api))** :

- `HfApi.model_info(repo_id, token=...)`, `dataset_info(...)`, `space_info(...)` : métadonnées (signature `dataset_info(repo_id, revision, files_metadata, expand, token)` vérifiée dans la doc ; les autres signatures n'ont pas pu être lues en entier).
- `hf_hub_download(repo_id, "README.md", repo_type="dataset"|"space")` pour le README. Non testé.

Le package est recommandé par la doc pour tout accès programmatique (voir 2.6). Pour le besoin ici (3 appels HTTP simples), l'usage direct de `httpx`/`requests` suffit ; `huggingface_hub` ajoute surtout le retry automatique sur 429.

### 2.4 Authentification et dépôts gated

- **Public** : pas de token requis. Vérifié live (model, dataset, space).
- **Gated** (`gated` = `"manual"` ou `"auto"`) : les métadonnées restent lisibles sans token. Vérifié live : `GET /api/models/meta-llama/Llama-3.1-8B` renvoie 200 avec `gated: "manual"`.
- **Fichiers d'un dépôt gated** : la doc indique qu'il faut être authentifié et avoir obtenu l'accès (un token d'un utilisateur ayant accepté les conditions) **(doc : [models-gated](https://huggingface.co/docs/hub/models-gated) : "To download files from a gated model you'll need to be authenticated")**. Vérifié live sans token :
  - `https://huggingface.co/meta-llama/Llama-3.1-8B/raw/main/README.md` renvoie **401** « Access to model ... is restricted. You must have access to it and be authenticated ».
  - `https://huggingface.co/meta-llama/Llama-3.1-8B/resolve/main/README.md` renvoie **200** avec le contenu, sans token.
  - Les deux URL ne se comportent pas de la même façon. **Ne pas exploiter cette incohérence** : le contrôle d'accès est décidé par les auteurs du modèle. Pour le service, passer `HF_TOKEN` quand l'utilisateur a accès, et traiter 401 comme « README non accessible ». Signaler à l'équipe que l'accès via `/resolve/` n'est pas une garantie et qu'il ne faut pas en faire un chemin officiel avant clarification.
- **Dépôts privés ou inexistants** : renvoient **401** « Invalid username or password. » sans token **(vérifié live)**. La doc `huggingface_hub` indique que `RepositoryNotFoundError` est levé dans les deux cas (inexistant ou privé sans accès) **(doc : hf_api)**. Il est donc impossible de distinguer les deux sans token : traiter 401 comme « non accessible ».
- `GatedRepoError` (doc `huggingface_hub`) : dépôt gated, utilisateur non autorisé.
- Token : `HF_TOKEN` (`Authorization: Bearer <token>`).

### 2.5 Codes de statut observés

| Cas | Statut live |
|---|---|
| Model public (`bert-base-uncased`, après redirection) | 200 |
| Model sans organisation (`bert-base-uncased`) | 307 vers `google-bert/bert-base-uncased` |
| Dataset sans organisation (`squad`) | 307 vers `rajpurkar/squad` |
| Space public (`gradio/hello_world`) | 200 |
| Model gated, métadonnées | 200 |
| Model gated, `/raw/main/README.md` sans token | 401 |
| Repo inexistant (`/api/models/...`, `/api/datasets/...`, `/api/spaces/...`) | 401 |

### 2.6 Limites de débit

**(doc : [hub/rate-limits](https://huggingface.co/docs/hub/rate-limits))** Trois compartiments, fenêtres fixes de 5 minutes :

| Plan | API (`/api/...`) | Resolvers (`/resolve/`) | Pages |
|---|---|---|---|
| Anonyme (par IP) | 500 | 3 000 | 100 |
| Compte gratuit | 1 000 | 5 000 | 200 |

- **Vérifié live** : en-tête `RateLimit: "api";r=490;t=269` et `RateLimit-Policy: "fixed window";"api";q=500;w=300` sur un appel anonyme ; cohérent avec le quota de 500 par 5 minutes.
- Dépassement : 429 ; la doc recommande de passer `HF_TOKEN` (« make sure you always pass a HF_TOKEN »).
- `huggingface_hub` >= 1.2.0 gère automatiquement le 429 (lecture du header `RateLimit`).
- Les chiffres sont indicatifs (« subject to change ») ; les limites des actions utilisateur ne sont pas documentées.

Note : le compartiment « Pages » est celui des pages web. Une lecture de README via `/raw/` compte probablement comme « Pages » ou « Resolvers » selon l'URL ; non vérifié.

---

## 3. Flux recommandé (une URL -> trois champs)

1. Identifier la plateforme (`github.com` ou `huggingface.co`) et le type (`datasets/`, `spaces/`, sinon model pour HF).
2. Extraire `{owner}/{repo}` ou `{namespace}/{name}` et retirer `.git`, sous-chemins, query string.
3. GitHub : `GET /repos/{o}/{r}` (titre = `full_name`, description, homepage, html_url), puis `GET /repos/{o}/{r}/readme` avec `Accept: application/vnd.github.raw+json`. Sur 404 du README, `readme = null`.
4. Hugging Face : `GET /api/{type}/{id}` (suivre les 307), puis `GET https://huggingface.co/{type-prefix}{id}/raw/main/README.md`. Titre et description selon 2.2.
5. Token : `Authorization: Bearer` avec `GITHUB_TOKEN` / `HF_TOKEN` quand disponible. Sans token, respecter 60/h (GitHub) et 500/5 min (HF).
6. États partiels : 401/403 HF (gated ou privé), 404 GitHub, README absent -> stocker ce qui est disponible et marquer l'état, sans faire échouer le traitement.
7. Clé d'indexation : l'identifiant canonique renvoyé par l'API (`full_name` ou `id`), pas l'URL saisie.

## 4. Points non vérifiés

- Comportement exact de `GET /repos/{o}/{r}` pour un dépôt renommé (301 documenté, redirection API non confirmée live).
- Comportement GitHub avec token sur dépôt privé sans accès (attendu 404, non testé).
- Cas « README absent » : 404 documenté, non reproduit live.
- Signatures complètes de `model_info`, `space_info`, `hf_hub_download` (non lues en entier).
- Le champ `description` des models et spaces : non trouvé dans les réponses testées ; un usage de `cardData` reste à valider.
- Limites de débit HF pour les endpoints `/raw/` (compartiment exact).
- Comportement `/resolve/` vs `/raw/` sur les dépôts gated : incohérence observée (voir 2.4), à clarifier avant usage.

## Sources

- GitHub, Get a repository : https://docs.github.com/en/rest/repos/repos#get-a-repository
- GitHub, Get a repository README : https://docs.github.com/en/rest/repos/contents#get-a-repository-readme
- GitHub, Rate limits : https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- GitHub, Getting started (en-têtes, User-Agent, raw) : https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api
- GitHub, Renaming a repository : https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository
- Hugging Face, Hub API (renvoie vers l'OpenAPI) : https://huggingface.co/docs/hub/api
- Hugging Face, OpenAPI (Markdown) : https://huggingface.co/.well-known/openapi.md
- Hugging Face, Rate limits : https://huggingface.co/docs/hub/rate-limits
- Hugging Face, Gated models : https://huggingface.co/docs/hub/models-gated
- Hugging Face, Getting started with repositories (formes d'URL de clone) : https://huggingface.co/docs/hub/repositories-getting-started
- huggingface_hub, HfApi (package reference) : https://huggingface.co/docs/huggingface_hub/package_reference/hf_api
- Vérifications live : `curl` sur les endpoints ci-dessus, 2026-11-24, sans token.
