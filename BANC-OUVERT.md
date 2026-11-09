# Banc d'essai ouvert : le transformateur sur des modèles écrits par d'autres

Version 1.2 (9 novembre 2026). Le corpus de validation de l'outil (vingt
modèles, référence experte, 59 décisions) a été écrit et annoté par
l'auteur ; sa portée statistique est limitée. Ce banc d'essai soumet le
transformateur à deux collections publiques de modèles BPMN dessinés par
d'autres, sans référence experte : il mesure la robustesse de la chaîne et
la charge réelle laissée à l'expert, pas la précision, et il montre l'effet
de la langue des libellés sur le lexique fermé Λ. Les chiffres ci-dessous
viennent de `banc-ouvert/synthese.md` et `banc-ouvert/resultats.csv`,
produits par `python -X utf8 outils/banc-ouvert.py` après
`python -X utf8 outils/telecharger-banc.py`.

## Les collections

| Collection | Modèles | Origine | Langue des libellés | Conditions d'usage |
|---|---|---|---|---|
| bpmn-for-research (bfr) | 3 739 | diagrammes dessinés par les participants de formations BPMN de Camunda, quatre exercices (expédition de marchandises, recours, scoring de crédit, restaurant en libre-service), plus le corrigé de chaque exercice | allemand (3 537) et anglais (202) | usage académique et de recherche seulement, lien vers https://github.com/camunda/bpmn-for-research à conserver |
| bpmn-miwg-test-suite (miwg) | 22 | modèles de référence du BPMN Model Interchange Working Group de l'OMG | anglais (libellés « Task 1 », « Task 2 »...) | OMG, https://github.com/bpmn-miwg/bpmn-miwg-test-suite |

Le Signavio Academic Dataset, cité par les encadreurs, ne se télécharge que
sur demande et au format propre à Signavio ; la collection de l'initiative
académique BPM (BPMAI, Zenodo) est dans le même format. Les deux collections
retenues sont des fichiers BPMN 2.0 XML, lisibles tels quels.

## Le protocole

Chaque modèle est lu par le parseur (un échec est consigné avec son motif),
puis transformé dans trois variantes :

