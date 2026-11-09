# -*- coding: utf-8 -*-
"""
Traçabilité et co-évolution entre le modèle de processus et le modèle de
décision.

Le lien entre les deux modèles repose sur trois choses que l'outil écrit
lui-même : des identifiants stables dans le DMN produit (chaque sommet du
DRD porte l'identifiant de l'élément BPMN dont il vient : Decision_T3,
InputData_do_dossier...), un élément de trace dans chaque sommet et chaque
exigence (élément source, patron, indices), et un fichier de trace à côté
du DMN (`.trace.json`). Ce module exploite ce lien dans les deux sens.

  * `synchroniser` (DMN -> BPMN) : le modélisateur a retouché le DRD dans
    Camunda Modeler (renommé une décision, ajouté une donnée d'entrée,
    retiré une exigence, écrit les règles d'une table) ; la fonction
    reporte chaque modification sur le fichier BPMN d'origine, élément par
    élément, sans toucher au reste du processus, puis rejoue la
    transformation sur le BPMN obtenu et vérifie qu'elle redonne le DRD
    modifié : la cohérence est établie, ou l'écart est nommé. Ce qu'un
    processus ne peut pas exprimer (un rôle qui gouverne une décision et
    pas une autre) est consigné dans le fichier d'arbitrages plutôt
    qu'inventé dans le BPMN ; une décision supprimée du DRD n'efface pas
    la tâche, elle devient un candidat écarté par arbitrage.

  * `impact` (BPMN -> DMN) : le processus a changé ; la fonction compare
    le DRD que la transformation en tire au DRD précédemment produit et
    nomme ce qui est invalidé (décision disparue ou renommée, exigence qui
    n'a plus de support dans le processus), ce qui apparaît et ce qui
    subsiste.

Le fichier BPMN est édité avec lxml pour conserver tout ce qui n'est pas
concerné (espaces de noms, commentaires, attributs des outils, mise en
page) ; les éléments ajoutés reçoivent une forme DI près de la tâche à
laquelle ils se rattachent.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from lxml import etree

from . import feel
from .inverse import parser_dmn
from .metamodeles import BKM, DECISION, INPUT_DATA, KNOWLEDGE_SOURCE, Mf
from .parseur import parser_bpmn
from .qualification import Arbitrages, normaliser
from .serialiseur import texte_xml
from .transformation import transformer
from .validation import equivalents

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
      "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC",
      "di": "http://www.omg.org/spec/DD/20100524/DI",
      "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
FEEL_URI = "https://www.omg.org/spec/DMN/20191111/FEEL/"
ARTEFACTS = ("textAnnotation", "association", "group")


def _local(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) and "}" in tag else str(tag)


def _q(prefixe: str, nom: str) -> str:
    return "{%s}%s" % (NS[prefixe], nom)


def identifiant_sur(texte: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", texte or "")
    s = re.sub(r"_+", "_", s).strip("_") or "n"
    return s if re.match(r"[A-Za-z_]", s) else "n" + s


@dataclass
class Changement:
    """Une modification lue dans le DRD et son sort dans le processus."""
    genre: str            # renommage-decision, ajout-decision, suppression-decision,
                          # renommage-donnee, ajout-donnee, suppression-donnee,
                          # ajout-exigence, suppression-exigence, ajout-source,
                          # suppression-source, renommage-source, table, arbitrage
    dmn: str              # élément du DRD concerné (identifiant ou nom)
    bpmn: str             # élément du processus touché (identifiant), ou vide
    detail: str           # ce qui a été fait, en une phrase
    applique: bool        # vrai si le BPMN ou les arbitrages ont été modifiés
    motif: str = ""       # pourquoi rien n'a été appliqué, le cas échéant


@dataclass
class Rapport:
    changements: List[Changement] = field(default_factory=list)
    coherent: Optional[bool] = None
    ecarts: List[str] = field(default_factory=list)
    tables_coherentes: Optional[bool] = None
    ecarts_tables: List[str] = field(default_factory=list)
    arbitrages: Dict = field(default_factory=dict)
    resume: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {"changements": [asdict(c) for c in self.changements],
                "appliques": sum(1 for c in self.changements if c.applique),
                "non_appliques": sum(1 for c in self.changements if not c.applique),
                "coherent": self.coherent, "ecarts": self.ecarts,
                "tables_coherentes": self.tables_coherentes,
                "ecarts_tables": self.ecarts_tables,
                "arbitrages": self.arbitrages, "resume": self.resume}


# ----------------------------------------------------------------------
# l'éditeur BPMN
# ----------------------------------------------------------------------
class EditeurBPMN:
    """Édition ciblée d'un document BPMN 2.0 : renommages, objets de
    données, associations, annotations, tâches, conditions ; mise en page
    des ajouts près de la tâche de rattachement."""

    def __init__(self, texte: str):
        self.texte_origine = texte
        analyseur = etree.XMLParser(remove_blank_text=False, remove_comments=False)
        self.racine = etree.fromstring(texte.encode("utf-8") if isinstance(texte, str)
                                       else texte, analyseur)
        self.nsmap = {k: v for k, v in self.racine.nsmap.items()}
        self.prefixe_bpmn = None
        for k, v in self.nsmap.items():
            if v == NS["bpmn"]:
                self.prefixe_bpmn = k
        self.plan = self.racine.find(".//bpmndi:BPMNPlane", NS)
        self.compteur = 0

    # -- services --------------------------------------------------------
    def element(self, eid: str):
        if not eid:
            return None
        trouves = self.racine.xpath(".//*[@id=$i]", i=eid)
        return trouves[0] if trouves else None

    def _balise(self, nom: str) -> str:
        return _q("bpmn", nom)

    def _nouvel_id(self, base: str) -> str:
        base = identifiant_sur(base)
        candidat = base
        while self.element(candidat) is not None:
            self.compteur += 1
            candidat = "%s_%d" % (base, self.compteur)
        return candidat

    def nom(self, eid: str) -> str:
        e = self.element(eid)
        return (e.get("name") or "") if e is not None else ""

    def renommer(self, eid: str, nom: str) -> bool:
        e = self.element(eid)
        if e is None:
            return False
        if _local(e.tag) == "textAnnotation":
            t = e.find("bpmn:text", NS)
            if t is None:
                t = etree.SubElement(e, self._balise("text"))
            t.text = texte_xml(nom)
        else:
            e.set("name", texte_xml(nom))
        return True

    def processus_de(self, e):
        p = e.getparent()
        while p is not None and _local(p.tag) not in ("process", "subProcess"):
            p = p.getparent()
        return p if p is not None else self.racine.find(".//bpmn:process", NS)

    def bounds(self, eid: str) -> Optional[Tuple[float, float, float, float]]:
        if self.plan is None:
            return None
        for forme in self.plan.findall("bpmndi:BPMNShape", NS):
            if forme.get("bpmnElement") == eid:
                b = forme.find("dc:Bounds", NS)
                if b is not None:
                    return (float(b.get("x")), float(b.get("y")),
                            float(b.get("width")), float(b.get("height")))
        return None

    def _forme(self, eid: str, x: float, y: float, w: float, h: float,
               libelle: bool = False) -> None:
        if self.plan is None:
            return
        forme = etree.SubElement(self.plan, _q("bpmndi", "BPMNShape"),
                                 id="di_" + eid, bpmnElement=eid)
        etree.SubElement(forme, _q("dc", "Bounds"), x=str(round(x)), y=str(round(y)),
                         width=str(round(w)), height=str(round(h)))
        if libelle:
            lab = etree.SubElement(forme, _q("bpmndi", "BPMNLabel"))
            etree.SubElement(lab, _q("dc", "Bounds"), x=str(round(x + w + 6)),
                             y=str(round(y + h / 2 - 14)), width="120", height="28")

    def _arete(self, eid: str, points: List[Tuple[float, float]]) -> None:
        if self.plan is None:
            return
        arete = etree.SubElement(self.plan, _q("bpmndi", "BPMNEdge"),
                                 id="di_" + eid, bpmnElement=eid)
        for a, b in points:
            etree.SubElement(arete, _q("di", "waypoint"), x=str(round(a)), y=str(round(b)))

    def _retirer_di(self, eid: str) -> None:
        if self.plan is None:
            return
        for x in list(self.plan):
            if x.get("bpmnElement") == eid:
                self.plan.remove(x)

    def _inserer_flux(self, processus, elem) -> None:
        """Insère un élément de flux juste après le dernier élément de flux
        du processus (l'ordre du fichier est respecté : le XSD veut les
        éléments de flux avant les artefacts, et un fichier qui s'en écarte
        n'est pas réordonné) ; à défaut avant le premier artefact."""
        dernier = None
        for i, enfant in enumerate(processus):
            t = _local(enfant.tag)
            if t not in ARTEFACTS and t not in ("laneSet", "property", "documentation",
                                                "extensionElements", "ioSpecification",
                                                "auditing", "monitoring", "resourceRole",
                                                "correlationSubscription", "supports")                and not (isinstance(enfant.tag, str) and enfant.tag.startswith("<cyfunction")):
                dernier = i
        if dernier is not None:
            processus.insert(dernier + 1, elem)
            return
        for i, enfant in enumerate(processus):
            if _local(enfant.tag) in ARTEFACTS:
                processus.insert(i, elem)
                return
        processus.append(elem)

    def _occupe(self, x: float, y: float, w: float, h: float) -> bool:
        if self.plan is None:
            return False
        for forme in self.plan.findall("bpmndi:BPMNShape", NS):
            b = forme.find("dc:Bounds", NS)
            if b is None:
                continue
            bx, by, bw, bh = (float(b.get("x")), float(b.get("y")),
                              float(b.get("width")), float(b.get("height")))
            if bx < x + w + 10 and bx + bw + 10 > x and by < y + h + 10 and by + bh + 10 > y:
                return True
        return False

    def _place_libre(self, x: float, y: float, w: float, h: float,
                     pas: Tuple[float, float]) -> Tuple[float, float]:
        for _ in range(40):
            if not self._occupe(x, y, w, h):
                return x, y
            x, y = x + pas[0], y + pas[1]
        return x, y

    # -- objets de données et associations --------------------------------
    def ajouter_objet(self, nom: str, pres_de: str, base_id: str = "") -> str:
        tache = self.element(pres_de)
        processus = self.processus_de(tache) if tache is not None \
            else self.racine.find(".//bpmn:process", NS)
        oid = self._nouvel_id(base_id or "do_" + nom)
        oid_o = self._nouvel_id(oid + "_o")
        ref = etree.Element(self._balise("dataObjectReference"), id=oid,
                            name=texte_xml(nom), dataObjectRef=oid_o)
        obj = etree.Element(self._balise("dataObject"), id=oid_o)
        self._inserer_flux(processus, ref)
        self._inserer_flux(processus, obj)
        b = self.bounds(pres_de)
        if b is not None:
            x, y = self._place_libre(b[0] + 10, b[1] - 95, 36, 50, (50, 0))
            self._forme(oid, x, y, 36, 50, libelle=True)
        return oid

    def associations_entree(self, tid: str) -> List[Tuple[str, str]]:
        """(identifiant de l'association, source) des lectures de la tâche."""
        t = self.element(tid)
        if t is None:
            return []
        out = []
        for a in t.findall("bpmn:dataInputAssociation", NS):
            s = a.find("bpmn:sourceRef", NS)
            out.append((a.get("id") or "", (s.text or "").strip() if s is not None else ""))
        return out

    def associations_sortie(self, tid: str) -> List[Tuple[str, str]]:
        t = self.element(tid)
        if t is None:
            return []
        out = []
        for a in t.findall("bpmn:dataOutputAssociation", NS):
            c = a.find("bpmn:targetRef", NS)
            out.append((a.get("id") or "", (c.text or "").strip() if c is not None else ""))
        return out

    def ajouter_lecture(self, tid: str, oid: str) -> bool:
        t = self.element(tid)
        if t is None or any(s == oid for _, s in self.associations_entree(tid)):
            return False
        prop = None
        for p in t.findall("bpmn:property", NS):
            prop = p
        if prop is None:
            prop = etree.Element(self._balise("property"), id=self._nouvel_id("prop_" + tid),
                                 name="__targetRef_placeholder")
            # une propriété précède les associations (ordre XSD)
            position = 0
            for i, enfant in enumerate(t):
                if _local(enfant.tag) in ("extensionElements", "documentation",
                                          "incoming", "outgoing", "ioSpecification",
                                          "property"):
                    position = i + 1
            t.insert(position, prop)
        aid = self._nouvel_id("dia_%s_%s" % (tid, oid))
        assoc = etree.Element(self._balise("dataInputAssociation"), id=aid)
        etree.SubElement(assoc, self._balise("sourceRef")).text = oid
        etree.SubElement(assoc, self._balise("targetRef")).text = prop.get("id")
        # après la dernière association d'entrée existante, sinon après la propriété
        dernier = list(t).index(prop)
        for i, enfant in enumerate(t):
            if _local(enfant.tag) in ("dataInputAssociation",):
                dernier = i
        t.insert(dernier + 1, assoc)
        self._arete_donnee(aid, oid, tid)
        return True

    def ajouter_ecriture(self, tid: str, oid: str) -> bool:
        t = self.element(tid)
        if t is None or any(c == oid for _, c in self.associations_sortie(tid)):
            return False
        aid = self._nouvel_id("doa_%s_%s" % (tid, oid))
        assoc = etree.Element(self._balise("dataOutputAssociation"), id=aid)
        etree.SubElement(assoc, self._balise("targetRef")).text = oid
        dernier = -1
        for i, enfant in enumerate(t):
            if _local(enfant.tag) in ("extensionElements", "documentation", "incoming",
                                      "outgoing", "ioSpecification", "property",
                                      "dataInputAssociation", "dataOutputAssociation"):
                dernier = i
        t.insert(dernier + 1, assoc)
        self._arete_donnee(aid, tid, oid)
        return True

    def _arete_donnee(self, aid: str, source: str, cible: str) -> None:
        bs, bc = self.bounds(source), self.bounds(cible)
        if bs and bc:
            self._arete(aid, [(bs[0] + bs[2] / 2, bs[1] + bs[3]), (bc[0] + bc[2] / 2, bc[1])])

    def retirer_lecture(self, tid: str, oid: str) -> bool:
        t = self.element(tid)
        if t is None:
            return False
        fait = False
        for a in t.findall("bpmn:dataInputAssociation", NS):
            s = a.find("bpmn:sourceRef", NS)
            if s is not None and (s.text or "").strip() == oid:
                t.remove(a)
                self._retirer_di(a.get("id") or "")
                fait = True
        return fait

    def retirer_objet_si_orphelin(self, oid: str) -> bool:
        if self.racine.xpath(".//bpmn:sourceRef[normalize-space(text())=$i] | "
                             ".//bpmn:targetRef[normalize-space(text())=$i]",
                             namespaces=NS, i=oid):
            return False
        e = self.element(oid)
        if e is None:
            return False
        ref = e.get("dataObjectRef")
        e.getparent().remove(e)
        self._retirer_di(oid)
        if ref and not self.racine.xpath(".//*[@dataObjectRef=$i]", i=ref):
            o = self.element(ref)
            if o is not None:
                o.getparent().remove(o)
        return True

    # -- annotations -------------------------------------------------------
    def ajouter_annotation(self, texte: str, tid: str, base_id: str = "") -> Tuple[str, str]:
        tache = self.element(tid)
        processus = self.processus_de(tache) if tache is not None \
            else self.racine.find(".//bpmn:process", NS)
        anid = self._nouvel_id(base_id or "annot_" + tid)
        annot = etree.SubElement(processus, self._balise("textAnnotation"), id=anid)
        etree.SubElement(annot, self._balise("text")).text = texte_xml(texte)
        asid = self._nouvel_id("assoc_%s_%s" % (anid, tid))
        etree.SubElement(processus, self._balise("association"), id=asid,
                         sourceRef=anid, targetRef=tid)
        b = self.bounds(tid)
        if b is not None:
            x, y = self._place_libre(b[0] - 20, b[1] + b[3] + 40, 200, 48, (0, 60))
            self._forme(anid, x, y, 200, 48)
            self._arete(asid, [(x + 100, y), (b[0] + b[2] / 2, b[1] + b[3])])
        return anid, asid

    def associer_annotation(self, anid: str, tid: str) -> Optional[str]:
        a = self.element(anid)
        if a is None:
            return None
        if self.racine.xpath(".//bpmn:association[@sourceRef=$a and @targetRef=$t] | "
                             ".//bpmn:association[@sourceRef=$t and @targetRef=$a]",
                             namespaces=NS, a=anid, t=tid):
            return None
        asid = self._nouvel_id("assoc_%s_%s" % (anid, tid))
        etree.SubElement(a.getparent(), self._balise("association"), id=asid,
                         sourceRef=anid, targetRef=tid)
        ba, bt = self.bounds(anid), self.bounds(tid)
        if ba and bt:
            self._arete(asid, [(ba[0] + ba[2] / 2, ba[1]), (bt[0] + bt[2] / 2, bt[1] + bt[3])])
        return asid

    def retirer_association_annotation(self, anid: str, tid: str) -> bool:
        fait = False
        for a in self.racine.xpath(".//bpmn:association[(@sourceRef=$a and @targetRef=$t) or "
                                   "(@sourceRef=$t and @targetRef=$a)]",
                                   namespaces=NS, a=anid, t=tid):
            a.getparent().remove(a)
            self._retirer_di(a.get("id") or "")
            fait = True
        if fait and not self.racine.xpath(".//bpmn:association[@sourceRef=$a or @targetRef=$a]",
                                          namespaces=NS, a=anid):
            e = self.element(anid)
            if e is not None:
                e.getparent().remove(e)
                self._retirer_di(anid)
        return fait

    # -- tâches de décision ---------------------------------------------------
    def flux_sortants(self, nid: str) -> List:
        return self.racine.xpath(".//bpmn:sequenceFlow[@sourceRef=$s]", namespaces=NS, s=nid)

    def flux_entrants(self, nid: str) -> List:
        return self.racine.xpath(".//bpmn:sequenceFlow[@targetRef=$t]", namespaces=NS, t=nid)

    def ajouter_tache_decision(self, nom: str, apres: str, base_id: str = "") -> Tuple[str, str]:
        """Une tâche utilisateur suivie d'une passerelle exclusive, insérée
        dans le premier flux sortant du nœud `apres` (sa branche « non »
        mène à une fin d'arrêt) ; même couloir que `apres`."""
        ancre = self.element(apres)
        processus = self.processus_de(ancre)
        tid = self._nouvel_id(base_id or "t_" + nom)
        gid = self._nouvel_id("g_" + tid)
        fid_fin = self._nouvel_id("fin_" + tid)
        tache = etree.Element(self._balise("userTask"), id=tid, name=texte_xml(nom))
        passerelle = etree.Element(self._balise("exclusiveGateway"), id=gid,
                                   name=texte_xml("Verdict : " + nom))
        fin = etree.Element(self._balise("endEvent"), id=fid_fin, name="Instruction arrêtée")
        for e in (tache, passerelle, fin):
            self._inserer_flux(processus, e)
        sortants = self.flux_sortants(apres)
        f1 = etree.Element(self._balise("sequenceFlow"), id=self._nouvel_id("f_" + tid),
                           sourceRef=tid, targetRef=gid)
        f_non = etree.Element(self._balise("sequenceFlow"), id=self._nouvel_id("f_" + gid + "_non"),
                              sourceRef=gid, targetRef=fid_fin, name="non")
        if sortants:
            premier = sortants[0]
            suite = premier.get("targetRef")
            premier.set("targetRef", tid)
            f_oui = etree.Element(self._balise("sequenceFlow"),
                                  id=self._nouvel_id("f_" + gid + "_oui"),
                                  sourceRef=gid, targetRef=suite, name="oui")
            self._retirer_di(premier.get("id") or "")
            nouveaux = [f1, f_oui, f_non]
        else:
            f0 = etree.Element(self._balise("sequenceFlow"), id=self._nouvel_id("f_" + apres),
                               sourceRef=apres, targetRef=tid)
            nouveaux = [f0, f1, f_non]
            premier = None
        for f in nouveaux:
            self._inserer_flux(processus, f)
        # couloir
        for lane in self.racine.xpath(".//bpmn:lane[bpmn:flowNodeRef[normalize-space(text())=$a]]",
                                      namespaces=NS, a=apres):
            for nid in (tid, gid, fid_fin):
                etree.SubElement(lane, self._balise("flowNodeRef")).text = nid
        # mise en page : sous le nœud d'ancrage
        b = self.bounds(apres)
        if b is not None:
            x, y = self._place_libre(b[0], b[1] + b[3] + 70, 140, 80, (0, 120))
            self._forme(tid, x, y, 140, 80)
            self._forme(gid, x + 180, y + 15, 50, 50)
            self._forme(fid_fin, x + 187, y + 110, 36, 36)
            if premier is not None:
                self._arete(premier.get("id"), [(b[0] + b[2] / 2, b[1] + b[3]), (x + 70, y)])
                bs = self.bounds(suite)
                if bs:
                    self._arete(f_oui.get("id"), [(x + 230, y + 40), (bs[0] + bs[2] / 2, bs[1] + bs[3])])
            else:
                self._arete(nouveaux[0].get("id"), [(b[0] + b[2] / 2, b[1] + b[3]), (x + 70, y)])
            self._arete(f1.get("id"), [(x + 140, y + 40), (x + 180, y + 40)])
            self._arete(f_non.get("id"), [(x + 205, y + 65), (x + 205, y + 110)])
        return tid, gid

    def passerelle_apres(self, tid: str) -> Optional[str]:
        """La première passerelle exclusive ou inclusive qui suit la tâche
        (en cascade, sans activité intermédiaire)."""
        vus: Set[str] = set()
        pile = [f.get("targetRef") for f in self.flux_sortants(tid)]
        while pile:
            nid = pile.pop(0)
            if not nid or nid in vus:
                continue
            vus.add(nid)
            e = self.element(nid)
            if e is None:
                continue
            if _local(e.tag) in ("exclusiveGateway", "inclusiveGateway"):
                return nid
            if _local(e.tag) in ("parallelGateway", "complexGateway", "eventBasedGateway"):
                pile.extend(f.get("targetRef") for f in self.flux_sortants(nid))
        return None

    def poser_condition(self, flux, expression: str) -> None:
        for c in flux.findall("bpmn:conditionExpression", NS):
            flux.remove(c)
        if expression:
            cond = etree.SubElement(flux, self._balise("conditionExpression"), language=FEEL_URI)
            cond.set(_q("xsi", "type"), "%s:tFormalExpression" % (self.prefixe_bpmn or "bpmn"))
            cond.text = expression

    def texte(self) -> str:
        return etree.tostring(self.racine, encoding="unicode", pretty_print=False)

    def document(self) -> str:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + self.texte()


# ----------------------------------------------------------------------
# synchronisation DMN -> BPMN
# ----------------------------------------------------------------------
def _correspondance(mf_mod: Mf, mf_ref: Mf) -> Dict[str, Optional[str]]:
    """Pour chaque sommet du DRD modifié, le sommet du DRD de référence
    qui lui correspond : même identifiant (identifiants stables), sinon
    même élément d'origine (trace), sinon même type et même nom ; None
    pour un sommet nouveau."""
    par_origine = {(n.type, n.origine): n.id for n in mf_ref.noeuds.values() if n.origine}
    par_nom = {(n.type, normaliser(n.nom)): n.id for n in mf_ref.noeuds.values()}
    corr: Dict[str, Optional[str]] = {}
    pris: Set[str] = set()
    for n in mf_mod.noeuds.values():
        cible = None
        if n.id in mf_ref.noeuds and mf_ref.noeuds[n.id].type == n.type:
            cible = n.id
        elif n.origine and (n.type, n.origine) in par_origine:
            cible = par_origine[(n.type, n.origine)]
        elif (n.type, normaliser(n.nom)) in par_nom:
            cible = par_nom[(n.type, normaliser(n.nom))]
        if cible in pris:
            cible = None
        if cible:
            pris.add(cible)
        corr[n.id] = cible
    return corr


def synchroniser(texte_bpmn: str, texte_dmn: str, arbitrages: Optional[Arbitrages] = None,
                 extensions=()) -> Tuple[str, Dict, Rapport]:
    """Reporte les modifications du DRD (`texte_dmn`) sur le processus
    (`texte_bpmn`). Retourne le BPMN mis à jour, les arbitrages mis à jour
    (dictionnaire JSON) et le rapport."""
    arbitrages = arbitrages or Arbitrages()
    ext = set(extensions or ())
    mi = parser_bpmn(texte_bpmn, est_texte=True)
    mf_mod = parser_dmn(texte_dmn, est_texte=True, exiger_decision=False)
    if mf_mod.logique:
        ext.add("logique")
    mf_ref = transformer(mi, arbitrages, ext)
    ed = EditeurBPMN(texte_bpmn)
    rapport = Rapport()
    arb = {"candidats": dict(arbitrages.candidats), "ressources": dict(arbitrages.ressources),
           "annotations": dict(arbitrages.annotations),
           "renommages": dict(arbitrages.renommages), "noms": dict(arbitrages.noms)}
    corr = _correspondance(mf_mod, mf_ref)
    inverse = {v: k for k, v in corr.items() if v}
    origine_de: Dict[str, str] = {}        # sommet du DRD modifié -> élément BPMN
    for nid, ref in corr.items():
        if ref:
            origine_de[nid] = mf_ref.noeuds[ref].origine
        elif mf_mod.noeuds[nid].origine:
            origine_de[nid] = mf_mod.noeuds[nid].origine

    def note(genre, dmn, bpmn, detail, applique=True, motif=""):
        rapport.changements.append(Changement(genre, dmn, bpmn, detail, applique, motif))

    # un sommet sans aucune exigence n'a pas d'image dans un processus (T ne
    # crée un sommet que relié à une décision) : signalé, laissé hors de la
    # comparaison finale
    relies = {x for arc in mf_mod.arcs for x in arc}
    orphelins = [n for n in mf_mod.noeuds.values()
                 if n.type != DECISION and n.id not in relies]
    for n in orphelins:
        note("orphelin", n.id, "", "« %s » n'est relié à aucune décision dans le DRD" % n.nom,
             False, "un sommet sans exigence n'a pas d'image dans le processus")

    # 1. décisions : renommages, ajouts, suppressions ----------------------
    taches_de: Dict[str, str] = {}          # décision du DRD modifié -> tâche
    for n in mf_mod.decisions:
        ref = corr[n.id]
        if ref:
            aid = mf_ref.noeuds[ref].origine
            taches_de[n.id] = aid
            if normaliser(n.nom) != normaliser(mf_ref.noeuds[ref].nom):
                if aid in arb["renommages"]:
                    arb["renommages"][aid] = n.nom
                    note("renommage-decision", n.id, aid,
                         "décision renommée « %s » : le renommage d'arbitrage de la tâche "
                         "« %s » est mis à jour (le libellé de la tâche est conservé)"
                         % (n.nom, ed.nom(aid)))
                else:
                    ed.renommer(aid, n.nom)
                    note("renommage-decision", n.id, aid,
                         "tâche « %s » renommée « %s »" % (mf_ref.noeuds[ref].nom, n.nom))
        else:
            # décision nouvelle : une tâche après la tâche d'une décision requise,
            # sinon avant celle d'une décision qui la requiert, sinon après le départ
            ancre = None
            for u, v in mf_mod.arcs:
                if v == n.id and mf_mod.noeuds[u].type == DECISION and u in taches_de:
                    ancre = taches_de[u]
                    break
            if ancre is None:
                for u, v in mf_mod.arcs:
                    if u == n.id and mf_mod.noeuds[v].type == DECISION and corr.get(v):
                        cible_t = mf_ref.noeuds[corr[v]].origine
                        entrants = ed.flux_entrants(cible_t)
                        if entrants:
                            ancre = entrants[0].get("sourceRef")
                        break
            if ancre is None:
                departs = [e for e in mi.evenements.values() if e.type == "startEvent"]
                ancre = departs[0].id if departs else next(iter(mi.activites), None)
            if ancre is None or ed.element(ancre) is None:
                note("ajout-decision", n.id, "", "décision nouvelle « %s »" % n.nom, False,
                     "aucun point d'insertion trouvé dans le processus")
                continue
            tid, gid = ed.ajouter_tache_decision(n.nom, ancre, base_id=identifiant_sur(
                n.id.replace("Decision_", "t_", 1) if n.id.startswith("Decision_") else "t_" + n.nom))
            taches_de[n.id] = tid
            origine_de[n.id] = tid
            note("ajout-decision", n.id, tid,
                 "tâche utilisateur « %s » et passerelle de verdict ajoutées après « %s »"
                 % (n.nom, ed.nom(ancre) or ancre))
    for n in mf_ref.decisions:
        if n.id not in inverse:
            arb["candidats"][n.origine] = False
            note("suppression-decision", n.id, n.origine,
                 "décision retirée du DRD : la tâche « %s » reste dans le processus et "
                 "devient un candidat écarté par arbitrage" % n.nom)

    # 2. données d'entrée -------------------------------------------------------
    objets_de: Dict[str, str] = {}          # donnée du DRD modifié -> élément BPMN
    for n in mf_mod.inputs:
        ref = corr[n.id]
        if ref:
            nref = mf_ref.noeuds[ref]
            objets_de[n.id] = nref.origine
            if normaliser(n.nom) != normaliser(nref.nom):
                if nref.pattern in ("P2", "P3") and ed.element(nref.origine) is not None:
                    ed.renommer(nref.origine, n.nom)
                    note("renommage-donnee", n.id, nref.origine,
                         "« %s » renommé « %s »" % (nref.nom, n.nom))
                elif nref.pattern == "P6":
                    arb["noms"][nref.origine] = n.nom
                    note("renommage-donnee", n.id, nref.origine,
                         "donnée issue d'une annotation : le nom « %s » est posé par arbitrage"
                         % n.nom)
                else:
                    note("renommage-donnee", n.id, nref.origine,
                         "donnée « %s » renommée « %s »" % (nref.nom, n.nom), False,
                         "une variable de condition (P7) ne se renomme pas sans réécrire "
                         "les conditions")
        else:
            lecteurs = [v for u, v in mf_mod.arcs if u == n.id and v in taches_de]
            if not lecteurs:
                note("ajout-donnee", n.id, "", "donnée nouvelle « %s »" % n.nom, False,
                     "aucune décision ne la lit")
                continue
            oid = ed.ajouter_objet(n.nom, taches_de[lecteurs[0]],
                                   base_id=identifiant_sur(n.id.replace("InputData_", "do_", 1)
                                                           if n.id.startswith("InputData_")
                                                           else "do_" + n.nom))
            objets_de[n.id] = oid
            note("ajout-donnee", n.id, oid,
                 "objet de données « %s » ajouté, lu par %s" % (
                     n.nom, ", ".join("« %s »" % ed.nom(taches_de[v]) for v in lecteurs)))
    for n in mf_ref.inputs:
        if n.id in inverse:
            continue
        if n.pattern in ("P2",):
            for a in mf_ref.decisions:
                if (n.id, a.id) in mf_ref.arcs:
                    ed.retirer_lecture(a.origine, n.origine)
            orphelin = ed.retirer_objet_si_orphelin(n.origine)
            note("suppression-donnee", n.id, n.origine,
                 "donnée « %s » retirée du DRD : lectures retirées des tâches%s"
                 % (n.nom, ", objet supprimé (plus aucune lecture)" if orphelin else ""))
        elif n.pattern == "P6":
            arb["annotations"][n.origine] = "non"
            note("suppression-donnee", n.id, n.origine,
                 "donnée issue d'une annotation : l'annotation est écartée par arbitrage")
        elif n.pattern == "P7":
            arb["annotations"]["condition:" + n.nom] = "non"
            note("suppression-donnee", n.id, n.origine,
                 "variable de condition écartée par arbitrage")
        else:
            note("suppression-donnee", n.id, n.origine,
                 "donnée « %s » retirée du DRD" % n.nom, False,
                 "elle vient d'un événement porteur : retirer la définition de message "
                 "ou de signal à la main")

    # 3. exigences d'information ---------------------------------------------------
    arcs_ref_mod = {(inverse.get(u), inverse.get(v)) for u, v in mf_ref.arcs}
    for u, v in mf_mod.arcs:
        tu, tv = mf_mod.noeuds[u].type, mf_mod.noeuds[v].type
        if (u, v) in arcs_ref_mod or tv != DECISION or v not in taches_de:
            continue
        if tu == INPUT_DATA and u in objets_de:
            if corr.get(u) and mf_ref.noeuds[corr[u]].pattern not in ("P2",):
                note("ajout-exigence", "%s -> %s" % (u, v), taches_de[v],
                     "exigence d'information ajoutée", False,
                     "la donnée vient d'un événement, d'une annotation ou d'une condition : "
                     "la relier à la tâche se fait dans l'outil de modélisation")
                continue
            if ed.ajouter_lecture(taches_de[v], objets_de[u]):
                note("ajout-exigence", "%s -> %s" % (u, v), taches_de[v],
                     "lecture de « %s » ajoutée à la tâche « %s »"
                     % (mf_mod.noeuds[u].nom, ed.nom(taches_de[v])))
        elif tu == DECISION and u in taches_de:
            oid = ed.ajouter_objet("Résultat : " + mf_mod.noeuds[u].nom, taches_de[u],
                                   base_id="res_" + taches_de[u])
            ed.ajouter_ecriture(taches_de[u], oid)
            ed.ajouter_lecture(taches_de[v], oid)
            note("ajout-exigence", "%s -> %s" % (u, v), oid,
                 "dépendance entre décisions : objet « %s » écrit par « %s » et lu par « %s »"
                 % (ed.nom(oid), ed.nom(taches_de[u]), ed.nom(taches_de[v])))
        elif tu == KNOWLEDGE_SOURCE or tu == BKM:
            pass                                    # traité avec les sources
    arcs_mod_ref = {(corr.get(u), corr.get(v)) for u, v in mf_mod.arcs}
    for u, v in mf_ref.arcs:
        if (u, v) in arcs_mod_ref or u not in inverse or v not in inverse:
            continue                                # sommet disparu : déjà traité
        nu, nv = mf_ref.noeuds[u], mf_ref.noeuds[v]
        if nv.type != DECISION:
            continue
        if nu.type == INPUT_DATA and nu.pattern == "P2":
            ed.retirer_lecture(nv.origine, nu.origine)
            note("suppression-exigence", "%s -> %s" % (u, v), nv.origine,
                 "lecture de « %s » retirée de la tâche « %s »" % (nu.nom, ed.nom(nv.origine)))
        elif nu.type == DECISION:
            retires = []
            for _, oid in ed.associations_sortie(nu.origine):
                if ed.retirer_lecture(nv.origine, oid):
                    retires.append(oid)
            note("suppression-exigence", "%s -> %s" % (u, v), nv.origine,
                 "dépendance entre décisions retirée : lectures %s retirées de « %s »"
                 % (", ".join("« %s »" % ed.nom(o) for o in retires) or "(aucune)",
                    ed.nom(nv.origine)), bool(retires),
                 "" if retires else "aucune donnée partagée trouvée dans le processus")
        elif nu.type in (INPUT_DATA,):
            note("suppression-exigence", "%s -> %s" % (u, v), nv.origine,
                 "exigence retirée", False,
                 "la donnée vient d'un événement, d'une annotation ou d'une condition")

    # 4. sources de connaissance et BKM --------------------------------------------
    for n in mf_mod.sources + mf_mod.bkms:
        ref = corr[n.id]
        cibles = [v for u, v in mf_mod.arcs if u == n.id and v in taches_de]
        if ref:
            nref = mf_ref.noeuds[ref]
            if normaliser(n.nom) != normaliser(nref.nom):
                if nref.pattern == "P6" and ed.element(nref.origine) is not None:
                    ed.renommer(nref.origine, re.sub(r"^Règle\s*:\s*", "", n.nom))
                    arb["noms"][nref.origine] = n.nom
                    note("renommage-source", n.id, nref.origine,
                         "annotation réécrite « %s »" % n.nom)
                elif nref.pattern == "P5":
                    for lane in ed.racine.xpath(".//bpmn:lane[@name=$n]", namespaces=NS, n=nref.nom):
                        lane.set("name", texte_xml(n.nom))
                    if nref.nom in arb["ressources"]:
                        arb["ressources"][n.nom] = arb["ressources"].pop(nref.nom)
                    note("renommage-source", n.id, "couloir « %s »" % nref.nom,
                         "couloir renommé « %s »" % n.nom)
            # exigences ajoutées depuis cette source
            for v in cibles:
                if (ref, corr.get(v)) in set(mf_ref.arcs):
                    continue
                if nref.pattern == "P6":
                    asid = ed.associer_annotation(nref.origine, taches_de[v])
                    note("ajout-exigence", "%s -> %s" % (n.id, v), taches_de[v],
                         "annotation « %s » associée à la tâche « %s »"
                         % (nref.nom, ed.nom(taches_de[v])), asid is not None)
                else:
                    note("ajout-exigence", "%s -> %s" % (n.id, v), taches_de[v],
                         "le rôle « %s » devrait gouverner « %s »" % (n.nom, ed.nom(taches_de[v])),
                         False, "un rôle gouverne par le couloir : déplacer la tâche dans ce "
                                "couloir se fait dans l'outil de modélisation")
        else:
            if not cibles:
                note("ajout-source", n.id, "", "source nouvelle « %s »" % n.nom, False,
                     "aucune décision ne la requiert")
                continue
            texte = re.sub(r"^Règle\s*:\s*", "", n.nom) if n.type == BKM else n.nom
            anid, _ = ed.ajouter_annotation(texte, taches_de[cibles[0]],
                                            base_id=identifiant_sur("annot_" + n.id))
            for v in cibles[1:]:
                ed.associer_annotation(anid, taches_de[v])
            arb["annotations"][anid] = "KS" if n.type == KNOWLEDGE_SOURCE else "BKM"
            arb["noms"][anid] = n.nom
            note("ajout-source", n.id, anid,
                 "annotation « %s » ajoutée et qualifiée %s par arbitrage, associée à %s"
                 % (texte, "source de connaissance" if n.type == KNOWLEDGE_SOURCE
                    else "modèle de connaissance métier",
                    ", ".join("« %s »" % ed.nom(taches_de[v]) for v in cibles)))
    for n in mf_ref.sources + mf_ref.bkms:
        if n.id in inverse:
            # exigences retirées depuis cette source
            for u, v in mf_ref.arcs:
                if u != n.id or (inverse.get(u), inverse.get(v)) in set(mf_mod.arcs) \
                   or v not in inverse:
                    continue
                nv = mf_ref.noeuds[v]
                if n.pattern == "P6":
                    ed.retirer_association_annotation(n.origine, nv.origine)
                    note("suppression-exigence", "%s -> %s" % (u, v), nv.origine,
                         "association de l'annotation « %s » à « %s » retirée" % (n.nom, nv.nom))
                else:
                    note("suppression-exigence", "%s -> %s" % (u, v), nv.origine,
                         "le rôle « %s » ne gouverne plus « %s »" % (n.nom, nv.nom), False,
                         "un rôle gouverne toutes les tâches de son couloir : déplacer la tâche "
                         "ou écarter le rôle (arbitrage « non »)")
            continue
        if n.pattern == "P6":
            for v in [v for u, v in mf_ref.arcs if u == n.id]:
                ed.retirer_association_annotation(n.origine, mf_ref.noeuds[v].origine)
            arb["annotations"][n.origine] = "non"
            note("suppression-source", n.id, n.origine,
                 "annotation « %s » dissociée des décisions et écartée par arbitrage" % n.nom)
        else:
            arb["ressources"][n.nom] = "non"
            note("suppression-source", n.id, "couloir « %s »" % n.nom,
                 "rôle écarté par arbitrage (il applique, il ne gouverne plus)")

    # 5. tables de décision -> conditions des flux ---------------------------------
    for did, table in mf_mod.logique.items():
        if did not in taches_de or not table.get("regles"):
            continue
        tid = taches_de[did]
        gid = ed.passerelle_apres(tid)
        if gid is None:
            note("table", did, tid, "table de décision sans passerelle après la tâche", False,
                 "aucune passerelle exclusive ou inclusive ne suit la tâche")
            continue
        types = {c["variable"]: c.get("type", "string") for c in table.get("entrees", [])}
        flux = ed.flux_sortants(gid)
        regles = table["regles"]
        appariement = _apparier_regles(ed, regles, flux)
        nb = 0
        for regle, f in appariement:
            if f is None:
                note("table", did, gid, "règle « %s » sans flux correspondant" % regle["branche"],
                     False, "ni libellé de flux ni nœud cible ne porte ce nom et les nombres "
                            "diffèrent")
                continue
            if regle.get("defaut"):
                ed.element(gid).set("default", f.get("id"))
                ed.poser_condition(f, "")
                nb += 1
                continue
            expression = feel.regle_vers_condition(regle["cellules"], types)
            if expression:
                ed.poser_condition(f, expression)
                if regle["branche"] and not f.get("name"):
                    f.set("name", texte_xml(regle["branche"]))
                nb += 1
        if nb:
            note("table", did, gid, "%d condition(s) de flux écrite(s) en FEEL depuis la table "
                 "de décision" % nb)

    # 6. vérification : T(BPMN') = DRD modifié ? -------------------------------------
    bpmn_prime = ed.document()
    arb_obj = Arbitrages.depuis_json(arb)
    try:
        mf_prime = transformer(parser_bpmn(bpmn_prime, est_texte=True), arb_obj, ext)
        # une tâche renommée peut ne plus être corroborée par kappa (verbe hors
        # lexique, pas de passerelle) : le DRD la tient pourtant pour une
        # décision, l'arbitrage « candidat confirmé » le dit au processus
        perdues = [d for d, tid in taches_de.items()
                   if tid not in mf_prime.delta and arb["candidats"].get(tid) is not False]
        if perdues:
            for d in perdues:
                arb["candidats"][taches_de[d]] = True
                note("arbitrage", d, taches_de[d],
                     "la tâche « %s » n'est plus corroborée par kappa : confirmée comme "
                     "décision par arbitrage" % ed.nom(taches_de[d]))
            arb_obj = Arbitrages.depuis_json(arb)
            mf_prime = transformer(parser_bpmn(bpmn_prime, est_texte=True), arb_obj, ext)
        attendu = copy.copy(mf_mod)
        attendu.noeuds = {k: v for k, v in mf_mod.noeuds.items()
                          if k not in {o.id for o in orphelins}}
        ok, ecarts = equivalents(attendu, mf_prime)
        rapport.coherent, rapport.ecarts = ok, ecarts
        if mf_mod.logique:
            rapport.tables_coherentes, rapport.ecarts_tables = _comparer_tables(mf_mod, mf_prime)
    except Exception as e:                              # pragma: no cover
        rapport.coherent, rapport.ecarts = False, ["transformation du BPMN mis à jour : %s" % e]
    rapport.arbitrages = arb
    rapport.resume = {"changements": len(rapport.changements),
                      "appliques": sum(1 for c in rapport.changements if c.applique),
                      "decisions": len(mf_mod.decisions), "exigences": len(mf_mod.arcs)}
    return bpmn_prime, arb, rapport


def _apparier_regles(ed: EditeurBPMN, regles: List[Dict], flux: List) -> List[Tuple[Dict, object]]:
    """Chaque règle à un flux sortant : par libellé de flux, par nom du
    nœud cible, sinon par rang quand les nombres coïncident."""
    restants = list(flux)
    paires: List[Tuple[Dict, object]] = []
    sans = []
    for r in regles:
        trouve = None
        nb = normaliser(r["branche"])
        for f in restants:
            if normaliser(f.get("name") or "") == nb or \
               normaliser(ed.nom(f.get("targetRef"))) == nb:
                trouve = f
                break
        if trouve is not None:
            restants.remove(trouve)
            paires.append((r, trouve))
        else:
            sans.append(r)
    if sans and len(sans) == len(restants):
        paires.extend(zip(sans, restants))
    else:
        paires.extend((r, None) for r in sans)
    return paires


def _comparer_tables(mf_mod: Mf, mf_prime: Mf) -> Tuple[bool, List[str]]:
    """Les règles lues du DRD modifié se retrouvent-elles dans les tables
    que T tire du BPMN mis à jour (mêmes cellules, même sortie) ?"""
    ecarts: List[str] = []
    for did, table in mf_mod.logique.items():
        attendu = {(tuple(sorted((k, v) for k, v in r["cellules"].items() if v.strip() not in ("", "-"))),
                    normaliser(r["branche"])) for r in table["regles"] if r.get("lue")}
        if not attendu:
            continue
        produit = mf_prime.logique.get(did)
        if produit is None:
            ecarts.append("%s : aucune table produite" % did)
            continue
        obtenu = {(tuple(sorted((k, v) for k, v in r["cellules"].items() if v.strip() not in ("", "-"))),
                   normaliser(r["branche"])) for r in produit["regles"] if r.get("lue")}
        if attendu - obtenu:
            ecarts.append("%s : règles non retrouvées %s" % (did, sorted(attendu - obtenu)))
    return (not ecarts, ecarts)


# ----------------------------------------------------------------------
# analyse d'impact BPMN -> DMN
# ----------------------------------------------------------------------
def impact(texte_dmn_ancien: str, texte_bpmn_nouveau: str,
           arbitrages: Optional[Arbitrages] = None, extensions=()) -> Dict:
    """Ce qu'une modification du processus change au DRD : le DRD que T
    tire du nouveau BPMN est comparé, sommet par sommet et exigence par
    exigence (identifiants stables), au DRD précédemment produit."""
    ancien = parser_dmn(texte_dmn_ancien, est_texte=True, exiger_decision=False)
    mi = parser_bpmn(texte_bpmn_nouveau, est_texte=True)
    ext = set(extensions or ())
    if ancien.logique:
        ext.add("logique")
    nouveau = transformer(mi, arbitrages or Arbitrages(), ext)
    corr = _correspondance(nouveau, ancien)          # nouveau -> ancien
    inverse = {v: k for k, v in corr.items() if v}

    def fiche(mf, nid):
        n = mf.noeuds[nid]
        return {"id": nid, "type": n.type, "nom": n.nom, "origine": n.origine,
                "pattern": n.pattern}

    rapport = {
        "sommets_conserves": [], "sommets_renommes": [], "sommets_nouveaux": [],
        "sommets_disparus": [], "exigences_conservees": [], "exigences_nouvelles": [],
        "exigences_invalidees": [], "tables": [], "points_expert_nouveaux": [],
    }
    for nid, ref in corr.items():
        if ref is None:
            rapport["sommets_nouveaux"].append(fiche(nouveau, nid))
        elif normaliser(nouveau.noeuds[nid].nom) != normaliser(ancien.noeuds[ref].nom):
            f = fiche(nouveau, nid)
            f["ancien_nom"] = ancien.noeuds[ref].nom
            rapport["sommets_renommes"].append(f)
        else:
            rapport["sommets_conserves"].append(fiche(nouveau, nid))
    for nid in ancien.noeuds:
        if nid not in inverse:
            rapport["sommets_disparus"].append(fiche(ancien, nid))
    arcs_anciens = set(ancien.arcs)
    arcs_nouveaux_en_ancien = {(corr.get(u), corr.get(v)): (u, v) for u, v in nouveau.arcs}
    for u, v in nouveau.arcs:
        a = (corr.get(u), corr.get(v))
        entree = {"de": nouveau.noeuds[u].nom, "vers": nouveau.noeuds[v].nom,
                  "pattern": nouveau.arcs_origine.get((u, v), "")}
        (rapport["exigences_conservees"] if a in arcs_anciens
         else rapport["exigences_nouvelles"]).append(entree)
    for u, v in ancien.arcs:
        if (u, v) not in arcs_nouveaux_en_ancien:
            rapport["exigences_invalidees"].append(
                {"de": ancien.noeuds[u].nom, "vers": ancien.noeuds[v].nom,
                 "pattern": ancien.arcs_origine.get((u, v), ""),
                 "motif": "sommet disparu" if u not in inverse or v not in inverse
                 else "le processus ne porte plus cette dépendance"})
    for did, table in ancien.logique.items():
        nid = inverse.get(did)
        if nid is None:
            rapport["tables"].append({"decision": ancien.noeuds[did].nom, "etat": "décision disparue"})
            continue
        prod = nouveau.logique.get(nid)
        if prod is None:
            rapport["tables"].append({"decision": nouveau.noeuds[nid].nom,
                                      "etat": "plus de passerelle après la tâche"})
            continue
        def cle(r):
            return (normaliser(r["branche"]),
                    tuple(sorted((k, v) for k, v in r["cellules"].items()
                                 if (v or "").strip() not in ("", "-"))))
        anciennes = {cle(r) for r in table["regles"]}
        nouvelles = {cle(r) for r in prod["regles"]}
        rapport["tables"].append({"decision": nouveau.noeuds[nid].nom,
                                  "etat": "identique" if anciennes == nouvelles else "modifiée",
                                  "regles_avant": len(anciennes), "regles_apres": len(nouvelles)})
    rapport["points_expert_nouveaux"] = [{"categorie": p.categorie, "objet": p.objet,
                                          "motif": p.motif} for p in nouveau.a_confirmer]
    ok, ecarts = equivalents(ancien, nouveau)
    rapport["identique"] = ok
    rapport["ecarts"] = ecarts
    rapport["resume"] = {k: len(v) for k, v in rapport.items() if isinstance(v, list)}
    return rapport


# ----------------------------------------------------------------------
# fichier de trace
# ----------------------------------------------------------------------
def fichier_trace(mi, mf: Mf, chemin_bpmn: str = "", chemin_dmn: str = "",
                  empreinte_bpmn: str = "", arbitrages: Optional[Arbitrages] = None) -> Dict:
    """Le contenu du fichier `.trace.json` écrit à côté du DMN : pour chaque
    sommet et chaque exigence du DRD, l'élément BPMN d'origine, le patron et
    le motif ; les arbitrages appliqués ; l'empreinte du BPMN source."""
    return {
        "bpmn": chemin_bpmn, "empreinte_bpmn_sha256": empreinte_bpmn, "dmn": chemin_dmn,
        "processus": mf.nom, "extensions": list(mf.extensions),
        "sommets": [{"dmn": n.id, "type": n.type, "nom": n.nom, "bpmn": n.origine,
                     "libelle_bpmn": (mi.noeuds[n.origine].nom if n.origine in mi.noeuds
                                      else mi.donnees[n.origine].nom
                                      if n.origine in mi.donnees else ""),
                     "pattern": n.pattern,
                     "motif": mf.motifs_corroboration.get(n.id, "")}
                    for n in mf.noeuds.values()],
        "exigences": [{"de": u, "vers": v, "genre": "IR" if (u, v) in set(mf.IR)
                       else "KR" if (u, v) in set(mf.KR) else "AR",
                       "pattern": mf.arcs_origine.get((u, v), "")} for u, v in mf.arcs],
        "arbitrages": {
            "candidats": dict(arbitrages.candidats), "ressources": dict(arbitrages.ressources),
            "annotations": dict(arbitrages.annotations),
            "renommages": dict(arbitrages.renommages), "noms": dict(arbitrages.noms)}
        if arbitrages else {},
        "points_expert": [{"cle": p.cle, "categorie": p.categorie, "objet": p.objet}
                          for p in mf.a_confirmer],
    }
