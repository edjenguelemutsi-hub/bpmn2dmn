# -*- coding: utf-8 -*-
"""
Les grandeurs mesurées sur une extraction : ce qui fait une ligne du
registre des expérimentations.

Chaque exécution de la transformation T sur un modèle BPMN est résumée par
une ligne chiffrée : taille et composition du modèle source Mi, candidats
DA et retenus DA* avec les indices de corroboration, sommets et exigences
du DRD Mf par type et par pattern, périmètre d'automatisation (points
soumis à l'expert, éléments écartés), vérifications (acyclicité,
invariants, relecture du DMN, aller-retour), mesure contre la référence
experte quand elle existe (précision, rappel), structure du DRD (taille,
densité, profondeur, degrés) et durées.

`COLONNES` fixe l'ordre et la définition de chaque colonne ; `mesurer`
calcule une ligne. Les colonnes d'identification (numéro d'expérience,
horodatage, code du modèle, contexte) sont remplies par le registre.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from .metamodeles import BKM, DECISION, INPUT_DATA, KNOWLEDGE_SOURCE, Mf, Mi
from .qualification import kappa
from .transformation import LIBELLES_HORS_DEFINITION, TYPES_DA
from .validation import mesurer_decisions, verifier_dmn_serialise, verifier_invariants

# (nom de colonne, groupe, libellé, définition)
COLONNES: List[Tuple[str, str, str, str]] = [
    # identification (remplie par le registre)
    ("experience", "Identification", "Numéro d'expérience",
     "Identifiant séquentiel de la ligne (EXP-000001, EXP-000002...)."),
    ("horodatage", "Identification", "Horodatage",
     "Date et heure de l'extraction (heure locale, format ISO 8601)."),
    ("code_modele", "Identification", "Code de référence du modèle",
     "Nom du fichier (abrégé) suivi de l'empreinte SHA-256 abrégée du "
     "contenu BPMN : un même modèle garde le même code, un modèle modifié "
     "en reçoit un nouveau."),
    ("fichier", "Identification", "Fichier BPMN",
     "Nom du fichier soumis (ou « exemple FIMEX », « <en mémoire> »)."),
    ("modele", "Identification", "Nom du processus",
     "Nom du ou des processus déclarés dans le fichier BPMN."),
    ("contexte", "Identification", "Contexte d'exécution",
     "Comment l'extraction a été lancée : ligne de commande, application "
     "web, validation du corpus, catalogue de patterns, test."),
    ("arbitrages", "Identification", "Arbitrages appliqués",
     "Nombre de verdicts de l'expert appliqués (candidats + ressources + "
     "annotations + renommages) ; 0 = première extraction, sans arbitrage."),
    ("variante", "Identification", "Variante de l'algorithme",
     "« reference » pour l'algorithme de référence tel que défini ; sinon la liste "
     "des extensions activées."),
    ("version", "Identification", "Version de l'outil",
     "Version du transformateur ayant produit la ligne."),
    # modèle source
    ("vi_sommets", "Modèle source (Mi)", "|V_i| sommets de flux",
     "Activités + passerelles + événements."),
    ("activites", "Modèle source (Mi)", "|A| activités", "Toutes natures confondues."),
    ("activites_utilisateur", "Modèle source (Mi)", "Tâches utilisateur", "Type userTask."),
    ("activites_regle_metier", "Modèle source (Mi)", "Tâches de règle métier",
     "Type businessRuleTask."),
    ("activites_generiques", "Modèle source (Mi)", "Tâches génériques", "Type task."),
    ("activites_service", "Modèle source (Mi)", "Tâches de service", "Type serviceTask."),
    ("activites_autres", "Modèle source (Mi)", "Autres activités",
     "Envoi, réception, manuelles, script, appels d'activité, transactions."),
    ("sous_processus", "Modèle source (Mi)", "Sous-processus",
     "Sous-processus repliés (activités de Mi) + dépliés (contenu remonté)."),
    ("passerelles", "Modèle source (Mi)", "|G| passerelles", "Toutes natures."),
    ("passerelles_exclusives", "Modèle source (Mi)", "Passerelles exclusives", ""),
    ("passerelles_inclusives", "Modèle source (Mi)", "Passerelles inclusives", ""),
    ("passerelles_paralleles", "Modèle source (Mi)", "Passerelles parallèles", ""),
    ("passerelles_autres", "Modèle source (Mi)", "Autres passerelles",
     "Passerelles d'événements et complexes."),
    ("evenements", "Modèle source (Mi)", "|E_v| événements", "Toutes natures."),
    ("evenements_porteurs", "Modèle source (Mi)", "Événements porteurs",
     "Événements à définition message ou signal (candidats de P3)."),
    ("evenements_frontiere", "Modèle source (Mi)", "Événements-frontière", ""),
    ("objets_donnees", "Modèle source (Mi)", "|D_o| objets de données", ""),
    ("magasins_donnees", "Modèle source (Mi)", "|D_s| magasins de données", ""),
    ("annotations", "Modèle source (Mi)", "|A_no| annotations", ""),
    ("flux_sequence", "Modèle source (Mi)", "|E_s| flux de séquence", ""),
    ("flux_donnees", "Modèle source (Mi)", "|E_d| associations de données",
     "Lectures et écritures d'objets et de magasins."),
    ("associations_annotations", "Modèle source (Mi)", "Associations d'annotations", ""),
    ("couloirs", "Modèle source (Mi)", "Couloirs (ressources)",
     "Nombre de ressources distinctes portées par les activités (rho)."),
    ("anomalies_source", "Modèle source (Mi)", "Anomalies du modèle",
     "Défauts non bloquants relevés par le parseur."),
    # détection
    ("da_candidats", "Détection (DA, κ)", "|DA| candidats",
     "Activités du type décisionnel (tâches utilisateur, tâches de règle "
     "métier, sous-processus repliés)."),
    ("da_retenus", "Détection (DA, κ)", "|DA*| retenus",
     "Candidats corroborés par κ ou retenus par l'expert : les décisions du DRD."),
    ("da_position_seule", "Détection (DA, κ)", "Retenus par la position seule",
     "Indice de position (passerelle exclusive ou inclusive à la suite) sans verbe de décision."),
    ("da_lexical_seul", "Détection (DA, κ)", "Retenus par le lexique seul",
     "Verbe de décision du lexique Λ dans le libellé, sans passerelle."),
    ("da_deux_indices", "Détection (DA, κ)", "Retenus par les deux indices", ""),
    ("da_par_arbitrage", "Détection (DA, κ)", "Retenus par arbitrage",
     "Candidats sans indice, confirmés par l'expert."),
    ("da_non_corrobores", "Détection (DA, κ)", "Candidats non corroborés",
     "Candidats sans indice, soumis à l'expert (« est-ce une décision ? »)."),
    ("da_ecartes_arbitrage", "Détection (DA, κ)", "Candidats écartés par l'expert", ""),
    ("taux_corroboration", "Détection (DA, κ)", "Taux de corroboration",
     "|DA*| / |DA| (vide si aucun candidat)."),
    ("hors_definition", "Détection (DA, κ)", "Activités hors définition",
     "Tâches génériques, de service, d'envoi... corroborées par un indice : "
     "décisions de fait que la définition de référence ne couvre pas."),
    # DRD
    ("decisions", "DRD (Mf)", "|D| décisions", ""),
    ("donnees_entree", "DRD (Mf)", "|I| données d'entrée", ""),
    ("sources_connaissance", "DRD (Mf)", "|KS| sources de connaissance", ""),
    ("bkm", "DRD (Mf)", "|BKM| modèles de connaissance métier", ""),
    ("vf_sommets", "DRD (Mf)", "|V_f| sommets", "D + I + KS + BKM."),
    ("ef_exigences", "DRD (Mf)", "|E_f| exigences", "IR + KR + AR."),
    ("ir", "DRD (Mf)", "IR exigences d'information", ""),
    ("ir_donnee_decision", "DRD (Mf)", "IR donnée vers décision", ""),
    ("ir_decision_decision", "DRD (Mf)", "IR décision vers décision", "Arcs du pattern P4."),
    ("kr", "DRD (Mf)", "KR exigences de connaissance", ""),
    ("ar", "DRD (Mf)", "AR exigences d'autorité", ""),
    ("p2_objets", "Patterns", "P2 : objets de données", "Données d'entrée issues d'objets."),
    ("p2_magasins", "Patterns", "P2 : magasins de données", "Données d'entrée issues de magasins."),
    ("p3_evenements", "Patterns", "P3 : événements",
     "Données d'entrée issues d'événements porteurs."),
    ("p3_optionnels", "Patterns", "P3 : frontières non interruptrices",
     "Données d'entrée marquées « (optionnel) »."),
    ("p4_dependances", "Patterns", "P4 : dépendances entre décisions", ""),
    ("p5_sources", "Patterns", "P5 : sources issues de rôles", ""),
    ("p6_donnees", "Patterns", "P6 : annotations en donnée d'entrée", ""),
    ("p6_sources", "Patterns", "P6 : annotations en source de connaissance", ""),
    ("p6_bkm", "Patterns", "P6 : annotations en BKM", ""),
    # périmètre d'automatisation
    ("points_expert", "Périmètre d'automatisation", "Points soumis à l'expert", "Total."),
    ("pe_candidats", "Périmètre d'automatisation", "dont candidats",
     "« Cette activité est-elle vraiment une décision ? »"),
    ("pe_ressources", "Périmètre d'automatisation", "dont ressources",
     "« Ce rôle gouverne-t-il ou applique-t-il ? »"),
    ("pe_annotations", "Périmètre d'automatisation", "dont annotations",
     "« Cette annotation : donnée, autorité ou règle ? »"),
    ("pe_hors_definition", "Périmètre d'automatisation", "dont hors définition", ""),
    ("pe_circuits", "Périmètre d'automatisation", "dont circuits",
     "Dépendances mutuelles entre décisions, écartées par la garde d'acyclicité."),
    ("ecartes", "Périmètre d'automatisation", "Éléments écartés automatiquement", "Total."),
    ("ec_ressources", "Périmètre d'automatisation", "dont ressources (systèmes)", ""),
    ("ec_annotations", "Périmètre d'automatisation", "dont annotations non décisionnelles", ""),
    ("ec_candidats", "Périmètre d'automatisation", "dont candidats écartés par l'expert", ""),
    ("questions_par_decision", "Périmètre d'automatisation", "Questions par décision",
     "Points soumis à l'expert / |D| (vide si aucune décision)."),
    ("part_regles_fermees", "Périmètre d'automatisation", "Part des règles fermées",
     "Exigences produites par P2, P3 et P4 / |E_f| (vide si aucune exigence)."),
    ("part_regles_ouvertes", "Périmètre d'automatisation", "Part des règles ouvertes",
     "Exigences produites par P5 et P6 / |E_f|."),
    # vérification
    ("acyclique", "Vérification", "Graphe acyclique", "1 = oui, 0 = non."),
    ("invariants_violes", "Vérification", "Invariants violés",
     "Nombre d'invariants formels (sur 8) violés ; 0 attendu."),
    ("partition_exacte", "Vérification", "Partition exacte {IR, KR, AR}", "1 = oui."),
    ("dmn_relu_conforme", "Vérification", "DMN produit relu conforme",
     "1 si le fichier DMN relu restitue exactement Mf (vide si non vérifié)."),
    ("aller_retour", "Vérification", "Aller-retour T(T⁻¹(M)) = M",
     "1 si vérifié, 0 si écart, vide si non calculé."),
    ("ref_attendues", "Référence experte", "Décisions attendues",
     "Nombre de décisions de la référence experte (.gold) ; vide sans référence."),
    ("ref_detectees", "Référence experte", "Décisions détectées", ""),
    ("ref_correctes", "Référence experte", "Détections correctes", ""),
    ("ref_a_tort", "Référence experte", "Détections à tort", ""),
    ("ref_manquees", "Référence experte", "Décisions manquées", ""),
    ("precision", "Référence experte", "Précision", "Correctes / détectées."),
    ("rappel", "Référence experte", "Rappel", "Correctes / attendues."),
    # structure du DRD
    ("drd_densite", "Structure du DRD", "Densité",
     "|E_f| / (|V_f| (|V_f| - 1)) ; vide si moins de deux sommets."),
    ("drd_profondeur", "Structure du DRD", "Profondeur",
     "Longueur (en décisions) du plus long chemin de dépendance entre décisions ; "
     "1 = décisions indépendantes ; vide si le graphe n'est pas acyclique."),
    ("drd_degre_entrant_max", "Structure du DRD", "Degré entrant maximal",
     "Plus grand nombre d'exigences arrivant sur une même décision."),
    ("drd_degre_entrant_moyen", "Structure du DRD", "Degré entrant moyen",
     "|E_f| / |D| (vide si aucune décision)."),
    ("drd_decisions_racines", "Structure du DRD", "Décisions de tête",
     "Décisions dont aucune autre décision ne dépend."),
    ("drd_composantes", "Structure du DRD", "Composantes connexes",
     "Nombre de fragments indépendants dans (V_f, E_f)."),
    # durées
    ("duree_analyse_ms", "Durées", "Durée d'analyse (ms)", "Lecture du BPMN et construction de Mi."),
    ("duree_transformation_ms", "Durées", "Durée de transformation (ms)", "Exécution de T."),
    ("duree_serialisation_ms", "Durées", "Durée de sérialisation (ms)", "Écriture du DMN."),
    ("duree_totale_ms", "Durées", "Durée totale (ms)", ""),
]

NOMS_COLONNES = [c[0] for c in COLONNES]
COLONNES_IDENTIFICATION = ("experience", "horodatage", "code_modele", "fichier",
                           "modele", "contexte", "arbitrages", "variante",
                           "version")

_TYPES_ACTIVITES_AUTRES = {"sendTask", "receiveTask", "manualTask", "scriptTask",
                           "callActivity", "transaction", "adHocSubProcess"}


def _ratio(num: float, den: float, decimales: int = 3):
    return round(num / den, decimales) if den else ""


def mesurer(mi: Mi, mf: Mf, arbitrages=None, reference: Optional[List[str]] = None,
            dmn: Optional[str] = None, aller_retour: Optional[bool] = None,
            durees: Optional[Dict[str, float]] = None) -> "OrderedDict[str, object]":
    """Une ligne de mesures (sans les colonnes d'identification)."""
    ligne: "OrderedDict[str, object]" = OrderedDict((n, "") for n in NOMS_COLONNES)
    _mesurer_source(mi, ligne)
    _mesurer_detection(mi, mf, arbitrages, ligne)
    _mesurer_drd(mf, ligne)
    ventiler_p2(mi, mf, ligne)
    _mesurer_perimetre(mf, ligne)
    _mesurer_verification(mf, dmn, aller_retour, ligne)
    if reference is not None:
        _mesurer_reference(mi, mf, reference, ligne)
    _mesurer_structure(mf, ligne)
    for cle in ("analyse", "transformation", "serialisation", "totale"):
        valeur = (durees or {}).get(cle)
        if valeur is not None:
            ligne["duree_%s_ms" % cle] = round(float(valeur), 2)
    return ligne


def _mesurer_source(mi: Mi, ligne) -> None:
    activites = list(mi.activites.values())
    types = [a.type for a in activites]
    ligne["vi_sommets"] = len(mi.noeuds)
    ligne["activites"] = len(activites)
    ligne["activites_utilisateur"] = types.count("userTask")
    ligne["activites_regle_metier"] = types.count("businessRuleTask")
    ligne["activites_generiques"] = types.count("task")
    ligne["activites_service"] = types.count("serviceTask")
    ligne["activites_autres"] = sum(1 for t in types if t in _TYPES_ACTIVITES_AUTRES)
    replies = types.count("subProcess")
    deplies = len(set(mi.conteneur.values()))
    ligne["sous_processus"] = replies + deplies
    passerelles = [g.type for g in mi.passerelles.values()]
    ligne["passerelles"] = len(passerelles)
    ligne["passerelles_exclusives"] = passerelles.count("exclusiveGateway")
    ligne["passerelles_inclusives"] = passerelles.count("inclusiveGateway")
    ligne["passerelles_paralleles"] = passerelles.count("parallelGateway")
    ligne["passerelles_autres"] = (len(passerelles) - ligne["passerelles_exclusives"]
                                   - ligne["passerelles_inclusives"]
                                   - ligne["passerelles_paralleles"])
    evenements = list(mi.evenements.values())
    ligne["evenements"] = len(evenements)
    ligne["evenements_porteurs"] = sum(1 for e in evenements if e.porteur_donnees)
    ligne["evenements_frontiere"] = sum(1 for e in evenements if e.type == "boundaryEvent")
    categories = [d.categorie for d in mi.donnees.values()]
    ligne["objets_donnees"] = categories.count("objet")
    ligne["magasins_donnees"] = categories.count("magasin")
    ligne["annotations"] = categories.count("annotation")
    ligne["flux_sequence"] = len(mi.flux_sequence)
    assoc_annotations = 0
    for s, t in mi.flux_donnees:
        if (s in mi.donnees and mi.donnees[s].categorie == "annotation") or \
           (t in mi.donnees and mi.donnees[t].categorie == "annotation"):
            assoc_annotations += 1
    ligne["associations_annotations"] = assoc_annotations
    ligne["flux_donnees"] = len(mi.flux_donnees) - assoc_annotations
    ligne["couloirs"] = len({a.ressource for a in activites if a.ressource})
    ligne["anomalies_source"] = len(mi.anomalies)


def _mesurer_detection(mi: Mi, mf: Mf, arbitrages, ligne) -> None:
    candidats = [aid for aid, a in mi.activites.items()
                 if a.type in TYPES_DA or a.type == "subProcess"]
    verdicts = getattr(arbitrages, "candidats", {}) or {}
    position = lexical = deux = par_arbitrage = 0
    for aid in candidats:
        if aid not in mf.delta:
            continue
        indices = kappa(mi, aid)
        if indices["position"] and indices["lexical"]:
            deux += 1
        elif indices["position"]:
            position += 1
        elif indices["lexical"]:
            lexical += 1
        elif verdicts.get(aid) is True:
            par_arbitrage += 1
    ligne["da_candidats"] = len(candidats)
    ligne["da_retenus"] = len(mf.delta)
    ligne["da_position_seule"] = position
    ligne["da_lexical_seul"] = lexical
    ligne["da_deux_indices"] = deux
    ligne["da_par_arbitrage"] = par_arbitrage
    ligne["da_non_corrobores"] = sum(1 for p in mf.a_confirmer if p.categorie == "candidat")
    ligne["da_ecartes_arbitrage"] = sum(1 for p in mf.ecartes if p.categorie == "candidat")
    ligne["taux_corroboration"] = _ratio(len(mf.delta), len(candidats))
    ligne["hors_definition"] = sum(1 for p in mf.a_confirmer
                                   if p.categorie == "hors-definition")


def _mesurer_drd(mf: Mf, ligne) -> None:
    ligne["decisions"] = len(mf.decisions)
    ligne["donnees_entree"] = len(mf.inputs)
    ligne["sources_connaissance"] = len(mf.sources)
    ligne["bkm"] = len(mf.bkms)
    ligne["vf_sommets"] = len(mf.noeuds)
    ligne["ef_exigences"] = len(mf.arcs)
    ir = mf.IR
    ligne["ir"] = len(ir)
    ligne["ir_decision_decision"] = sum(1 for u, _ in ir if mf.noeuds[u].type == DECISION)
    ligne["ir_donnee_decision"] = len(ir) - ligne["ir_decision_decision"]
    ligne["kr"] = len(mf.KR)
    ligne["ar"] = len(mf.AR)
    ligne["p2_objets"] = ligne["p2_magasins"] = 0
    ligne["p3_evenements"] = ligne["p3_optionnels"] = 0
    ligne["p5_sources"] = ligne["p6_donnees"] = ligne["p6_sources"] = ligne["p6_bkm"] = 0
    for n in mf.noeuds.values():
        if n.pattern == "P2":
            # l'origine est un objet ou un magasin : le nom du nœud Mf ne le
            # dit pas, la catégorie est relue sur l'identifiant d'origine
            ligne["p2_objets"] += 1
        elif n.pattern == "P3":
            ligne["p3_evenements"] += 1
            if n.nom.endswith("(optionnel)"):
                ligne["p3_optionnels"] += 1
        elif n.pattern == "P5":
            ligne["p5_sources"] += 1
        elif n.pattern == "P6":
            if n.type == INPUT_DATA:
                ligne["p6_donnees"] += 1
            elif n.type == KNOWLEDGE_SOURCE:
                ligne["p6_sources"] += 1
            elif n.type == BKM:
                ligne["p6_bkm"] += 1
    ligne["p4_dependances"] = sum(1 for a in mf.arcs if mf.arcs_origine.get(a) == "P4")


def ventiler_p2(mi: Mi, mf: Mf, ligne) -> None:
    """Sépare, parmi les données d'entrée du pattern P2, celles issues
    d'objets de données de celles issues de magasins (l'information est
    dans Mi, pas dans Mf)."""
    objets = magasins = 0
    for n in mf.noeuds.values():
        if n.pattern != "P2":
            continue
        source = mi.donnees.get(n.origine)
        if source is not None and source.categorie == "magasin":
            magasins += 1
        else:
            objets += 1
    ligne["p2_objets"], ligne["p2_magasins"] = objets, magasins


def _mesurer_perimetre(mf: Mf, ligne) -> None:
    def compter(points, categorie):
        return sum(1 for p in points if p.categorie == categorie)
    ligne["points_expert"] = len(mf.a_confirmer)
    ligne["pe_candidats"] = compter(mf.a_confirmer, "candidat")
    ligne["pe_ressources"] = compter(mf.a_confirmer, "ressource")
    ligne["pe_annotations"] = compter(mf.a_confirmer, "annotation")
    ligne["pe_hors_definition"] = compter(mf.a_confirmer, "hors-definition")
    ligne["pe_circuits"] = compter(mf.a_confirmer, "circuit")
    ligne["ecartes"] = len(mf.ecartes)
    ligne["ec_ressources"] = compter(mf.ecartes, "ressource")
    ligne["ec_annotations"] = compter(mf.ecartes, "annotation")
    ligne["ec_candidats"] = compter(mf.ecartes, "candidat")
    ligne["questions_par_decision"] = _ratio(len(mf.a_confirmer), len(mf.decisions), 2)
    fermees = sum(1 for a in mf.arcs if mf.arcs_origine.get(a) in ("P2", "P3", "P4"))
    ouvertes = sum(1 for a in mf.arcs if mf.arcs_origine.get(a) in ("P5", "P6"))
    ligne["part_regles_fermees"] = _ratio(fermees, len(mf.arcs))
    ligne["part_regles_ouvertes"] = _ratio(ouvertes, len(mf.arcs))


def _mesurer_verification(mf: Mf, dmn: Optional[str], aller_retour: Optional[bool],
                          ligne) -> None:
    ligne["acyclique"] = 1 if mf.acyclique() else 0
    ligne["invariants_violes"] = len(verifier_invariants(mf))
    ligne["partition_exacte"] = 1 if mf.partition_exacte() else 0
    if dmn is not None:
        ligne["dmn_relu_conforme"] = 0 if verifier_dmn_serialise(dmn, mf) else 1
    if aller_retour is not None:
        ligne["aller_retour"] = 1 if aller_retour else 0


def _mesurer_reference(mi: Mi, mf: Mf, reference: List[str], ligne) -> None:
    """La référence experte nomme des activités du modèle source : la
    comparaison porte sur le libellé d'origine de chaque décision, un
    renommage par l'expert ne doit pas passer pour une erreur."""
    noms = [mi.noeuds[n.origine].nom if n.origine in mi.noeuds else n.nom
            for n in mf.decisions]
    m = mesurer_decisions(noms, reference)
    ligne["ref_attendues"] = m["attendues"]
    ligne["ref_detectees"] = m["detectees"]
    ligne["ref_correctes"] = m["vraies"]
    ligne["ref_a_tort"] = len(m["a_tort"])
    ligne["ref_manquees"] = len(m["manquees"])
    ligne["precision"] = round(m["precision"], 3)
    ligne["rappel"] = round(m["rappel"], 3)


def _mesurer_structure(mf: Mf, ligne) -> None:
    n_sommets = len(mf.noeuds)
    ligne["drd_densite"] = (_ratio(len(mf.arcs), n_sommets * (n_sommets - 1), 4)
                            if n_sommets >= 2 else "")
    entrants: Dict[str, int] = {d.id: 0 for d in mf.decisions}
    for _, v in mf.arcs:
        if v in entrants:
            entrants[v] += 1
    ligne["drd_degre_entrant_max"] = max(entrants.values()) if entrants else 0
    ligne["drd_degre_entrant_moyen"] = _ratio(sum(entrants.values()), len(entrants), 2)
    sortants_vers_decision = {d.id: 0 for d in mf.decisions}
    for u, v in mf.arcs:
        if u in sortants_vers_decision and mf.noeuds[v].type == DECISION:
            sortants_vers_decision[u] += 1
    ligne["drd_decisions_racines"] = sum(1 for k in sortants_vers_decision.values()
                                         if k == 0)
    ligne["drd_profondeur"] = _profondeur(mf) if mf.acyclique() else ""
    ligne["drd_composantes"] = _composantes(mf)


def _profondeur(mf: Mf) -> int:
    """Nombre de décisions sur le plus long chemin de dépendance."""
    decisions = [d.id for d in mf.decisions]
    if not decisions:
        return 0
    pred: Dict[str, List[str]] = {d: [] for d in decisions}
    for u, v in mf.arcs:
        if u in pred and v in pred:
            pred[v].append(u)
    memo: Dict[str, int] = {}
    for d in decisions:
        pile = [d]
        while pile:
            x = pile[-1]
            if x in memo:
                pile.pop()
                continue
            manquants = [p for p in pred[x] if p not in memo]
            if manquants:
                pile.extend(manquants)
            else:
                memo[x] = 1 + max((memo[p] for p in pred[x]), default=0)
                pile.pop()
    return max(memo.values())


def _composantes(mf: Mf) -> int:
    parent = {n: n for n in mf.noeuds}

    def racine(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for u, v in mf.arcs:
        ru, rv = racine(u), racine(v)
        if ru != rv:
            parent[ru] = rv
    return len({racine(n) for n in parent})
