# Glossary

Le code est en anglais ; chaque terme indique son nom dans le code.

**Source**: un contenu en ligne enregistré pour pouvoir être retrouvé plus tard (vidéo YouTube, dépôt GitHub ou Hugging Face, article de blog). Elle est identifiée par son URL canonique et porte un titre, un Site d'origine, un Résumé, des Mots-clés et son Texte intégral.
_Code_: `source`
_Avoid_: document, ressource, item

**URL canonique**: la forme normalisée de l'URL d'une Source. Deux URL qui désignent le même contenu (lien court, paramètres de suivi, sous-page d'un même dépôt) ont la même URL canonique, si bien qu'une Source ne peut pas exister en double.
_Code_: `canonical_url`

**Site d'origine**: la plateforme ou le domaine d'où vient une Source (youtube.com, github.com, huggingface.co, le domaine d'un blog).
_Code_: `origin_site`

**Résumé**: un texte court qui couvre les enjeux et l'intérêt principal d'une Source, assez précis pour décider si elle mérite d'être rouverte.
_Code_: `summary`

**Mots-clés**: des termes attachés à une Source, surtout des noms propres (outils, modèles, auteurs), qui la rendent trouvable même quand la recherche par le sens échoue. Ils peuvent être générés ou ajoutés à la main.
_Code_: `keywords` (générés : `generated_keywords`, manuels : `manual_keywords`)

**Mot-clé rejeté**: un Mot-clé généré que l'utilisateur a retiré d'une Source. Il n'y réapparaît pas quand la Source est mise à jour.
_Code_: `rejected_keywords`

**Texte intégral**: le contenu brut d'une Source (transcription, README, texte de l'article). Il est conservé, mais il ne sert pas forcément à la recherche.
_Code_: `full_text`

**Capture**: le fait d'envoyer au service une Source avec son Texte intégral déjà extrait par l'appelant (par exemple par l'extension web).
_Code_: `capture`

**Récupération par URL**: le fait de n'envoyer que l'URL d'une Source et de laisser le service aller chercher le Texte intégral. Elle est limitée à GitHub et Hugging Face.
_Code_: `fetch`
