# Faisabilité de la capture d'une transcription YouTube

- Ticket : MINLEGO/VeilleFacile#5 (`wayfinder:research`), parent #1
- Date de la recherche : 2026-11-24
- Périmètre : confirmer si une extension de navigateur peut obtenir la transcription d'une vidéo YouTube depuis une page de visionnage ouverte. Pas de conception d'extension ici.

## Question

Depuis une page YouTube ouverte dans le navigateur, une extension peut-elle obtenir la transcription ? Quelles voies existent (panneau DOM, données de la page, endpoints internes) ? Que se passe-t-il sans sous-titres ou avec sous-titres auto-générés ?

## Réponse courte

- **Oui, c'est faisable, mais fragile.** Aucune voie n'est documentée ni garantie par YouTube. Toutes reposent sur des éléments internes du site.
- **Voie la plus robuste aujourd'hui : le panneau de transcription affiché dans la page.** Un script peut cliquer sur « Afficher la transcription », attendre le panneau, puis lire les segments dans le DOM. C'est la méthode retenue par Firefox pour son extracteur intégré. Elle ne demande ni jeton ni appel réseau spécifique. Les sélecteurs CSS changent cependant régulièrement.
- **Voie directe `timedtext` : à ne pas considérer comme unique.** Les URL de sous-titres de la page peuvent exiger un PO token (jeton généré par le client). Dans ce cas, YouTube renvoie une réponse HTTP 200 vide. Un ticket ouvert le 2026-04-25 sur le projet `youtube-transcript-api` le confirme pour certaines vidéos.
- **Endpoint `youtubei/v1/get_transcript` : possible mais non documenté.** Il est utilisé par des projets tiers. Ses paramètres et sa version client changent sans préavis.
- **API officielle `captions.download` : inutilisable** pour ce besoin. Elle exige un droit d'édition sur la vidéo.
- **Vidéos sans sous-titres :** aucune transcription. Le panneau est absent ou vide, et les endpoints ne renvoient rien. Ce cas doit être géré explicitement.
- **Sous-titres auto-générés :** accessibles via les mêmes voies. Ils sont identifiés par `kind: "asr"` dans les pistes de sous-titres. Le panneau DOM ne fait pas cette distinction dans l'extracteur Firefox.

## Les voies d'accès

### 1. Panneau de transcription dans le DOM

Principe : le script ouvre le panneau puis lit les segments rendus.

Étapes observées dans l'extracteur Firefox (`YouTubeExtraction.sys.mjs`) :

1. Si un segment est déjà rendu, le lire sans toucher au panneau.
2. Sinon, cliquer sur le bouton de transcription. Sélecteurs essayés dans l'ordre : `ytd-video-description-transcript-section-renderer button`, puis `button[aria-label="Show transcript"]`, puis `button[aria-label="Transcript"]`.
3. Attendre l'apparition des segments avec un `MutationObserver`, avec un délai de 3 s (`OPEN_PANEL_TIMEOUT_MS`).
4. Lire les segments : `transcript-segment-view-model` (nouvelle structure) ou `ytd-transcript-segment-renderer` (ancienne structure). Les deux coexistent d'après le code source.
5. Refermer le panneau seulement si le script l'a ouvert lui-même.

Points d'attention :

- Les segments ne sont présents dans le DOM que lorsque le panneau est visible. Il faut donc l'ouvrir d'abord (source : fil de discussion Obsidian, février 2026, et code Firefox).
- Selon la mise en page, la transcription peut être fusionnée dans un panneau « Dans cette vidéo » sans identifiant spécifique.
- Un sélecteur fonctionnel en février 2026 ne l'était plus en mars 2026 selon le même fil. Les identifiants doivent être traités comme instables, avec plusieurs sélecteurs de repli.
- Si aucun bouton n'est trouvé, l'extracteur Firefox renvoie une liste vide. Il ne lève pas d'erreur.
- Avantage : pas d'appel réseau interne, donc pas de PO token ni de blocage IP lié aux requêtes.

### 2. `captionTracks` de la page, puis `timedtext`

