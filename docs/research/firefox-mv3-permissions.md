# Firefox MV3 : permissions d'hôte, CORS et signature unlisted

- Ticket : MINLEGO/VeilleFacile#27 (`wayfinder:research`), parent #26
- Date de la recherche : 2026-11-25
- Périmètre : permissions d'hôte pour une URL de backend saisie par l'utilisateur, CORS, injection de script au clic sur la barre d'outils, signature unlisted sur AMO. Pas de conception d'extension ici.

## Réponse courte

1. **Permission d'hôte.** Déclarer `optional_host_permissions: ["*://*/*"]` (ou `<all_urls>`), puis appeler `browser.permissions.request({origins: [...]})` depuis un gestionnaire de clic de la page d'options. **Piège majeur : Firefox ne gère pas les ports dans les motifs.** Un motif avec port (`http://nas:8000/*`) est ignoré et la permission ne produit aucun effet. Il faut demander `http://nas/*` (sans port), qui couvre tous les ports de cet hôte.
2. **CORS.** Avec la permission accordée (motif correct), `fetch` depuis une page d'extension (popup, options, background) n'est pas soumis au CORS. **Pas de `CORSMiddleware` nécessaire.** Les content scripts MV3, eux, restent soumis au CORS de la page : le `fetch` doit donc partir du background ou de la popup, pas du script injecté. L'en-tête `Origin` envoyé est probablement `moz-extension://<uuid>` (déduit, non confirmé par une source primaire) ; le backend ne doit pas s'en servir pour l'authentification, la clé Bearer suffit.
3. **Injection.** `permissions: ["activeTab", "scripting"]` suffit. Le clic sur le bouton de barre d'outils accorde `activeTab` sur l'onglet courant ; `scripting.executeScript({target:{tabId}, func})` renvoie un tableau d'`InjectionResult` dont `result` contient la valeur retournée (structured clone, Promise attendue).
4. **Signature unlisted.** `web-ext sign --channel=unlisted --api-key=... --api-secret=...` (clés JWT créées sur AMO). `browser_specific_settings.gecko.id` est obligatoire en MV3, et `data_collection_permissions` l'est pour toute nouvelle extension depuis le 2025-11-03. Pas de code source à fournir si rien n'est minifié ni compilé ; une bibliothèque vendored doit être identique à la version officielle publiée. Délai annoncé : jusqu'à 24 h, `web-ext` attend 15 min par défaut.

## 1. Permission d'hôte pour une origine saisie par l'utilisateur

### Ce que dit la documentation

- `optional_host_permissions` (MV3 uniquement) sert aux « requêtes d'accès à l'exécution », accordées par l'utilisateur après l'installation. On les demande avec l'API `permissions`, ce qui peut afficher une boîte de dialogue. L'utilisateur peut les accorder ou retirer dans l'onglet Permissions du gestionnaire de modules. (MDN, `manifest.json/optional_host_permissions`.)
- `host_permissions` : « most browsers treat `host_permissions` as optional » car l'utilisateur peut les accorder ou révoquer à tout moment. À partir de Firefox 127, ces permissions s'affichent dans l'invite d'installation ; celles ajoutées lors d'une mise à jour ne sont pas montrées (bug 1893232). Il faut donc vérifier avec `permissions.contains` puis demander avec `permissions.request`. (MDN, `manifest.json/host_permissions`.)
- Nuance : la page MDN `activeTab` écrit que Firefox et Chrome accordent les `host_permissions` demandées à l'installation. Les deux pages ne disent pas exactement la même chose ; dans tous les cas l'utilisateur peut les révoquer, donc le code doit tester la présence avant chaque usage.
- `permissions.request()` : appel autorisé seulement dans un gestionnaire d'action utilisateur ; renvoie une `Promise<boolean>` ; une seule demande pour l'ensemble, tout ou rien. Les origines demandées doivent être couvertes par les permissions optionnelles du manifeste (la page cite `optional_permissions`, mais en MV3 ce sont `optional_host_permissions`). Les permissions accordées survivent aux mises à jour et à la désactivation/réactivation. (MDN, `API/permissions/request`.) Les pages options et popup ne sont pas mentionnées explicitement ; un clic de bouton y compte comme action utilisateur.

### Syntaxe des motifs

Forme `<schéma>://<hôte><chemin>` ; le chemin est obligatoire (`https://exemple.org` est invalide, `https://exemple.org/*` est valide). `*://*/*` couvre http, https, ws et wss ; `*.exemple.org` couvre le domaine et ses sous-domaines ; le joker n'est autorisé qu'en début d'hôte. (MDN, Match patterns.)

### Le piège du port

- MDN : « Firefox doesn't support the inclusion of a port number » dans les motifs (bugs 1362809 et 1468162).
- Bug 1362809 (ouvert, statut NEW, dernière modification 2026-08-02) : « URLs with ports should either be rejected as "matches" patterns, or be matched properly ». Un commentaire indique qu'un motif avec port est ignoré et que `http://localhost:1234` correspond à `http://localhost/*`.
- Bug 2052000 (fermé en doublon du 1362809, Firefox 152 à 154 touchés) : un `fetch` du background vers un NAS du réseau local reste bloqué par le CORS quand la permission est accordée avec un port. Avec le motif sans port, la même réponse devient lisible. La permission apparaît pourtant comme active dans `permissions.getAll()` et dans about:addons, ce qui rend le défaut difficile à diagnostiquer.

