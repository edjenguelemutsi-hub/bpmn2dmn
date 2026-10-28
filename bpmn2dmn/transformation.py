# -*- coding: utf-8 -*-
"""
La transformation T : Mi -> Mf, algorithme de référence raffiné.

Les six patterns P1..P6 sont appliqués avec les quatre raffinements du
cadre formel : le prédicat de corroboration kappa, DA* = {a ∈ DA | κ(a)},
les candidats non corroborés étant soumis à l'expert et non supprimés ;
P2 raffiné, qui exclut des données d'entrée les sorties de décisions
Outs(DA*) ; P4 raffiné (« ordonner n'est pas alimenter »), où l'arc d1 -> d2
exige a1 ⪯_s a2 et Outs(a1) ∩ Ins(a2) non vide ; enfin les fonctions de
qualification omega (P5) et gamma (P6), proposées, tracées et arbitrables.
Delta et iota sont injectives : un nœud déjà créé n'est jamais dupliqué.

La fonction `transformer` déroule l'algorithme ligne à ligne ; chaque étape
est une méthode de `_Construction`, qui porte l'état partagé (Mi, Mf en
cours, arbitrages, registres d'injectivité et graphes précalculés).
"""
from __future__ import annotations

import copy
import re
from typing import Dict, FrozenSet, Iterable, List, Set, Tuple

from .extensions import normaliser_extensions
from .metamodeles import (BKM, DECISION, INPUT_DATA, KNOWLEDGE_SOURCE,
                          Mf, Mi, NoeudDonnees, NoeudMf, PointExpert)
from .qualification import (Arbitrages, VIDE, gamma, indice_gouvernance,
                            kappa, normaliser, omega)

TYPES_DA = ("businessRuleTask", "userTask")   # définition de DA (+ subProcess replié)

LIBELLES_TYPES = {"businessRuleTask": "tâche de règle métier",
                  "userTask": "tâche utilisateur",
                  "subProcess": "sous-processus"}

TYPES_EVENEMENTS_P3 = ("startEvent", "intermediateCatchEvent", "boundaryEvent")

# activités hors de la définition des candidates, nommées pour le diagnostic d'un DRD vide
LIBELLES_HORS_DEFINITION = {
    "task": ("tâche générique", "tâches génériques"),
    "serviceTask": ("tâche de service", "tâches de service"),
    "sendTask": ("tâche d'envoi", "tâches d'envoi"),
    "receiveTask": ("tâche de réception", "tâches de réception"),
    "manualTask": ("tâche manuelle", "tâches manuelles"),
    "scriptTask": ("tâche de script", "tâches de script"),
    "callActivity": ("appel d'activité", "appels d'activité"),
}


def _libelle(nom: str, defaut: str) -> str:
    return nom.strip() if nom and nom.strip() else defaut


class _Fabrique:
    """Attribution d'identifiants stables et déterministes (D1, I1, K1, B1...)."""
    PREFIXES = {DECISION: "D", INPUT_DATA: "I",
                KNOWLEDGE_SOURCE: "K", BKM: "B"}

    def __init__(self, mf: Mf):
        self.mf = mf
        self.compteurs = {t: 0 for t in self.PREFIXES}

    def creer(self, type_: str, nom: str, origine: str, pattern: str) -> str:
        self.compteurs[type_] += 1
        nid = "%s%d" % (self.PREFIXES[type_], self.compteurs[type_])
        self.mf.noeuds[nid] = NoeudMf(id=nid, type=type_, nom=nom,
                                      origine=origine, pattern=pattern)
        return nid


class _Atteignabilite:
    """Relation ⪯_s sur le graphe de séquence, mémoïsée : une seule
    exploration par nœud de départ, en O(|V_i| + |E_s|), ce qui compte sur
    les très grands modèles (P2 raffiné, P3 et P4 la partagent)."""

    def __init__(self, mi: Mi):
        self.adjacence: Dict[str, List[str]] = {}
        for s, t, _ in mi.flux_sequence:
            self.adjacence.setdefault(s, []).append(t)
        self._atteints: Dict[str, Set[str]] = {}

    def successeurs(self, nid: str) -> List[str]:
        return self.adjacence.get(nid, [])

    def atteints(self, depart: str) -> Set[str]:
        """Les nœuds atteignables depuis `depart` par les flux de séquence."""
        if depart not in self._atteints:
            vus: Set[str] = set()
            pile = list(self.adjacence.get(depart, []))
            while pile:
                u = pile.pop()
                if u in vus:
                    continue
                vus.add(u)
                pile.extend(self.adjacence.get(u, []))
            self._atteints[depart] = vus
        return self._atteints[depart]


