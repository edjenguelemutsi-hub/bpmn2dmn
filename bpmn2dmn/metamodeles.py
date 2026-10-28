# -*- coding: utf-8 -*-
"""
Métamodèles réduits Mi et Mf, tels que le cadre formel les définit.

Mi = (Gi, tau_i, beta) avec Gi = (V_i, DN, E_i) : V_i = A ∪ G ∪ E_v,
DN = D_o ∪ D_s ∪ A_no, E_i = E_s ∪ E_d ; tau_i porte le typage et la
ressource rho, beta associe chaque événement frontière à son hôte.

Mf = (Gf, tau_f) avec Gf = (V_f, E_f) : V_f = D ∪ BKM ∪ I ∪ KS. E_f est
l'ensemble unifié des exigences ; IR, KR et AR s'en déduisent par la
dérivation canonique et ne sont jamais construits à part.
Chaque nœud garde sa provenance (identifiant source, pattern appliqué),
la traçabilité étant une exigence du cadre (objectif OS4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# typage tau_i : natures contextuelles et sous-types BPMN normalisés
ACTIVITES = {
    "task", "userTask", "businessRuleTask", "serviceTask", "sendTask",
    "receiveTask", "manualTask", "scriptTask", "callActivity", "subProcess",
    "transaction", "adHocSubProcess",
}
PASSERELLES = {
    "exclusiveGateway", "inclusiveGateway", "parallelGateway",
    "eventBasedGateway", "complexGateway",
}
EVENEMENTS = {
    "startEvent", "endEvent", "intermediateCatchEvent",
    "intermediateThrowEvent", "boundaryEvent",
}
# Définitions d'événement « à charge utile » (critère du cadre formel : un
# événement est porteur de données si son typage comporte une définition
# message ou signal).
DEFINITIONS_PORTEUSES = {"messageEventDefinition", "signalEventDefinition"}


@dataclass
class NoeudFlux:
    """Un sommet de V_i = A ∪ G ∪ E_v."""
    id: str
    type: str                          # sous-type BPMN normalisé (tau_i.type)
    nom: str = ""
    nature: str = ""                   # "activite" | "passerelle" | "evenement"
    ressource: Optional[str] = None    # rho(v) : nom du couloir (lane)
    porteur_donnees: bool = False      # événement à définition message/signal
    interrompt: bool = True            # boundaryEvent : cancelActivity
    processus: str = ""                # id du process propriétaire

    @property
    def est_activite(self) -> bool:
        return self.nature == "activite"


@dataclass
class NoeudDonnees:
    """Un élément de DN = D_o ∪ D_s ∪ A_no."""
    id: str
    categorie: str                     # "objet" | "magasin" | "annotation"
    nom: str = ""                      # pour une annotation : son texte


@dataclass
class Mi:
    """Modèle de processus BPMN simplifié (définition de Mi)."""
    nom: str = ""
    source: str = ""                                   # chemin du fichier
    noeuds: Dict[str, NoeudFlux] = field(default_factory=dict)      # V_i
    donnees: Dict[str, NoeudDonnees] = field(default_factory=dict)  # DN
    flux_sequence: List[Tuple[str, str, str]] = field(default_factory=list)
    #   E_s : (source, cible, libellé)
    flux_donnees: List[Tuple[str, str]] = field(default_factory=list)
    #   E_d : (source, cible) — orienté ; couvre lectures, écritures
    #   et associations d'annotations (annotation -> activité)
    beta: Dict[str, str] = field(default_factory=dict)
    #   événement-frontière -> activité hôte
    conteneur: Dict[str, str] = field(default_factory=dict)
    #   nœud -> sous-processus déplié qui le contenait (traçabilité du
    #   dépliage : couloir hérité, frontière posée sur la façade)
    anomalies: List[str] = field(default_factory=list)
    #   défauts non bloquants relevés par le parseur (référence pendante...)
    # informations relevées pour les extensions de l'algorithme ; sans
    # extension, aucune n'influence la transformation
    conditions: Dict[Tuple[str, str], str] = field(default_factory=dict)
    #   (source, cible) d'un flux de séquence -> texte de sa condition
    donnees_processus: Dict[str, str] = field(default_factory=dict)
    #   dataInput / dataOutput déclarés par l'ioSpecification d'un processus
    definitions_evenements: Dict[str, List[str]] = field(default_factory=dict)
    #   événement -> noms locaux de ses définitions (message, timer...)
    flux_donnees_ecartes: List[Tuple[str, str]] = field(default_factory=list)
    #   associations de données vers un identifiant inconnu, écartées

    @property
    def activites(self) -> Dict[str, NoeudFlux]:
        return {i: n for i, n in self.noeuds.items() if n.nature == "activite"}

    @property
    def passerelles(self) -> Dict[str, NoeudFlux]:
        return {i: n for i, n in self.noeuds.items() if n.nature == "passerelle"}

    @property
    def evenements(self) -> Dict[str, NoeudFlux]:
        return {i: n for i, n in self.noeuds.items() if n.nature == "evenement"}

    def successeurs(self, nid: str) -> List[str]:
        return [t for s, t, _ in self.flux_sequence if s == nid]

    def contenu(self, sp: str) -> List[str]:
        """Nœuds remontés d'un sous-processus déplié, à tout niveau
        d'imbrication, dans l'ordre de V_i."""
        out = []
        for nid in self.noeuds:
            parent = self.conteneur.get(nid)
            while parent is not None and parent != sp:
                parent = self.conteneur.get(parent)
            if parent == sp:
                out.append(nid)
        return out

    def predecesseurs(self, nid: str) -> List[str]:
        return [s for s, t, _ in self.flux_sequence if t == nid]

    def entrees_donnees(self, nid: str) -> List[str]:
        """Ins(a) : identifiants des nœuds de données lus par a."""
        return [s for s, t in self.flux_donnees
                if t == nid and s in self.donnees
                and self.donnees[s].categorie != "annotation"]

    def sorties_donnees(self, nid: str) -> List[str]:
        """Outs(a) : identifiants des nœuds de données produits par a."""
        return [t for s, t in self.flux_donnees
                if s == nid and t in self.donnees
                and self.donnees[t].categorie != "annotation"]

    def annotations_de(self, nid: str) -> List[str]:
        """Annotations associées à l'activité nid (les deux sens d'association)."""
        out = []
        for s, t in self.flux_donnees:
            if t == nid and s in self.donnees \
               and self.donnees[s].categorie == "annotation":
                out.append(s)
            elif s == nid and t in self.donnees \
                    and self.donnees[t].categorie == "annotation":
                out.append(t)
        return out

    def atteignable(self, a: str, b: str) -> bool:
        """a ⪯_s b : chemin de a vers b par les seuls flux de séquence."""
        adj: Dict[str, List[str]] = {}
        for s, t, _ in self.flux_sequence:
            adj.setdefault(s, []).append(t)
        vus: Set[str] = set()
        pile = [a]
        while pile:
            u = pile.pop()
            if u == b and u != a or (u == b and b in vus):
                return True
            if u in vus:
                continue
            vus.add(u)
            for v in adj.get(u, []):
                if v == b:
                    return True
                if v not in vus:
                    pile.append(v)
        return False


# typage tau_f : les quatre types de sommets du DRD
DECISION = "Decision"
BKM = "BKM"
INPUT_DATA = "InputData"
KNOWLEDGE_SOURCE = "KnowledgeSource"
TYPES_MF = (DECISION, BKM, INPUT_DATA, KNOWLEDGE_SOURCE)


@dataclass
class NoeudMf:
    """Un sommet de V_f, avec son typage tau_f et sa provenance."""
    id: str
    type: str                          # l'un de TYPES_MF
    nom: str
    origine: str = ""                  # id de l'élément Mi source
    pattern: str = ""                  # P1..P6 (traçabilité)


@dataclass
class PointExpert:
    """Un point d'indétermination soumis à l'expert (règles ouvertes)."""
    cle: str                           # clé stable pour l'arbitrage
    categorie: str                     # "candidat" | "ressource" | "annotation" | "hors-definition" | "circuit"
    objet: str                         # libellé de l'élément concerné
    motif: str                         # pourquoi le programme ne tranche pas
    proposition: str = ""              # verdict proposé (jamais imposé)

    def as_tuple(self):
        return (self.categorie, self.objet, self.motif, self.proposition)


@dataclass
class Mf:
    """Modèle DRD simplifié (définition de Mf) + trace d'exécution de T."""
    nom: str = ""
    noeuds: Dict[str, NoeudMf] = field(default_factory=dict)   # V_f
    arcs: List[Tuple[str, str]] = field(default_factory=list)  # E_f (unifié)
    arcs_origine: Dict[Tuple[str, str], str] = field(default_factory=dict)
    #   arc -> pattern qui l'a produit (traçabilité)
    a_confirmer: List[PointExpert] = field(default_factory=list)
    ecartes: List[PointExpert] = field(default_factory=list)
    delta: Dict[str, str] = field(default_factory=dict)   # activité Mi -> décision Mf
    iota: Dict[str, str] = field(default_factory=dict)    # donnée/évt Mi -> InputData Mf
    motifs_corroboration: Dict[str, str] = field(default_factory=dict)
    #   décision Mf -> indices kappa qui l'ont retenue (traçabilité)
    extensions: Tuple[str, ...] = ()
    #   extensions de l'algorithme actives lors de la construction
    suggestions_noms: Dict[str, str] = field(default_factory=dict)
    #   activité Mi -> nom de décision suggéré (extension noms-suggeres)
    logique: Dict[str, Dict] = field(default_factory=dict)
    #   décision Mf -> squelette de table de décision (extension logique)

    def par_type(self, t: str) -> List[NoeudMf]:
        return [n for n in self.noeuds.values() if n.type == t]

    @property
    def decisions(self) -> List[NoeudMf]:
        return self.par_type(DECISION)

    @property
    def inputs(self) -> List[NoeudMf]:
        return self.par_type(INPUT_DATA)

    @property
    def sources(self) -> List[NoeudMf]:
        return self.par_type(KNOWLEDGE_SOURCE)

    @property
    def bkms(self) -> List[NoeudMf]:
        return self.par_type(BKM)

    # dérivation canonique des trois familles d'exigences
    @property
    def IR(self) -> List[Tuple[str, str]]:
        """(u,v) ∈ E_f, tau(u) ∈ {InputData, Decision}, tau(v) = Decision."""
        return [(u, v) for u, v in self.arcs
                if self.noeuds[u].type in (INPUT_DATA, DECISION)
                and self.noeuds[v].type == DECISION]

    @property
    def KR(self) -> List[Tuple[str, str]]:
        """(u,v) ∈ E_f, tau(u) = BKM, tau(v) ∈ {Decision, BKM}."""
        return [(u, v) for u, v in self.arcs
                if self.noeuds[u].type == BKM
                and self.noeuds[v].type in (DECISION, BKM)]

    @property
    def AR(self) -> List[Tuple[str, str]]:
        """Forme résiduelle retenue : AR = E_f \\ (IR ∪ KR).
        {IR, KR, AR} est ainsi une partition exacte de E_f."""
        ir, kr = set(self.IR), set(self.KR)
        return [a for a in self.arcs if a not in ir and a not in kr]

    def acyclique(self) -> bool:
        """Garde d'acyclicité de l'algorithme : parcours en profondeur, détection
        d'arc arrière sur (V_f, E_f)."""
        adj: Dict[str, List[str]] = {}
        for u, v in self.arcs:
            adj.setdefault(u, []).append(v)
        BLANC, GRIS, NOIR = 0, 1, 2
        coul: Dict[str, int] = {}

        def visite(dep: str) -> bool:
            pile = [(dep, iter(adj.get(dep, [])))]
            coul[dep] = GRIS
            while pile:
                u, it = pile[-1]
                avance = False
                for v in it:
                    c = coul.get(v, BLANC)
                    if c == GRIS:
                        return False
                    if c == BLANC:
                        coul[v] = GRIS
                        pile.append((v, iter(adj.get(v, []))))
                        avance = True
                        break
                if not avance:
                    coul[u] = NOIR
                    pile.pop()
            return True

        for n in list(adj):
            if coul.get(n, BLANC) == BLANC and not visite(n):
                return False
        return True

    def partition_exacte(self) -> bool:
        """Propriété de la dérivation canonique : IR, KR, AR partitionnent E_f."""
        return sorted(self.IR + self.KR + self.AR) == sorted(self.arcs) \
            and len(self.IR) + len(self.KR) + len(self.AR) == len(self.arcs)

    def resume(self) -> Dict[str, int]:
        return {
            "decisions": len(self.decisions),
            "inputs": len(self.inputs),
            "sources": len(self.sources),
            "bkm": len(self.bkms),
            "IR": len(self.IR),
            "KR": len(self.KR),
            "AR": len(self.AR),
            "a_confirmer": len(self.a_confirmer),
            "ecartes": len(self.ecartes),
        }
