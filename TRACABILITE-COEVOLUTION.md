# Traçabilité et co-évolution entre le processus et le modèle de décision

Version 1.2 (novembre 2026). Ce document décrit comment l'outil relie chaque
élément du DRD produit à l'élément du processus dont il vient, et comment ce
lien sert dans les deux sens : reporter sur le processus les modifications
faites au DRD (`synchroniser`), et dire ce qu'une modification du processus
change au DRD (`impact`). Notation : Mi le modèle de processus réduit, Mf le
DRD réduit, T la transformation, δ et ι les appariements injectifs
(activité vers décision, donnée ou événement vers donnée d'entrée), P1 à P7
les patrons.

## 1. Le lien entre les deux modèles

Trois choses, écrites par l'outil lui-même, portent le lien.

**Des identifiants stables.** Chaque sommet du DRD porte l'identifiant de
l'élément BPMN dont il vient, préfixé par son type : la décision issue de la
tâche `T3` s'appelle `Decision_T3`, la donnée d'entrée issue de l'objet
`do_dossier` s'appelle `InputData_do_dossier`, la source de connaissance
issue du couloir « Agent signataire » s'appelle
`KnowledgeSource_role_Agent_signataire`, le modèle de connaissance métier
issu de l'annotation `A1` s'appelle `BKM_A1`, la donnée d'entrée issue de la
variable `montant` d'une condition (P7) s'appelle
`InputData_condition_montant`. Un identifiant déjà pris reçoit un suffixe
numérique. L'identité d'un sommet ne dépend donc ni de l'ordre de parcours ni
des autres éléments : ajouter une tâche au processus ne renumérote pas les
décisions, ce qui n'était pas le cas des identifiants `D1`, `D2`... de la
version 1.0. Le DRD lui-même (sommets, types, noms, exigences, points soumis
à l'expert) est inchangé : les tests `tests/test_v4.py` vérifient
l'équivalence avec les sorties publiées de la version 1.0.

**Un élément de trace dans le DMN.** Chaque sommet et chaque exigence du
fichier DMN porte, dans l'élément `extensionElements` que la norme réserve
aux outils, un élément `bpmn2dmn:trace` (espace de noms
`https://github.com/edjenguelemutsi-hub/bpmn2dmn/trace`) :

```xml
<decision id="Decision_T3" name="Vérifier la conformité documentaire">
  <extensionElements>
    <bpmn2dmn:trace source="T3" pattern="P1"
        motif="précède une passerelle exclusive + verbe décisionnel dans le libellé"/>
  </extensionElements>
  <informationRequirement id="ir3">
    <extensionElements><bpmn2dmn:trace pattern="P2"/></extensionElements>
    <requiredInput href="#InputData_do_dossier"/>
  </informationRequirement>
  ...
```

`source` est l'identifiant de l'élément BPMN, `pattern` le patron qui a posé
le sommet ou l'arc, `motif` les indices de corroboration d'une décision. Le
fichier reste conforme au schéma DMN 1.3 de l'OMG (`outils/valider_xsd.py`),
s'ouvre dans Camunda Modeler et dmn-js, et le parseur DMN de l'outil
(`inverse.parser_dmn`) relit la trace.

**Un fichier de trace.** La commande `transformer` écrit, à côté du DMN, un
fichier `<nom>.trace.json` : pour chaque sommet, son identifiant DMN, son
type, son nom, l'identifiant et le libellé de l'élément BPMN, le patron, le
motif ; pour chaque exigence, ses extrémités, son genre (IR, KR, AR) et son
patron ; les arbitrages appliqués ; l'empreinte SHA-256 du BPMN source ; les
points soumis à l'expert.

## 2. DMN vers BPMN : `synchroniser`

```
python cli.py synchroniser corpus/fimex.bpmn fimex-modifie.dmn -a corpus/fimex.arbitrages.json
                           [-o fimex-mis-a-jour.bpmn] [--json rapport.json] [--extensions logique]
```

Le modélisateur a retouché le DRD dans Camunda Modeler. L'outil rejoue la
transformation sur le BPMN d'origine (avec les arbitrages d'origine), met en
correspondance le DRD ainsi recalculé et le DRD modifié (par identifiant,
sinon par élément source de la trace, sinon par type et nom), puis reporte
chaque différence sur le fichier BPMN, élément par élément, sans toucher au
reste du processus. Le fichier est édité avec lxml : espaces de noms,
commentaires, attributs des outils et mise en page sont conservés ; les
éléments ajoutés reçoivent une forme de diagramme près de la tâche à
laquelle ils se rattachent.

| Modification lue dans le DRD | Ce qui est fait dans le processus |
|---|---|
| décision renommée | la tâche est renommée ; si un renommage d'arbitrage existait déjà pour cette tâche (l'expert avait choisi de garder le libellé de la tâche et de nommer la décision autrement), c'est l'arbitrage qui est mis à jour et le libellé est conservé |
| décision nouvelle | une tâche utilisateur et sa passerelle de verdict sont insérées après la tâche d'une décision qu'elle requiert, sinon avant la tâche d'une décision qui la requiert, sinon après l'événement de début ; même couloir que le point d'insertion |
| décision retirée | la tâche n'est pas supprimée : elle devient un candidat écarté par arbitrage (`candidats: {id: false}`) |
| donnée d'entrée renommée | l'objet ou le magasin de données (P2) ou l'événement (P3) est renommé ; pour une donnée issue d'une annotation (P6), le nom est posé par arbitrage (`noms`) ; une variable de condition (P7) n'est pas renommée (les conditions devraient être réécrites) |
| donnée d'entrée nouvelle | un objet de données est créé près de la première décision qui la lit, et une lecture (`dataInputAssociation`) est ajoutée à chaque tâche de décision qui la requiert |
| donnée d'entrée retirée | les lectures sont retirées des tâches ; l'objet est supprimé s'il n'a plus aucune lecture ni écriture ; une annotation (P6) ou une variable (P7) est écartée par arbitrage |
| exigence d'information ajoutée (donnée vers décision) | une lecture est ajoutée à la tâche (donnée P2) ; pour une donnée issue d'un événement, d'une annotation ou d'une condition, rien n'est inventé, le rapport le dit |
| exigence d'information ajoutée (décision vers décision) | un objet « Résultat : décision amont » est créé, écrit par la tâche amont et lu par la tâche aval (c'est ce que P4 raffiné lit) |
| exigence d'information retirée | la lecture correspondante est retirée de la tâche |
| source de connaissance ou BKM nouveau | une annotation textuelle est créée, associée à chaque tâche de décision concernée, et qualifiée KS ou BKM par arbitrage |
| source ou BKM renommé | l'annotation est réécrite (P6) ou le couloir renommé (P5) |
| exigence d'autorité ou de connaissance ajoutée ou retirée depuis une annotation | l'association est ajoutée ou retirée ; une annotation sans plus aucune association est supprimée |
| exigence d'autorité depuis un rôle (couloir) ajoutée ou retirée | rien n'est modifié : un rôle gouverne toutes les tâches de son couloir, déplacer la tâche se fait dans l'outil de modélisation ; le rapport le dit |
| source issue d'un rôle retirée | le rôle est écarté par arbitrage (`ressources: {nom: "non"}`) |
| règles d'une table de décision écrites | chaque règle est reportée en condition FEEL sur le flux sortant de la passerelle qui suit la tâche (`conditionExpression`, langage FEEL) ; la règle du flux par défaut pose l'attribut `default` de la passerelle ; les règles sont appariées aux flux par le libellé du flux, sinon par le nom du nœud cible, sinon par le rang |
| sommet sans aucune exigence | signalé : un sommet orphelin n'a pas d'image dans un processus |