La page de visionnage embarque les données du lecteur dans `ytInitialPlayerResponse`. Le chemin utile est `captions.playerCaptionsTracklistRenderer.captionTracks[]`, qui contient notamment `baseUrl`, `languageCode`, `vssId` et `kind` (`"asr"` pour l'auto-généré).

Le code de yt-dlp (`yt_dlp/extractor/youtube/_video.py`) construit les URL de sous-titres à partir de `baseUrl`, en ajoutant `fmt` (`json3`, `srv1` à `srv3`, `ttml`, `srt`, `vtt`). Il lit aussi la langue via `vssId`, avec repli sur `languageCode`.

Limites actuelles :

- **PO token.** La documentation de yt-dlp indique que le client `web` a besoin d'un PO token pour les sous-titres (colonne « Subs »). Les autres clients listés n'en ont pas besoin pour cette ressource. Le guide ne parle pas d'erreur 429 pour les sous-titres. Les pistes manuelles et auto-générées dans la langue originale ne sont pas distinguées par ce guide.
- **Réponse vide.** Le ticket `youtube-transcript-api#592` (ouvert le 2026-04-25) décrit des `baseUrl` contenant `&exp=xpe`. Pour ces URL, `timedtext` renvoie une réponse HTTP 200 au corps vide, même avec cookies de session. Le mainteneur n'a pas encore donné de correctif à la date de consultation. Selon le rapporteur, le jeton devrait être passé dans un paramètre `&pot=` généré à l'exécution, et non dans les cookies (affirmation du ticket, non vérifiée par ailleurs).
- **Blocage IP.** Depuis la version 1.1.1 de `youtube-transcript-api`, une réponse HTTP 429 sur `timedtext` lève une erreur `IpBlocked`. Le README indique que YouTube bloque la plupart des IP de fournisseurs cloud. Cela ne concerne pas une extension qui s'exécute dans le navigateur de l'utilisateur, mais un backend qui ferait les requêtes depuis un serveur.
- **Résultat attendu :** la solution la plus fiable pour `timedtext` est d'exécuter la requête depuis le contexte du navigateur de l'utilisateur. La condition de validité du PO token reste à vérifier au moment de l'implémentation.

### 3. `youtubei/v1/get_transcript`

C'est l'endpoint interne utilisé par le panneau de transcription. Il reçoit un corps JSON avec un contexte client et un paramètre `params`, qui est une chaîne protobuf encodée en base64 contenant l'ID vidéo, la langue et l'indicateur d'auto-génération.

- Invidious l'appelle via `YoutubeAPI.get_transcript(params)`, avec un paramètre généré par `Invidious::Videos::Transcript.generate_param(id, language_code, auto_generated)`. Le projet indique que cet endpoint n'est pas soumis aux mêmes limites de débit, et l'option est désactivée par défaut (source : commit `842e9fa` d'Invidious).
- Un gist ancien montre une clé API et une version client figées en 2021. Ces valeurs ne doivent pas être reprises telles quelles.
- **Non vérifié :** les paramètres actuellement attendus par le client web, et s'il exige aussi un PO token.

### 4. API officielle YouTube Data v3, `captions.download`

Non viable pour ce besoin. La méthode exige que l'utilisateur ait le droit de modifier la vidéo (erreur 403 sinon). Elle coûte 200 unités de quota par appel. Elle ne sert qu'aux pistes de ses propres vidéos.

Source : https://developers.google.com/youtube/v3/docs/captions/download

## Contraintes de l'extension (MV3)

Source : https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts et https://developer.chrome.com/docs/extensions/reference/api/scripting

- Un content script s'exécute par défaut dans un monde **isolé** (`ISOLATED`). Il ne voit pas les variables JavaScript de la page, donc pas `ytInitialPlayerResponse` directement.
- Il partage le DOM avec la page. Le contenu de `<script>` est donc lisible, et le DOM est accessible (lecture du panneau, clic sur le bouton).
- Pour lire une variable JavaScript de la page, il faut un script dans le monde **`MAIN`** (`world: "MAIN"` dans le manifeste ou `chrome.scripting`). La doc indique que `MAIN` partage l'environnement JavaScript de la page, sous réserve de la CSP de la page.
- Les requêtes réseau vers `youtube.com` depuis un content script sont soumises à CORS sous l'origine de la page. Une requête depuis le service worker avec les permissions d'hôte est une alternative. **Inférence non vérifiée dans les sources consultées.**

## Cas particuliers

- **Pas de sous-titres :** pas de bouton « Afficher la transcription » ou panneau vide (voie 1), `captionTracks` absent (voie 2). Aucun texte n'est disponible. L'extension doit distinguer « absent » et « échec technique ».
- **Auto-généré vs manuel :** dans `captionTracks`, `kind === "asr"` indique l'auto-génération. `youtube-transcript-api` préfère les transcriptions manuelles lorsque les deux existent dans la langue demandée, et expose `is_generated`.
- **Langues :** une piste par langue dans `captionTracks`. Les langues de traduction proposées sont listées dans `translationLanguages` (yt-dlp). Le paramètre de traduction côté `timedtext` n'a pas été vérifié dans les sources. Le choix de langue doit donc être explicite.
- **Vidéos restreintes ou live :** non étudié.

## Projets et extensions de référence

Les exemples suivants ont été repérés par recherche. Seul le premier point a été ouvert, les autres sont des résultats de recherche non vérifiés en détail. Aucun code n'a été téléchargé ni exécuté.

