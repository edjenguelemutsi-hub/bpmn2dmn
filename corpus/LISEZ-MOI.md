# Corpus de validation — banque de modèles BPMN réels

Ce dossier est la **banque de modèles** du transformateur BPMN → DMN :
dix processus réalistes, chacun accompagné de sa **référence experte**
(fichier `.gold` : les libellés exacts des activités de décision
attendues). C'est sur ce corpus que se mesurent la précision et le
rappel de la détection des décisions.

## Usage

Depuis le dossier `transformateur/` :

```
python cli.py valider "corpus/*.bpmn"
```

Résultat attendu (état au 31 août 2026) : **10 modèles, 32 décisions
attendues, 32 correctement détectées, 0 à tort, 0 manquée — précision
100 %, rappel 100 %, invariants formels 8/8 sur chaque modèle, graphes
acycliques.**

Chaque modèle peut aussi être transformé individuellement :

```
python cli.py transformer corpus/credit-bancaire.bpmn
```

Le `.dmn` produit s'ouvre dans Camunda Modeler (onglet DRD) ou sur
https://demo.bpmn.io/dmn.

## Les modèles

| Fichier | Domaine | Inspiration | Décisions attendues | Particularités exercées |
|---|---|---|---|---|
| `fimex.bpmn` | Commerce extérieur (GUCE) | **Cas d'étude de référence** (processus réel e-FORCE/e-GOV) | 3 | Modèle historique : collaboration 2 pools, 3 couloirs dont un système, P₁–P₆ au complet, mise en page d'origine Camunda |
| `copd.bpmn` | Santé (BPCO) | **Article de base** : Bazhenova, Zerbato, Oliboni & Weske, *Information Systems* 83 (2019), fig. 1 | 4 | Modèle historique : événement-frontière non interrupteur, sous-processus, annotations d'autorité en anglais |
| `credit-bancaire.bpmn` | Banque | Domaine bancaire de Bazhenova et al. (2019) ; pratique CEMAC | 3 | Chaîne P₄ (avis de solvabilité), magasin « Centrale des risques », couloir système, annotation décorative |
| `sinistre-assurance.bpmn` | Assurance | Indemnisation zone CIMA ; « claim handling » (Dumas et al.) | 3 | Décision par lexique seul (« Vérifier les garanties »), P₄, couloir plateforme |
| `admission-hopital.bpmn` | Santé | Triage des urgences ; parallèle au cas BPCO | 3 | **Événement-frontière non interrupteur** (P₃ optionnel), départ à message, magasin DMP |
| `recrutement.bpmn` | Ressources humaines | « Hiring process » (Dumas et al., *Fundamentals of BPM*) ; pratique RH | 3 | Départ **sans** message, annotation décorative (charte), businessRuleTask |
| `marche-public.bpmn` | Marchés publics | Codes des marchés publics CEMAC, commissions de passation | 4 | **Passerelle inclusive** (indice de position), 4ᵉ décision par lexique seul, 3 couloirs |
| `dedouanement.bpmn` | Douane | Procédure SYDONIA (CNUCED) ; contexte GUCE voisin de FIMEX | 3 | Circuits de sélectivité, couloir « Système SYDONIA » écarté par ω, annotation QR code écartée par γ |
| `bourse-etudes.bpmn` | Enseignement supérieur | Commissions nationales des bourses | 3 | Chaîne complète P₁-P₂-P₄-P₆, annotation d'autorité (arrêté ministériel) |
| `permis-construire.bpmn` | Urbanisme | Instruction des autorisations d'urbanisme communales | 3 | « Consulter … » comme distracteur (« consulter » ∉ Λ), magasin plan d'urbanisme, 3 annotations (autorité, règle, décorative) |

**Total : 32 décisions attendues.**

## Conventions

- `fimex.bpmn` et `copd.bpmn` sont les **deux modèles historiques de
  mes travaux** (validation du premier prototype `deriver.py`) ; le
  `fimex.bpmn` repris ici est la version à mise en page d'origine
  (`sources-figures/rendu-bpmn-js/fimex.bpmn`) et son `.gold` celui du
  prototype (la mesure normalise accents et casse : l'écart
  ASCII/accentué est sans effet).
- Le cas FIMEX est accompagné de deux références supplémentaires :
  `fimex.arbitrages.json`, les arbitrages de l'expert (utilisés par
  `cli.py transformer -a` et figés dans les tests), et
  `fimex-drd-reference.dmn`, le DRD de référence établi à la main avec
  l'expert (copie de `sources-figures/fimex-drd.dmn`, exercé par le
  contrôle final). Les tests ne dépendent ainsi que de ce dossier.
- Les huit autres modèles ont été rédigés pour la banque de tests du
  transformateur (31 août 2026) : chaque en-tête XML cite son
  inspiration. Leur mise en page BPMNDI est générée par
  `injecter_di.py` (module `bpmn2dmn.miseenpage`) — correcte et
  déterministe, elle peut être embellie librement dans Camunda Modeler.
- Un `.gold` liste **une décision par ligne** (libellé exact de la tâche
  dans le BPMN) ; les lignes `#` sont des commentaires.
- Les modèles générés en masse (des milliers, avec oracle complet) ne
  vivent pas ici : voir `python cli.py generer` et `python cli.py
  campagne` — ce dossier ne contient que les modèles *réels* relus à la
  main.
