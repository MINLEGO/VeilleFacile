# Modèles OpenRouter gratuits : embeddings et résumé

- Issue : [MINLEGO/VeilleFacile#2](https://github.com/MINLEGO/VeilleFacile/issues/2) (label `wayfinder:research`)
- Date des constats : 2026-11-24
- Méthode : lecture des sources primaires d'OpenRouter (API `/api/v1/models`, `/api/v1/embeddings/models`, endpoints par modèle, pages modèles, documentation). Aucune inscription, aucune clé API, aucun appel d'inférence. Les pages NVIDIA ont été lues via le résumé de WebFetch, pas en texte brut.

## Réponse courte

- Les trois identifiants existent sur OpenRouter : `nvidia/nemotron-3.5-embed-8b:free`, `nvidia/nemotron-3.5-lightning:free`, `nvidia/nemotron-3.5-super-vl:free`.
- **Embeddings** : `nvidia/nemotron-3.5-embed-8b:free` renvoie des vecteurs de **4096 dimensions**, réductibles par troncature (exemples NVIDIA : 1024 et 512, puis renormalisation L2). Contexte de **32 768 tokens** par entrée : une transcription d'1 h (~15k tokens) tient en une seule entrée.
- **Résumé** : `nvidia/nemotron-3.5-lightning:free` (1M de contexte, texte seul) est le candidat naturel. Attention : son endpoint gratuit n'annonce pas `response_format`, donc le JSON structuré doit passer par le prompt ou par `tools`. `nvidia/nemotron-3.5-super-vl:free` (1M, multimodal, `structured_outputs` supporté) est plus lent et moins stable, et son multimodal n'est pas utile ici.
- **Quotas** : palier gratuit commun à tous les modèles `:free` : 20 requêtes/minute et **50 requêtes/jour tant que le compte a acheté moins de 10 crédits**, 1000/jour au-delà. C'est la vraie contrainte du projet, plus que le contexte.
- **Données** : sur les endpoints gratuits NVIDIA, l'usage est journalisé « à des fins de sécurité et pour améliorer les produits NVIDIA » (non lié à l'identité). À éviter pour des données confidentielles ou personnelles.
- **Dépréciation** : aucune date de fin annoncée, mais les trois modèles sont récents (sortis en août à octobre 2026) et n'ont qu'un seul fournisseur (NVIDIA). Aucune variante payante des modèles `embed` n'est listée sur OpenRouter : si le `:free` disparaît, il n'y a pas de repli OpenRouter direct.
- **Endpoint embeddings** : oui, `POST https://openrouter.ai/api/v1/embeddings` (format OpenAI-compatible, détails plus bas).

## 1. Existence des identifiants

| Identifiant demandé | Existe ? | Source |
|---|---|---|
| `nvidia/nemotron-3.5-embed-8b:free` | Oui (embedding, texte + image) | `/api/v1/embeddings/models` ; [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) |
| `nvidia/nemotron-3.5-lightning:free` | Oui (chat, texte seul) | `/api/v1/models` ; [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-lightning:free) |
| `nvidia/nemotron-3.5-super-vl:free` | Oui (chat, texte + image + vidéo) | `/api/v1/models` ; [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free) |

Les slugs sans `:free` des modèles `embed` (`nvidia/nemotron-3.5-embed-8b`) renvoient un endpoint vide dans `/api/v1/models/{slug}/endpoints` : seule la version gratuite est routable.

Voisins NVIDIA d'embedding également présents : `nvidia/nemotron-3.5-embed-1b:free` (2048 dimensions, 32k de contexte, [page](https://openrouter.ai/nvidia/nemotron-3.5-embed-1b:free)) et `nvidia/nemotron-3-embed-1b:free` (4096 de contexte seulement, texte seul, [page](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free)). Ce dernier est trop court pour une transcription d'1 h sans découpage.

## 2. Embeddings : `nvidia/nemotron-3.5-embed-8b:free`

