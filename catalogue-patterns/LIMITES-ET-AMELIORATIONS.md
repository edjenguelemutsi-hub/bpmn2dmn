# Catalogue de patterns : limites établies et améliorations proposées

Synthèse de l'exécution du catalogue (`outils/executer_catalogue.py`, 34 diagrammes,
34 conformes à l'attendu) le 8 septembre 2026. Chaque comportement cité ci-dessous a
été observé sur un diagramme du catalogue (identifiant entre parenthèses) ou sur une
variante construite avec le même générateur (mention « hors catalogue »).

## 1. Ce que l'algorithme fait sans intervention (règles fermées)

| Id | Pattern | Résultat |
|---|---|---|
| A01, A02 | objet ou magasin de données lu (Π1, Π3 / P2) | donnée d'entrée + IR |
| A06, A07 | événement de départ ou intermédiaire à message précédant la décision (Π4 / P3) | donnée d'entrée + IR |
| A08 | frontière à message non interruptive (Π5 / P3) | donnée d'entrée « (optionnel) » + IR |
| A10 | donnée produite par d1 et lue par d2, d1 ⪯ d2 (P4 raffiné, P2 raffiné) | IR d1 → d2, sans donnée d'entrée intermédiaire |
| A11 | composition des fragments | un DRD unique, acyclique |
| B01, B02, B04 | corroboration par la position (passerelle exclusive ou inclusive) ou par le lexique | décision retenue, motif tracé |
| B05 | deux décisions en séquence sans donnée partagée | aucun arc (« ordonner n'est pas alimenter ») |
| B06 | donnée produite sur une branche parallèle, lue sur l'autre | donnée d'entrée, pas d'arc P4 (pas d'atteignabilité) |
| B08 | une donnée lue par deux décisions, une annotation reliée à deux décisions | un seul nœud, relié deux fois (injectivité) |
| B09 | sous-processus replié devant une passerelle | activité candidate, retenue |
| B10 | sous-processus déplié, frontière sur la façade, couloir hérité | décision interne retenue, frontière rapportée à la décision |
| B11 | annotation décorative | écartée avec motif, sans question |
| B12 | couloir « système » | ressource écartée avec motif, sans question |
| B13 | flux de message vers un événement sans définition | événement porteur, donnée d'entrée + IR |

## 2. Ce que l'algorithme propose sans trancher (règles ouvertes)

| Id | Situation | Ce qui est soumis à l'expert |
|---|---|---|
| A04, A05 | annotation à indice d'autorité ou de règle (γ) | source de connaissance ou BKM créé, confirmation demandée |
| A03, C08 | annotation sans indice lexical (γ indéterminé) | « donnée d'entrée ou source de connaissance ? », aucun nœud créé avant arbitrage |
| A09, A08, B06, B10, C06 | couloir humain (ω indéterminé) | « gouverne-t-elle la décision ? », un point par nom de ressource |
| B03, C05, C09 | candidate sans indice (κ faux) | « est-ce une décision ? », DRD vide et diagnostic explicatif |
| B07 | dépendance mutuelle entre deux décisions | second arc écarté, sens de la dépendance à trancher |

## 3. Limites établies

L1. **Définition des candidates** (C01, C02, C03). Seules les tâches utilisateur, les
tâches de règle métier et les sous-processus repliés sont candidats. Une tâche générique,
une tâche de service ou un appel d'activité corroborés par la position ou le lexique sont
signalés « hors définition » ; le DRD reste vide et le diagnostic invite à retyper. Une
décision automatisée (contrôle de cohérence par un système) échappe donc à l'extraction
tant que le modélisateur ne l'a pas typée en tâche de règle métier.

L2. **Conditions des flux non lues** (C04 ; hors catalogue : tâche utilisateur neutre devant
une passerelle conditionnée). Les expressions de condition portées par les flux sortants
d'une passerelle ne sont pas exploitées. Dans C04 aucune activité n'est candidate ; dans la
variante hors catalogue, la tâche « Saisir le montant » est retenue par position mais la
variable `montant` testée par la passerelle ne devient pas une donnée d'entrée. C'est la
frontière avec l'approche par le flux de contrôle (Batoulis et al., 2015).

L3. **Passerelle d'événements** (C05). Elle n'est pas un indice de position : la tâche qui la
précède reste non corroborée, alors qu'elle prépare bien une attente d'événement.

L4. **Événements non porteurs** (C06). Une frontière de minuterie n'apporte rien au DRD ; un
délai d'instruction, qui conditionne pourtant le résultat, ne peut pas devenir une donnée
d'entrée.

L5. **Événement porteur séparé de la décision** (hors catalogue). Seul l'événement qui
précède immédiatement l'activité, ou qui lui est attaché, est relié (P3). Si une passerelle
s'intercale entre l'événement de départ à message et la décision, la décision est retenue
mais la donnée d'entrée n'est pas créée.

L6. **Décision sans lecture** (C07). Une décision qui n'écrit qu'une sortie produit une
décision isolée, sans exigence, et aucun avertissement ne le signale : la limite est celle
du modèle source, mais l'utilisateur n'en est pas averti.

L7. **Lexique de γ** (A03, C08). Une annotation qui porte une valeur (« Capital social déclaré
par le demandeur ») ou un contexte n'est pas qualifiée : la question est posée à l'expert,
et la donnée d'entrée n'apparaît dans le DRD qu'après arbitrage.

L8. **Lexique Λ** (C09, B03). Un verbe absent du lexique (« valider », volontairement exclu ;
« traiter », « instruire ») ne corrobore pas : sans passerelle, la tâche est soumise à
l'expert. Le rappel dépend du lexique et du style de nommage.