def transformer(mi: Mi, arbitrages: Arbitrages = VIDE,
                extensions: Iterable[str] = frozenset()) -> Mf:
    """Exécute la transformation T : Mi -> Mf. Sans extension, c'est
    l'algorithme de référence ; chaque extension (voir extensions.py)
    ajoute une règle, activable une à une."""
    ext = normaliser_extensions(list(extensions)) if extensions else frozenset()
    construction = _Construction(_mi_etendu(mi, ext), arbitrages, ext)

    candidats = construction.extraire_candidats()          # lignes 2 à 4 : DA
    retenus = construction.corroborer(candidats)            # DA* = {a ∈ DA | κ(a)}
    construction.preparer_graphes(retenus)

    for aid in retenus:                                     # lignes 5 à 20 : V_f
        did = construction.creer_decision(aid)              # P1
        construction.relier_donnees_lues(aid, did)          # P2 raffiné
        construction.relier_evenements(aid, did)            # P3
        construction.relier_ressource(aid, did)             # P5 raffiné
        construction.relier_annotations(aid, did)           # P6
        construction.relier_conditions(aid, did)            # P7 (extension)

    construction.relier_decisions_amont(retenus)            # lignes 21 à 30 : P4
    construction.suggerer_noms(retenus)                     # extension
    construction.preparer_logique(retenus)                  # extension
    construction.dedoublonner_points_experts()
    construction.mf.extensions = tuple(sorted(ext))
    return construction.mf


def _mi_etendu(mi: Mi, ext: FrozenSet[str]) -> Mi:
    """Les extensions « donnees-processus » et « evenements-conditionnels »
    élargissent la lecture du modèle : elles travaillent sur une copie de
    Mi, le modèle lu par le parseur restant celui de référence."""
    if not ({"donnees-processus", "evenements-conditionnels"} & ext):
        return mi
    m = copy.copy(mi)
    m.noeuds = dict(mi.noeuds)
    m.donnees = dict(mi.donnees)
    m.flux_donnees = list(mi.flux_donnees)
    m.anomalies = list(mi.anomalies)
    if "donnees-processus" in ext:
        adoptees: Set[str] = set()
        for s, t in mi.flux_donnees_ecartes:
            for x in (s, t):
                if x in mi.donnees_processus and x not in m.donnees:
                    m.donnees[x] = NoeudDonnees(
                        id=x, categorie="objet",
                        nom=mi.donnees_processus[x] or x)
                    adoptees.add(x)
        connus = set(m.noeuds) | set(m.donnees)
        for s, t in mi.flux_donnees_ecartes:
            if s in connus and t in connus and (s, t) not in m.flux_donnees:
                m.flux_donnees.append((s, t))
        m.anomalies = [a for a in m.anomalies
                       if not any("« %s »" % x in a for x in adoptees)]
    if "evenements-conditionnels" in ext:
        for eid, definitions in mi.definitions_evenements.items():
            n = m.noeuds.get(eid)
            if n is not None and not n.porteur_donnees \
               and "conditionalEventDefinition" in definitions:
                n2 = copy.copy(n)
                n2.porteur_donnees = True
                m.noeuds[eid] = n2
    return m


# mots réservés et opérateurs des langages d'expression usuels (FEEL,
# JUEL de Camunda, JavaScript, Groovy), à ne pas prendre pour des variables
_MOTS_RESERVES = {
    "and", "or", "not", "true", "false", "null", "if", "then", "else", "in",
    "between", "instance", "of", "return", "function", "var", "let", "const",
    "new", "typeof", "eq", "ne", "lt", "le", "gt", "ge", "div", "mod",
    "empty", "some", "every", "satisfies", "for", "is", "date", "time",
    "duration", "string", "number", "boolean", "execution", "task",
}

_LITTERAUX = re.compile(r'"[^"]*"|' + r"'[^']*'")
_IDENTIFIANT = re.compile(r"[A-Za-z_\u00C0-\u017F][\w.\u00C0-\u017F]*")


def _variables_condition(texte: str) -> List[str]:
    """Les identifiants lus dans une expression de condition : `${...}`
    et `#{...}` de Camunda sont ouverts, les littéraux (chaînes, nombres),
    les mots réservés et les appels de fonction écartés, l'ordre
    d'apparition conservé."""
    if not texte:
        return []
    t = re.sub(r"[$#]\{(.*?)\}", r" \1 ", texte, flags=re.S)
    t = _LITTERAUX.sub(" ", t)
    vus: List[str] = []
    for m in _IDENTIFIANT.finditer(t):
        ident = m.group(0).rstrip(".")
        if t[m.end():].lstrip().startswith("("):
            continue                                  # appel de fonction
        if ident.lower() in _MOTS_RESERVES or ident.replace(".", "").isdigit():
            continue
        if ident not in vus:
            vus.append(ident)
    return vus


