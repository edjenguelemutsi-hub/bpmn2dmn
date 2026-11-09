# Extensions de l'algorithme de transformation

Le catalogue de patterns (`catalogue-patterns/`) établit les limites de
l'algorithme de référence tel qu'il est défini : ce qu'il ne voit pas (famille C) et
ce qu'il remet à l'expert (points d'arbitrage des familles A et B). Ce
document décrit les huit améliorations qui en découlent (sept à la version
1.0, une huitième, l'indice sémantique, à la version 1.2, qui réécrit aussi
la septième). Chacune est une
**extension activable** : sans extension, l'algorithme de référence
s'exécute et ses sorties sont strictement celles d'avant (empreintes
identiques sur le corpus, les jeux Camunda, FIMEX avec et sans arbitrage,
le cas BPCO, le catalogue et 300 modèles générés ; test
`tests/test_extensions.py`, classe `TestSansExtensionReference` ; depuis la
version 1.2 les identifiants des sommets sont dérivés du modèle source et le
DMN porte une trace, ce qui change le texte du fichier mais pas le DRD :
`tests/test_v4.py` vérifie l'équivalence avec les sorties publiées). La
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

## 7. `logique` — la table de décision écrite depuis les conditions des flux

**Limite d'origine** : le niveau produit est le DRD ; la logique interne
des décisions (les règles « si... alors... ») restait à écrire dans Camunda
Modeler. La version 1.0 produisait une table squelette (entrées, valeurs de
sortie, cellules à compléter) ; les encadreurs ont demandé que l'algorithme
lise les conditions écrites sur les flux de séquence sortants des passerelles
pour ébaucher les règles. C'est ce que fait la version 1.2.

**Règle** : pour a ∈ DA* suivie d'une passerelle exclusive ou inclusive g
(en cascade : un flux dont la cible est une autre passerelle de choix sans
activité intermédiaire est déplié, la branche terminale portant la
conjonction des conditions rencontrées), la décision δ(a) reçoit dans le DMN
une `decisionTable` :

- **entrées** : les données d'entrée et décisions reliées à δ(a) par une
  exigence d'information (une colonne chacune, variable FEEL dérivée du
  libellé), puis une colonne par variable lue dans les conditions des flux
  et qui ne correspond à aucune exigence (une variable arbitrée par P7 est
  rattachée au nœud qu'elle a créé) ; le type de la colonne (`number`,
  `boolean`, `string`) vient des littéraux comparés ;
- **sortie** : le verdict, nommé d'après la passerelle, dont les valeurs
  admises sont les libellés des branches terminales (à défaut le nom du
  nœud cible) ;
- **règles** : une par branche, ou une par terme quand la condition est une
  disjonction ; chaque cellule porte le test unaire FEEL tiré de la condition
  (`> 5000000`, `"CM"`, `true`, `[18..65)`, `not("A", "B")`) ; une condition
  non lue laisse ses cellules à compléter (`-`) et reste en description de
  la règle ; le flux par défaut (`default` de la passerelle) devient une
  dernière règle sans condition, la politique passant de `UNIQUE` à `FIRST` ;
- **sans aucune condition**, une passerelle qui pose une question fermée
  (branches oui/non, yes/no, ja/nein) donne une colonne booléenne nommée
  d'après la question, avec `true` et `false` en cellules ;
- la table est dite **exécutable** quand chaque règle est écrite ou couverte
  par le flux par défaut : un moteur DMN peut alors l'évaluer.

Le module `bpmn2dmn/feel.py` lit le sous-ensemble commun à FEEL, au JUEL de
Camunda (`${...}`), à JavaScript et à Groovy : comparaisons d'une variable
à un littéral (nombre, chaîne, booléen), variables booléennes nues,
négation, conjonction, disjonction, parenthèses. Tout ce qui sort de ce
sous-ensemble (appel de fonction, arithmétique, comparaison de deux
variables) rend la condition « non lue » : rien n'est deviné. Le DRD
(V_f, E_f) est strictement inchangé.

**Mise en œuvre** : `transformation._TableDecision` (branches en cascade,
colonnes, règles), `feel.analyser` et `feel.test_unaire`,
`serialiseur._table_de_decision` ; le parseur relève les identifiants des
flux (`mi.ids_flux`) et les flux par défaut (`mi.flux_defaut`). La table est
relue par `inverse.parser_dmn` (co-évolution : ses règles, modifiées dans le
DRD, sont reportées en conditions FEEL sur les flux ; voir
`TRACABILITE-COEVOLUTION.md`). Le DMN produit reste conforme au XSD DMN 1.3
(`outils/valider_xsd.py`) et dmn-js ouvre chaque table. L'inverse T⁻¹
ignore la table pour reconstruire le squelette.

**Effet** : sur le catalogue, 30 tables, 61 règles dont 59 écrites en FEEL,
29 tables exécutables (les passerelles du catalogue posent des questions
fermées) ; C04, le cas des conditions écrites, donne une table à trois
règles et deux colonnes typées (`montant` : number, `paysARisque` :
boolean), exécutable. Sur le corpus de validation, dont les passerelles
n'ont ni condition ni libellé oui/non, 36 tables et 74 règles, dont 4 en
FEEL : les tables y restent à compléter, ce que le rapport dit.

## 8. `indice-semantique` — un troisième indice pour κ, lu par un modèle de langue

**Limite d'origine** : le lexique Λ est une liste fermée de verbes
français et anglais, réglée à la lumière de FIMEX et de la BPCO ; un
libellé dans une autre langue ou avec un verbe absent de la liste n'a que
l'indice de position. Les encadreurs y voyaient un risque de
sur-apprentissage et demandaient des plongements lexicaux ou un modèle de
langue léger.

**Règle** : un modèle de phrases multilingue (MiniLM-L12, douze couches,
384 dimensions, exécuté par ONNX Runtime sur le processeur, quantifié en
entiers de 8 bits, 118 Mo) plonge le libellé ; une régression logistique
apprise sur 392 libellés écrits à la main (150 décisions, 242
non-décisions, en français, anglais, allemand et espagnol, dans des
domaines variés, aucun repris du corpus de validation) donne un score
entre 0 et 1 ; l'indice κ_s(a) vaut vrai au-dessus du seuil 0,5, fixé en
validation croisée sur les exemples. Dans le prédicat :

- un candidat de DA corroboré par la position ou le lexique est retenu
  comme avant ;
- un candidat de DA que seul l'indice sémantique corrobore **n'est pas
  retenu : il est soumis à l'expert** avec la proposition « décision
  (indice sémantique) », le score, le seuil et l'exemple d'apprentissage
  le plus proche dans le motif (même règle que pour une candidate étendue
  à un seul indice) ;
- un candidat sans aucun indice est soumis à l'expert, le motif disant que
  l'indice sémantique ne le juge pas décisionnel non plus ;
- avec `definition-etendue`, une activité hors définition est retenue avec
  la position et le lexique **ou** la position et l'indice sémantique ;
- le motif de rétention de chaque décision porte le score.

**Ce que l'indice garde des exigences du cadre** : il est déterministe
(mêmes fichiers, identifiés par leur empreinte SHA-256, mêmes poids, même
seuil), tracé (score et exemple proche dans le motif et dans le DMN), et
optionnel : sans l'extension, rien ne change ; avec elle, le DRD de
référence du corpus ne change pas non plus, seuls les motifs et les
propositions aux experts changent (`tests/test_v4.py`).

**Mesure** (`experimentations/evaluation-indices-kappa-2026-11-09.md`,
`python outils/evaluer-indices.py`) : sur les 109 candidats du corpus,
l'indice sémantique seul retient 68 candidats, précision 72 %, rappel
83 % ; « position ou sémantique » (le lexique remplacé) : précision 75 %,
rappel 98 % ; la référence « position ou lexique » : 100 / 100. Le
remplacement pur du lexique coûte donc en précision, ce qui justifie la
règle « proposer sans retenir » ; les erreurs sont nommées dans le rapport
(« Saisir l'observation de réexamen » jugé décisionnel, « Statuer sur
l'octroi du crédit » non). Sur le banc d'essai ouvert
(`BANC-OUVERT.md`), où les libellés sont allemands et le lexique aveugle,
l'indice fait passer les décisions retenues de 51 à 4 150 sur 3 530
modèles, avec une précision estimée à 83 % sur un échantillon de 60 jugé
par l'auteur.

**Mise en œuvre** : `bpmn2dmn/semantique.py` (`Plongeur`,
`IndiceSemantique`, `entrainer`), exemples dans
`bpmn2dmn/modeles/exemples-indice-semantique.txt`, classifieur dans
`bpmn2dmn/modeles/classifieur-semantique.json`, apprentissage par
`outils/entrainer-indice-semantique.py`, modèle téléchargé par
`outils/telecharger-modele.py` (dépendances : `requirements-semantique.txt`).
Sans le modèle, l'extension est annoncée indisponible (ligne de commande,
`GET /api/extensions`, case grisée dans l'application) et tout le reste
fonctionne.

## Effet mesuré sur le catalogue

`catalogue-patterns/resultats-extensions/LISEZ-MOI.md` donne, pattern par
pattern, le DRD de référence et le DRD avec toutes les extensions
(D / I / KS / BKM / exigences / points experts), les sorties `.drd.dmn` et
`.rapport.json` étant dans le même dossier. En résumé : 3 patterns de la
famille C gagnent une décision (C01, C02, C03), 1 gagne sa donnée d'entrée
(C10), 4 gagnent une source de connaissance (A08, A09, A11, C06), 4
reçoivent un nom suggéré (B01, B04, B09, C04), 30 une table de décision
dont 29 exécutables ; C04 est traité (tâche de service retenue par la
position et l'indice sémantique, deux variables P7, table à trois règles
FEEL) ; C09 (verbe hors lexique) reçoit une proposition de l'indice
sémantique ; C05 (passerelle d'événements), C07 (décision sans lecture) et
C08 (annotation ambiguë) restent des limites : elles tiennent au modèle
source.

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
- `logique` écrit les règles que les conditions des flux permettent de
  lire ; une table est annoncée exécutable seulement si chaque règle est
  écrite, et une condition non lue reste visible en description.
- `indice-semantique` ne retient jamais seul : il propose, avec son score ;
  sa précision mesurée sur le corpus (72 %) et estimée sur le banc ouvert
  (83 %) interdit d'en faire un critère de rétention automatique.
