# Registre des expérimentations

Ce dossier est alimenté automatiquement : chaque extraction d'un DRD à
partir d'un modèle BPMN y ajoute **une ligne**, que l'extraction soit lancée
par la ligne de commande (`python cli.py transformer …`, `python cli.py
valider …`), par l'application web (bouton « Extraire DRD », y compris après
arbitrage) ou par le catalogue de patterns. La table est le résumé de toutes
les expérimentations ; les analyses et projections se font à partir d'elle.

## Fichiers

| Fichier | Contenu |
|---|---|
| `registre.csv` | La table, une ligne par expérimentation (séparateur « ; », UTF-8, point décimal). C'est la source de vérité. |
| `registre.xlsx` | Le même contenu en classeur Excel, régénéré à chaque ligne : feuille « Expérimentations » (en-tête figé, filtre automatique), feuille « Synthèse » (nombre, moyenne, minimum, maximum, somme de chaque grandeur), feuille « Dictionnaire » (définition de chaque colonne), feuille « Campagnes » si des campagnes massives ont été consignées. |
| `campagnes.csv` | Une ligne par campagne massive (`python cli.py campagne N`) : nombre de modèles, décisions, exigences, points experts, divergences, durée. Le fichier n'existe qu'à partir de la première campagne consignée. |
| `dictionnaire-colonnes.md` | La définition de chaque colonne, groupe par groupe. |
| `sorties/` | Pour chaque expérience `EXP-nnnnnn_<code>` : le modèle BPMN soumis, le DRD produit (`.drd.dmn`) et le rapport détaillé (`.rapport.json`). Chaque ligne du registre reste ainsi vérifiable. |

## Le code de référence du modèle

Chaque modèle reçoit un code `nom-empreinte` : le nom du fichier abrégé
(lettres, chiffres, tirets) suivi des huit premiers caractères de
l'empreinte SHA-256 de son contenu. Un même fichier soumis dix fois garde le
même code (dix lignes, un modèle) ; un fichier modifié reçoit un nouveau
code. La colonne `arbitrages` distingue la première extraction (0) des
réapplications avec verdicts de l'expert.

## Les grandeurs

Une centaine de colonnes, en neuf groupes : identification ; composition du
modèle source (activités par type, passerelles, événements, données,
annotations, flux, couloirs) ; détection des décisions (|DA|, |DA*|, indices
de corroboration par position et par lexique, candidats non corroborés,
activités hors définition) ; DRD extrait (décisions, données d'entrée,
sources de connaissance, BKM, exigences IR/KR/AR) ; patterns appliqués
(P2 objets et magasins, P3 événements, P4 dépendances, P5 rôles, P6
annotations selon leur verdict) ; périmètre d'automatisation (points soumis
à l'expert par catégorie, éléments écartés, questions par décision, part des
règles fermées et ouvertes) ; vérification (acyclicité, invariants, relecture
du DMN, aller-retour) ; mesure contre la référence experte quand un fichier
`.gold` accompagne le modèle (précision, rappel) ; structure du DRD (densité,
profondeur, degrés entrants, décisions de tête, composantes connexes) ;
durées. Le détail est dans `dictionnaire-colonnes.md`.

## Commandes

```
python cli.py registre                 # synthèse
python cli.py registre --dernieres 10  # les dix dernières lignes
python cli.py registre --excel         # régénérer le classeur
python cli.py transformer modele.bpmn --sans-registre   # ne pas consigner
python cli.py servir --registre D:\mes-experimentations  # autre dossier
```

Variables d'environnement : `BPMN2DMN_REGISTRE=<dossier>` déplace le
registre, `BPMN2DMN_SANS_REGISTRE=1` le suspend. En version autonome
(exécutable), le dossier `experimentations/` est créé à côté de
l'exécutable.

Le classeur `registre.xlsx` peut rester ouvert dans Excel pendant les
extractions : s'il est verrouillé, une copie datée est déposée à côté et le
fichier CSV, lui, est toujours à jour.
