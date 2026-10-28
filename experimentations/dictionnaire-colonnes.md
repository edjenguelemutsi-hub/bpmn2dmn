# Dictionnaire des colonnes du registre des expérimentations

Chaque ligne de `registre.csv` (séparateur « ; », UTF-8, point décimal) et de la feuille « Expérimentations » de `registre.xlsx` décrit une extraction. Les colonnes suivent l'ordre ci-dessous. Une cellule vide signifie « non applicable » (par exemple : pas de référence experte).


## Identification

| Colonne | Libellé | Définition |
|---|---|---|
| `experience` | Numéro d'expérience | Identifiant séquentiel de la ligne (EXP-000001, EXP-000002...). |
| `horodatage` | Horodatage | Date et heure de l'extraction (heure locale, format ISO 8601). |
| `code_modele` | Code de référence du modèle | Nom du fichier (abrégé) suivi de l'empreinte SHA-256 abrégée du contenu BPMN : un même modèle garde le même code, un modèle modifié en reçoit un nouveau. |
| `fichier` | Fichier BPMN | Nom du fichier soumis (ou « exemple FIMEX », « <en mémoire> »). |
| `modele` | Nom du processus | Nom du ou des processus déclarés dans le fichier BPMN. |
| `contexte` | Contexte d'exécution | Comment l'extraction a été lancée : ligne de commande, application web, validation du corpus, catalogue de patterns, test. |
| `arbitrages` | Arbitrages appliqués | Nombre de verdicts de l'expert appliqués (candidats + ressources + annotations + renommages) ; 0 = première extraction, sans arbitrage. |
| `variante` | Variante de l'algorithme | « reference » pour l'algorithme de référence tel que défini ; sinon la liste des extensions activées. |
| `version` | Version de l'outil | Version du transformateur ayant produit la ligne. |

## Modèle source (Mi)

| Colonne | Libellé | Définition |
|---|---|---|
| `vi_sommets` | \|V_i\| sommets de flux | Activités + passerelles + événements. |
| `activites` | \|A\| activités | Toutes natures confondues. |
| `activites_utilisateur` | Tâches utilisateur | Type userTask. |
| `activites_regle_metier` | Tâches de règle métier | Type businessRuleTask. |
| `activites_generiques` | Tâches génériques | Type task. |
| `activites_service` | Tâches de service | Type serviceTask. |
| `activites_autres` | Autres activités | Envoi, réception, manuelles, script, appels d'activité, transactions. |
| `sous_processus` | Sous-processus | Sous-processus repliés (activités de Mi) + dépliés (contenu remonté). |
| `passerelles` | \|G\| passerelles | Toutes natures. |
| `passerelles_exclusives` | Passerelles exclusives |  |
| `passerelles_inclusives` | Passerelles inclusives |  |
| `passerelles_paralleles` | Passerelles parallèles |  |
| `passerelles_autres` | Autres passerelles | Passerelles d'événements et complexes. |
| `evenements` | \|E_v\| événements | Toutes natures. |
| `evenements_porteurs` | Événements porteurs | Événements à définition message ou signal (candidats de P3). |
| `evenements_frontiere` | Événements-frontière |  |
| `objets_donnees` | \|D_o\| objets de données |  |
| `magasins_donnees` | \|D_s\| magasins de données |  |
| `annotations` | \|A_no\| annotations |  |
| `flux_sequence` | \|E_s\| flux de séquence |  |
| `flux_donnees` | \|E_d\| associations de données | Lectures et écritures d'objets et de magasins. |
| `associations_annotations` | Associations d'annotations |  |
| `couloirs` | Couloirs (ressources) | Nombre de ressources distinctes portées par les activités (rho). |
| `anomalies_source` | Anomalies du modèle | Défauts non bloquants relevés par le parseur. |

## Détection (DA, κ)

| Colonne | Libellé | Définition |
|---|---|---|
| `da_candidats` | \|DA\| candidats | Activités du type décisionnel (tâches utilisateur, tâches de règle métier, sous-processus repliés). |
| `da_retenus` | \|DA*\| retenus | Candidats corroborés par κ ou retenus par l'expert : les décisions du DRD. |
| `da_position_seule` | Retenus par la position seule | Indice de position (passerelle exclusive ou inclusive à la suite) sans verbe de décision. |
| `da_lexical_seul` | Retenus par le lexique seul | Verbe de décision du lexique Λ dans le libellé, sans passerelle. |
| `da_deux_indices` | Retenus par les deux indices |  |
| `da_par_arbitrage` | Retenus par arbitrage | Candidats sans indice, confirmés par l'expert. |
| `da_non_corrobores` | Candidats non corroborés | Candidats sans indice, soumis à l'expert (« est-ce une décision ? »). |
| `da_ecartes_arbitrage` | Candidats écartés par l'expert |  |
| `taux_corroboration` | Taux de corroboration | \|DA*\| / \|DA\| (vide si aucun candidat). |
| `hors_definition` | Activités hors définition | Tâches génériques, de service, d'envoi... corroborées par un indice : décisions de fait que la définition de référence ne couvre pas. |

## DRD (Mf)