1. **référence** : les candidats sont les tâches utilisateur, les tâches de
   règle métier et les sous-processus repliés, corroborés par la position ou
   le lexique (l'outil tel que publié) ;
2. **definition-etendue** : toute activité, quel que soit son type, devient
   candidate dès qu'un indice la corrobore ; elle est retenue avec les deux
   indices et soumise à l'expert avec un seul ;
3. **definition-etendue + indice-semantique** : l'indice sémantique s'ajoute
   comme indice ; sur une activité hors définition il compte comme second
   indice avec la position ; seul, il propose sans retenir.

Pour chaque variante : invariants, relecture du DMN produit, aller-retour
T(T⁻¹(M)) = M quand le DRD a une décision, déterminisme (deux exécutions
identiques), durées, et toutes les grandeurs du registre. Aucun arbitrage
n'est appliqué.

## Résultats

**Lecture et robustesse.** 3 754 modèles lus sur 3 761 ; les 7 autres sont
des diagrammes vides (aucun processus non vide). Sur les 3 754 modèles et
dans chaque variante : invariants 8/8 respectés, DMN relu conforme, DRD sans
circuit, aller-retour exact sur tous les modèles qui ont une décision (35
en référence, 134 avec la définition étendue), deux exécutions identiques.
Durée moyenne d'une extraction complète : 3,5 ms, maximum 50 ms. Durée
totale du banc, trois variantes, plongements sémantiques compris : deux
minutes.

**La définition de référence ne s'applique pas à ces collections.** La
tâche générique représente 98,5 % des 32 669 activités (tâches utilisateur
0,4 %, tâches de règle métier 0,03 %) : les participants d'une formation
ne typent pas leurs tâches. La variante de référence ne voit donc que 193
candidats et retient 68 décisions (34 dans bfr, toutes par la position ;
34 dans miwg) ; 3 710 des 3 732 modèles bfr n'ont aucune décision, et les
8 603 activités génériques corroborées par un indice sont seulement
signalées « hors définition ». C'est la limite C01 du catalogue de patrons,
observée à grande échelle, et la raison d'être de l'extension
« definition-etendue ».

**Avec la définition étendue, l'effet de la langue est net.** Sur les 202
modèles anglais, 160 décisions sont retenues (deux indices : un verbe de Λ
et une passerelle), 114 modèles sur 202 restent sans décision ; sur les
3 530 modèles allemands, 51 décisions seulement (34 tâches typées retenues par la
position, 17 tâches génériques dont le libellé contient un verbe anglais du lexique), 3 497 modèles sans décision, et 8 136 candidats sont
soumis à l'expert avec un seul indice. Le lexique Λ ne contient aucun verbe
allemand : « prüfen », « auswählen », « entscheiden » lui échappent. C'est
exactement la dépendance à une liste fermée que les encadreurs relevaient.

**L'indice sémantique lève cette dépendance, au prix d'erreurs visibles.**
Avec l'indice, les décisions retenues passent de 160 à 219 sur l'anglais et
de 51 à 4 150 sur l'allemand ; les points soumis à l'expert baissent de
8 153 à 5 423 sur l'allemand. Sur un échantillon tiré au sort de 60
décisions allemandes retenues grâce au seul indice sémantique
(`banc-ouvert/echantillon-semantique-DE.md`), 50 désignent bien une étape
de décision (« Widerspruch prüfen », « Regress möglich ? », « Lieferant
auswählen ») et 10 non (« Versicherung abschließen », souscrire
l'assurance ; « Anfrage Warenversand »), soit une précision estimée de 83 %
par un seul annotateur. Sur les 213 activités de la collection miwg, aux
libellés sans sens (« Task 1 »), l'indice en juge 46 décisionnelles : il
réagit à la forme des libellés autant qu'à leur sens, et c'est pourquoi il
propose au lieu de retenir.

**La charge laissée à l'expert.** Avec la définition étendue, un modèle
soumet en moyenne 2,3 points à l'expert (médiane 2, maximum 15) ; rapportés
aux décisions inférées, 1,98 question par décision en moyenne (médiane
1,33), contre 2,1 sur le corpus de validation. La distribution des points
par modèle est donnée dans la synthèse : 590 modèles sans aucune question,
2 293 avec une à trois, 10 avec dix ou plus.

| Variante | Décisions (bfr EN / bfr DE / miwg) | Points expert (bfr EN / DE / miwg) | Modèles bfr sans décision |
|---|---|---|---|
| référence | 0 / 34 / 34 | 530 / 8 167 / 77 | 3 710 |
| definition-etendue | 160 / 51 / 35 | 416 / 8 153 / 76 | 3 611 |
| definition-etendue + indice-semantique | 219 / 4 150 / 37 | 385 / 5 423 / 75 | 1 289 |

## Ce que le banc établit et ce qu'il n'établit pas

Il établit que la chaîne tient sur des fichiers venus d'ailleurs (lecture,
invariants, relecture, aller-retour, déterminisme, temps), que la
définition de référence des candidats présuppose un typage des tâches que
des modèles de formation n'ont pas, que le lexique fermé est aveugle à une
langue qu'il ne couvre pas, et que l'indice sémantique rend des décisions
lisibles dans cette langue. Il n'établit pas la précision ni le rappel du
transformateur sur ces modèles : il n'existe pas de référence experte pour
eux, et l'échantillon allemand est annoté par l'auteur seul. Une évaluation
indépendante demanderait deux annotateurs sur un tirage de ces modèles ;
le banc en donne le protocole et les fichiers.

## Fichiers

```
banc-ouvert/
  synthese.md                    tableaux de la synthèse (généré)
  resultats.csv                  une ligne par modèle et par variante, toutes les colonnes du registre (généré)
  echantillon-semantique-DE.md   les 60 décisions allemandes tirées au sort et leur jugement
  journal-execution.txt          journal de la dernière exécution
  sources/                       les modèles téléchargés (non versionnés) : bfr/<EN|DE>/<01..04>/<resultats|solution>/, miwg/
outils/telecharger-banc.py       téléchargement des deux collections
outils/banc-ouvert.py            exécution et synthèse
```
