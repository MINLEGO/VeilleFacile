# Extension Firefox VeilleFacile

Enregistre la page courante dans VeilleFacile en un clic (voir l'issue #32).

## Chargement temporaire

1. `about:debugging` > Ce Firefox > Charger un module complémentaire temporaire.
2. Choisir `extension/addon/manifest.json`.
3. Ouvrir les options de l'extension : URL du backend et clé API, puis Enregistrer (accepter la permission d'hôte) et Tester la connexion.

## Tests

```
cd extension
npm install
npm test
```