L9. **Données d'entrée du processus** (C10). Les `dataInput` déclarés par l'`ioSpecification`
du processus ne sont ni des objets ni des magasins : l'association qui les lit vise un
identifiant inconnu (anomalie non bloquante signalée) et la décision reste sans exigence.

L10. **Points ressource systématiques** (A09, A08, B06, B10, C06). Chaque couloir humain
soulève une question ω, dédoublonnée par nom de ressource ; sur un modèle à cinq couloirs,
cinq questions, sans proposition étayée (toujours « KS si elle gouverne »).

L11. **Circuit** (B07). L'arc conservé est le premier rencontré dans l'ordre des décisions
retenues (ici « Contrôler les observations → Évaluer la demande »), c'est-à-dire l'arc qui
entre dans la première décision déclarée ; l'écart est signalé, mais le choix par défaut
n'a pas de justification métier.

L12. **Portée de la frontière sur une façade** (B10 ; hors catalogue : deux nœuds internes).
La frontière posée sur un sous-processus déplié vaut pour tous les nœuds internes ; avec
plusieurs décisions internes, la même donnée optionnelle les alimente toutes, ce qui peut
sur-approximer.

L13. **Sous-processus replié et appel d'activité** (B09, C03). Le sous-processus replié est
retenu comme une décision unique alors qu'il peut en contenir plusieurs ; l'appel
d'activité est signalé sans que le processus appelé soit exploré, même s'il figure dans
le même fichier.

## 4. Améliorations proposées

Chaque proposition indique la limite d'origine, l'idée, et le risque pour les résultats de
référence (FIMEX, BPCO, corpus, jeux, campagnes), dont les empreintes doivent rester
identiques ; les propositions qui changent le DRD sont conçues comme des extensions
activables, le comportement par défaut restant celui du cadre.

| N° | Limite | Idée | Risque pour la référence |
|---|---|---|---|
| I1 | L1 | Définition étendue, activable : une tâche générique, de service ou un appel d'activité corroboré à la fois par la position et par le lexique est proposé comme candidat (point « est-ce une décision ? » avec proposition « oui ») au lieu d'être seulement signalé | nul par défaut ; activée, elle ajouterait des points experts sur les modèles qui en contiennent |
| I2 | L2 | Lecture des conditions de flux (pattern P7) : les variables des `conditionExpression` de la passerelle qui suit une décision retenue deviennent des données d'entrée proposées, à confirmer | nul par défaut ; les corpus de référence n'ont pas de conditions formelles |
| I3 | L3 | Passerelle d'événements comptée comme indice de position faible (proposition « oui », non retenue d'office) | nul par défaut ; risque de faux positifs si retenue d'office |
| I4 | L9 | Le parseur adopte les `dataInput` / `dataOutput` de l'`ioSpecification` comme objets de données (D_o) ; l'association devient une lecture ordinaire | nul : aucun modèle de référence n'en déclare (à vérifier par empreintes) |
| I5 | L5 | P3 étendu : un événement porteur relié à la décision à travers des passerelles seulement (sans activité intermédiaire) est rattaché à la décision | changement de DRD possible sur les modèles où un événement précède une passerelle ; extension activable, ou vérification par empreintes |
| I6 | L6 | Avertissement « décision isolée » dans le rapport et le diagnostic quand une décision n'a aucune exigence | nul (rapport seulement) |
| I7 | L7 | Heuristique de valeur pour γ : une annotation qui contient un nombre, une unité ou la forme « libellé : valeur » reçoit la proposition « I » (le verdict reste indéterminé) | nul (seule la proposition change) |
| I8 | L10 | Lexique de gouvernance pour ω : « comité », « commission », « conseil », « direction », « chef », « responsable » → proposition « KS » étayée ; « agent », « secrétariat », « guichet », « opérateur » → proposition « non » ; le point reste soumis à l'expert | nul sur le DRD ; les libellés de proposition changent |
| I9 | L11 | Choix déterministe et motivé de l'arc conservé dans un circuit : garder l'arc qui va de la décision atteinte en premier depuis le départ vers l'autre (ordre du processus), et le dire dans le motif | nul sur la référence (aucun circuit) ; change B07 |
| I10 | L12 | Frontière de façade rapportée aux seules décisions internes qui sont atteignables depuis l'entrée du sous-processus avant sa sortie, avec un point expert si plusieurs décisions sont concernées | nul sur la référence |
| I11 | L13 | Dépliage de l'appel d'activité et du sous-processus replié quand le processus visé (`calledElement`) est présent dans le fichier | nul sur la référence |
| I12 | L8 | Lexique Λ chargé depuis un fichier de configuration (métier, langue), « valider » et « consulter » restant exclus par défaut ; mesure de l'effet du lexique dans le registre d'expérimentations | nul par défaut |
| I13 | vers le déploiement | Squelette de table de décision par décision : entrées = données d'entrée du DRD, valeurs de sortie = libellés des flux sortants de la passerelle (« oui », « non »), pour un dépôt direct dans Camunda | nul sur le DRD ; la sérialisation DMN gagne un élément `decisionTable` optionnel |

Depuis, sept extensions activables ont été livrées (voir `EXTENSIONS-ALGORITHME.md`) :
I1 (`definition-etendue`), I2 (`conditions-passerelle`), I4 (`donnees-processus`),
I8 (`roles-gouvernants`) et I13 (`logique`) y sont mises en œuvre telles quelles ;
l'extension `evenements-conditionnels` répond à L4 et `noms-suggeres` aux patterns B01,
B04 et B09. Les propositions I3, I5, I6, I7 et I9 à I12 restent des pistes, à évaluer sur
le catalogue puis sur le corpus. Sans extension, le comportement par défaut et les
empreintes des résultats de référence sont inchangés.
