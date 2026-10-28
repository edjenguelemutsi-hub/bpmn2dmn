# -*- coding: utf-8 -*-
"""
Mise en page BPMN automatique : ajoute un bloc BPMNDI aux modèles qui n'en
ont pas (exports partiels, modèles générés) pour qu'ils s'affichent dans
bpmn-js ou Camunda Modeler.

Le niveau d'un nœud est la longueur du plus long chemin depuis un nœud
sans prédécesseur (les arcs de retour des boucles sont ignorés), chaque
niveau devenant une colonne ; les nœuds de données sont placés au-dessus
de leur première activité liée, les annotations en dessous. Dans une
collaboration, chaque processus occupe sa propre bande horizontale et son
participant est dessiné comme un cadre englobant. Le résultat est
déterministe et suffisant pour visualiser et retravailler le modèle.

`ajouter_di` enchaîne les étapes : inventaire du modèle, lecture de la
collaboration, niveaux, positions, cadres, écriture du bloc, insertion.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .metamodeles import ACTIVITES, EVENEMENTS, PASSERELLES

DIMS = {"activite": (120, 80), "passerelle": (50, 50), "evenement": (36, 36),
        "donnee": (36, 50), "annotation": (200, 40)}
PAS_X, PAS_Y = 190, 130
H_BOITE_NOIRE = 80          # participant sans processus détaillé

Rect = Tuple[float, float, float, float]
Arete = Tuple[str, str, str]                 # (id, source, cible)


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def possede_di(texte_bpmn: str) -> bool:
    return "BPMNDiagram" in texte_bpmn


def ajouter_di(texte_bpmn: str) -> str:
    """Retourne le document augmenté d'un BPMNDI si absent (sinon inchangé)."""
    if possede_di(texte_bpmn):
        return texte_bpmn
    racine = ET.parse(io.StringIO(texte_bpmn)).getroot()
    inv = _Inventaire(racine)
    collaboration_id, participants, messages = _lire_collaboration(racine)
    niveaux = _niveaux(inv.noeuds, inv.flux)
    pos, bandes, y0 = _positions(inv, niveaux)
    cadres = _cadres(participants, bandes, pos, y0)
    bloc = _bloc_di(inv, collaboration_id, pos, cadres, messages)
    return _inserer_avant_fermeture(texte_bpmn, bloc)


class _Inventaire:
    """Les éléments du modèle utiles à la mise en page, par processus."""

    def __init__(self, racine: ET.Element):
        self.noeuds: Dict[str, str] = {}                    # id -> genre
        self.flux: List[Arete] = []
        self.donnees: List[str] = []
        self.annotations: List[str] = []
        self.assocs: List[Arete] = []
        self.dataassocs: List[Arete] = []
        self.processus_de: Dict[str, str] = {}              # élément -> processus
        self.ordre_processus: List[str] = []
        for proc in racine.iter():
            if _local(proc.tag) == "process":
                self._lire_processus(proc)

    def _lire_processus(self, proc: ET.Element) -> None:
        """Classe chaque élément d'un processus par genre, dans l'ordre du
        document, et retient son processus d'appartenance."""
        pid = proc.get("id") or "process"
        if pid not in self.ordre_processus:
            self.ordre_processus.append(pid)
        for e in proc.iter():
            t, nid = _local(e.tag), e.get("id") or ""
            if not nid:
                continue
            if t in ACTIVITES:
                self.noeuds[nid] = "activite"
                self._lire_associations_donnees(e, nid)
            elif t in PASSERELLES:
                self.noeuds[nid] = "passerelle"
            elif t in EVENEMENTS:
                self.noeuds[nid] = "evenement"
            elif t == "sequenceFlow":
                self.flux.append((nid, (e.get("sourceRef") or "").strip(),
                                  (e.get("targetRef") or "").strip()))
            elif t in ("dataObjectReference", "dataStoreReference"):
                self.donnees.append(nid)
            elif t == "textAnnotation":
                self.annotations.append(nid)
            elif t == "association":
                self.assocs.append((nid, (e.get("sourceRef") or "").strip(),
                                    (e.get("targetRef") or "").strip()))
            else:
                continue
            self.processus_de.setdefault(nid, pid)

    def _lire_associations_donnees(self, e: ET.Element, nid: str) -> None:
        """Associations de données d'une activité : (id, source, cible)."""
        for x in e:
            xt = _local(x.tag)
            if xt in ("dataInputAssociation", "dataOutputAssociation"):
                refs = [r.text.strip() for r in x
                        if _local(r.tag) in ("sourceRef", "targetRef")
                        and r.text]
                if refs:
                    if xt == "dataInputAssociation":
                        self.dataassocs.append((x.get("id") or "", refs[0], nid))
                    else:
                        self.dataassocs.append((x.get("id") or "", nid, refs[0]))


