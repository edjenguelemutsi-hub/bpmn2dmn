# Extensions de l'algorithme de transformation

Le catalogue de patterns (`catalogue-patterns/`) établit les limites de
l'algorithme de référence tel qu'il est défini : ce qu'il ne voit pas (famille C) et
ce qu'il remet à l'expert (points d'arbitrage des familles A et B). Ce
document décrit les sept améliorations qui en découlent. Chacune est une
**extension activable** : sans extension, l'algorithme de référence
s'exécute et ses sorties sont strictement celles d'avant (empreintes
identiques sur le corpus, les jeux Camunda, FIMEX avec et sans arbitrage,
le cas BPCO, le catalogue et 300 modèles générés ; test
`tests/test_extensions.py`, classe `TestSansExtensionReference`). La
variante retenue, « reference » ou la liste des extensions actives, est
consignée dans la colonne `variante` du registre des expérimentations, ce
qui permet de comparer les variantes sur une même table.

Notation : Mi = (Gi, τ, β) le modèle source, A les activités, DA les
candidates, κ le prédicat de corroboration (indice de position, indice
lexical Λ), DA* = {a ∈ DA | κ(a)}, ω et γ les fonctions de qualification,
P1 à P6 les patterns de la correspondance, δ et ι les appariements
injectifs, E_f les exigences du DRD.

## Activer une extension

```
python cli.py extensions                                   # la liste
python cli.py transformer modele.bpmn --extensions logique,noms-suggeres
python cli.py transformer modele.bpmn --extensions toutes
python cli.py valider "catalogue-patterns/*.bpmn" --extensions toutes
```

Dans l'application web, le bloc « Extensions de l'algorithme » sous le
bouton « Extraire DRD » porte une case par extension ; le rapport affiche
la variante. Par l'API : champ `extensions` (liste de noms) de
`POST /api/transformer`, liste servie par `GET /api/extensions`.

## 1. `definition-etendue` — les activités hors définition

**Limite d'origine** : C01 (tâche générique devant une passerelle), C02
(tâche de service au verbe décisionnel), C03 (appel d'activité). La
définition de référence ne retient comme candidates que les tâches
utilisateur, les tâches de règle métier et les sous-processus repliés ; une
activité d'un autre type qui décide de fait est seulement signalée
« hors définition », le DRD reste vide.

**Règle** : DA_ext = DA ∪ {a ∈ A | τ(a) ∉ {userTask, businessRuleTask,
subProcess} ∧ κ(a)}. Pour ces candidates supplémentaires, la corroboration
est plus exigeante que pour DA : a ∈ DA* si les deux indices sont
présents (position et lexique), ou si l'expert la confirme ; avec un seul
indice, elle est soumise à l'expert (catégorie « candidat », motif nommant
le type et l'indice observé).

**Mise en œuvre** : `_Construction.extraire_candidats` et `corroborer`
(`candidats_etendus`) ; le motif de rétention de la décision mentionne le
type d'origine et l'extension.

**Effet sur le catalogue** : C01, C02 et C03 passent de 0 à 1 décision
(deux indices dans chaque cas) ; C04 voit sa tâche de service devenir une
candidate soumise à l'expert (un seul indice), retenue si l'expert
confirme.

**Ce qui reste à l'expert** : une candidate étendue à un seul indice. La
prudence est voulue : une tâche de service qui précède une passerelle peut
n'être qu'un calcul dont le résultat est testé plus loin.

## 2. `conditions-passerelle` — les variables des conditions (P7)

**Limite d'origine** : C04, le cas de l'approche par le flux de contrôle
(Batoulis et al., 2015) : la logique est dans les `conditionExpression`
des flux sortants des passerelles, que l'algorithme ne lit pas.

**Règle** : pour a ∈ DA* et toute passerelle exclusive ou inclusive g
atteinte depuis a en ne traversant que des passerelles (cascade), pour
tout flux (g, t) ∈ E_s porteur d'une condition c, chaque identifiant v lu
dans c (hors littéraux, mots réservés et appels de fonction ; `${…}` et
`#{…}` de Camunda ouverts) qui ne nomme pas une donnée déjà reliée à
δ(a) est un **point d'arbitrage** de catégorie « condition », proposition
« I ». Si l'expert répond « I » (clé `condition:<v>` dans la section
`annotations` des arbitrages), v devient une donnée d'entrée ι(v) de
pattern **P7**, une seule par variable pour tout le modèle (injectivité),
reliée par une exigence d'information à chaque décision dont une
passerelle la teste ; « non » l'écarte.

**Choix** : rien n'est ajouté au DRD sans arbitrage. Un identifiant
d'expression est un nom technique (`paysARisque`, `dossier.type`) qui ne
désigne pas toujours une donnée métier distincte de celles déjà lues ;
créer la donnée d'office contredirait le principe « proposer, motiver,
tracer, ne jamais deviner ».

**Mise en œuvre** : le parseur relève les conditions dans
`mi.conditions` ; `_variables_condition` extrait les identifiants ;
`_Construction.relier_conditions`.

**Effet** : sur C04, avec `definition-etendue` et l'arbitrage de la
candidate, les variables `montant` et `paysARisque` sont proposées puis,
acceptées, deviennent deux données d'entrée (P7) de la décision ; sur les
autres patterns du catalogue, aucune condition n'est écrite, l'extension
est sans effet.

## 3. `evenements-conditionnels` — les événements à condition

**Limite d'origine** : C06 (frontière de minuterie) et le critère de
porteur de données : seuls message et signal sont porteurs.

**Règle** : un événement à `conditionalEventDefinition` est porteur (sa
condition porte sur des données du processus : il apporte une valeur à la
décision qu'il précède ou à laquelle il est attaché) ; P3 s'applique.
Restent non porteurs : la minuterie (un délai n'est pas une donnée), les
frontières d'erreur et d'escalade interruptrices (elles interrompent
l'activité au lieu de l'alimenter, et signalent un échec plutôt qu'une
valeur d'entrée).

**Mise en œuvre** : le parseur relève les définitions de chaque
événement (`mi.definitions_evenements`) ; `_mi_etendu` marque porteurs
les événements conditionnels sur une copie de Mi (le Mi lu reste intact).

**Effet** : aucun diagramme du catalogue ne porte d'événement
conditionnel ; l'extension est vérifiée par un test dédié.

## 4. `donnees-processus` — les données déclarées par le processus

**Limite d'origine** : C10. Une donnée déclarée par l'`ioSpecification`
du processus (`dataInput`, `dataOutput`) n'est ni un objet ni un magasin ;
l'association qui la lit vise un identifiant inconnu (anomalie signalée)
et la décision reste sans exigence.

**Règle** : DN_ext = DN ∪ {d ∈ ioSpecification(p) | ∃ (d, a) ou (a, d)
association écartée} ; ces données sont des objets de données de D_o, les
associations écartées sont rétablies, P2 s'applique.

**Mise en œuvre** : le parseur relève `mi.donnees_processus` et
`mi.flux_donnees_ecartes` ; `_mi_etendu` les adopte sur la copie de Mi et
retire l'anomalie correspondante.

**Effet** : C10 passe de 0 à 1 donnée d'entrée et 1 exigence.

## 5. `roles-gouvernants` — la qualification lexicale des rôles

**Limite d'origine** : A09, A08, A11, B06, B10, C06 : ω ne tranche que les
systèmes ; tout rôle humain est un point d'arbitrage (« gouverne-t-elle ou
applique-t-elle ? »).

**Règle** : ω_ext(r) = KS si le nom de r porte, par mots entiers, un
indice de gouvernance (comité, commission, conseil, jury, directeur,
direction, chef, responsable, autorité, ministre, signataire, superviseur,
contrôleur, inspecteur, board, committee, director, manager…), la source
de connaissance étant créée et reliée par une exigence d'autorité ; le
point d'arbitrage subsiste avec la proposition « KS (indice lexical) »,
comme γ le fait pour une annotation d'autorité, et l'expert peut encore
écarter la ressource. Les autres rôles humains restent indéterminés.

**Mise en œuvre** : `IND_GOUVERNANCE` et `indice_gouvernance` dans
`qualification.py` ; `_Construction.relier_ressource`.

**Effet** : A08, A09, C06 (couloir « Chef de service »), A11 (« Chef de
service ») gagnent une source de connaissance et une exigence
d'autorité ; sur FIMEX, « Agent signataire » est proposé comme source (le
DRD du cas d'étude après arbitrage la retient), « Agent de traitement »
reste à arbitrer.

## 6. `noms-suggeres` — un nom pour la décision retenue par sa position

**Limite d'origine** : B01, B04, B09 : une activité retenue par la seule
position garde un libellé qui ne dit pas ce qu'elle décide (« Instruire le
dossier »).

**Règle** : pour a ∈ DA* retenue par la position seule et non renommée,
si la passerelle qui suit porte une question « Q ? », le nom suggéré est
« Décider si q » (q = Q, initiale en minuscule) ; sinon « Décider : Q ».
La suggestion est consignée dans `rapport["suggestions_noms"]` ; δ n'est
modifié que par un renommage de l'expert (bouton « utiliser » dans
l'application).

**Effet** : B01, B04, B09 reçoivent une suggestion (« Décider si demande
recevable »…) ; les passerelles de FIMEX n'ont pas de libellé, aucune
suggestion.

## 7. `logique` — vers le déploiement : la table de décision squelette

**Limite d'origine** : le niveau produit est le DRD ; la logique interne
des décisions reste à écrire dans Camunda Modeler. Le schéma de
construction prévoit l'enchaînement P1 → P2 → P3 → passerelle → Camunda
(« déployer »).

**Règle** : pour a ∈ DA* suivie d'une passerelle exclusive ou inclusive
g, la décision δ(a) reçoit dans le DMN une `decisionTable` (politique
UNIQUE) dont les entrées sont les données d'entrée et décisions reliées à
δ(a) par une exigence d'information (`typeRef` string, expression = un
nom de variable dérivé du libellé), dont la sortie porte le nom de la
passerelle et les valeurs admises = libellés des flux sortants de g (à
défaut le nom du nœud cible), et une règle par branche : entrées « - » à
compléter, sortie = le libellé de la branche, la condition du flux
recopiée en description de la règle quand elle existe. Le DRD (V_f, E_f)
est strictement inchangé ; la table est un squelette, les conditions
restent à écrire par le modélisateur (c'est pourquoi les règles se
recouvrent tant qu'elles ne sont pas remplies).

**Mise en œuvre** : `_Construction.preparer_logique` (branches) et
`serialiseur._table_de_decision`. Le DMN produit reste conforme au XSD DMN
1.3 (`outils/valider_xsd.py` valide désormais aussi les corpus avec toutes
les extensions : 174 documents) et dmn-js ouvre chaque table
(`tests/fabriquer_page_rendu_extensions.py`, rendu headless
« RENDU-OK … vues=drd,decisionTable,… »). L'inverse T⁻¹ ignore la table.

**Effet** : 27 des 34 patterns du catalogue reçoivent une table
squelette (ceux dont la décision est suivie d'une passerelle) ; FIMEX en
reçoit deux (conformité : incomplet / non conforme / conforme ; signature :
accordée / réexamen).

## Effet mesuré sur le catalogue

`catalogue-patterns/resultats-extensions/LISEZ-MOI.md` donne, pattern par
pattern, le DRD de référence et le DRD avec toutes les extensions
(D / I / KS / BKM / exigences / points experts), les sorties `.drd.dmn` et
`.rapport.json` étant dans le même dossier. En résumé : 3 patterns de la
famille C gagnent une décision (C01, C02, C03), 1 gagne sa donnée d'entrée
(C10), 4 gagnent une source de connaissance (A08, A09, A11, C06), 3
reçoivent un nom suggéré (B01, B04, B09), 27 une table squelette ; C04
devient traitable après arbitrage (candidate étendue + deux variables P7) ;
C05 (passerelle d'événements), C07 (décision sans lecture), C08
(annotation ambiguë) et C09 (verbe hors lexique) restent des limites :
elles tiennent au modèle source ou aux lexiques, qui sont des paramètres.

## Risques et garanties

- Les extensions n'altèrent jamais l'algorithme de référence : test
  d'empreintes, 112 tests, contrôle final de 20 épreuves, validation XSD,
  campagne du générateur inchangée.
- Chaque extension conserve les six propriétés : les nouveaux sommets
  passent par la fabrique (injectivité), les arcs par `_ajouter_arc` (pas
  de doublon), aucun arc n'arrive sur une donnée d'entrée, la garde
  d'acyclicité n'est pas contournée (P7 et P5 étendus ne créent que des
  arcs vers des décisions depuis des sommets sans arc entrant).
- `definition-etendue` et `roles-gouvernants` élargissent ce que
  l'algorithme propose ; ils ne retirent rien à l'expert, qui garde le
  dernier mot par les arbitrages `candidats` et `ressources`.
- `conditions-passerelle` dépend de la qualité des expressions écrites
  dans le modèle ; l'analyse des identifiants est volontairement simple
  et tout est soumis à l'expert.
- `logique` produit des tables à compléter, pas des tables exécutables.
