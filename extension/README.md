# Extension Firefox VeilleFacile

Enregistre la page courante dans VeilleFacile en un clic (spec : issue #32). Un clic sur le bouton de la barre d'outils envoie l'onglet courant au backend (`POST /api/sources`) :

- GitHub et Hugging Face : l'URL seule (le backend récupère le README) ;
- YouTube `/watch` : titre et transcription lus dans le DOM ;
- page avec `citation_abstract` (arXiv `/abs/`, etc.) : l'abstract ;
- toute autre page : texte extrait par Readability.js.

Usage personnel. Firefox uniquement (MV3, JS simple, sans build). Le seul dossier empaqueté est `addon/`.

## Installation (`.xpi` signé)

1. Récupérer le `.xpi` signé (voir « Signature » pour le produire).
2. Dans Firefox, ouvrir le fichier (glisser-déposer dans une fenêtre, ou `about:addons` > engrenage > « Installer un module depuis un fichier »).
3. Accepter l'installation. Firefox affiche la collecte de données déclarée (contenu des sites web, activité de navigation) : c'est le contenu de la page envoyé à votre propre backend.

Un `.xpi` non signé est refusé par Firefox stable ; pour un test sans signature, utiliser le chargement temporaire ci-dessous.

## Configuration

1. Ouvrir les options : `about:addons` > VeilleFacile > Préférences.
2. Renseigner l'**URL du backend** (ex. `http://192.168.1.10:8000` ou `https://veille.example.com`) et la **clé API**.
3. Cliquer **Enregistrer** et accepter la demande de permission d'accès à l'hôte du backend. La permission porte sur `<schéma>://<hôte>/*` sans port (Firefox ignore les ports dans les motifs). Elle est demandée au clic sur le bouton.
4. Cliquer **Tester la connexion** : OK, clé refusée (401), backend injoignable ou permission absente.

Sans configuration ni permission, la popup affiche « Configurer l'extension ».

## Développement

Chargement temporaire :

1. `about:debugging` > Ce Firefox > Charger un module complémentaire temporaire.
2. Choisir `extension/addon/manifest.json`.
3. Recharger depuis la même page après chaque modification. L'extension disparaît à la fermeture de Firefox.

Tests (extracteurs et routage, `node --test` + jsdom) :

```
cd extension
npm install
npm test
```

Vérifications statiques : `npx web-ext lint --source-dir addon` (0 erreur attendue ; les avertissements `UNSAFE_VAR_ASSIGNMENT` viennent de `vendor/Readability.js`, copie non modifiée de `@mozilla/readability` 0.6.0, voir `addon/vendor/README`).

Les sélecteurs YouTube changent sans préavis : quand l'extraction casse, refaire les fixtures de `test/fixtures/` à partir de la nouvelle page (voir `docs/research/youtube-transcript-capture.md`).

## Signature (AMO, canal unlisted)

Firefox stable n'installe que des extensions signées par Mozilla. La signature *unlisted* est automatique et gratuite, sans publication sur le store.

1. Créer un compte sur addons.mozilla.org, puis générer des clés API (Outils pour développeurs > Gérer les clés API) : un *JWT issuer* et un *JWT secret*.
2. Les exposer en variables d'environnement (ne jamais les committer) :
   - bash : `export WEB_EXT_API_KEY=user:12345:67 WEB_EXT_API_SECRET=...`
   - PowerShell : `$env:WEB_EXT_API_KEY="user:12345:67"; $env:WEB_EXT_API_SECRET="..."`
3. Dans `addon/manifest.json`, **changer `browser_specific_settings.gecko.id`** (`veillefacile@minlego` est celui du dépôt d'origine ; prendre p. ex. `veillefacile@votre-nom`).
4. **Incrémenter `version`** : AMO refuse deux fois la même version pour un même id.
5. `cd extension && npm run sign` (= `web-ext sign --source-dir addon --channel=unlisted`).
6. Le `.xpi` signé est écrit dans `web-ext-artifacts/`. La validation automatique prend en général quelques secondes à quelques minutes. Si `web-ext` expire avant la fin, patienter puis relancer en incrémentant `version` (une version déjà soumise ne peut pas être renvoyée ; le `.xpi` éventuellement signé se télécharge aussi depuis le tableau de bord AMO).

Aucune minification ni bundler : pas de code source à fournir à AMO. `vendor/README` donne la version et l'origine de Readability.js, comme l'exige la revue.

## Liste de contrôle manuelle (Firefox stable)

À faire avec un `.xpi` signé (ou temporaire), après chaque changement notable.

### Permission et réseau

- [ ] Backend `http` du réseau local : options enregistrées (permission sans port), « Tester la connexion » = OK.
- [ ] Backend `https` : même vérification.
- [ ] Le `POST` avec `Authorization` vers un backend sans CORS réussit (envoi fait par le script d'arrière-plan).
- [ ] Mauvaise clé : « Clé API refusée » + bouton Ouvrir les options.
- [ ] Backend arrêté : « Backend injoignable à <URL> » + Réessayer.

### Pages (sur chaque backend)

- [ ] Dépôt GitHub : Source ajoutée (URL seule), titre, Résumé, Mots-clés.
- [ ] Article de blog : texte propre, paragraphes séparés, sans menu ni pied de page, date de publication si la page la donne.
- [ ] arXiv `/abs/` : abstract seul, vrai titre, date normalisée.
- [ ] YouTube `/watch` avec transcription : transcription complète, sans libellés de temps, panneau refermé ensuite.
- [ ] YouTube `/watch` sans transcription : enregistrée avec le titre seul, avertissement « sans transcription », description non envoyée.
- [ ] Après une navigation interne YouTube (clic sur une vidéo suggérée) : titre et date de la bonne vidéo.
- [ ] Une erreur : `about:blank` ou visionneuse PDF = « Page non capturable » ; Shorts ou accueil YouTube = « Page YouTube non prise en charge ».

### Comportement

- [ ] Fermer la popup pendant l'envoi : l'envoi continue, le badge passe de `…` à `✓` (ou `!`).
- [ ] Rouvrir la popup sur le même onglet : le dernier résultat s'affiche.
- [ ] Renvoyer une page déjà enregistrée : « Mise à jour ».
- [ ] Réessayer après une erreur : renvoie la même charge utile sans refaire l'extraction (sauf « Page pas encore chargée »).
- [ ] Vidéo très longue (~2 h, ~110 000 caractères de transcription) : acceptée.