def _lire_collaboration(racine: ET.Element) -> Tuple[Optional[str], List[Tuple[str, str]], List[Arete]]:
    """Collaboration : participants (cadres) et flux de messages ; sans
    participant, il n'y a pas de collaboration à dessiner."""
    collaboration_id: Optional[str] = None
    participants: List[Tuple[str, str]] = []       # (id, processRef)
    messages: List[Arete] = []
    for elem in racine.iter():
        if _local(elem.tag) != "collaboration" or collaboration_id is not None:
            continue
        collaboration_id = elem.get("id") or "collaboration"
        for x in elem:
            xt = _local(x.tag)
            if xt == "participant" and x.get("id"):
                participants.append((x.get("id"),
                                     (x.get("processRef") or "").strip()))
            elif xt == "messageFlow" and x.get("id"):
                messages.append((x.get("id"),
                                 (x.get("sourceRef") or "").strip(),
                                 (x.get("targetRef") or "").strip()))
    if not participants:
        collaboration_id = None
    return collaboration_id, participants, messages


def _niveaux(noeuds: Dict[str, str], flux: List[Arete]) -> Dict[str, int]:
    """Niveau d'un nœud = longueur du plus long chemin depuis un départ.
    Les arcs de retour (repérés par un parcours en profondeur) sont
    ignorés : les boucles d'un processus ne doivent pas faire croître les
    niveaux sans fin."""
    succ: Dict[str, List[str]] = {}
    pred: Dict[str, List[str]] = {}
    for _, s, t in flux:
        if s in noeuds and t in noeuds:
            succ.setdefault(s, []).append(t)
            pred.setdefault(t, []).append(s)
    departs = [n for n in noeuds if n not in pred] or list(noeuds)[:1]
    etat: Dict[str, int] = {}          # 1 = visite en cours, 2 = visité
    retours = set()
    postordre: List[str] = []

    def visiter(depart: str) -> None:
        pile = [(depart, iter(succ.get(depart, [])))]
        etat[depart] = 1
        while pile:
            u, suivants = pile[-1]
            for v in suivants:
                if etat.get(v) == 1:
                    retours.add((u, v))
                elif v not in etat:
                    etat[v] = 1
                    pile.append((v, iter(succ.get(v, []))))
                    break
            else:
                etat[u] = 2
                postordre.append(u)
                pile.pop()

    for n in departs + list(noeuds):
        if n not in etat:
            visiter(n)
    niveaux: Dict[str, int] = {n: 0 for n in noeuds}
    for u in reversed(postordre):
        for v in succ.get(u, []):
            if (u, v) not in retours:
                niveaux[v] = max(niveaux[v], niveaux[u] + 1)
    return niveaux


def _positions(inv: _Inventaire, niveaux: Dict[str, int]
               ) -> Tuple[Dict[str, Rect], Dict[str, Tuple[float, float]], float]:
    """Une bande horizontale par processus, empilées ; la bande d'une
    donnée ou d'une annotation est celle de son processus. Retourne
    (positions, bandes par processus, ordonnée libre sous la dernière)."""
    pos: Dict[str, Rect] = {}
    lie: Dict[str, str] = {}
    for _, s, t in inv.dataassocs:
        d = s if s in inv.donnees else t
        a = t if s in inv.donnees else s
        lie.setdefault(d, a)
    bandes: Dict[str, Tuple[float, float]] = {}    # processus -> (haut, bas)
    y0 = 0.0
    for pid in inv.ordre_processus:
        membres = _poser_noeuds_de_flux(inv, niveaux, pid, y0, pos)
        _poser_donnees(inv, pid, y0, lie, pos)
        _poser_annotations(inv, pid, y0, pos)
        elements = membres + [x for x in inv.donnees + inv.annotations
                              if inv.processus_de.get(x) == pid]
        bas = max([pos[x][1] + pos[x][3] for x in elements] or [y0 + 200])
        bandes[pid] = (y0, bas + 40)
        y0 = bas + 100
    return pos, bandes, y0


def _poser_noeuds_de_flux(inv: _Inventaire, niveaux: Dict[str, int], pid: str,
                          y0: float, pos: Dict[str, Rect]) -> List[str]:
    """Colonne par niveau, rangée par ordre d'arrivée dans la colonne."""
    occupes: Dict[int, int] = {}
    membres = [n for n in inv.noeuds if inv.processus_de.get(n) == pid]
    for n in membres:
        c = niveaux[n]
        rang = occupes.get(c, 0)
        occupes[c] = rang + 1
        w, h = DIMS[inv.noeuds[n]]
        pos[n] = (60 + c * PAS_X + (120 - w) / 2,
                  y0 + 200 + rang * PAS_Y + (80 - h) / 2, w, h)
    return membres