Conséquence pour la page d'options : convertir l'URL saisie en `schéma://hôte/*` en retirant le port avant `permissions.request`. Le `fetch` utilise ensuite l'URL complète, port compris.

### Schéma d'implémentation

```json
{
  "manifest_version": 3,
  "optional_host_permissions": ["*://*/*"],
  "options_ui": { "page": "options.html" }
}
```

```js
// options.js, dans le gestionnaire de clic du bouton « Enregistrer »
const u = new URL(input.value);
const origins = [`${u.protocol}//${u.hostname}/*`]; // sans port
if (!(await browser.permissions.contains({ origins }))) {
  const ok = await browser.permissions.request({ origins });
  if (!ok) { /* afficher : permission refusée */ }
}
```

Le motif large dans `optional_host_permissions` est nécessaire car le domaine est inconnu à l'avance ; l'invite ne présente que l'origine réellement demandée. Un schéma `http` en clair reste possible si le backend n'est pas en HTTPS.

## 2. CORS et en-tête `Origin`

- MDN (Content scripts) : en MV3 sous Firefox 101 et suivants, les content scripts sont soumis à la même politique CORS que la page ; « Only backend scripts have elevated cross-domain privileges ». Les permissions d'hôte « don't work in content scripts, but they still do in regular extension pages ».
- MDN (`host_permissions`) : une extension obtient « XMLHttpRequest and fetch access to those origins without cross-origin restrictions, but not for requests from content scripts ».
- Bug 1796977 (fermé INVALID) : un `fetch` du background échouait faute d'entrée correcte dans les permissions ; Rob Wu précise que la déclaration est requise et que ce n'est pas un défaut de Firefox.
- Bug 1722703 : depuis Firefox 92, les requêtes d'une extension ayant accès au site cible portent `Sec-Fetch-Site: same-origin`.
- Bug 1605197 (ouvert) : un content script sans permission d'hôte n'envoie pas d'`Origin` et échoue en CORS. Raison de plus pour poster depuis le background.
- `Origin` : le fil Discourse 129856 indique que `fetch()` en POST depuis un background envoie l'en-tête `Origin` par défaut, et le code de l'échange teste une valeur commençant par `moz-extension`. Aucune source primaire consultée ne donne la valeur exacte ; supposer `moz-extension://<uuid-par-profil>` (l'UUID change d'un profil à l'autre) et ne pas la figer côté serveur.

Conclusion : le backend n'a pas besoin de `CORSMiddleware` pour une extension qui poste depuis le background ou la popup avec une permission valide (sans port). Les requêtes à en-tête `Authorization` déclenchent normalement un préchauffage CORS, mais l'accès accordé par la permission lève la contrainte. Ne pas ajouter de CORS « au cas où » : il faudrait l'ouvrir à `moz-extension://*`, ce qui élargit la surface sans bénéfice.

À tester à l'implémentation : un `fetch` POST JSON avec `Authorization: Bearer` vers un hôte sans en-têtes CORS, avec et sans port dans le motif demandé.

## 3. Lire le DOM de l'onglet courant au clic

Permissions minimales : `["activeTab", "scripting"]`, aucun motif d'hôte.

- `activeTab` (MDN, activeTab permission) : accordée silencieusement lors d'une action utilisateur (clic sur le bouton de barre d'outils, menu contextuel, raccourci clavier). Elle permet d'injecter du JavaScript via l'API `scripting`, et de lire `url`, `title` et `favIconUrl` de l'onglet sans la permission `tabs`. Elle seule ne suffit pas : `scripting` est requis.
- Durée : la fermeture de l'onglet la révoque ; en Firefox, toute navigation vers un nouveau document la termine, mais les changements de fragment et `pushState` la conservent. L'accès est limité à l'onglet actif, au document de premier niveau et aux iframes de même origine.
- Pages interdites : vue lecteur, view-source, visionneuse PDF, interface du navigateur ; les restrictions de sites (AMO notamment) s'appliquent. Prévoir un message d'erreur.
- `scripting.executeScript` (MDN) : `target` obligatoire, `files` ou `func` (pas les deux), `args` sérialisables JSON avec `func`. Renvoie une `Promise` d'un tableau d'`InjectionResult` (`frameId`, `documentId`, `result`, `error`), un par frame. La `Promise` est rejetée si l'injection échoue ; si le script lui-même lève une exception, elle est résolue et l'erreur se trouve dans `error`. `result` est la dernière valeur évaluée, une `Promise` finale est attendue. Firefox exige un résultat clonable par structured clone.
- Si on utilise `default_popup`, l'ouverture de la popup est aussi un clic sur le bouton d'action. Avec `action.onClicked`, il ne faut pas de popup.