Quand une tâche renommée n'est plus corroborée par κ (verbe hors lexique,
pas de passerelle), la décision serait perdue : l'outil ajoute l'arbitrage
`candidats: {id: true}` (l'expert la confirme) et le dit.

**Vérification.** La transformation est rejouée sur le BPMN mis à jour avec
les arbitrages mis à jour, et le DRD obtenu est comparé au DRD modifié
(mêmes sommets par type et nom, mêmes exigences ; les tables de décision
sont comparées règle à règle). Le rapport dit « cohérence vérifiée » ou nomme
l'écart. Le code de retour de la commande vaut 0 si la cohérence est
vérifiée, 2 sinon.

**Sorties.** Le BPMN mis à jour (`<nom>.synchronise.bpmn` par défaut), les
arbitrages mis à jour (`.arbitrages.json`), le rapport (texte et, avec
`--json`, JSON : liste des changements avec, pour chacun, sa nature, l'élément
du DRD, l'élément du processus, ce qui a été fait, appliqué ou non et
pourquoi ; cohérence ; écarts).

## 3. BPMN vers DMN : `impact`

```
python cli.py impact fimex.drd.dmn corpus/fimex-modifie.bpmn -a corpus/fimex.arbitrages.json [--json rapport.json]
```

Le processus a changé. L'outil transforme le nouveau BPMN et compare le DRD
obtenu au DRD précédemment produit, sommet par sommet (identifiants
stables, puis trace, puis type et nom) et exigence par exigence : sommets
conservés, renommés, nouveaux, disparus ; exigences conservées, nouvelles,
invalidées (avec le motif : sommet disparu, ou dépendance que le processus
ne porte plus) ; tables de décision identiques ou modifiées ; questions à
poser à l'expert sur le nouveau processus. Exemple : renommer la tâche
« Affecter le dossier à un agent » en « Attribuer le dossier » (verbe hors
lexique, pas de passerelle à sa suite) fait disparaître la décision et
invalide ses trois exigences ; le rapport les nomme. Code de retour 0 si le
DRD est identique, 2 sinon.

## 4. Dans l'application web et par l'API

L'onglet « Co-évolution » de l'application reçoit le BPMN d'origine (ou le
reprend de l'onglet d'extraction, avec ses arbitrages), le DMN, et offre les
deux actions ; le BPMN mis à jour est rendu par bpmn-js et téléchargeable
avec les arbitrages et le rapport. Par l'API : `POST /api/synchroniser
{bpmn, dmn, arbitrages?, extensions?}` et `POST /api/impact {dmn, bpmn,
arbitrages?, extensions?}`.

## 5. Ce qui reste hors de portée

Un DRD ne contient pas la topologie du processus : l'ordre des tâches, les
branches, les couloirs ne s'en déduisent pas. La synchronisation reporte donc
ce que le DRD détermine (sommets, exigences, règles) et laisse au
modélisateur ce qu'il ne détermine pas (où placer une tâche nouvelle au-delà
du point d'insertion choisi, quel couloir donner à un rôle). Les choix sont
conservateurs : rien n'est supprimé du processus sans qu'un arbitrage le
dise, rien n'est inventé quand le processus ne peut pas l'exprimer, et chaque
décision de l'outil est écrite dans le rapport.

## 6. Mise en œuvre et tests

Module `bpmn2dmn/coevolution.py` (`EditeurBPMN`, `synchroniser`, `impact`,
`fichier_trace`) ; identifiants stables dans `transformation._Fabrique` ;
trace écrite par `serialiseur` et relue par `inverse.parser_dmn`. Tests :
`tests/test_v4.py` (classes `TestIdentifiantsEtTrace`, `TestCoevolution`),
validation XSD du BPMN mis à jour dans `outils/valider_xsd.py`, parcours de
l'interface `tests/controle_interface.py` (mode `?auto=5`).
