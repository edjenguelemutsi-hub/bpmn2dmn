# -*- coding: utf-8 -*-
"""
Transformation inverse T_inv : DMN (DRD) -> BPMN 2.0, le chemin retour.

Un DRD ne contient pas toute l'information d'un processus (ordre
d'exécution, branches et ressources ont été abstraits par T). T_inv
reconstruit donc le squelette de processus canonique dont la transformation
directe redonne le DRD de départ : chaque décision devient une tâche
utilisateur suivie d'une passerelle exclusive (l'indice de position de kappa
est garanti par construction), les tâches sont ordonnées topologiquement
selon les IR décision -> décision, chaque IR d1 -> d2 devient un objet de
données écrit par d1 et lu par d2 (retrouvé par P4 raffiné, exclu par P2
raffiné), chaque donnée d'entrée un objet lu (P2), chaque source ou BKM une
annotation associée (P6). Un fichier d'arbitrages accompagne le BPMN pour
fixer les verdicts gamma et les noms, de sorte que T(T_inv(Mf)) = Mf.

Un nœud orphelin du DRD (donnée ou source sans exigence) n'a pas d'image
dans un processus, T ne créant un nœud que relié à une décision : il est
omis du squelette et l'équivalence d'aller-retour le signale.

La fonction `inverser` enchaîne les étapes ; `_Squelette` porte l'état du
document en construction (éléments MODEL, éléments DI, positions).
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import quoteattr, escape

from .metamodeles import (BKM, DECISION, INPUT_DATA, KNOWLEDGE_SOURCE,
                          Mf, NoeudMf)
from .serialiseur import texte_xml

# rangées du squelette : données (70), tâches (230), fins d'arrêt (360),
# annotations (452) ; les associations sont routées orthogonalement dans
# les inter-rangées, avec des ancrages décalés pour ne pas se recouvrir
X0, Y_DONNEES, Y_TACHES, Y_FIN, Y_ANNOT = 60, 70, 230, 360, 452
PAS = 240
LT, HT = 140, 80           # tâche
H_DON = 50                 # objet de données

Rect = Tuple[float, float, float, float]


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


class ErreurDMN(Exception):
    """Fichier DMN illisible ou sans décision."""


def parser_dmn(chemin_ou_texte: str, est_texte: bool = False,
               exiger_decision: bool = True) -> Mf:
    """Lit un fichier (ou une chaîne) DMN, versions 1.1 à 1.5, et construit
    Mf. Un DRD sans décision est refusé, sauf demande contraire (relecture
    d'un DRD que T a produit vide)."""
    try:
        if est_texte:
            racine = ET.parse(io.StringIO(chemin_ou_texte)).getroot()
        else:
            racine = ET.parse(chemin_ou_texte).getroot()
    except ET.ParseError as e:
        raise ErreurDMN("XML mal formé : %s" % e) from e
    if _local(racine.tag) != "definitions":
        raise ErreurDMN("La racine n'est pas <definitions> (DMN attendu).")

    mf = Mf(nom=racine.get("name") or racine.get("id") or "DRD")
    correspondance = {"decision": DECISION, "inputData": INPUT_DATA,
                      "knowledgeSource": KNOWLEDGE_SOURCE,
                      "businessKnowledgeModel": BKM}

    # les nœuds
    for elem in racine:
        t = _local(elem.tag)
        if t in correspondance:
            nid = elem.get("id") or ("n%d" % (len(mf.noeuds) + 1))
            mf.noeuds[nid] = NoeudMf(id=nid, type=correspondance[t],
                                     nom=elem.get("name") or nid)

    if exiger_decision and not mf.decisions:
        raise ErreurDMN("Aucune décision dans le fichier DMN.")

    # les exigences (href="#id")
    def cible_href(e: ET.Element) -> Optional[str]:
        for enfant in e:
            h = enfant.get("href") or ""
            if h.startswith("#"):
                return h[1:]
        return None

    for elem in racine:
        t = _local(elem.tag)
        if t not in correspondance:
            continue
        vid = elem.get("id")
        for req in elem:
            rt = _local(req.tag)
            if rt in ("informationRequirement", "knowledgeRequirement",
                      "authorityRequirement"):
                u = cible_href(req)
                if u and u in mf.noeuds and vid in mf.noeuds:
                    arc = (u, vid)
                    if arc not in mf.arcs:
                        mf.arcs.append(arc)
    return mf


def _tri_topologique(mf: Mf) -> List[str]:
    """Ordre topologique des décisions selon les IR décision -> décision
    (les décisions requises d'abord), stable par ordre du document."""
    dec = [n.id for n in mf.decisions]
    rang = {d: i for i, d in enumerate(dec)}
    requises: Dict[str, List[str]] = {d: [] for d in dec}
    for u, v in mf.arcs:
        if u in requises and v in requises:
            requises[v].append(u)
    resultat: List[str] = []
    etat: Dict[str, int] = {}       # 1 : en cours, 2 : classée

    def par_rang(d):
        return iter(sorted(requises[d], key=lambda x: rang[x]))

    # parcours en profondeur, pile explicite : une chaîne de plusieurs
    # milliers de décisions dépasserait la pile d'appels. Une requise en
    # cours de visite (cycle : DRD invalide signalé ailleurs) est ignorée.
    for depart in dec:
        if depart in etat:
            continue
        etat[depart] = 1
        pile = [(depart, par_rang(depart))]
        while pile:
            d, restantes = pile[-1]
            for r in restantes:
                if r not in etat:
                    etat[r] = 1
                    pile.append((r, par_rang(r)))
                    break
            else:
                etat[d] = 2
                resultat.append(d)
                pile.pop()
    return resultat


def inverser(mf: Mf, nom_processus: str = "") -> Tuple[str, Dict]:
    """Mf -> (document BPMN 2.0 + BPMNDI, arbitrages garantissant l'aller-retour)."""
    squelette = _Squelette(mf, nom_processus)
    squelette.poser_chaine_principale()      # début -> [tâche -> passerelle]* -> fins
    squelette.poser_donnees_entree()         # P2 : objets lus
    squelette.poser_objets_resultat()        # P4 : IR décision -> décision
    squelette.poser_annotations()            # P6 : sources et BKM
    corps = squelette.injecter_associations_donnees()
    corps = squelette.ajouter_flux_sequence(corps)
    return squelette.assembler(corps, squelette.formes_di()), squelette.arbitrages


def _arete_di(eid: str, points: List[Tuple[float, float]]) -> str:
    """Élément BPMNEdge d'une arête, par ses points de passage."""
    wp = "".join('<di:waypoint x="%d" y="%d"/>' % (round(a), round(b))
                 for a, b in points)
    return ('      <bpmndi:BPMNEdge id="die_%s" bpmnElement="%s">%s'
            '</bpmndi:BPMNEdge>' % (eid, eid, wp))


class _Squelette:
    """Le squelette de processus en construction et ses étapes."""

    def __init__(self, mf: Mf, nom_processus: str):
        self.mf = mf
        self.ordre = _tri_topologique(mf)
        self.nom = texte_xml(nom_processus or (mf.nom or "Processus reconstruit"))
        self.noms = {n.id: texte_xml(n.nom) for n in mf.noeuds.values()}
        self.arbitrages: Dict[str, Dict] = {"annotations": {}, "renommages": {},
                                            "ressources": {}, "candidats": {},
                                            "noms": {}}
        self.pris: Dict[str, int] = {}             # identifiants déjà attribués
        self.M: List[str] = []                     # éléments MODEL
        self.DI: List[str] = []                    # éléments DI (arêtes)
        self.flux: List[Tuple[str, str, str, str]] = []   # (id, source, cible, nom)
        self.n_flux = 0
        self.pos: Dict[str, Rect] = {}
        self.occupes_donnees: List[float] = []     # centres x de la rangée données
        self.taches: Dict[str, str] = {}           # décision -> id de tâche
        self.passerelles: Dict[str, str] = {}      # décision -> id de passerelle
        self.assoc_data: List[Tuple[str, str, str]] = []   # (genre, donnée, tâche)

    # ------------------------------------------------------------------
    # services
    # ------------------------------------------------------------------
    def id_sur(self, prefixe: str, brut: str) -> str:
        """Identifiant XML unique même après nettoyage (« d.1 » et « d-1 »
        se réduisent tous deux à « d_1 » : on suffixe alors un compteur)."""
        base = prefixe + re.sub(r"[^A-Za-z0-9_]", "_", brut)
        n = self.pris.get(base, 0)
        self.pris[base] = n + 1
        return base if n == 0 else "%s_%d" % (base, n + 1)

    def flecher(self, s: str, t: str, nomf: str = "") -> str:
        """Déclare un flux de séquence s -> t et retourne son identifiant."""
        self.n_flux += 1
        fid = "f%d" % self.n_flux
        self.flux.append((fid, s, t, nomf))
        return fid

    def caser_donnee(self, cx: float) -> float:
        """Abscisse libre sur la rangée des données, à droite du souhait."""
        cx = max(X0 + 40, cx)
        while any(abs(cx - o) < 165 for o in self.occupes_donnees):
            cx += 165
        self.occupes_donnees.append(cx)
        return cx

    def _declarer_objet(self, oid: str, nom: str) -> None:
        """dataObjectReference + son dataObject porteur ; le porteur passe
        lui aussi par id_sur : « X » et « X_o » donneraient sinon deux
        fois le même identifiant."""
        oid_o = self.id_sur(oid, "_o")
        self.M.append('    <bpmn:dataObjectReference id="%s" name=%s '
                      'dataObjectRef="%s"/>' % (oid, quoteattr(nom), oid_o))
        self.M.append('    <bpmn:dataObject id="%s"/>' % oid_o)

    # ------------------------------------------------------------------
    # étapes
    # ------------------------------------------------------------------
    def poser_chaine_principale(self) -> None:
        """start -> [tâche_d -> passerelle_d]* -> end ; chaque passerelle a
        une branche « poursuivre » et sa propre fin « arrêter » juste
        dessous, ce qui évite les longues diagonales à travers le diagramme.
        L'événement de départ est sans définition de message : un départ
        porteur créerait par P3 une donnée d'entrée absente du DRD d'origine
        et briserait l'aller-retour T(T_inv(Mf)) = Mf."""
        M, pos = self.M, self.pos
        M.append('    <bpmn:startEvent id="debut" name="Début"/>')
        pos["debut"] = (X0, Y_TACHES + HT / 2 - 18, 36, 36)
        precedent = "debut"
        x = X0 + 120

        for did in self.ordre:
            d = self.mf.noeuds[did]
            tid = self.id_sur("t_", did)
            gid = self.id_sur("g_", did)
            self.taches[did] = tid
            self.passerelles[did] = gid
            M.append('    <bpmn:userTask id="%s" name=%s>'
                     % (tid, quoteattr(self.noms[did])))
            M.append('    </bpmn:userTask>')
            M.append('    <bpmn:exclusiveGateway id="%s" name=%s/>'
                     % (gid, quoteattr("Verdict : " + self.noms[did])))
            self.flecher(precedent, tid)
            self.flecher(tid, gid)
            pos[tid] = (x, Y_TACHES, LT, HT)
            pos[gid] = (x + LT + 40, Y_TACHES + HT / 2 - 25, 50, 50)
            precedent = gid
            x += PAS + 90
            self.arbitrages["renommages"][tid] = d.nom

        M.append('    <bpmn:endEvent id="fin_ok" name="Processus poursuivi"/>')
        pos["fin_ok"] = (x, Y_TACHES + HT / 2 - 18, 36, 36)
        self.flecher(precedent, "fin_ok", "poursuivre")
        # une fin d'arrêt locale sous chaque passerelle, en descente verticale
        for i, did in enumerate(self.ordre):
            gid = self.passerelles[did]
            fid_fin = "fin_arret_%d" % (i + 1)
            M.append('    <bpmn:endEvent id="%s" name="Instruction arrêtée"/>'
                     % fid_fin)
            gx, _, gw, _ = pos[gid]
            pos[fid_fin] = (gx + gw / 2 - 18, Y_FIN, 36, 36)
            self.flecher(gid, fid_fin, "arrêter")

    def poser_donnees_entree(self) -> None:
        """P2 : chaque objet est posé au-dessus de son premier lecteur,
        espacé pour que ni les formes ni les libellés ne se recouvrent."""
        for j, n in enumerate(self.mf.inputs):
            oid = self.id_sur("do_", n.id)
            self._declarer_objet(oid, self.noms[n.id])
            lecteurs = [v for u, v in self.mf.arcs
                        if u == n.id and v in self.taches]
            xs = [self.pos[self.taches[v]][0] + LT / 2 for v in lecteurs] \
                or [X0 + 120 + j * 160]
            cx = self.caser_donnee(min(xs))
            self.pos[oid] = (cx - 18, Y_DONNEES, 36, H_DON)
            for v in lecteurs:
                self.assoc_data.append(("in", oid, self.taches[v]))

    def poser_objets_resultat(self) -> None:
        """P4 : chaque IR décision -> décision devient un objet « Résultat »
        écrit par la source et lu par la cible, posé entre les deux."""
        mf, pos = self.mf, self.pos
        resultats: Dict[str, str] = {}      # décision source -> id d'objet résultat
        for u, v in mf.arcs:
            if mf.noeuds[u].type == DECISION and mf.noeuds[v].type == DECISION:
                if u not in resultats:
                    resultats[u] = self.id_sur("res_", u)
                rid = resultats[u]
                if rid not in pos:
                    self._declarer_objet(rid, "Résultat : " + self.noms[u])
                    # entre l'écrivain et son premier lecteur
                    xu = pos[self.taches[u]][0] + LT / 2
                    xv = pos[self.taches[v]][0] + LT / 2
                    cx = self.caser_donnee((xu + xv) / 2)
                    pos[rid] = (cx - 18, Y_DONNEES, 36, H_DON)
                    self.assoc_data.append(("out", rid, self.taches[u]))
                self.assoc_data.append(("in", rid, self.taches[v]))

    def poser_annotations(self) -> None:
        """P6 : sources de connaissance et BKM -> annotations et arbitrages.
        L'annotation se centre sous sa première tâche cible (rangée dédiée,
        sous les fins d'arrêt), association orthogonale."""
        M, DI, pos = self.M, self.DI, self.pos
        for k_annot, n in enumerate(self.mf.sources + self.mf.bkms, start=1):
            anid = "annot%d" % k_annot
            if n.type == KNOWLEDGE_SOURCE:
                texte = self.noms[n.id]
                self.arbitrages["annotations"][anid] = "KS"
            else:
                texte = re.sub(r"^Règle\s*:\s*", "", self.noms[n.id])
                self.arbitrages["annotations"][anid] = "BKM"
            # restitution exacte du libellé au retour (préfixe « Règle : »
            # absent, nom long, homonymes... : le nom d'origine fait foi)
            self.arbitrages["noms"][anid] = n.nom
            M.append('    <bpmn:textAnnotation id="%s"><bpmn:text>%s'
                     '</bpmn:text></bpmn:textAnnotation>' % (anid, escape(texte)))
            cibles = [v for u, v in self.mf.arcs
                      if u == n.id and v in self.taches]
            if cibles:
                tx0 = pos[self.taches[cibles[0]]][0]
                ax = tx0 + LT / 2 - 100
            else:
                ax = X0
            while any(abs(ax - p[0]) < 220 for p in pos.values()
                      if abs(p[1] - Y_ANNOT) < 4):
                ax += 220
            pos[anid] = (ax, Y_ANNOT, 200, 48)
            for k, v in enumerate(cibles):
                aid = "assoc_%s_%d" % (anid, k)
                M.append('    <bpmn:association id="%s" sourceRef="%s" '
                         'targetRef="%s"/>' % (aid, anid, self.taches[v]))
                tx, ty, tw, th = pos[self.taches[v]]
                acx = ax + 100
                tcx = tx + tw / 2 - 14
                if abs(acx - tcx) < 6:
                    DI.append(_arete_di(aid, [(acx, Y_ANNOT), (tcx, ty + th)]))
                else:
                    my = ty + th + 26
                    DI.append(_arete_di(aid, [(acx, Y_ANNOT), (acx, my),
                                              (tcx, my), (tcx, ty + th)]))

    def injecter_associations_donnees(self) -> List[str]:
        """Les associations de données sont des éléments enfants des
        tâches : chaque bloc userTask est réécrit en y injectant ses
        lectures et ses écritures. Lectures : entrée par le haut de la
        tâche, ancrages décalés, couloir horizontal au-dessus de la rangée
        des tâches ; écritures : sortie par le haut à droite, couloir
        distinct."""
        lectures: Dict[str, List[str]] = {}
        ecritures: Dict[str, List[str]] = {}
        for genre, donnee, tache in self.assoc_data:
            (lectures if genre == "in" else ecritures) \
                .setdefault(tache, []).append(donnee)

        n_assoc = 0
        corps: List[str] = []
        for ligne in self.M:
            if '<bpmn:userTask id="' not in ligne:
                corps.append(ligne)
                continue
            tid = ligne.split('id="')[1].split('"')[0]
            corps.append(ligne)
            tx, ty, tw, _ = self.pos[tid]
            # le XSD BPMN 2.0 exige un targetRef sur chaque
            # dataInputAssociation : une propriété interne de la tâche
            # sert de cible (même convention que Camunda Modeler)
            if lectures.get(tid):
                corps.append('      <bpmn:property id="prop_%s" '
                             'name="__targetRef_placeholder"/>' % tid)
            for k, donnee in enumerate(lectures.get(tid, [])):
                n_assoc += 1
                corps.append('      <bpmn:dataInputAssociation id="dia%d">'
                             '<bpmn:sourceRef>%s</bpmn:sourceRef>'
                             '<bpmn:targetRef>prop_%s</bpmn:targetRef>'
                             '</bpmn:dataInputAssociation>'
                             % (n_assoc, donnee, tid))
                ox, oy, ow, oh = self.pos[donnee]
                ocx = ox + ow / 2
                dock = tx + 24 + k * 26
                if abs(ocx - dock) < 6:
                    self.DI.append(_arete_di("dia%d" % n_assoc,
                                             [(ocx, oy + oh), (dock, ty)]))
                else:
                    my = ty - 26 - (k % 3) * 10
                    self.DI.append(_arete_di("dia%d" % n_assoc,
                                             [(ocx, oy + oh), (ocx, my),
                                              (dock, my), (dock, ty)]))
            for k, donnee in enumerate(ecritures.get(tid, [])):
                n_assoc += 1
                corps.append('      <bpmn:dataOutputAssociation id="doa%d">'
                             '<bpmn:targetRef>%s</bpmn:targetRef>'
                             '</bpmn:dataOutputAssociation>'
                             % (n_assoc, donnee))
                ox, oy, ow, oh = self.pos[donnee]
                ocx = ox + ow / 2
                dock = tx + tw - 24 - k * 26
                if abs(ocx - dock) < 6:
                    self.DI.append(_arete_di("doa%d" % n_assoc,
                                             [(dock, ty), (ocx, oy + oh)]))
                else:
                    my = ty - 48 - (k % 3) * 10
                    self.DI.append(_arete_di("doa%d" % n_assoc,
                                             [(dock, ty), (dock, my),
                                              (ocx, my), (ocx, oy + oh)]))
        return corps

    def ajouter_flux_sequence(self, corps: List[str]) -> List[str]:
        """Flux de séquence ancrés bord à bord. Conformité XSD : les
        artefacts (annotations, associations) doivent suivre tous les
        éléments de flux dans <process>, ils sont donc reportés en fin."""
        artefacts = [l for l in corps if "<bpmn:textAnnotation" in l
                     or "<bpmn:association " in l]
        corps = [l for l in corps if l not in artefacts]
        for fid, s, t, nomf in self.flux:
            attr_nom = " name=%s" % quoteattr(nomf) if nomf else ""
            corps.append('    <bpmn:sequenceFlow id="%s" sourceRef="%s" '
                         'targetRef="%s"%s/>' % (fid, s, t, attr_nom))
            sx, sy, sw, sh = self.pos[s]
            tx, ty, tw, th = self.pos[t]
            scx, scy = sx + sw / 2, sy + sh / 2
            tcx, tcy = tx + tw / 2, ty + th / 2
            if abs(scy - tcy) < 4:                       # même rangée
                self.DI.append(_arete_di(fid, [(sx + sw, scy), (tx, tcy)]))
            elif tcy > scy:                              # descente (fin d'arrêt)
                self.DI.append(_arete_di(fid, [(scx, sy + sh), (tcx, ty)]))
            else:
                self.DI.append(_arete_di(fid, [(sx + sw, scy),
                                               ((sx + sw + tx) / 2, scy),
                                               ((sx + sw + tx) / 2, tcy),
                                               (tx, tcy)]))
        corps.extend(artefacts)              # artefacts en dernier (XSD)
        return corps

    def formes_di(self) -> List[str]:
        """Formes DI : libellés des passerelles au-dessus du losange
        (dégagés de la branche « arrêter »), libellés des données à droite
        (dégagés des flèches)."""
        ids_passerelles = set(self.passerelles.values())
        ids_donnees = {nid for nid, p in self.pos.items()
                       if abs(p[1] - Y_DONNEES) < 4}
        shapes = []
        for nid, (px, py, w, h) in self.pos.items():
            label = ""
            if nid in ids_passerelles:
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" '
                         'width="150" height="40"/></bpmndi:BPMNLabel>'
                         % (round(px + w / 2 - 75), round(py - 46)))
            elif nid in ids_donnees:
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" '
                         'width="120" height="28"/></bpmndi:BPMNLabel>'
                         % (round(px + w + 6), round(py + h / 2 - 14)))
            shapes.append('      <bpmndi:BPMNShape id="di_%s" bpmnElement="%s">'
                          '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>%s'
                          '</bpmndi:BPMNShape>'
                          % (nid, nid, round(px), round(py), round(w), round(h),
                             label))
        return shapes

    def assembler(self, corps: List[str], shapes: List[str]) -> str:
        """Le document BPMN complet : definitions, process, BPMNDI."""
        pid = "Process_" + re.sub(r"[^A-Za-z0-9_]", "_", self.nom)[:32]
        doc = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<bpmn:definitions '
            'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
            'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
            'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
            'id="Definitions_inverse" targetNamespace="http://bpmn2dmn/inverse" '
            'exporter="bpmn2dmn" exporterVersion="1.0">',
            '  <bpmn:process id="%s" name=%s isExecutable="false">'
            % (pid, quoteattr(self.nom)),
        ]
        doc.extend(corps)
        doc.append('  </bpmn:process>')
        doc.append('  <bpmndi:BPMNDiagram id="diag_inverse">')
        doc.append('    <bpmndi:BPMNPlane id="plane_inverse" bpmnElement="%s">' % pid)
        doc.extend(shapes)
        doc.extend(self.DI)
        doc.append('    </bpmndi:BPMNPlane>')
        doc.append('  </bpmndi:BPMNDiagram>')
        doc.append('</bpmn:definitions>')
        return "\n".join(doc) + "\n"