| Colonne | Libellé | Définition |
|---|---|---|
| `decisions` | \|D\| décisions |  |
| `donnees_entree` | \|I\| données d'entrée |  |
| `sources_connaissance` | \|KS\| sources de connaissance |  |
| `bkm` | \|BKM\| modèles de connaissance métier |  |
| `vf_sommets` | \|V_f\| sommets | D + I + KS + BKM. |
| `ef_exigences` | \|E_f\| exigences | IR + KR + AR. |
| `ir` | IR exigences d'information |  |
| `ir_donnee_decision` | IR donnée vers décision |  |
| `ir_decision_decision` | IR décision vers décision | Arcs du pattern P4. |
| `kr` | KR exigences de connaissance |  |
| `ar` | AR exigences d'autorité |  |

## Patterns

| Colonne | Libellé | Définition |
|---|---|---|
| `p2_objets` | P2 : objets de données | Données d'entrée issues d'objets. |
| `p2_magasins` | P2 : magasins de données | Données d'entrée issues de magasins. |
| `p3_evenements` | P3 : événements | Données d'entrée issues d'événements porteurs. |
| `p3_optionnels` | P3 : frontières non interruptrices | Données d'entrée marquées « (optionnel) ». |
| `p4_dependances` | P4 : dépendances entre décisions |  |
| `p5_sources` | P5 : sources issues de rôles |  |
| `p6_donnees` | P6 : annotations en donnée d'entrée |  |
| `p6_sources` | P6 : annotations en source de connaissance |  |
| `p6_bkm` | P6 : annotations en BKM |  |

## Périmètre d'automatisation

| Colonne | Libellé | Définition |
|---|---|---|
| `points_expert` | Points soumis à l'expert | Total. |
| `pe_candidats` | dont candidats | « Cette activité est-elle vraiment une décision ? » |
| `pe_ressources` | dont ressources | « Ce rôle gouverne-t-il ou applique-t-il ? » |
| `pe_annotations` | dont annotations | « Cette annotation : donnée, autorité ou règle ? » |
| `pe_hors_definition` | dont hors définition |  |
| `pe_circuits` | dont circuits | Dépendances mutuelles entre décisions, écartées par la garde d'acyclicité. |
| `ecartes` | Éléments écartés automatiquement | Total. |
| `ec_ressources` | dont ressources (systèmes) |  |
| `ec_annotations` | dont annotations non décisionnelles |  |
| `ec_candidats` | dont candidats écartés par l'expert |  |
| `questions_par_decision` | Questions par décision | Points soumis à l'expert / \|D\| (vide si aucune décision). |
| `part_regles_fermees` | Part des règles fermées | Exigences produites par P2, P3 et P4 / \|E_f\| (vide si aucune exigence). |
| `part_regles_ouvertes` | Part des règles ouvertes | Exigences produites par P5 et P6 / \|E_f\|. |

## Vérification

| Colonne | Libellé | Définition |
|---|---|---|
| `acyclique` | Graphe acyclique | 1 = oui, 0 = non. |
| `invariants_violes` | Invariants violés | Nombre d'invariants formels (sur 8) violés ; 0 attendu. |
| `partition_exacte` | Partition exacte {IR, KR, AR} | 1 = oui. |
| `dmn_relu_conforme` | DMN produit relu conforme | 1 si le fichier DMN relu restitue exactement Mf (vide si non vérifié). |
| `aller_retour` | Aller-retour T(T⁻¹(M)) = M | 1 si vérifié, 0 si écart, vide si non calculé. |

## Référence experte

| Colonne | Libellé | Définition |
|---|---|---|
| `ref_attendues` | Décisions attendues | Nombre de décisions de la référence experte (.gold) ; vide sans référence. |
| `ref_detectees` | Décisions détectées |  |
| `ref_correctes` | Détections correctes |  |
| `ref_a_tort` | Détections à tort |  |
| `ref_manquees` | Décisions manquées |  |
| `precision` | Précision | Correctes / détectées. |
| `rappel` | Rappel | Correctes / attendues. |

## Structure du DRD

| Colonne | Libellé | Définition |
|---|---|---|
| `drd_densite` | Densité | \|E_f\| / (\|V_f\| (\|V_f\| - 1)) ; vide si moins de deux sommets. |
| `drd_profondeur` | Profondeur | Longueur (en décisions) du plus long chemin de dépendance entre décisions ; 1 = décisions indépendantes ; vide si le graphe n'est pas acyclique. |
| `drd_degre_entrant_max` | Degré entrant maximal | Plus grand nombre d'exigences arrivant sur une même décision. |
| `drd_degre_entrant_moyen` | Degré entrant moyen | \|E_f\| / \|D\| (vide si aucune décision). |
| `drd_decisions_racines` | Décisions de tête | Décisions dont aucune autre décision ne dépend. |
| `drd_composantes` | Composantes connexes | Nombre de fragments indépendants dans (V_f, E_f). |

## Durées

| Colonne | Libellé | Définition |
|---|---|---|
| `duree_analyse_ms` | Durée d'analyse (ms) | Lecture du BPMN et construction de Mi. |
| `duree_transformation_ms` | Durée de transformation (ms) | Exécution de T. |
| `duree_serialisation_ms` | Durée de sérialisation (ms) | Écriture du DMN. |
| `duree_totale_ms` | Durée totale (ms) |  |

## Campagnes (`campagnes.csv`)

Une ligne par campagne massive : `horodatage`, `contexte`, `graine_debut`, `modeles`, `modeles_verifies`, `decisions`, `exigences`, `points_expert`, `divergences`, `duree_s`, `processus`, `version`.

## Sorties conservées (`sorties/`)

Pour chaque expérience `EXP-nnnnnn_<code>` : le modèle BPMN soumis (`.bpmn`), le DRD produit (`.drd.dmn`) et le rapport détaillé (`.rapport.json`).