Schéma : le background (ou la popup) appelle `executeScript` avec `files: ["vendor/Readability.js", "extract.js"]` ; `extract.js` termine par l'expression qui renvoie `{url, title, html, article}` ; le background poste le résultat vers `<backend>/api/sources`. Sans motif d'hôte, `tab.url` reste lisible grâce à `activeTab`.

## 4. Signature unlisted sur AMO

### Procédure

- Toute extension doit être signée par Mozilla pour s'installer dans Firefox release et beta. Les modules « unlisted » (autodistribués) ne sont ni visibles ni installables depuis AMO. (Extension Workshop, Signing and distribution overview.)
- Voies pour l'unlisted : le Developer Hub (envoi web), `web-ext sign` (v8 et suivantes : première soumission et mises à jour), les API Add-on Create / Version Create V5. (Même page.)
- `web-ext sign` : `--channel` obligatoire (`unlisted` pour l'autodistribution), `--api-key` et `--api-secret` (émetteur et secret JWT AMO, variables `WEB_EXT_API_KEY` et `WEB_EXT_API_SECRET`), `--approval-timeout` (15 min par défaut, 0 pour ne pas attendre), `--upload-source-code`, `--source-dir`, `--artifacts-dir` (par défaut `./web-ext-artifacts`, où est écrit le `.xpi` signé), `--ignore-files`. `--amo-metadata` n'est exigé que pour une première version listée. (Extension Workshop, web-ext command reference.)
- Les clés API se génèrent sur le Developer Hub AMO (page des identifiants d'API) ; cette étape n'a pas été relue ici sur une page dédiée. Ne pas commiter les clés.

### Exigences

- `browser_specific_settings.gecko.id` : requis en MV3 pour signer ; AMO n'en attribue pas. Format : chaîne `@nom.auteur` de 80 caractères au plus (`^[a-zA-Z0-9-._]*@[a-zA-Z0-9-._]+$`) ou GUID entre accolades. L'unicité est vérifiée à la première signature. (MDN, `browser_specific_settings`.)
- `gecko.data_collection_permissions` : requis pour les nouvelles extensions soumises à AMO depuis le 2025-11-03 ; `{"required": ["none"]}` si rien n'est collecté. Ici l'extension envoie la page à un backend choisi par l'utilisateur, vérifier quelle catégorie (`websiteContent` par exemple) déclarer : à trancher dans le ticket d'implémentation.
- Code source : à fournir uniquement si l'extension est générée par un minificateur, un bundler, un moteur de gabarits ou tout outil de pré-traitement. Le code obfusqué est interdit. Sans étape de build, rien à envoyer. (Extension Workshop, Source code submission.)
- Bibliothèques tierces : le fichier doit être identique à la distribution officielle (les vérifications portent sur des sommes de contrôle, un espace modifié suffit à faire échouer) ; le télécharger depuis le site officiel ou npm, pas depuis un CDN ; viser une version publiée précise ; indiquer dans « Notes for Reviewers » le lien vers l'original et vers la source lisible. Un fichier `.min.js` officiel est accepté. (Extension Workshop, Third-party library usage.) Pour Readability.js : copier le fichier de la version publiée sans le modifier, et noter la version et l'URL dans un `extension/vendor/README`.
- Tous les envois, unlisted compris, sont soumis aux règles du programme de modules et à l'accord de distribution.

### Délais

- Validation automatique pour chaque envoi ; « up to 24 hours » avant signature et publication. Un examen manuel est possible à tout moment après coup, avec risque de rejet ou de blocage d'une version. (Extension Workshop, Signing and distribution overview.)
- Par défaut `web-ext sign` attend 15 minutes la signature ; au-delà, relancer avec `--approval-timeout` plus long ou récupérer le fichier sur le Developer Hub.
- Non vérifié ici : le comportement concret pour une extension unlisted perso (en général quelques minutes selon l'expérience courante, sans source citée) et l'obligation d'incrémenter `version` à chaque soumission (comportement connu d'AMO, pas relu dans les pages consultées).

## Points ouverts pour l'implémentation (#29)

- Tester sur Firefox stable : permission demandée sans port, `fetch` POST avec `Authorization` vers un backend sans CORS, hôte `http` du réseau local et hôte `https`.
- Le motif sans port couvre tous les ports de l'hôte ; accepter ce périmètre.
- Choisir la déclaration `data_collection_permissions` adaptée.
- Si le bug 1362809 est corrigé un jour, le comportement avec port changera ; garder la conversion tolérante.

## Sources

- MDN : `manifest.json/optional_host_permissions`, `manifest.json/host_permissions`, `manifest.json/permissions`, `manifest.json/browser_specific_settings`, `API/permissions/request`, `API/scripting/executeScript`, `activeTab_permission`, `Match_patterns`, `Content_scripts`.
- Extension Workshop : Signing and distribution overview, web-ext command reference, Source code submission, Third-party library usage, Extensions and the add-on ID.
- Bugzilla : 1362809, 1468162, 2052000, 1796977, 1722703, 1605197. Discourse Mozilla : « Choosing Origin header from background script » (129856).
