# WME DiaLog

Userscript pour l'[éditeur de cartes Waze](https://www.waze.com/editor) : affiche
sur la carte les **arrêtés de circulation permanents** issus de
[DiaLog](https://dialog.beta.gouv.fr), la base nationale des arrêtés de
circulation (DGITM), avec leur géométrie réelle.

Objectif : donner aux éditeurs la réglementation permanente — limitations de
vitesse, zones 30, interdictions d'accès — qui n'atteint aujourd'hui la carte
par aucun canal. L'export CIFS de DiaLog ne transmet à Waze que les fermetures
temporaires ; tout le permanent n'existe qu'en DATEX II.

## Installation

1. Installer [Tampermonkey](https://www.tampermonkey.net/)
2. Ouvrir [`WME-DiaLog.user.js`](WME-DiaLog.user.js) et confirmer l'installation
3. Recharger l'éditeur Waze

## Utilisation

Un bouton apparaît dans la barre de boutons de la carte, avec le nombre de
mesures à traiter dans la vue élargie de 10 km.

- Le département de la vue est téléchargé automatiquement à la première
  approche. L'avancement s'affiche en anneau autour du bouton.
- Un clic sur le bouton ouvre le panneau ; un clic sur une ligne cadre la carte
  sur la géométrie de l'arrêté.
- Filtres : type de mesure, à vérifier, restrictions horaires, sauf riverains.

Les données sont mises en cache 7 jours dans le navigateur, par département.

## Périmètre

Seules sont retenues les mesures qui **concernent les véhicules de tourisme, les
taxis et les motos** — le périmètre de Waze. Sont donc écartées toutes les
restrictions bornées par un gabarit (poids, hauteur, largeur, longueur) et
toutes les catégories étrangères à ces usages (poids lourds, autocars, engins
agricoles, matières dangereuses, camping-cars). Le stationnement est également
hors périmètre.

Sur les 10 520 mesures exploitables de DiaLog, **7 507 sont retenues** :
6 837 limitations de vitesse et 670 interdictions d'accès.

### Points de vigilance signalés dans le panneau

- **restriction horaire** : la mesure ne s'applique pas en permanence, elle ne
  doit pas être appliquée comme telle ;
- **vitesse inhabituelle** : valeur hors des vitesses réglementaires usuelles ;
- **géométrie ponctuelle** : la localisation n'est pas un tronçon.

## Données

Le dossier [`docs/`](docs/) contient un fichier par département, régénéré par
[`outils/export_departements.py`](outils/export_departements.py) depuis l'API
publique de DiaLog. `docs/index.json` porte, pour chaque département, l'emprise
réelle de ses données — c'est ce qui permet au script de savoir quoi charger
sans interroger le moindre service tiers.

Ces fichiers sont pré-générés parce que **l'API DiaLog n'offre aucun filtre
géographique exploitable** : son paramètre `inseeCode` renvoie zéro résultat
quelle que soit sa valeur, et un chargement intégral demande plus de dix minutes.

## Source et attribution

Données produites par **DiaLog** (Direction générale des infrastructures, des
transports et des mobilités), <https://dialog.beta.gouv.fr>.
Les fichiers de ce dépôt en sont un **dérivé filtré et allégé** : ils ne font pas
autorité, l'arrêté publié par la collectivité reste la seule référence.

> ⚠️ Avant toute diffusion large, vérifier la licence applicable aux données
> DiaLog et reprendre ici la mention exacte qu'elle impose.

## Licence

Le code du userscript est publié sous licence MIT. Les données relèvent de la
licence de leur producteur (voir ci-dessus).