def _poser_donnees(inv: _Inventaire, pid: str, y0: float,
                   lie: Dict[str, str], pos: Dict[str, Rect]) -> None:
    """Chaque donnée au-dessus de sa première activité liée."""
    for i, d in enumerate(x for x in inv.donnees if inv.processus_de.get(x) == pid):
        a = lie.get(d)
        x = pos[a][0] if a in pos else 60 + i * 120
        w, h = DIMS["donnee"]
        pos[d] = (x + 20 + (i % 3) * 60, y0 + 60, w, h)


def _poser_annotations(inv: _Inventaire, pid: str, y0: float,
                       pos: Dict[str, Rect]) -> None:
    """Chaque annotation sous l'élément qu'elle commente, les orphelines en
    file sur la même rangée."""
    annots_bande = [x for x in inv.annotations if inv.processus_de.get(x) == pid]
    for _, s, t in inv.assocs:
        an = s if s in annots_bande else (t if t in annots_bande else None)
        autre = t if an == s else s
        if an and an not in pos:
            x = pos[autre][0] if autre in pos else 60
            w, h = DIMS["annotation"]
            pos[an] = (x, y0 + 460 + 50 * (len([a for a in pos
                                                if a in annots_bande]) % 3),
                       w, h)
    for i, an in enumerate(annots_bande):
        if an not in pos:
            w, h = DIMS["annotation"]
            pos[an] = (60 + i * 220, y0 + 460, w, h)


def _cadres(participants: List[Tuple[str, str]],
            bandes: Dict[str, Tuple[float, float]],
            pos: Dict[str, Rect], y0: float) -> Dict[str, Rect]:
    """Cadres des participants ; une boîte noire reçoit une bande à part."""
    droite = max([p[0] + p[2] for p in pos.values()] or [400]) + 40
    cadres: Dict[str, Rect] = {}
    for partid, pref in participants:
        if pref in bandes:
            haut, bas = bandes[pref]
            cadres[partid] = (20, haut + 20, droite - 20, bas - haut - 20)
        else:
            cadres[partid] = (20, y0 + 20, droite - 20, H_BOITE_NOIRE)
            y0 += H_BOITE_NOIRE + 60
    return cadres


def _bloc_di(inv: _Inventaire, collaboration_id: Optional[str],
             pos: Dict[str, Rect], cadres: Dict[str, Rect],
             messages: List[Arete]) -> str:
    """Le bloc BPMNDI : formes des cadres et des nœuds, puis arêtes de
    centre à centre."""
    L = ['  <bpmndi:BPMNDiagram id="diag_auto" '
         'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
         'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
         'xmlns:di="http://www.omg.org/spec/DD/20100524/DI">',
         '    <bpmndi:BPMNPlane id="plane_auto" bpmnElement="%s">'
         % (collaboration_id or (inv.ordre_processus[0] if inv.ordre_processus
                                 else "process"))]
    for partid, (x, y, w, h) in cadres.items():
        L.append('      <bpmndi:BPMNShape id="dis_%s" bpmnElement="%s" '
                 'isHorizontal="true">'
                 '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>'
                 '</bpmndi:BPMNShape>' % (partid, partid, x, y, w, h))
    for nid, (x, y, w, h) in pos.items():
        L.append('      <bpmndi:BPMNShape id="dis_%s" bpmnElement="%s">'
                 '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>'
                 '</bpmndi:BPMNShape>' % (nid, nid, x, y, w, h))

    formes = dict(pos)
    formes.update(cadres)
    aretes = [(fid, s, t) for fid, s, t in inv.flux] + inv.assocs + \
             [(i, s, t) for i, s, t in inv.dataassocs if i] + messages
    for eid, s, t in aretes:
        if s not in formes or t not in formes or not eid:
            continue
        a, b = formes[s], formes[t]
        ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
        bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
        L.append('      <bpmndi:BPMNEdge id="die_%s" bpmnElement="%s">'
                 '<di:waypoint x="%d" y="%d"/><di:waypoint x="%d" y="%d"/>'
                 '</bpmndi:BPMNEdge>' % (eid, eid, ax, ay, bx, by))
    L.append('    </bpmndi:BPMNPlane>')
    L.append('  </bpmndi:BPMNDiagram>')
    return "\n".join(L) + "\n"


def _inserer_avant_fermeture(texte_bpmn: str, bloc: str) -> str:
    """Insère le bloc juste avant la dernière balise fermante de
    definitions (quel que soit le préfixe, et même si un commentaire suit)."""
    fermetures = list(re.finditer(r"</[A-Za-z0-9_]*:?definitions>", texte_bpmn))
    if not fermetures:
        return texte_bpmn
    m = fermetures[-1]
    return texte_bpmn[:m.start()] + bloc + texte_bpmn[m.start():]