class _Construction:
    """État partagé d'une exécution de T et ses étapes."""

    def __init__(self, mi: Mi, arbitrages: Arbitrages,
                 extensions: FrozenSet[str] = frozenset()):
        self.mi = mi
        self.arbitrages = arbitrages
        self.ext = extensions
        self.candidats_etendus: Set[str] = set()   # extension definition-etendue
        self.mf = Mf(nom=mi.nom)
        self.fab = _Fabrique(self.mf)
        self.sequence = _Atteignabilite(mi)
        # registres d'injectivité des sources et BKM (delta et iota sont
        # portés par Mf lui-même)
        self.ks_par_nom: Dict[str, str] = {}          # P5, une par ressource
        self.ks_par_annotation: Dict[str, str] = {}   # P6, une par annotation
        self.bkm_par_annotation: Dict[str, str] = {}  # P6, un par annotation
        # graphes précalculés (voir preparer_graphes)
        self.ins_de: Dict[str, Set[str]] = {}
        self.outs_de: Dict[str, Set[str]] = {}
        self.producteurs: Dict[str, List[str]] = {}
        self.evenements_de: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # étape 1 : extraction et corroboration
    # ------------------------------------------------------------------
    def extraire_candidats(self) -> List[str]:
        """DA : les activités de type décisionnel selon la définition de
        référence. Une tâche de
        service ou un appel d'activité corroborés sont hors de la définition
        de référence : ils sont signalés au titre d'OS1, non retenus."""
        mi, mf = self.mi, self.mf
        DA: List[str] = []
        for aid, a in mi.activites.items():
            if a.type in TYPES_DA or a.type == "subProcess":
                DA.append(aid)
            elif "definition-etendue" in self.ext \
                    and a.type in LIBELLES_HORS_DEFINITION \
                    and any(kappa(mi, aid).values()):
                # DA_ext = DA ∪ {a ∈ A | τ(a) ∉ types DA ∧ κ(a)} : l'activité
                # devient candidate, sa corroboration exige les deux indices
                DA.append(aid)
                self.candidats_etendus.add(aid)
            elif a.type == "serviceTask" and any(kappa(mi, aid).values()):
                mf.a_confirmer.append(PointExpert(
                    cle=aid, categorie="hors-definition",
                    objet=_libelle(a.nom, aid),
                    motif="tâche de SERVICE corroborée par un indice de décision : "
                          "décision de fait, non couverte par la définition de "
                          "référence"))
            elif a.type == "callActivity" and any(kappa(mi, aid).values()):
                mf.a_confirmer.append(PointExpert(
                    cle=aid, categorie="hors-definition",
                    objet=_libelle(a.nom, aid),
                    motif="APPEL D'ACTIVITÉ corroboré par un indice de décision : "
                          "non couvert par la définition de référence"))
            elif a.type in LIBELLES_HORS_DEFINITION and any(kappa(mi, aid).values()):
                # tâche générique, d'envoi, manuelle... : même angle mort
                mf.a_confirmer.append(PointExpert(
                    cle=aid, categorie="hors-definition",
                    objet=_libelle(a.nom, aid),
                    motif="%s corroborée par un indice de décision, hors de "
                          "la définition de référence : si une décision y est "
                          "prise, retypez-la en tâche utilisateur ou en tâche "
                          "de règle métier dans votre outil de modélisation"
                          % LIBELLES_HORS_DEFINITION[a.type][0].upper()))
        return DA

    def corroborer(self, DA: List[str]) -> List[str]:
        """DA* : les candidats corroborés par kappa (position ou lexique) ou
        retenus par l'expert ; les autres lui sont soumis, jamais supprimés."""
        mi, mf = self.mi, self.mf
        DA_etoile: List[str] = []
        for aid in DA:
            a = mi.noeuds[aid]
            verdict_expert = self.arbitrages.candidats.get(aid)
            indices = kappa(mi, aid)
            if verdict_expert is True:
                DA_etoile.append(aid)
            elif verdict_expert is False:
                mf.ecartes.append(PointExpert(
                    cle=aid, categorie="candidat", objet=_libelle(a.nom, aid),
                    motif="écarté par arbitrage de l'expert"))
            elif aid in self.candidats_etendus:
                if indices["position"] and indices["lexical"]:
                    DA_etoile.append(aid)
                else:
                    type_ = LIBELLES_HORS_DEFINITION[a.type][0]
                    indice = ("précède une passerelle de choix"
                              if indices["position"]
                              else "porte un verbe de décision")
                    mf.a_confirmer.append(PointExpert(
                        cle=aid, categorie="candidat", objet=_libelle(a.nom, aid),
                        motif="%s hors de la définition de référence, mais "
                              "elle %s : une décision y est-elle prise ?"
                              % (type_[0].upper() + type_[1:], indice),
                        proposition="décision si l'expert confirme"))
            elif indices["position"] or indices["lexical"]:
                DA_etoile.append(aid)
            else:
                base = LIBELLES_TYPES.get(a.type, a.type)
                mf.a_confirmer.append(PointExpert(
                    cle=aid, categorie="candidat", objet=_libelle(a.nom, aid),
                    motif=base + " : rien n'indique qu'une décision y est prise "
                          "(pas de verbe de décision dans son nom, pas de "
                          "passerelle de choix à sa suite) — est-ce une "
                          "décision ?"))
        return DA_etoile

    def preparer_graphes(self, DA_etoile: List[str]) -> None:
        """Précalculs partagés par P2, P3 et P4 : Ins et Outs de chaque
        décision retenue (sinon le parcours des paires redevient
        quadratique en |E_d|), producteurs de chaque donnée, et événements
        liés à chaque activité."""
        mi = self.mi
        self.ins_de = {a: set(mi.entrees_donnees(a)) for a in DA_etoile}
        self.outs_de = {a: set(mi.sorties_donnees(a)) for a in DA_etoile}
        self.producteurs = {}
        for aid in DA_etoile:
            for dnid in self.outs_de[aid]:
                self.producteurs.setdefault(dnid, []).append(aid)
        self.evenements_de = self._evenements_lies()

    def _evenements_lies(self) -> Dict[str, List[str]]:
        """Événements liés à chaque activité (successeur immédiat ou
        frontière), dans l'ordre de E_v ; une frontière posée sur la façade
        d'un sous-processus déplié vaut pour chaque nœud qu'il contenait."""
        mi = self.mi
        evenements_de: Dict[str, List[str]] = {}
        contenu_de: Dict[str, List[str]] = {}
        for eid in mi.evenements:
            hotes = list(self.sequence.successeurs(eid))
            hote = mi.beta.get(eid)
            if hote is not None:
                hotes.append(hote)
                if hote not in contenu_de:
                    contenu_de[hote] = mi.contenu(hote)
                hotes.extend(contenu_de[hote])
            for h in hotes:
                lies = evenements_de.setdefault(h, [])
                if eid not in lies:
                    lies.append(eid)
        return evenements_de

    def _produite_en_amont(self, dnid: str, aid: str) -> bool:
        """Une décision amont distincte produit dnid : P4 posera l'arc
        décision -> décision, la donnée ne devient pas une donnée d'entrée.
        Sans producteur amont (branches parallèles, lecture avant écriture),
        la donnée est lue de l'extérieur et P2 s'applique."""
        return any(a2 != aid and aid in self.sequence.atteints(a2)
                   for a2 in self.producteurs.get(dnid, ()))

    def _ajouter_arc(self, u: str, v: str, pattern: str) -> None:
        """Arc u -> v de E_f, tracé par son pattern ; jamais dupliqué."""
        arc = (u, v)
        if arc not in self.mf.arcs:
            self.mf.arcs.append(arc)
            self.mf.arcs_origine[arc] = pattern

    # ------------------------------------------------------------------
    # étape 2 : création des sommets V_f, décision par décision
    # ------------------------------------------------------------------
    def creer_decision(self, aid: str) -> str:
        """P1 : la décision delta(a), avec le motif de sa corroboration."""
        mi, mf = self.mi, self.mf
        a = mi.noeuds[aid]
        motifs = kappa(mi, aid)
        motif_txt = " + ".join(
            m for m, ok in (("précède une passerelle exclusive",
                             motifs["position"]),
                            ("verbe décisionnel dans le libellé",
                             motifs["lexical"])) if ok) \
            or "retenue par arbitrage de l'expert"
        if aid in self.candidats_etendus:
            motif_txt += " ; %s hors de la définition de référence, retenue " \
                         "par l'extension « definition-etendue »" \
                         % LIBELLES_HORS_DEFINITION.get(a.type, (a.type,))[0]
        nom_d = self.arbitrages.renommages.get(
            aid, _libelle(a.nom, "Décision " + aid))
        did = self.fab.creer(DECISION, nom_d, origine=aid, pattern="P1")
        mf.delta[aid] = did
        mf.motifs_corroboration[did] = motif_txt
        return did

    def relier_donnees_lues(self, aid: str, did: str) -> None:
        """P2 raffiné : nœuds de données lus, hors celles qu'une décision
        amont produit (elles porteront un IR décision -> décision)."""
        mi, mf = self.mi, self.mf
        for dnid in mi.entrees_donnees(aid):
            if self._produite_en_amont(dnid, aid):
                continue
            if dnid not in mf.iota:
                dn = mi.donnees[dnid]
                mf.iota[dnid] = self.fab.creer(
                    INPUT_DATA, _libelle(dn.nom, dnid),
                    origine=dnid, pattern="P2")
            self._ajouter_arc(mf.iota[dnid], did, "P2")

    def relier_evenements(self, aid: str, did: str) -> None:
        """P3 : seuls les événements porteurs (définition message ou signal)
        produisent une donnée d'entrée ; une frontière non interruptrice
        non porteuse (minuterie...) ne produit rien. Le suffixe
        « (optionnel) » marque les frontières non interruptrices porteuses
        (cas « Free time slot » du modèle BPCO)."""
        mi, mf = self.mi, self.mf
        for eid in self.evenements_de.get(aid, ()):
            e = mi.noeuds[eid]
            optionnel = (e.type == "boundaryEvent" and not e.interrompt)
            if not e.porteur_donnees:
                continue
            if e.type not in TYPES_EVENEMENTS_P3:
                continue
            if eid not in mf.iota:
                nom_i = _libelle(e.nom, "Événement")
                if optionnel:
                    nom_i += " (optionnel)"
                mf.iota[eid] = self.fab.creer(INPUT_DATA, nom_i,
                                              origine=eid, pattern="P3")
            self._ajouter_arc(mf.iota[eid], did, "P3")

    def relier_ressource(self, aid: str, did: str) -> None:
        """P5 raffiné : la ressource rho(a), qualifiée par omega ; une source
        de connaissance si elle gouverne, écartée si elle ne fait
        qu'appliquer, soumise à l'expert sinon."""
        a = self.mi.noeuds[aid]
        mf = self.mf
        if not a.ressource:
            return
        verdict = omega(a.ressource, self.arbitrages)
        if verdict == "KS":
            if a.ressource not in self.ks_par_nom:
                self.ks_par_nom[a.ressource] = self.fab.creer(
                    KNOWLEDGE_SOURCE, a.ressource,
                    origine=aid, pattern="P5")
            self._ajouter_arc(self.ks_par_nom[a.ressource], did, "P5")
        elif verdict == "non":
            arbitre_r = a.ressource in self.arbitrages.ressources
            mf.ecartes.append(PointExpert(
                cle="ressource:" + a.ressource, categorie="ressource",
                objet=a.ressource,
                motif="écartée par arbitrage de l'expert (elle applique "
                      "la règle sans la gouverner)" if arbitre_r
                else "un système exécute, il ne gouverne pas"))
        elif "roles-gouvernants" in self.ext and indice_gouvernance(a.ressource):
            # la source est proposée et posée, comme gamma le fait pour une
            # annotation d'autorité ; l'expert peut encore l'écarter
            if a.ressource not in self.ks_par_nom:
                self.ks_par_nom[a.ressource] = self.fab.creer(
                    KNOWLEDGE_SOURCE, a.ressource,
                    origine=aid, pattern="P5")
            self._ajouter_arc(self.ks_par_nom[a.ressource], did, "P5")
            mf.a_confirmer.append(PointExpert(
                cle="ressource:" + a.ressource, categorie="ressource",
                objet=a.ressource,
                motif="proposée comme SOURCE DE CONNAISSANCE : son nom "
                      "désigne une instance qui gouverne (extension "
                      "« roles-gouvernants »)",
                proposition="KS (indice lexical)"))
        else:
            mf.a_confirmer.append(PointExpert(
                cle="ressource:" + a.ressource, categorie="ressource",
                objet=a.ressource,
                motif="gouverne-t-elle la décision, ou se contente-t-elle "
                      "de l'appliquer ?",
                proposition="KS si elle gouverne"))

    def relier_annotations(self, aid: str, did: str) -> None:
        """P6 : les annotations associées, qualifiées par gamma. Le nœud
        produit porte le texte complet de l'annotation et deux annotations
        distinctes ne fusionnent jamais, même homonymes (injectivité de
        iota) ; la version tronquée `court` ne sert qu'à l'affichage des
        points experts."""
        mi, mf, arbitrages = self.mi, self.mf, self.arbitrages
        for anid in mi.annotations_de(aid):
            an = mi.donnees[anid]
            texte = an.nom
            court = (texte[:60] + "…") if len(texte) > 60 else texte
            verdict = gamma(anid, texte, arbitrages)
            arbitre = anid in arbitrages.annotations
            if verdict == "I":
                if anid not in mf.iota:
                    nom_i = arbitrages.noms.get(anid, texte)
                    mf.iota[anid] = self.fab.creer(INPUT_DATA, nom_i,
                                                   origine=anid, pattern="P6")
                self._ajouter_arc(mf.iota[anid], did, "P6")
            elif verdict == "KS":
                if anid not in self.ks_par_annotation:
                    nom_k = arbitrages.noms.get(anid, texte)
                    self.ks_par_annotation[anid] = self.fab.creer(
                        KNOWLEDGE_SOURCE, nom_k, origine=anid, pattern="P6")
                self._ajouter_arc(self.ks_par_annotation[anid], did, "P6")
                if not arbitre:
                    mf.a_confirmer.append(PointExpert(
                        cle=anid, categorie="annotation", objet=court,
                        motif="proposée comme SOURCE DE CONNAISSANCE "
                              "(elle gouverne la décision)",
                        proposition="KS"))
            elif verdict == "BKM":
                if anid not in self.bkm_par_annotation:
                    nom_b = arbitrages.noms.get(anid, "Règle : " + texte)
                    self.bkm_par_annotation[anid] = self.fab.creer(
                        BKM, nom_b, origine=anid, pattern="P6")
                self._ajouter_arc(self.bkm_par_annotation[anid], did, "P6")
                if not arbitre:
                    mf.a_confirmer.append(PointExpert(
                        cle=anid, categorie="annotation", objet=court,
                        motif="proposée comme MODÈLE DE CONNAISSANCE MÉTIER "
                              "(règle exécutable)",
                        proposition="BKM"))
            elif verdict == "non":
                mf.ecartes.append(PointExpert(
                    cle=anid, categorie="annotation", objet=court,
                    motif="aucune valeur décisionnelle"))
            else:
                mf.a_confirmer.append(PointExpert(
                    cle=anid, categorie="annotation", objet=court,
                    motif="NON TRANCHÉ : donnée d'entrée ou source de "
                          "connaissance ?",
                    proposition="I ou KS"))

    # ------------------------------------------------------------------
    # extensions : conditions des passerelles, noms suggérés, logique
    # ------------------------------------------------------------------
    def _passerelles_de_verdict(self, aid: str) -> List[str]:
        """Les passerelles exclusives ou inclusives qui suivent l'activité,
        en cascade (une passerelle peut en alimenter une autre)."""
        mi = self.mi
        trouvees: List[str] = []
        pile = list(self.sequence.successeurs(aid))
        vus: Set[str] = set()
        while pile:
            g = pile.pop(0)
            n = mi.noeuds.get(g)
            if g in vus or n is None or n.nature != "passerelle":
                continue
            vus.add(g)
            if n.type in ("exclusiveGateway", "inclusiveGateway"):
                trouvees.append(g)
            pile.extend(self.sequence.successeurs(g))
        return trouvees

    def relier_conditions(self, aid: str, did: str) -> None:
        """P7 (extension « conditions-passerelle ») : les variables lues
        dans les conditions des flux sortants des passerelles qui suivent
        la décision sont proposées comme données d'entrée ; une variable
        arbitrée « I » devient une donnée d'entrée, une seule par variable
        (injectivité), reliée par une exigence d'information."""
        if "conditions-passerelle" not in self.ext:
            return
        mi, mf, arbitrages = self.mi, self.mf, self.arbitrages
        deja = {normaliser(mi.donnees[d].nom) for d in self.ins_de.get(aid, ())
                if d in mi.donnees}
        deja |= {normaliser(mf.noeuds[u].nom) for u, v in mf.arcs if v == did}
        for g in self._passerelles_de_verdict(aid):
            for s, t, _ in mi.flux_sequence:
                if s != g:
                    continue
                condition = mi.conditions.get((g, t), "")
                for variable in _variables_condition(condition):
                    if normaliser(variable) in deja \
                       or normaliser(variable.replace(".", " ")) in deja:
                        continue
                    cle = "condition:" + variable
                    verdict = arbitrages.annotations.get(cle)
                    if verdict == "I":
                        if cle not in mf.iota:
                            mf.iota[cle] = self.fab.creer(
                                INPUT_DATA, arbitrages.noms.get(cle, variable),
                                origine=g, pattern="P7")
                        self._ajouter_arc(mf.iota[cle], did, "P7")
                    elif verdict == "non":
                        mf.ecartes.append(PointExpert(
                            cle=cle, categorie="condition", objet=variable,
                            motif="écartée par arbitrage de l'expert"))
                    else:
                        mf.a_confirmer.append(PointExpert(
                            cle=cle, categorie="condition", objet=variable,
                            motif="variable lue dans la condition « %s » de la "
                                  "passerelle « %s » : est-ce une donnée "
                                  "d'entrée de la décision « %s » ?"
                                  % (condition[:60], _libelle(mi.noeuds[g].nom, g),
                                     mf.noeuds[did].nom),
                            proposition="I"))

    def suggerer_noms(self, DA_etoile: List[str]) -> None:
        """Extension « noms-suggeres » : une décision retenue par la seule
        position reçoit un nom proposé d'après la question de la passerelle
        qui la suit ; delta n'est modifié que par un renommage de l'expert."""
        if "noms-suggeres" not in self.ext:
            return
        mi, mf = self.mi, self.mf
        for aid in DA_etoile:
            indices = kappa(mi, aid)
            if not indices["position"] or indices["lexical"] \
               or aid in self.arbitrages.renommages:
                continue
            for g in self._passerelles_de_verdict(aid):
                question = (mi.noeuds[g].nom or "").strip()
                if not question:
                    continue
                if question.endswith("?"):
                    corps = question[:-1].strip()
                    corps = corps[:1].lower() + corps[1:]
                    mf.suggestions_noms[aid] = "Décider si " + corps
                else:
                    mf.suggestions_noms[aid] = "Décider : " + question
                break

    def preparer_logique(self, DA_etoile: List[str]) -> None:
        """Extension « logique » : pour chaque décision suivie d'une
        passerelle, les branches sortantes (libellés, à défaut le nom de la
        cible) et leurs conditions ; le sérialiseur en fait une table de
        décision squelette, le DRD restant identique."""
        if "logique" not in self.ext:
            return
        mi, mf = self.mi, self.mf
        for aid in DA_etoile:
            passerelles = self._passerelles_de_verdict(aid)
            if not passerelles:
                continue
            g = passerelles[0]
            branches: List[Dict[str, str]] = []
            for s, t, libelle in mi.flux_sequence:
                if s != g:
                    continue
                cible = mi.noeuds.get(t)
                nom = (libelle or "").strip() or _libelle(
                    cible.nom if cible else "", t)
                if any(b["sortie"] == nom for b in branches):
                    nom = "%s (%d)" % (nom, len(branches) + 1)
                branches.append({"sortie": nom,
                                 "condition": mi.conditions.get((g, t), "")})
            if branches:
                mf.logique[mf.delta[aid]] = {
                    "passerelle": _libelle(mi.noeuds[g].nom,
                                           "Verdict : " + mf.noeuds[mf.delta[aid]].nom),
                    "branches": branches}

    # ------------------------------------------------------------------
    # étape 3 : P4 raffiné, décisions amont
    # ------------------------------------------------------------------
    def relier_decisions_amont(self, DA_etoile: List[str]) -> None:
        """P4 raffiné : l'arc d2 -> d exige a2 ⪯_s a (atteignabilité) et
        Outs(a2) ∩ Ins(a) non vide (« ordonner n'est pas alimenter »).

        Garde d'acyclicité de l'algorithme de référence : un arc P4 qui
        fermerait un circuit entre décisions n'est pas ajouté, le circuit
        est signalé à l'expert qui tranche le sens réel de la dépendance.
        Seuls les arcs P4 peuvent créer un cycle, les autres sommets n'ayant
        aucun arc entrant. Le premier arc rencontré est conservé et le
        second écarté : lequel des deux dépend de l'ordre de déclaration
        dans le fichier BPMN, c'est pourquoi le point est soumis à l'expert."""
        mf = self.mf
        adj_decisions: Dict[str, Set[str]] = {}
        for aid in DA_etoile:
            did = mf.delta[aid]
            ins_a = self.ins_de[aid]
            for a2id in DA_etoile:
                if a2id == aid:
                    continue
                if not (self.outs_de[a2id] & ins_a):
                    continue                      # ordonner n'est pas alimenter
                if aid not in self.sequence.atteints(a2id):   # a2 ⪯_s a requis
                    continue
                d2 = mf.delta[a2id]
                if _fermerait_un_cycle(adj_decisions, d2, did):
                    mf.a_confirmer.append(PointExpert(
                        cle="circuit:%s>%s" % (a2id, aid), categorie="circuit",
                        objet="%s ⇄ %s" % (mf.noeuds[d2].nom,
                                           mf.noeuds[did].nom),
                        motif="ces deux décisions semblent dépendre l'une de "
                              "l'autre (chacune produit une donnée que l'autre "
                              "lit) ; un modèle de décision ne peut pas "
                              "contenir de boucle — le lien « %s → %s » a été "
                              "écarté : lequel des deux sens est le bon ?"
                              % (mf.noeuds[d2].nom, mf.noeuds[did].nom)))
                    continue
                arc = (d2, did)
                if arc not in mf.arcs:
                    mf.arcs.append(arc)
                    mf.arcs_origine[arc] = "P4"
                    adj_decisions.setdefault(d2, set()).add(did)

    def dedoublonner_points_experts(self) -> None:
        """Un même point peut être soulevé par plusieurs décisions : il est
        conservé une fois par clé d'arbitrage, deux éléments homonymes
        restant deux points distincts."""
        vus: Set[Tuple[str, str]] = set()
        for liste in (self.mf.a_confirmer, self.mf.ecartes):
            uniques = []
            for p in liste:
                t = (p.categorie, p.cle)
                if t not in vus:
                    vus.add(t)
                    uniques.append(p)
            liste[:] = uniques


