# Effet des extensions sur le catalogue de patterns

Chaque diagramme est transformé avec **toutes** les extensions actives ; les variables de condition proposées (P7) sont acceptées par un arbitrage pour que l'effet apparaisse dans le DRD. Colonnes : référence (algorithme sans extension) puis avec extensions, D / I / KS / BKM / exigences / points soumis à l'expert ; puis les tables de décision produites (règles écrites en FEEL sur le total, tables exécutables). Sorties dans ce dossier (`.drd.dmn`, `.rapport.json`). Regénération : `python -X utf8 outils/resultats_extensions.py`.

| Id | Référence D/I/KS/BKM/E/expert | Avec extensions | Tables (règles FEEL / total, exécutables) | Changement |
|---|---|---|---|---|
| A01 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A02 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A03 | 1/0/0/0/0/1 | 1/0/0/0/0/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A04 | 1/0/1/0/1/1 | 1/0/1/0/1/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A05 | 1/0/0/1/1/1 | 1/0/0/1/1/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A06 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A07 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A08 | 1/1/0/0/1/1 | 1/1/1/0/2/1 | 2 / 2, 1 | sources 0 → 1; exigences 1 → 2; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A09 | 1/1/0/0/1/1 | 1/1/1/0/2/1 | 2 / 2, 1 | sources 0 → 1; exigences 1 → 2; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| A10 | 2/1/0/0/2/0 | 2/1/0/0/2/0 | 4 / 4, 2 | 2 table(s), 4/4 règle(s) FEEL, exécutable(s) : 2 |
| A11 | 2/2/1/0/4/3 | 2/2/2/0/5/3 | 4 / 4, 2 | sources 1 → 2; exigences 4 → 5; 2 table(s), 4/4 règle(s) FEEL, exécutable(s) : 2 |
| B01 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1; 1 nom(s) suggéré(s) |
| B02 | 1/2/0/0/2/0 | 1/2/0/0/2/0 | - | aucun |
| B03 | 0/0/0/0/0/1 | 0/0/0/0/0/1 | - | aucun |
| B04 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 0 / 2, 0 | 1 table(s), 0/2 règle(s) FEEL; 1 nom(s) suggéré(s) |
| B05 | 2/2/0/0/2/0 | 2/2/0/0/2/0 | 4 / 4, 2 | 2 table(s), 4/4 règle(s) FEEL, exécutable(s) : 2 |
| B06 | 2/2/0/0/2/2 | 2/2/0/0/2/2 | - | aucun |
| B07 | 2/0/0/0/1/1 | 2/0/0/0/1/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| B08 | 2/1/1/0/4/1 | 2/1/1/0/4/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| B09 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1; 1 nom(s) suggéré(s) |
| B10 | 1/2/0/0/2/1 | 1/2/0/0/2/1 | - | aucun |
| B11 | 1/0/0/0/0/0 | 1/0/0/0/0/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| B12 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| B13 | 1/1/0/0/1/0 | 1/1/0/0/1/0 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C01 | 0/0/0/0/0/1 | 1/1/0/0/1/0 | 2 / 2, 1 | décisions 0 → 1; données d'entrée 0 → 1; exigences 0 → 1; points expert 1 → 0; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C02 | 0/0/0/0/0/1 | 1/1/0/0/1/0 | 2 / 2, 1 | décisions 0 → 1; données d'entrée 0 → 1; exigences 0 → 1; points expert 1 → 0; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C03 | 0/0/0/0/0/1 | 1/0/0/0/0/0 | 2 / 2, 1 | décisions 0 → 1; points expert 1 → 0; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C04 | 0/0/0/0/0/1 | 1/2/0/0/2/0 | 3 / 3, 1 | décisions 0 → 1; données d'entrée 0 → 2; exigences 0 → 2; points expert 1 → 0; 1 table(s), 3/3 règle(s) FEEL, exécutable(s) : 1; 1 nom(s) suggéré(s) |
| C05 | 0/0/0/0/0/1 | 0/0/0/0/0/1 | - | 1 candidat(s) proposé(s) par l'indice sémantique |
| C06 | 1/1/0/0/1/1 | 1/1/1/0/2/1 | 2 / 2, 1 | sources 0 → 1; exigences 1 → 2; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C07 | 1/0/0/0/0/0 | 1/0/0/0/0/0 | - | aucun |
| C08 | 1/0/0/0/0/1 | 1/0/0/0/0/1 | 2 / 2, 1 | 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |
| C09 | 0/0/0/0/0/1 | 0/0/0/0/0/1 | - | 1 candidat(s) proposé(s) par l'indice sémantique |
| C10 | 1/0/0/0/0/0 | 1/1/0/0/1/0 | 2 / 2, 1 | données d'entrée 0 → 1; exigences 0 → 1; 1 table(s), 2/2 règle(s) FEEL, exécutable(s) : 1 |

Total : 30 tables de décision, 61 règles dont 59 écrites en FEEL, 29 tables exécutables ; 4 patterns gagnent au moins une décision ; 4 noms suggérés ; 2 candidats proposés par le seul indice sémantique.