- **Firefox, `toolkit/components/pageextractor/YouTubeExtraction.sys.mjs`** (Mozilla, source officielle) : approche DOM décrite ci-dessus. Référence la plus fiable.
- **`jdepoix/youtube-transcript-api`** (Python, MIT) : bibliothèque qui utilise les pistes de sous-titres de la page. Le README avertit qu'elle utilise une partie non documentée de l'API YouTube. Référence utile pour les cas d'erreur (`TranscriptsDisabled`, `NoTranscriptFound`, `IpBlocked`), mais elle est côté serveur.
- **`yt-dlp`** : référence la plus complète sur les PO tokens pour les sous-titres. Source : `_video.py` et le PO Token Guide.
- **Extensions open source vues en recherche (non ouvertes) :** `ynlmz/ytcaptiongrabber` (MIT, dernier commit janvier 2025), `rishabhk571/youtube-transcript-pdf-exporter`, `atarantino/CaptionClip`, `Savecoders/YTranscripts` (MIT). Leur date de mise à jour et leur méthode sont à vérifier avant toute réutilisation.

## Risques

- **Conditions d'utilisation de YouTube.** Les CGU interdisent l'accès automatisé (robots, scrapers) sans autorisation écrite, sauf exceptions pour les moteurs de recherche. Une extension qui lit la page de l'utilisateur reste dans une zone grise. Un avis juridique est nécessaire avant une mise en production. Source : version régionale des CGU (`youtube.com/static?...template=terms`, mars 2025). La page canonique n'a pas pu être lue.
- **Fragilité.** Les sélecteurs DOM et les paramètres internes changent sans préavis. Il faut prévoir des tests de non-régression et une dégradation propre (« transcription indisponible »).
- **Blocage.** Des réponses vides ou 429 peuvent apparaître selon le client, le PO token ou l'IP.

## Recommandation pour la suite (sans concevoir l'extension)

1. Considérer la lecture du panneau DOM comme voie principale. Elle est la plus proche de ce que l'utilisateur voit et ne dépend pas d'un jeton.
2. Garder `captionTracks` + `timedtext` comme voie secondaire, avec gestion explicite des réponses vides.
3. Traiter « pas de transcription » comme un état normal, pas comme une erreur.
4. Décider avant implémentation de la position juridique (CGU) et de la tolérance aux pannes.

## Points non vérifiés

- Structure exacte actuelle de `ytInitialPlayerResponse` et des pistes `captionTracks` dans le client web en 2026. Sources : code de yt-dlp et d'Invidious, pas une vérification directe sur la page.
- Présence effective d'un PO token sur `timedtext` pour les pistes manuelles dans la langue originale. Le guide ne le précise pas.
- Paramètres actuels de `get_transcript` (client, version, protobuf).
- Comportement exact du panneau pour les vidéos sans sous-titres.
- Comportement d'un content script face à CORS pour `timedtext` (inférence).
- Contenu des extensions open source citées, non ouvertes.

## Sources

Primaires ou de référence :

- Chrome, content scripts : https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts
- Chrome, API scripting (`ExecutionWorld`) : https://developer.chrome.com/docs/extensions/reference/api/scripting
- YouTube Data API, `captions.download` : https://developers.google.com/youtube/v3/docs/captions/download
- Firefox, extracteur YouTube : https://searchfox.org/firefox-main/source/toolkit/components/pageextractor/YouTubeExtraction.sys.mjs
- yt-dlp, PO Token Guide : https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
- yt-dlp, extracteur YouTube (code) : https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/extractor/youtube/_video.py
- Invidious, commit `842e9fa` (`get_transcript`, `use_innertube_for_captions`) : https://github.com/iv-org/invidious/commit/842e9fade58414c606b8d97b5050c5f9c9ab77dd
- youtube-transcript-api, README : https://github.com/jdepoix/youtube-transcript-api
- youtube-transcript-api, ticket #592 : https://github.com/jdepoix/youtube-transcript-api/issues/592
- CGU YouTube (version régionale, mars 2025) : https://youtube.com/static?gl=FR&template=terms

Secondaires (résultats de recherche, non ouverts ou non primaires) :

- Gist `get_transcript` (ancien, constantes de 2021) : https://gist.github.com/MinePlayersPE/f645f15d477be694748df721492d8a38
- Fil Obsidian Web Clipper, février 2026 : https://forum.obsidian.md/t/web-clipper-youtube-video-transcript-for-yts-ui-feb-2026-update/111550
- Article DEV sur l'extraction via `captionTracks` : https://dev.to/mohduwaish59/i-built-a-chrome-extension-to-extract-youtube-transcripts-in-bulk-and-its-been-a-game-changer-59g9
- Extensions open source (non ouvertes) : https://github.com/ynlmz/ytcaptiongrabber, https://github.com/rishabhk571/youtube-transcript-pdf-exporter, https://github.com/atarantino/CaptionClip, https://github.com/Savecoders/YTranscripts