def expliquer_drd_vide(mi: Mi, mf: Mf) -> str:
    """Pourquoi T n'a retenu aucune décision. Le message distingue les
    candidats en attente d'arbitrage (par définition : tâches utilisateur,
    tâches de règle métier, sous-processus repliés) des activités d'un
    autre type, nomme celles qui précèdent une passerelle exclusive pour
    que l'utilisateur retype son modèle en connaissance de cause, et
    signale les annotations qui ne sont reliées à rien. Chaîne vide dès
    qu'une décision existe."""
    if mf.decisions:
        return ""
    activites = list(mi.activites.values())
    if not activites:
        return ("Aucune décision extraite : le modèle ne contient aucune "
                "activité.")
    phrases: List[str] = []
    en_attente = [p.objet for p in mf.a_confirmer if p.categorie == "candidat"]
    ecartes = [p.objet for p in mf.ecartes if p.categorie == "candidat"]
    if en_attente:
        phrases.append(
            "Aucune décision retenue : %s attend(ent) votre arbitrage dans "
            "les points à confirmer (« est-ce une décision ? »)."
            % " et ".join("« %s »" % n for n in en_attente))
    elif ecartes:
        phrases.append("Aucune décision retenue : tous les candidats ont été "
                       "écartés par arbitrage.")
    else:
        phrases.append("Aucune activité candidate : seules les tâches utilisateur, "
                       "les tâches de règle métier et les sous-processus repliés "
                       "sont candidats.")
    hors_definition = [a for a in activites if a.type in LIBELLES_HORS_DEFINITION]
    par_type: Dict[str, List[str]] = {}
    for a in hors_definition:
        par_type.setdefault(a.type, []).append(_libelle(a.nom, a.id))
    if par_type:
        inventaire = []
        for type_, noms in par_type.items():
            sing, plur = LIBELLES_HORS_DEFINITION[type_]
            inventaire.append("%d %s (%s)" % (
                len(noms), plur if len(noms) > 1 else sing,
                ", ".join("« %s »" % n for n in noms)))
        phrases.append("Ce modèle contient %s : %s." % (
            "aussi" if (en_attente or ecartes) else "seulement",
            " ; ".join(inventaire)))
        devant_passerelle = [_libelle(a.nom, a.id) for a in hors_definition
                             if kappa(mi, a.id)["position"]]
        if devant_passerelle:
            phrases.append(
                "%s précède une passerelle exclusive : si une décision y est "
                "prise, retypez cette activité en tâche utilisateur ou en "
                "tâche de règle métier dans votre outil de modélisation, puis "
                "relancez l'extraction."
                % " et ".join("« %s »" % n for n in devant_passerelle))
        else:
            phrases.append("Si l'une de ces activités prend une décision, "
                           "retypez-la en tâche utilisateur ou en tâche de "
                           "règle métier dans votre outil de modélisation, "
                           "puis relancez l'extraction.")
    annotations = [d for d in mi.donnees.values() if d.categorie == "annotation"]
    associees = {x for s, t in mi.flux_donnees for x in (s, t)}
    orphelines = [d for d in annotations if d.id not in associees]
    if annotations and len(orphelines) == len(annotations):
        phrases.append("Les %d annotation(s) du modèle ne sont associées à "
                       "aucune tâche : reliez-les par une association pour "
                       "qu'elles soient prises en compte." % len(annotations))
    return " ".join(phrases)


def _fermerait_un_cycle(adj_decisions: Dict[str, Set[str]],
                        u_dec: str, v_dec: str) -> bool:
    """L'arc u -> v fermerait-il un circuit dans le graphe des décisions ?"""
    pile, vus = [v_dec], set()
    while pile:
        x = pile.pop()
        if x == u_dec:
            return True
        if x in vus:
            continue
        vus.add(x)
        pile.extend(adj_decisions.get(x, ()))
    return False