| Critère | Valeur | Source |
|---|---|---|
| Dimension des vecteurs | 4096 par défaut | [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) ; [NVIDIA NIM, model card](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-embed-8b) |
| Réduction de dimension | Oui, par troncature de la fin du vecteur puis renormalisation L2 ; exemples 1024 et 512 | NVIDIA NIM model card (même source) |
| Paramètre `dimensions` côté OpenRouter | Non documenté ; `supported_parameters` vide. La troncature se fait donc côté client | `/api/v1/embeddings/models` ; [doc embeddings](https://openrouter.ai/docs/api/reference/embeddings) |
| Contexte par entrée | 32 768 tokens (affiché « 33K ») | [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) ; NVIDIA NIM : « max context length is 32,768 tokens » |
| Adéquation à 1 h de transcription (~15k tokens) | Oui, marge d'environ 2x. Pour la recherche hybride, découper quand même en segments reste préférable | Calcul à partir des deux valeurs ci-dessus |
| Entrées acceptées | Texte, et images / pages de document (asymétrique : requêtes en texte, documents texte ou image) | [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) ; NVIDIA NIM |
| Fournisseur | NVIDIA seul, latence P50 0,50 s, uptime 100 % sur 3 jours (disponibilité 99,92 %) | [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) |
| Date de sortie | 21 octobre 2026 | [page modèle](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free) |

Variante `nvidia/nemotron-3.5-embed-1b:free` : 2048 dimensions, même contexte 32k, mais espace vectoriel différent du 8B (voir section 6). Option de repli si le 8B est trop lourd ; le 8B reste le choix naturel ici, à condition de ne pas changer de modèle après indexation.

Point à valider avant de l'utiliser : la qualité après troncature (512 ou 1024 dimensions) n'est pas mesurée par les sources. NVIDIA recommande de valider la qualité de recherche avant de changer de taille.

## 3. Résumé : `nvidia/nemotron-3.5-lightning:free` et `nvidia/nemotron-3.5-super-vl:free`

| Critère | Lightning `:free` | Super VL `:free` | Source |
|---|---|---|---|
| Architecture | MoE 30B total, 3B actifs, texte seul | MoE 120B total, 12B actifs, texte + image + vidéo | pages modèles |
| Contexte | 1 000 000 tokens | 1 000 000 tokens | `/api/v1/models` |
| Sortie max | 65 536 tokens | 131 072 tokens | endpoints (`max_completion_tokens`) |
| Quantification | `nvfp4` | non renseignée (`unknown`) | endpoints |
| `response_format` / `structured_outputs` (endpoint gratuit) | **Non** (seulement `tools` et `tool_choice`) | Oui | endpoints |
| Uptime 30 min / 1 j | 100 % / 100 % | — / 98,75 % (40 % sur 5 min au moment de la lecture) | endpoints |
| Statut endpoint | `0` (OK) | `-2` au moment de la lecture (signification non documentée dans les sources lues) | endpoints |
| Raisonnement | Paramètre `reasoning` supporté | Raisonnement activé par défaut selon la page | pages modèles |

Conséquences :

- Une transcription d'1 h (~15k tokens) tient largement dans les deux modèles.
- Pour un JSON strict (résumé structuré + mots-clés), Super VL gratuit est le seul des deux à annoncer `structured_outputs`. Lightning gratuit exige un JSON contrôlé par le prompt, ou un appel d'outil (`tools`) avec un schéma.
- Le raisonnement étant actif par défaut sur Super VL, il consomme des tokens de sortie : prévoir un `max_tokens` large ou désactiver le raisonnement via `reasoning` si ce n'est pas voulu.

Alternatives gratuites avec `json_schema` et `tools` (texte, contexte >= 256k), vérifiées dans `/api/v1/models` mais leurs politiques de données **non vérifiées** ici : `google/gemma-4-31b-it:free` (262k), `google/gemma-4-26b-a4b-it:free` (262k), `inclusionai/ling-3.2-flash:free` (1M), `baidu/ernie-5.5-flash-preview:free` (1,02M).

## 4. Limites de débit (palier gratuit)

Source : [doc limites](https://openrouter.ai/docs/api/reference/limits).

| Crédits achetés (cumul) | Requêtes/minute (modèles `:free`) | Requêtes/jour (modèles `:free`) |
|---|---|---|
| Moins de 10 | 20 | 50 |
| Au moins 10 | 20 | 1000 |

- Les limites s'appliquent à l'ensemble du compte pour les modèles `:free` (le compteur `free_model_daily_requests` de `GET /api/v1/key` est unique). Les doubles comptes ou clés ne contournent pas la limite (« we govern capacity globally »).
- La page limites ne donne pas de quota propre aux embeddings ; elle ne mentionne pas les embeddings. Les pages modèles renvoient vers ces limites (« Free endpoints are rate limited »). Une requête d'embedding compte probablement comme une requête, donc **envoyer plusieurs segments dans un seul appel `input` (tableau)** réduit fortement la consommation du quota journalier. La taille maximale d'un tableau n'est pas documentée : à tester.
- Dépassement : HTTP 429 avec `error_type: rate_limit_exceeded`, en-têtes `X-RateLimit-*` et `Retry-After` parfois présents. Backoff exponentiel recommandé.
- Conséquence concrète : avec moins de 10 crédits, 50 appels/jour suffisent pour des résumés de quelques dizaines de sources, mais pas pour une réindexation complète. Au-delà de 10 crédits achetés, la limite passe à 1000/jour. Cet achat est une décision à prendre par l'utilisateur, non effectuée ici.

## 5. Politique de données et de journalisation

Deux niveaux à distinguer.

**OpenRouter (plateforme)** : source [politique de collecte](https://openrouter.ai/docs/guides/privacy/data-collection).

- OpenRouter ne stocke pas les prompts ni les réponses par défaut. Les options « logs privés » et « amélioration du produit » sont désactivées par défaut.
- Certains endpoints « Safety Retention » peuvent conserver prompts et réponses pour la sécurité (pas pour l'entraînement). Le filtre « ZDR only » les exclut.
- OpenRouter dit n'avoir jamais vendu ni concédé de licence sur les données de prompt.
- Le paramètre de routage `provider.data_collection: "deny"` (cité dans la doc embeddings) permet d'exclure les fournisseurs susceptibles d'entraîner sur les données. **Non vérifié** : je ne sais pas si le fournisseur NVIDIA gratuit est exclu par ce filtre. Si oui, les appels échoueraient avec ce réglage.

**NVIDIA (endpoints gratuits)** : mention identique sur les pages des trois modèles :

> « For the free endpoint, please do not upload any confidential information or personal data [...] Your use is logged for security purposes and to improve NVIDIA products and services. The logged session data for improvement purposes is not linked to your identity or any persistent identifier. »

Traduction : les requêtes sur les endpoints gratuits sont journalisées et réutilisées pour améliorer les produits NVIDIA. Aucune donnée personnelle ni confidentielle ne doit y être envoyée. Pour une veille sur du contenu public (transcriptions YouTube, README GitHub/HF, articles), le risque est faible, mais le contenu envoyé pour le résumé doit rester public.

## 6. Dépréciation et stabilité

- Aucun des trois modèles n'a de `expiration_date` renseignée dans `/api/v1/models` au 2026-11-24. OpenRouter renseigne ce champ quand une fin de vie est connue (exemple observé : `nvidia/nemotron-3.5-content-safety`, fin prévue le 2026-11-30).
- Dates de sortie : Lightning 11 août 2026, Super VL 15 octobre 2026, Embed 8B 21 octobre 2026. Ce sont des modèles très récents.
- Concentration : un seul fournisseur (NVIDIA) pour les trois. Pas de repli automatique sur un autre hébergeur.
- Pas de variante payante des `embed` NVIDIA sur OpenRouter (voir section 1). Si le gratuit disparaît, il faudra changer de modèle, donc re-indexer tous les vecteurs (espace vectoriel différent).
- Espaces vectoriels : d'après les pages modèles, `nemotron-3.5-embed-8b` partage l'espace texte de `nemotron-3-embed-8b`, et `nemotron-3.5-embed-1b` celui de `nemotron-3-embed-1b`. Le 8B et le 1B ont donc des espaces différents : ne jamais mélanger leurs vecteurs dans un même index.

## 7. Endpoint embeddings OpenRouter

Source : [doc embeddings](https://openrouter.ai/docs/api/reference/embeddings).

Requête :

- `POST https://openrouter.ai/api/v1/embeddings`
- Corps : `model` (obligatoire), `input` (obligatoire : chaîne, tableau de chaînes, ou objets multimodaux `{content: [{type: "text"|"image_url", ...}]}`), `input_type` (optionnel : `"document"` ou `"query"`), `encoding_format` (optionnel, seul `"float"` est montré dans les exemples), `provider` (routage : `order`, `allow_fallbacks`, `data_collection`).
- `dimensions` n'est pas documenté.

Réponse :

```json
{
  "object": "list",
  "model": "...",
  "data": [{ "object": "embedding", "index": 0, "embedding": [0.0, "..."] }],
  "usage": { "prompt_tokens": 0, "total_tokens": 0 }
}
```

- Codes d'erreur documentés : 400, 401, 402, 404, 429, 529.
- Pas de streaming. Identiques entrées = sorties identiques (affirmation de la doc).
- `input_type` : pertinent pour l'asymétrie requête / document. Pour le modèle NVIDIA, l'usage exact de `input_type` n'est pas détaillé dans les sources lues : à confirmer.

## 8. Alternatives et recommandations

Si le modèle gratuit est indisponible ou trop contraint, les alternatives d'embedding (prix et contexte relevés dans `/api/v1/embeddings/models`) :

| Modèle | Contexte | Prix (USD / 1M tokens entrée) | Remarque |
|---|---|---|---|
| `qwen/qwen3-embedding-8b` | 40 960 | 0,01 | Contexte le plus long, bon candidat payant quasi gratuit |
| `qwen/qwen3-embedding-4b` | 32 768 | 0,02 | Même contexte que le 8B NVIDIA |
| `baai/bge-m3` | 8 194 | 0,01 | Multilingue, 1024 dimensions (description du modèle) |
| `openai/text-embedding-3-small` | 8 192 | 0,02 | 1536 dimensions (exemple de la doc embeddings) |
| `google/gemini-embedding-001` | 20 000 | 0,15 | Contexte limité pour 15k tokens |

Un volume d'une centaine de transcriptions d'1 h (~1,5M de tokens) coûte moins d'un centime avec `qwen/qwen3-embedding-8b`. Un modèle payant peut donc être plus pratique que le quota gratuit de 50 requêtes/jour.

Pour le résumé, si le JSON strict est critique et que Lightning gratuit ne l'accepte pas : Super VL gratuit, ou un modèle de la liste gratuite de la section 3 qui annonce `json_schema`.

Recommandation (à valider par l'utilisateur) :

1. Embeddings : `nvidia/nemotron-3.5-embed-8b:free`, tronqué à 1024 ou 512 dimensions si l'index le demande, en regroupant plusieurs segments par appel. Tester la qualité de recherche après troncature.
2. Résumé : `nvidia/nemotron-3.5-lightning:free` avec JSON contrôlé par le prompt ou un outil ; repli `nvidia/nemotron-3.5-super-vl:free` si `structured_outputs` est indispensable.
3. Acheter 10 crédits fait passer la limite de 50 à 1000 requêtes/jour : décision de l'utilisateur.
4. Garder un modèle payant de repli (`qwen/qwen3-embedding-8b`) prêt, en sachant qu'il change l'espace vectoriel.

## 9. Points non vérifiés

- Appel réel à l'API : aucun appel d'inférence ni de clé (conformément à la consigne). Le format de réponse et la taille maximale d'un tableau `input` ne sont pas testés.
- Comportement de `data_collection: "deny"` avec le fournisseur NVIDIA gratuit : inconnu.
- Qualité de récupération après troncature à 512 ou 1024 dimensions : non mesurée.
- Signification du statut `-2` sur l'endpoint Super VL : non documentée dans les sources lues.
- Politiques de données des modèles gratuits non NVIDIA (Gemma, Ling, Ernie) : non vérifiées.
- Page NVIDIA build.nvidia.com (model card) : non lisible via WebFetch (contenu de navigation seulement). Les caractéristiques d'embedding viennent de la page NIM `docs.api.nvidia.com` (résumé WebFetch) et de la page modèle OpenRouter.

## Sources

- API modèles OpenRouter : https://openrouter.ai/api/v1/models (JSON, consulté 2026-11-24)
- API modèles d'embedding : https://openrouter.ai/api/v1/embeddings/models
- Endpoints par modèle : https://openrouter.ai/api/v1/models/nvidia/nemotron-3.5-lightning:free/endpoints ; https://openrouter.ai/api/v1/models/nvidia/nemotron-3.5-super-vl:free/endpoints ; https://openrouter.ai/api/v1/models/nvidia/nemotron-3.5-embed-8b-20261021/endpoints
- Pages modèles : https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free ; https://openrouter.ai/nvidia/nemotron-3.5-embed-1b:free ; https://openrouter.ai/nvidia/nemotron-3-embed-1b:free ; https://openrouter.ai/nvidia/nemotron-3.5-lightning:free ; https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free
- Documentation embeddings : https://openrouter.ai/docs/api/reference/embeddings
- Documentation limites de débit : https://openrouter.ai/docs/api/reference/limits
- Documentation collecte de données : https://openrouter.ai/docs/guides/privacy/data-collection
- NVIDIA NIM, model card Nemotron 3.5 Embed 8B : https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-embed-8b
