# Banc d'essai ouvert : synthèse

Modèles : 3761 (3754 lus, 7 en échec de lecture) ; durée totale 120 s.
Variantes : référence et « definition-etendue » sur tous les modèles lus ; « definition-etendue + indice-semantique » : oui.

## Robustesse de la chaîne (variante de référence)

| contrôle | modèles concernés | conformes | taux |
|---|---|---|---|
| invariants 8/8 respectés | 3754 | 3754 | 100.0 % |
| DMN produit relu conforme | 3754 | 3754 | 100.0 % |
| DRD sans circuit | 3754 | 3754 | 100.0 % |
| aller-retour T(T⁻¹(M)) = M | 35 | 35 | 100.0 % |
| deux exécutions identiques | 3754 | 3754 | 100.0 % |

Durée moyenne d'une extraction complète : 3.52 ms (maximum 50.26 ms).

## Variante de référence

### Par collection

| collection | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfr | 3732 | 3732 | 32456 | 114 | 34 | 34 | 0 | 0 | 80 | 8603 | 34 | 10 | 8697 | 255.79 | 3710 |
| miwg | 22 | 22 | 213 | 79 | 34 | 16 | 6 | 12 | 45 | 21 | 34 | 16 | 77 | 2.26 | 9 |

### bpmn-for-research, par langue du cours

| langue | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DE | 3530 | 3530 | 30616 | 113 | 34 | 34 | 0 | 0 | 79 | 8074 | 34 | 10 | 8167 | 240.21 | 3508 |
| EN | 202 | 202 | 1840 | 1 | 0 | 0 | 0 | 0 | 1 | 529 | 0 | 0 | 530 | - | 202 |

## Variante « definition-etendue »

Les activités de tout type sont candidates dès qu'un indice les corrobore ; retenues avec les deux indices, soumises à l'expert avec un seul. Les colonnes « position seule », « lexique seul » et « deux » comptent les décisions retenues selon les indices de la définition de référence ; « non corroborés » compte les candidats soumis à l'expert.

### Par collection

| collection | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfr | 3732 | 3732 | 32456 | 114 | 211 | 34 | 0 | 0 | 8506 | 0 | 211 | 93 | 8569 | 40.61 | 3611 |
| miwg | 22 | 22 | 213 | 79 | 35 | 16 | 6 | 12 | 65 | 0 | 35 | 16 | 76 | 2.17 | 9 |

### bpmn-for-research, par langue du cours

| langue | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DE | 3530 | 3530 | 30616 | 113 | 51 | 34 | 0 | 0 | 8136 | 0 | 51 | 17 | 8153 | 159.86 | 3497 |
| EN | 202 | 202 | 1840 | 1 | 160 | 0 | 0 | 0 | 370 | 0 | 160 | 76 | 416 | 2.60 | 114 |

### bpmn-for-research, par exercice

| exercice | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01 | 1209 | 1209 | 10694 | 51 | 86 | 20 | 0 | 0 | 4086 | 0 | 86 | 1 | 4132 | 48.05 | 1154 |
| 02 | 1088 | 1088 | 7139 | 23 | 116 | 10 | 0 | 0 | 2718 | 0 | 116 | 86 | 2733 | 23.56 | 1029 |
| 03 | 864 | 864 | 5713 | 6 | 7 | 2 | 0 | 0 | 1472 | 0 | 7 | 6 | 1474 | 210.57 | 859 |
| 04 | 571 | 571 | 8910 | 34 | 2 | 2 | 0 | 0 | 230 | 0 | 2 | 0 | 230 | 115.00 | 569 |

### bpmn-for-research, diagrammes des participants et corrigés

| genre | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| resultats | 3722 | 3722 | 32358 | 114 | 208 | 34 | 0 | 0 | 8481 | 0 | 208 | 91 | 8543 | 41.07 | 3603 |
| solution | 10 | 10 | 98 | 0 | 3 | 0 | 0 | 0 | 25 | 0 | 3 | 2 | 26 | 8.67 | 8 |

### Robustesse de la chaîne avec « definition-etendue »

| contrôle | modèles concernés | conformes | taux |
|---|---|---|---|
| invariants 8/8 respectés | 3754 | 3754 | 100.0 % |
| DMN produit relu conforme | 3754 | 3754 | 100.0 % |
| DRD sans circuit | 3754 | 3754 | 100.0 % |
| aller-retour T(T⁻¹(M)) = M (modèles avec décision) | 134 | 134 | 100.0 % |
| deux exécutions identiques | 3754 | 3754 | 100.0 % |

Charge laissée à l'expert avec « definition-etendue » : points soumis par modèle, moyenne 2.30, médiane 2.0, maximum 15 ; questions par décision inférée : moyenne 1.98, médiane 1.33 ; modèles avec au moins une décision : 134 sur 3754.

## Types d'activités rencontrés

| type | activités | part |
|---|---|---|
| task | 32139 | 98.5 % |
| autres | 293 | 0.9 % |
| userTask | 131 | 0.4 % |
| serviceTask | 44 | 0.1 % |
| businessRuleTask | 9 | 0.0 % |

La définition de référence des candidats (tâches utilisateur, tâches de règle métier, sous-processus repliés) ne couvre que 0.4 % des activités de ces collections, où la tâche générique domine ; les activités hors définition corroborées par un indice sont comptées à part (colonne « hors définition corroborées »), l'extension « definition-etendue » les retient.

## Charge laissée à l'expert (variante de référence)

Points soumis à l'expert par modèle : moyenne 2.34, médiane 2.0, maximum 15 ; questions par décision inférée (modèles avec au moins une décision) : moyenne 2.68, médiane 2.00.

| points soumis à l'expert | modèles |
|---|---|
| 0 | 590 |
| 1 | 642 |
| 2 | 881 |
| 3 | 770 |
| 4 | 569 |
| 5 | 160 |
| 6 | 78 |
| 7 | 36 |
| 8 | 13 |
| 9 | 5 |
| 10 et plus | 10 |

## Variante « definition-etendue + indice-semantique »

L'indice sémantique ne retient jamais seul : il propose. Sur une activité hors définition, il compte comme second indice avec la position. Les colonnes donnent, par langue, les activités que le modèle de langue juge décisionnelles, les candidats que le seul indice sémantique propose à l'expert, et l'effet sur les décisions retenues et les points soumis à l'expert.

| collection / langue | modèles | activités | jugées décisionnelles par l'indice | candidats DA | proposés par le seul indice sémantique | décisions retenues (étendue) | décisions retenues (étendue + sémantique) | points expert (étendue) | points expert (étendue + sémantique) |
|---|---|---|---|---|---|---|---|---|---|
| bfr/EN | 202 | 1840 | 436 | 1 | 0 | 160 | 219 | 416 | 385 |
| bfr/DE | 3530 | 30616 | 8091 | 113 | 10 | 51 | 4150 | 8153 | 5423 |
| miwg | 22 | 213 | 46 | 79 | 10 | 35 | 37 | 76 | 75 |

## Modèles non lus

| motif | modèles |
|---|---|
| Aucun processus BPMN non vide dans le fichier. | 7 |

