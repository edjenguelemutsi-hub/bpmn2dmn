# -*- coding: utf-8 -*-
"""
Générateur du catalogue de patterns BPMN de la transformation vers DMN.

Chaque pattern reconnu (ou non) par l'algorithme de transformation est
illustré par un diagramme BPMN 2.0 minimal, à mise en page calculée aux
conventions de Camunda Modeler : pool horizontal, couloirs nommés, flux de
gauche à droite, données au-dessus des tâches qui les lisent, annotations
dans la bande basse, branches de rejet vers le bas. Trois familles :

  A  patterns de référence (article pivot, correspondance P1 à P6) ;
  B  raffinements et gardes de l'algorithme ;
  C  limites : cas hors définition ou non couverts.

Chaque diagramme est accompagné de sa référence experte (`.gold`, décisions
attendues) et du DRD attendu (`.attendu.json`), établi à la main d'après
les règles de transformation, qui sert d'oracle à `outils/executer_catalogue.py`
et à `tests/test_catalogue.py`.

Usage :  python outils/generer_catalogue_patterns.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
DOSSIER = os.path.join(RACINE, "catalogue-patterns")

# constantes de mise en page (px)
POOL_X, POOL_Y = 160, 80
BANDEAU = 30                # bandeau vertical du libellé de couloir ou de pool
LANE_H = 260
ECART_POOLS = 70            # espace vertical entre deux pools
X_DEPART = 240
COLONNE = 200               # entraxe des colonnes du flux
L_TACHE, H_TACHE = 130, 80
L_GW = 50
L_EVT = 36
L_DATA, H_DATA = 36, 50
L_STORE, H_STORE = 50, 50
L_ANNOT, H_ANNOT = 200, 48

RANGEES = {"donnees": 45, "taches": 140, "bas": 206, "annotations": 224}
ECART_DONNEES = 125         # entraxe minimal entre nœuds de données

Rect = Tuple[float, float, float, float]


class Constructeur:
    """Construit un diagramme à partir d'une description déclarative : les
    éléments sont posés sur une grille (colonne, couloir, rangée), les flux
    et associations sont routés orthogonalement."""

    def __init__(self, meta: Dict):
        self.meta = meta
        self.lanes: List[str] = meta.get("lanes", [])
        self.pool2: Optional[Dict] = meta.get("pool2")
        self.M: List[str] = []             # éléments du processus principal
        self.M2: List[str] = []            # éléments du second pool
        self.artefacts: List[str] = []
        self.SHAPES: List[str] = []
        self.EDGES: List[str] = []
        self.pos: Dict[str, Rect] = {}
        self.ids: Dict[str, str] = {}      # clé déclarative -> identifiant BPMN
        self.genre: Dict[str, str] = {}    # identifiant -> genre d'élément
        self.membres: Dict[int, List[str]] = {i: [] for i in range(len(self.lanes))}
        self.donnees: Dict[str, str] = {}  # nom -> id (objets déjà posés)
        self.gold: List[str] = []
        self.n = 0
        self.lane_h = meta.get("lane_h", LANE_H)
        self.hauteur1 = max(1, len(self.lanes)) * self.lane_h
        self.label_droite: set = set()     # événements dont le libellé est à droite
        self.lectures: Dict[str, int] = {}  # tâche -> rang du prochain ancrage
        self.x_max = X_DEPART

    # ------------------------------------------------------------------
    # identifiants et géométrie
    # ------------------------------------------------------------------
    def nid(self, p: str) -> str:
        self.n += 1
        return "%s_%d" % (p, self.n)

    def lane_top(self, lane: int, pool: int = 1) -> float:
        if pool == 2:
            return POOL_Y + self.hauteur1 + ECART_POOLS + lane * self.lane_h
        return POOL_Y + lane * self.lane_h

    def cx(self, col: float) -> float:
        return X_DEPART + L_TACHE / 2 + col * COLONNE

    def cy(self, lane: int, rangee: str = "taches", pool: int = 1,
           dy: float = 0) -> float:
        return self.lane_top(lane, pool) + RANGEES[rangee] + dy

    def poser(self, eid: str, w: float, h: float, cx: float, cy: float) -> None:
        self.pos[eid] = (cx - w / 2, cy - h / 2, w, h)
        self.x_max = max(self.x_max, cx + w / 2)

    def centre(self, eid: str) -> Tuple[float, float]:
        x, y, w, h = self.pos[eid]
        return x + w / 2, y + h / 2

    def edge(self, eid: str, points: List[Tuple[float, float]],
             etiquette: str = "") -> None:
        wp = "".join('<di:waypoint x="%d" y="%d"/>' % (round(a), round(b))
                     for a, b in points)
        label = ""
        if etiquette == "droite":          # juste sous la source, à droite du trait
            x, y = points[0]
            label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="60" '
                     'height="20"/></bpmndi:BPMNLabel>' % (round(x + 6), round(y + 6)))
        self.EDGES.append('      <bpmndi:BPMNEdge id="di_%s" bpmnElement="%s">'
                          '%s%s</bpmndi:BPMNEdge>' % (eid, eid, wp, label))

    def shape(self, eid: str, extra: str = "", label: str = "") -> None:
        x, y, w, h = self.pos[eid]
        self.SHAPES.append('      <bpmndi:BPMNShape id="di_%s" bpmnElement="%s"%s>'
                           '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>%s'
                           '</bpmndi:BPMNShape>'
                           % (eid, eid, extra, round(x), round(y), round(w),
                              round(h), label))

    # ------------------------------------------------------------------
    # routage des flux de séquence
    # ------------------------------------------------------------------
    def route(self, s: str, t: str, mode: str = "auto") -> List[Tuple[float, float]]:
        sx, sy, sw, sh = self.pos[s]
        tx, ty, tw, th = self.pos[t]
        scx, scy = sx + sw / 2, sy + sh / 2
        tcx, tcy = tx + tw / 2, ty + th / 2
        if mode == "retour":                       # boucle de retour : sortie à
            return [(sx, scy), (tcx - 30, scy),    # gauche, entrée par le bas
                    (tcx - 30, ty + th)]
        if mode == "descente":                     # frontière -> tâche plus bas
            return [(scx, sy + sh), (scx, tcy), (tx, tcy)]
        if abs(scy - tcy) < 2:                     # même rangée
            return [(sx + sw, scy), (tx, tcy)]
        if abs(scx - tcx) < 2:                     # même colonne
            if tcy > scy:
                return [(scx, sy + sh), (tcx, ty)]
            return [(scx, sy), (tcx, ty + th)]
        if self.genre.get(s) == "passerelle":      # sortie par le bas ou le haut
            if tcy > scy:
                return [(scx, sy + sh), (scx, tcy), (tx, tcy)]
            return [(scx, sy), (scx, tcy), (tx, tcy)]
        if self.genre.get(t) == "passerelle":      # entrée par le bas ou le haut
            if scy > tcy:
                return [(sx + sw, scy), (tcx, scy), (tcx, ty + th)]
            return [(sx + sw, scy), (tcx, scy), (tcx, ty)]
        mx = (sx + sw + tx) / 2                    # coude à mi-chemin
        return [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)]

    def flux(self, s_cle: str, t_cle: str, nom: str = "", condition: str = "",
             mode: str = "auto", conteneur: Optional[List[str]] = None,
             etiquette: str = "") -> None:
        s, t = self.ids[s_cle], self.ids[t_cle]
        fid = self.nid("Flux")
        attr = " name=%s" % quoteattr(nom) if nom else ""
        if condition:
            corps = ('<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                     '%s</bpmn:conditionExpression>' % escape(condition))
            ligne = ('      <bpmn:sequenceFlow id="%s" sourceRef="%s" targetRef="%s"%s>'
                     '%s</bpmn:sequenceFlow>' % (fid, s, t, attr, corps))
        else:
            ligne = ('      <bpmn:sequenceFlow id="%s" sourceRef="%s" '
                     'targetRef="%s"%s/>' % (fid, s, t, attr))
        (conteneur if conteneur is not None else self.M).append(ligne)
        self.edge(fid, self.route(s, t, mode), etiquette)

    # ------------------------------------------------------------------
    # données et annotations
    # ------------------------------------------------------------------
    def objet(self, nom: str, magasin: bool, x_centre: float, lane: int,
              rangee: str = "donnees", pool: int = 1, dy: float = 0) -> str:
        """Pose (ou retrouve) un nœud de données ; par défaut dans la rangée
        haute du couloir, au-dessus de la tâche qui le lit."""
        if nom in self.donnees:
            return self.donnees[nom]
        oid = self.nid("Donnee")
        self.donnees[nom] = oid
        if magasin:
            self.M.append('      <bpmn:dataStoreReference id="%s" name=%s/>'
                          % (oid, quoteattr(nom)))
            w, h = L_STORE, H_STORE
        else:
            self.M.append('      <bpmn:dataObjectReference id="%s" name=%s '
                          'dataObjectRef="%s_o"/>' % (oid, quoteattr(nom), oid))
            self.M.append('      <bpmn:dataObject id="%s_o"/>' % oid)
            w, h = L_DATA, H_DATA
        cy = self.cy(lane, rangee, pool, dy)
        x = x_centre - w / 2
        rangs = [p for p in self.pos.values() if abs((p[1] + p[3] / 2) - cy) < 4]
        while any(abs(x - p[0]) < ECART_DONNEES for p in rangs):
            x += ECART_DONNEES
        self.pos[oid] = (x, cy - h / 2, w, h)
        self.x_max = max(self.x_max, x + w)
        self.genre[oid] = "donnee"
        return oid

    def association_donnee(self, oid: str, tid: str, lecture: bool) -> str:
        """Association de lecture (donnée -> tâche) ou d'écriture (tâche ->
        donnée), routée verticalement ; les ancrages sur la tâche sont
        décalés pour que deux flèches ne se confondent jamais."""
        aid = self.nid("Lecture" if lecture else "Ecriture")
        ox, oy, ow, oh = self.pos[oid]
        tx, ty, tw, th = self.pos[tid]
        ocx, ocy = ox + ow / 2, oy + oh / 2
        if oy < ty + th and oy + oh > ty:          # même rangée : à l'horizontale
            if ocx > tx + tw:
                chemin = [(ox, ocy), (tx + tw, ocy)]
            else:
                chemin = [(ox + ow, ocy), (tx, ocy)]
            if not lecture:
                chemin = list(reversed(chemin))
            self.edge(aid, chemin)
            return self._balise_association(aid, oid, lecture)
        dessus = oy + oh <= ty
        if lecture:
            rang = self.lectures.get(tid, 0)
            self.lectures[tid] = rang + 1
            dock_x = tx + tw / 2 + (-30 + rang * 26 if dessus else 30 - rang * 26)
        else:
            dock_x = tx + tw / 2 + 44
        if dessus:
            p_obj, p_tache = (ocx, oy + oh), (dock_x, ty)
            my = ty - (18 if lecture else 26)
        else:
            p_obj, p_tache = (ocx, oy), (dock_x, ty + th)
            my = ty + th + (18 if lecture else 26)
        if abs(ocx - dock_x) < 6:
            chemin = [p_obj, p_tache]
        else:
            chemin = [p_obj, (ocx, my), (dock_x, my), p_tache]
        if not lecture:
            chemin = list(reversed(chemin))
        self.edge(aid, chemin)
        return self._balise_association(aid, oid, lecture)

    @staticmethod
    def _balise_association(aid: str, oid: str, lecture: bool) -> str:
        if lecture:
            return ('        <bpmn:dataInputAssociation id="%s">'
                    '<bpmn:sourceRef>%s</bpmn:sourceRef>'
                    '<bpmn:targetRef>%s</bpmn:targetRef>'
                    '</bpmn:dataInputAssociation>' % (aid, oid, "%PROP%"))
        return ('        <bpmn:dataOutputAssociation id="%s">'
                '<bpmn:targetRef>%s</bpmn:targetRef>'
                '</bpmn:dataOutputAssociation>' % (aid, oid))

    def annoter(self, texte: str, cibles: List[str], x_centre: float,
                lane: int, pool: int = 1) -> None:
        anid = self.nid("Annotation")
        self.artefacts.append('      <bpmn:textAnnotation id="%s"><bpmn:text>%s'
                              '</bpmn:text></bpmn:textAnnotation>'
                              % (anid, escape(texte)))
        ax = x_centre - L_ANNOT / 2
        ay = self.cy(lane, "annotations", pool) - H_ANNOT / 2
        self.pos[anid] = (ax, ay, L_ANNOT, H_ANNOT)
        self.genre[anid] = "annotation"
        self.x_max = max(self.x_max, ax + L_ANNOT)
        acx = ax + L_ANNOT / 2
        for tid in cibles:
            aid = self.nid("Assoc")
            self.artefacts.append('      <bpmn:association id="%s" sourceRef="%s" '
                                  'targetRef="%s"/>' % (aid, anid, tid))
            tx, ty, tw, th = self.pos[tid]
            tcx = tx + tw / 2
            if abs(acx - tcx) < 6:
                self.edge(aid, [(acx, ay), (tcx, ty + th)])
            else:
                my = ty + th + 20
                self.edge(aid, [(acx, ay), (acx, my), (tcx, my), (tcx, ty + th)])

    # ------------------------------------------------------------------
    # éléments
    # ------------------------------------------------------------------
    def evenement(self, e: Dict, conteneur: List[str], pool: int) -> str:
        genre = e["e"]
        balise = {"depart": "startEvent", "fin": "endEvent",
                  "inter": "intermediateCatchEvent"}[genre]
        eid = self.nid({"depart": "Depart", "fin": "Fin", "inter": "Evt"}[genre])
        contenu = ""
        if e.get("message"):
            contenu = '<bpmn:messageEventDefinition id="%s_md"/>' % eid
        elif e.get("minuterie"):
            contenu = '<bpmn:timerEventDefinition id="%s_td"/>' % eid
        conteneur.append('      <bpmn:%s id="%s" name=%s>%s</bpmn:%s>'
                         % (balise, eid, quoteattr(e["nom"]), contenu, balise))
        self.poser(eid, L_EVT, L_EVT, self.cx(e["col"]),
                   self.cy(e.get("lane", 0), e.get("rangee", "taches"), pool,
                           e.get("dy", 0)))
        self.genre[eid] = "evenement"
        if e.get("libelle") == "droite":
            self.label_droite.add(eid)
        return eid

    def activite(self, e: Dict, conteneur: List[str], pool: int,
                 conteneur_donnees: Optional[List[str]] = None) -> str:
        """Tâche, sous-processus replié, appel d'activité ; avec ses
        lectures, écritures et annotations."""
        type_ = e.get("type", "userTask")
        tid = self.nid("Tache")
        lane = e.get("lane", 0)
        self.poser(tid, L_TACHE, H_TACHE, self.cx(e["col"]),
                   self.cy(lane, e.get("rangee", "taches"), pool, e.get("dy", 0)))
        self.genre[tid] = "activite"
        cx, _ = self.centre(tid)
        contenu: List[str] = []
        prop = self.nid("Prop")
        k = 0
        dx = e.get("dx_lectures", -40)
        for nom_d in e.get("lit", []):
            oid = self.objet(nom_d, False, cx + dx + k * ECART_DONNEES, lane,
                             pool=pool)
            contenu.append(self.association_donnee(oid, tid, True))
            k += 1
        for nom_d in e.get("lit_magasin", []):
            oid = self.objet(nom_d, True, cx - 40 + k * ECART_DONNEES, lane,
                             pool=pool)
            contenu.append(self.association_donnee(oid, tid, True))
            k += 1
        for nom_d in e.get("lit_bas", []):
            oid = self.objet(nom_d, False, cx - 40 + k * ECART_DONNEES, lane,
                             rangee="bas", pool=pool)
            contenu.append(self.association_donnee(oid, tid, True))
            k += 1
        for ref in e.get("lit_io", []):        # donnée d'entrée du processus
            contenu.append(self.association_donnee(self.ids[ref], tid, True))
        ecrits = e.get("ecrit", [])
        if isinstance(ecrits, str):
            ecrits = [ecrits]
        for j, nom_d in enumerate(ecrits):
            oid = self.objet(nom_d, False, cx + 150 + j * ECART_DONNEES, lane,
                             pool=pool)
            contenu.append(self.association_donnee(oid, tid, False))
        for nom_d in e.get("ecrit_bas", []):
            oid = self.objet(nom_d, False, cx + 150, lane, rangee="bas",
                             pool=pool)
            contenu.append(self.association_donnee(oid, tid, False))
        if any("dataInputAssociation" in c for c in contenu):
            contenu.insert(0, '<bpmn:property id="%s" name="__targetRef_placeholder"/>'
                              % prop)
        contenu = [c.replace("%PROP%", prop) for c in contenu]
        conteneur.append('      <bpmn:%s id="%s" name=%s>%s</bpmn:%s>'
                         % (type_, tid, quoteattr(e["nom"]), "".join(contenu),
                            type_))
        if e.get("decision"):
            self.gold.append(e["nom"])
        if e.get("annotation"):
            self.annoter(e["annotation"], [tid], cx, lane, pool)
        return tid

    def passerelle(self, e: Dict, conteneur: List[str], pool: int) -> str:
        balise = {"exclusive": "exclusiveGateway", "inclusive": "inclusiveGateway",
                  "parallele": "parallelGateway",
                  "evenements": "eventBasedGateway"}[e.get("type", "exclusive")]
        gid = self.nid("Passerelle")
        nom = e.get("nom", "")
        conteneur.append('      <bpmn:%s id="%s"%s/>'
                         % (balise, gid, (" name=%s" % quoteattr(nom)) if nom else ""))
        self.poser(gid, L_GW, L_GW, self.cx(e["col"]),
                   self.cy(e.get("lane", 0), e.get("rangee", "taches"), pool,
                           e.get("dy", 0)))
        self.genre[gid] = "passerelle"
        return gid

    def frontiere(self, e: Dict, conteneur: List[str]) -> str:
        """Événement-frontière posé en bas à droite de son hôte."""
        hote = self.ids[e["sur"]]
        bid = self.nid("Bord")
        if e.get("message"):
            defn = '<bpmn:messageEventDefinition id="%s_md"/>' % bid
        else:
            defn = '<bpmn:timerEventDefinition id="%s_td"/>' % bid
        interrompt = "true" if e.get("interrompt") else "false"
        conteneur.append('      <bpmn:boundaryEvent id="%s" name=%s attachedToRef="%s" '
                         'cancelActivity="%s">%s</bpmn:boundaryEvent>'
                         % (bid, quoteattr(e["nom"]), hote, interrompt, defn))
        hx, hy, hw, hh = self.pos[hote]
        self.pos[bid] = (hx + hw - 50, hy + hh - L_EVT / 2, L_EVT, L_EVT)
        self.genre[bid] = "evenement"
        self.label_droite.add(bid)
        return bid

    def sous_processus_deplie(self, e: Dict, pool: int) -> str:
        """Sous-processus détaillé : façade rectangulaire dépliée contenant
        ses propres nœuds et flux."""
        sid = self.nid("SousProcessus")
        lane = e.get("lane", 0)
        c0, c1 = e["cols"]
        x0 = self.cx(c0) - L_TACHE / 2 - 30
        x1 = self.cx(c1) + L_TACHE / 2 + 30
        top = self.lane_top(lane, pool) + 95
        self.pos[sid] = (x0, top, x1 - x0, 160)
        self.x_max = max(self.x_max, x1)
        self.genre[sid] = "activite"
        internes: List[str] = []
        for x in e["contenu"]:
            x = dict(x, lane=lane)
            self.ids[x["cle"]] = self.element(x, internes, pool)
        for f in e.get("flux", []):
            self.flux(f["s"], f["t"], f.get("nom", ""), f.get("condition", ""),
                      f.get("mode", "auto"), internes)
        self.M.append('      <bpmn:subProcess id="%s" name=%s>\n%s\n      </bpmn:subProcess>'
                      % (sid, quoteattr(e["nom"]), "\n".join(internes)))
        self.shape(sid, ' isExpanded="true"')
        return sid

    def element(self, e: Dict, conteneur: List[str], pool: int = 1) -> str:
        genre = e["e"]
        if genre in ("depart", "fin", "inter"):
            eid = self.evenement(e, conteneur, pool)
        elif genre == "tache":
            eid = self.activite(e, conteneur, pool)
        elif genre == "passerelle":
            eid = self.passerelle(e, conteneur, pool)
        elif genre == "frontiere":
            eid = self.frontiere(e, conteneur)
        elif genre == "sous_processus":
            return self.sous_processus_deplie(e, pool)
        else:
            raise ValueError("genre inconnu : %s" % genre)
        if pool == 1 and self.lanes and genre != "frontiere":
            self.membres[e.get("lane", 0)].append(eid)
        elif pool == 1 and self.lanes and genre == "frontiere":
            self.membres[e.get("lane", 0)].append(eid)
        return eid

    # ------------------------------------------------------------------
    # assemblage
    # ------------------------------------------------------------------
    def construire(self) -> Tuple[str, List[str]]:
        m = self.meta
        io_spec: List[str] = []
        for d in m.get("entrees_processus", []):
            did = self.nid("EntreeProcessus")
            self.ids[d["cle"]] = did
            self.poser(did, L_DATA, H_DATA, self.cx(d["col"]),
                       self.cy(d.get("lane", 0), "donnees"))
            self.genre[did] = "donnee"
            io_spec.append((did, d["nom"]))
        for d in m.get("donnees", []):     # nœuds de données placés à la main
            self.objet(d["nom"], d.get("magasin", False), self.cx(d["col"]),
                       d.get("lane", 0), d.get("rangee", "donnees"),
                       dy=d.get("dy", 0))
        for e in m["elements"]:
            self.ids[e["cle"]] = self.element(e, self.M, 1)
        for f in m.get("flux", []):
            self.flux(f["s"], f["t"], f.get("nom", ""), f.get("condition", ""),
                      f.get("mode", "auto"), etiquette=f.get("etiquette", ""))
        for a in m.get("annotations", []):
            self.annoter(a["texte"], [self.ids[c] for c in a["sur"]],
                         self.cx(a["col"]), a.get("lane", 0))
        if self.pool2:
            for e in self.pool2["elements"]:
                self.ids[e["cle"]] = self.element(e, self.M2, 2)
            for f in self.pool2.get("flux", []):
                self.flux(f["s"], f["t"], f.get("nom", ""), mode=f.get("mode", "auto"),
                          conteneur=self.M2)
        messages: List[str] = []
        for msg in m.get("messages", []):
            mid = self.nid("Message")
            s, t = self.ids[msg["s"]], self.ids[msg["t"]]
            messages.append('    <bpmn:messageFlow id="%s" sourceRef="%s" targetRef="%s"/>'
                            % (mid, s, t))
            sx, sy, sw, sh = self.pos[s]
            tx, ty, tw, th = self.pos[t]
            scx, tcx = sx + sw / 2, tx + tw / 2
            if sy > ty:                                   # émetteur en bas
                self.edge(mid, [(scx, sy), (scx, ty + th)] if abs(scx - tcx) < 2
                          else [(scx, sy), (scx, (sy + ty + th) / 2),
                                (tcx, (sy + ty + th) / 2), (tcx, ty + th)])
            else:
                self.edge(mid, [(scx, sy + sh), (scx, ty)] if abs(scx - tcx) < 2
                          else [(scx, sy + sh), (scx, (sy + sh + ty) / 2),
                                (tcx, (sy + sh + ty) / 2), (tcx, ty)])
        return self.document(io_spec, messages), self.gold

    def document(self, io_spec: List[Tuple[str, str]], messages: List[str]) -> str:
        largeur = self.x_max + 60 - POOL_X
        L = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<bpmn:definitions '
             'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
             'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
             'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
             'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
             'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'id="Definitions_1" targetNamespace="http://bpmn2dmn/catalogue" '
             'exporter="bpmn2dmn" exporterVersion="1.0">',
             '  <bpmn:collaboration id="Collab_1">',
             '    <bpmn:participant id="Pool_1" name=%s processRef="Process_1"/>'
             % quoteattr(self.meta["pool"])]
        if self.pool2:
            L.append('    <bpmn:participant id="Pool_2" name=%s processRef="Process_2"/>'
                     % quoteattr(self.pool2["pool"]))
        L.extend(messages)
        L.append('  </bpmn:collaboration>')
        L.append('  <bpmn:process id="Process_1" name=%s isExecutable="false">'
                 % quoteattr(self.meta["nom"]))
        if io_spec:
            L.append('    <bpmn:ioSpecification id="IoSpec_1">')
            for did, nom in io_spec:
                L.append('      <bpmn:dataInput id="%s" name=%s/>' % (did, quoteattr(nom)))
            L.append('      <bpmn:inputSet id="InputSet_1">%s</bpmn:inputSet>'
                     % "".join('<bpmn:dataInputRefs>%s</bpmn:dataInputRefs>' % d
                               for d, _ in io_spec))
            L.append('      <bpmn:outputSet id="OutputSet_1"/>')
            L.append('    </bpmn:ioSpecification>')
        if self.lanes:
            L.append('    <bpmn:laneSet id="Lanes_1">')
            for i, nom in enumerate(self.lanes):
                L.append('      <bpmn:lane id="Lane_%d" name=%s>' % (i + 1, quoteattr(nom)))
                for eid in self.membres[i]:
                    L.append('        <bpmn:flowNodeRef>%s</bpmn:flowNodeRef>' % eid)
                L.append('      </bpmn:lane>')
            L.append('    </bpmn:laneSet>')
        L.extend(self.M)
        L.extend(self.artefacts)
        L.append('  </bpmn:process>')
        if self.pool2:
            L.append('  <bpmn:process id="Process_2" name=%s isExecutable="false">'
                     % quoteattr(self.pool2["nom"]))
            L.extend(self.M2)
            L.append('  </bpmn:process>')
        L.append('  <bpmndi:BPMNDiagram id="Diagramme_1">')
        L.append('    <bpmndi:BPMNPlane id="Plan_1" bpmnElement="Collab_1">')
        L.append('      <bpmndi:BPMNShape id="di_Pool_1" bpmnElement="Pool_1" '
                 'isHorizontal="true"><dc:Bounds x="%d" y="%d" width="%d" '
                 'height="%d"/></bpmndi:BPMNShape>'
                 % (POOL_X, POOL_Y, largeur, self.hauteur1))
        for i in range(len(self.lanes)):
            L.append('      <bpmndi:BPMNShape id="di_Lane_%d" bpmnElement="Lane_%d" '
                     'isHorizontal="true"><dc:Bounds x="%d" y="%d" width="%d" '
                     'height="%d"/></bpmndi:BPMNShape>'
                     % (i + 1, i + 1, POOL_X + BANDEAU, self.lane_top(i),
                        largeur - BANDEAU, self.lane_h))
        if self.pool2:
            L.append('      <bpmndi:BPMNShape id="di_Pool_2" bpmnElement="Pool_2" '
                     'isHorizontal="true"><dc:Bounds x="%d" y="%d" width="%d" '
                     'height="%d"/></bpmndi:BPMNShape>'
                     % (POOL_X, self.lane_top(0, 2), largeur, self.lane_h))
        for eid, (x, y, w, h) in self.pos.items():
            if any('bpmnElement="%s"' % eid in s for s in self.SHAPES):
                continue
            label = ""
            g = self.genre.get(eid)
            if g == "donnee" or eid in self.label_droite:
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="110" '
                         'height="28"/></bpmndi:BPMNLabel>'
                         % (round(x + w + 6), round(y + h / 2 - 14)))
            elif g == "passerelle":
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="150" '
                         'height="26"/></bpmndi:BPMNLabel>'
                         % (round(x + w / 2 - 75), round(y - 32)))
            L.append('      <bpmndi:BPMNShape id="di_%s" bpmnElement="%s">'
                     '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>%s'
                     '</bpmndi:BPMNShape>'
                     % (eid, eid, round(x), round(y), round(w), round(h), label))
        L.extend(self.SHAPES)
        L.extend(self.EDGES)
        L.append('    </bpmndi:BPMNPlane>')
        L.append('  </bpmndi:BPMNDiagram>')
        L.append('</bpmn:definitions>')
        return "\n".join(L) + "\n"


# ----------------------------------------------------------------------
# le catalogue
# ----------------------------------------------------------------------
def _attendu(decisions=(), inputs=(), sources=(), bkms=(), arcs=(),
             points=(), ecartes=(), verdict="conforme", enseignement=""):
    return {"decisions": list(decisions), "inputs": list(inputs),
            "sources": list(sources), "bkms": list(bkms),
            "arcs": [list(a) for a in arcs],
            "points_experts": sorted(points), "ecartes": sorted(ecartes),
            "verdict_attendu": verdict, "enseignement": enseignement}


def _chaine_simple(nom_decision, lit=None, lit_magasin=None, annotation=None,
                   type_="userTask", ecrit=None, decision=True):
    """Départ, tâche neutre, activité de décision devant une passerelle
    exclusive, deux fins : le squelette commun des patterns simples."""
    tache = dict(cle="d", e="tache", nom=nom_decision, col=2, type=type_,
                 decision=decision)
    if lit:
        tache["lit"] = lit
    if lit_magasin:
        tache["lit_magasin"] = lit_magasin
    if annotation:
        tache["annotation"] = annotation
    if ecrit:
        tache["ecrit"] = ecrit
    return dict(
        elements=[
            dict(cle="s", e="depart", nom="Demande déposée", col=0),
            dict(cle="t1", e="tache", nom="Enregistrer la demande", col=1, type="task"),
            tache,
            dict(cle="g", e="passerelle", nom="Demande recevable ?", col=3),
            dict(cle="f1", e="fin", nom="Demande acceptée", col=4),
            dict(cle="f2", e="fin", nom="Demande rejetée", col=3, rangee="bas"),
        ],
        flux=[dict(s="s", t="t1"), dict(s="t1", t="d"), dict(s="d", t="g"),
              dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non")])


GUICHET = "Guichet unique du commerce extérieur"

MODELES: List[Dict] = []


def _ajouter(fichier, titre, pattern, elements_bpmn, attendu, lanes=None,
             squelette=None, **extra):
    m = dict(fichier=fichier, titre=titre, pattern=pattern,
             elements_bpmn=elements_bpmn, pool=GUICHET, nom=titre,
             lanes=lanes or [], attendu=attendu)
    if squelette:
        m.update(squelette)
    m.update(extra)
    MODELES.append(m)


# ---------------------------------------------------------------- famille A
_ajouter("A01-objet-de-donnees", "Objet de données lu par la décision",
         "Π1 / P2 : objet de données → donnée d'entrée (IR)",
         "dataObjectReference, dataInputAssociation, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Vérifier la recevabilité de la demande", "P2")],
                  enseignement="L'objet de données lu devient une donnée d'entrée reliée "
                  "par une exigence d'information ; règle fermée, sans intervention."),
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  lit=["Demande d'agrément"]))

_ajouter("A02-magasin-de-donnees", "Magasin de données lu par la décision",
         "Π3 / P2 : magasin de données → donnée d'entrée (IR)",
         "dataStoreReference, dataInputAssociation, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier l'inscription de l'opérateur"],
                  inputs=["Fichier des importateurs"],
                  arcs=[("Fichier des importateurs", "Vérifier l'inscription de l'opérateur", "P2")],
                  enseignement="Un magasin persistant est traité comme un objet transitoire : "
                  "même donnée d'entrée, même exigence d'information."),
         squelette=_chaine_simple("Vérifier l'inscription de l'opérateur",
                                  lit_magasin=["Fichier des importateurs"]))

_ajouter("A03-annotation-valeur", "Annotation portant une valeur",
         "Π2 / P6 (γ) : annotation-valeur → donnée d'entrée attendue, non tranchée",
         "textAnnotation, association, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  points=["annotation"], verdict="point-expert",
                  enseignement="Sans indice lexical d'autorité ni de règle, γ ne tranche pas : "
                  "l'annotation est soumise à l'expert (donnée d'entrée ou source de "
                  "connaissance ?) et aucun nœud n'est créé avant arbitrage."),
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  annotation="Capital social déclaré par le demandeur"))

_ajouter("A04-annotation-autorite", "Annotation d'autorité",
         "Π2 / P6 (γ = KS) : annotation réglementaire → source de connaissance (AR)",
         "textAnnotation, association, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  sources=["Réglementation FIMEX en vigueur"],
                  arcs=[("Réglementation FIMEX en vigueur",
                         "Vérifier la recevabilité de la demande", "P6")],
                  points=["annotation"],
                  enseignement="L'indice « réglementation » fait proposer une source de "
                  "connaissance reliée par une exigence d'autorité ; le verdict reste "
                  "à confirmer par l'expert."),
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  annotation="Réglementation FIMEX en vigueur"))

_ajouter("A05-annotation-regle", "Annotation énonçant une règle",
         "P6 étendu (γ = BKM) : annotation-règle → modèle de connaissance métier (KR)",
         "textAnnotation, association, userTask, exclusiveGateway",
         _attendu(decisions=["Coter le dossier de l'opérateur"],
                  bkms=["Règle : Barème de cotation par catégorie d'opérateur"],
                  arcs=[("Règle : Barème de cotation par catégorie d'opérateur",
                         "Coter le dossier de l'opérateur", "P6")],
                  points=["annotation"],
                  enseignement="L'extension de la correspondance de référence : une annotation "
                  "qui énonce une règle (barème, calcul) devient un BKM relié par une "
                  "exigence de connaissance, à confirmer."),
         squelette=_chaine_simple("Coter le dossier de l'opérateur",
                                  annotation="Barème de cotation par catégorie d'opérateur"))

_ajouter("A06-evenement-depart-message", "Événement de départ à message",
         "Π4 / P3 : événement de départ porteur → donnée d'entrée (IR)",
         "startEvent + messageEventDefinition, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  inputs=["Demande d'agrément reçue"],
                  arcs=[("Demande d'agrément reçue", "Vérifier la recevabilité de la demande", "P3")],
                  enseignement="L'événement de départ à message précède immédiatement la "
                  "décision : sa charge utile devient une donnée d'entrée."),
         elements=[
             dict(cle="s", e="depart", nom="Demande d'agrément reçue", col=0, message=True),
             dict(cle="d", e="tache", nom="Vérifier la recevabilité de la demande",
                  col=1, decision=True),
             dict(cle="g", e="passerelle", nom="Demande recevable ?", col=2),
             dict(cle="f1", e="fin", nom="Demande acceptée", col=3),
             dict(cle="f2", e="fin", nom="Demande rejetée", col=2, rangee="bas")],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non")])

_ajouter("A07-evenement-intermediaire-message", "Événement intermédiaire de réception",
         "Π4 / P3 : événement intermédiaire porteur précédant la décision → donnée d'entrée (IR)",
         "intermediateCatchEvent + messageEventDefinition, userTask, exclusiveGateway",
         _attendu(decisions=["Statuer sur la demande d'agrément"],
                  inputs=["Pièces complémentaires reçues"],
                  arcs=[("Pièces complémentaires reçues", "Statuer sur la demande d'agrément", "P3")],
                  enseignement="Un événement intermédiaire de réception qui précède la "
                  "décision joue le même rôle qu'un événement de départ porteur."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="t1", e="tache", nom="Enregistrer la demande", col=1, type="task"),
             dict(cle="e", e="inter", nom="Pièces complémentaires reçues", col=2, message=True),
             dict(cle="d", e="tache", nom="Statuer sur la demande d'agrément", col=3,
                  decision=True),
             dict(cle="g", e="passerelle", nom="Agrément accordé ?", col=4),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=5),
             dict(cle="f2", e="fin", nom="Agrément refusé", col=4, rangee="bas")],
         flux=[dict(s="s", t="t1"), dict(s="t1", t="e"), dict(s="e", t="d"),
               dict(s="d", t="g"), dict(s="g", t="f1", nom="oui"),
               dict(s="g", t="f2", nom="non")])

_ajouter("A08-evenement-frontiere-non-interruptif", "Événement-frontière non interruptif",
         "Π5 / P3 : frontière à message non interruptive → donnée d'entrée optionnelle (IR)",
         "boundaryEvent cancelActivity=false + messageEventDefinition, userTask",
         _attendu(decisions=["Statuer sur la demande d'agrément"],
                  inputs=["Observation de l'opérateur (optionnel)"],
                  arcs=[("Observation de l'opérateur (optionnel)",
                         "Statuer sur la demande d'agrément", "P3")],
                  enseignement="La frontière non interruptive porteuse alimente la décision "
                  "sans l'arrêter : donnée d'entrée marquée optionnelle."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Statuer sur la demande d'agrément", col=1,
                  decision=True),
             dict(cle="b", e="frontiere", nom="Observation de l'opérateur", sur="d",
                  message=True),
             dict(cle="g", e="passerelle", nom="Agrément accordé ?", col=2),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=3),
             dict(cle="f2", e="fin", nom="Agrément refusé", col=2, rangee="bas"),
             dict(cle="h", e="tache", nom="Joindre l'observation au dossier", col=2,
                  lane=1, type="task"),
             dict(cle="f3", e="fin", nom="Observation classée", col=3, lane=1)],
         lanes=["Chef de service", "Agent instructeur"],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non"),
               dict(s="b", t="h", mode="descente"), dict(s="h", t="f3")])
MODELES[-1]["attendu"]["points_experts"] = ["ressource"]
MODELES[-1]["attendu"]["enseignement"] += (" Le couloir « Chef de service » soulève en "
                                           "outre la question ω (point ressource).")

_ajouter("A09-role-du-couloir", "Rôle du couloir qui exécute la décision",
         "Π6 / P5 (ω) : ressource humaine → source de connaissance proposée (AR), non tranchée",
         "laneSet / lane, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Vérifier la recevabilité de la demande", "P2")],
                  points=["ressource"], verdict="point-expert",
                  enseignement="Un rôle humain gouverne-t-il la décision ou l'applique-t-il ? "
                  "ω ne tranche pas : la source de connaissance est proposée, l'expert "
                  "arbitre (règle ouverte)."),
         lanes=["Chef de service"],
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  lit=["Demande d'agrément"]))

_ajouter("A10-dependance-entre-decisions", "Dépendance entre deux décisions",
         "P4 raffiné + P2 raffiné : d1 produit une donnée lue par d2 → IR décision → décision",
         "deux userTask décisionnelles, dataOutputAssociation, dataInputAssociation",
         _attendu(decisions=["Vérifier la complétude du dossier", "Statuer sur l'agrément"],
                  inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Vérifier la complétude du dossier", "P2"),
                        ("Vérifier la complétude du dossier", "Statuer sur l'agrément", "P4")],
                  enseignement="La donnée intermédiaire « Dossier vérifié » n'est pas une "
                  "donnée d'entrée : elle porte la dépendance d1 → d2 (P4 raffiné : "
                  "atteignabilité et donnée partagée)."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d1", e="tache", nom="Vérifier la complétude du dossier", col=1,
                  lit=["Demande d'agrément"], ecrit="Dossier vérifié", decision=True),
             dict(cle="g1", e="passerelle", nom="Dossier complet ?", col=2),
             dict(cle="f2", e="fin", nom="Dossier retourné", col=2, rangee="bas"),
             dict(cle="d2", e="tache", nom="Statuer sur l'agrément", col=3,
                  lit=["Dossier vérifié"], decision=True),
             dict(cle="g2", e="passerelle", nom="Agrément accordé ?", col=4),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=5),
             dict(cle="f3", e="fin", nom="Agrément refusé", col=4, rangee="bas")],
         flux=[dict(s="s", t="d1"), dict(s="d1", t="g1"),
               dict(s="g1", t="d2", nom="oui"), dict(s="g1", t="f2", nom="non"),
               dict(s="d2", t="g2"), dict(s="g2", t="f1", nom="oui"),
               dict(s="g2", t="f3", nom="non")])

_ajouter("A11-composition", "Composition des patterns",
         "P1–P6 composés : DRD à deux décisions (P2, P3, P4, P5, P6)",
         "startEvent à message, deux couloirs, objets de données, annotation, passerelles",
         _attendu(decisions=["Vérifier la complétude du dossier", "Statuer sur l'agrément"],
                  inputs=["Demande d'agrément reçue", "Demande d'agrément"],
                  sources=["Réglementation FIMEX en vigueur"],
                  arcs=[("Demande d'agrément reçue", "Vérifier la complétude du dossier", "P3"),
                        ("Demande d'agrément", "Vérifier la complétude du dossier", "P2"),
                        ("Vérifier la complétude du dossier", "Statuer sur l'agrément", "P4"),
                        ("Réglementation FIMEX en vigueur", "Statuer sur l'agrément", "P6")],
                  points=["annotation", "ressource", "ressource"],
                  enseignement="Les fragments produits par chaque pattern se composent en un "
                  "DRD unique et acyclique ; les deux rôles et l'annotation restent des "
                  "points d'arbitrage."),
         lanes=["Agent instructeur", "Chef de service"],
         elements=[
             dict(cle="s", e="depart", nom="Demande d'agrément reçue", col=0, message=True),
             dict(cle="d1", e="tache", nom="Vérifier la complétude du dossier", col=1,
                  lit=["Demande d'agrément"], ecrit="Dossier vérifié", decision=True),
             dict(cle="g1", e="passerelle", nom="Dossier complet ?", col=2),
             dict(cle="f2", e="fin", nom="Dossier retourné", col=2, rangee="bas"),
             dict(cle="d2", e="tache", nom="Statuer sur l'agrément", col=3, lane=1,
                  lit=["Dossier vérifié"], decision=True,
                  annotation="Réglementation FIMEX en vigueur"),
             dict(cle="g2", e="passerelle", nom="Agrément accordé ?", col=4, lane=1),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=5, lane=1),
             dict(cle="f3", e="fin", nom="Agrément refusé", col=4, lane=1, rangee="bas")],
         flux=[dict(s="s", t="d1"), dict(s="d1", t="g1"),
               dict(s="g1", t="d2", nom="oui"), dict(s="g1", t="f2", nom="non"),
               dict(s="d2", t="g2"), dict(s="g2", t="f1", nom="oui"),
               dict(s="g2", t="f3", nom="non")])

# ---------------------------------------------------------------- famille B
_ajouter("B01-kappa-position", "Corroboration par la position",
         "κ (position) : tâche au libellé neutre suivie d'une passerelle exclusive",
         "userTask, exclusiveGateway, dataObjectReference",
         _attendu(decisions=["Instruire la demande"], inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Instruire la demande", "P2")],
                  enseignement="« Instruire » n'est pas un verbe de décision, mais la "
                  "passerelle de choix qui suit corrobore la candidate : indice de position."),
         squelette=_chaine_simple("Instruire la demande", lit=["Demande d'agrément"]))

_ajouter("B02-kappa-lexique", "Corroboration par le lexique",
         "κ (lexique) : tâche de règle métier au verbe décisionnel, sans passerelle",
         "businessRuleTask, dataObjectReference, dataStoreReference",
         _attendu(decisions=["Évaluer le niveau de risque de l'opérateur"],
                  inputs=["Dossier de l'opérateur", "Historique des contrôles"],
                  arcs=[("Dossier de l'opérateur", "Évaluer le niveau de risque de l'opérateur", "P2"),
                        ("Historique des contrôles", "Évaluer le niveau de risque de l'opérateur", "P2")],
                  enseignement="Aucune passerelle ne suit la tâche : c'est le verbe « évaluer » "
                  "du lexique Λ qui la corrobore ; la sortie « Niveau de risque » n'entre pas "
                  "dans le DRD."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Évaluer le niveau de risque de l'opérateur", col=1,
                  type="businessRuleTask", lit=["Dossier de l'opérateur"],
                  lit_magasin=["Historique des contrôles"], ecrit="Niveau de risque",
                  decision=True),
             dict(cle="t2", e="tache", nom="Notifier le résultat", col=2, type="sendTask"),
             dict(cle="f", e="fin", nom="Demande traitée", col=3)],
         flux=[dict(s="s", t="d"), dict(s="d", t="t2"), dict(s="t2", t="f")])

_ajouter("B03-candidat-non-corrobore", "Candidat non corroboré",
         "κ faux : tâche utilisateur neutre, sans passerelle → soumise à l'expert",
         "userTask, dataObjectReference",
         _attendu(points=["candidat"], verdict="point-expert",
                  enseignement="Le type d'activité est nécessaire mais non suffisant : "
                  "sans indice, la candidate n'est ni retenue ni supprimée, le DRD reste "
                  "vide et le diagnostic l'explique."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Traiter la demande", col=1,
                  lit=["Demande d'agrément"]),
             dict(cle="t2", e="tache", nom="Archiver le dossier", col=2, type="task"),
             dict(cle="f", e="fin", nom="Demande traitée", col=3)],
         flux=[dict(s="s", t="d"), dict(s="d", t="t2"), dict(s="t2", t="f")])

_ajouter("B04-passerelle-inclusive", "Passerelle inclusive comme indice de position",
         "κ (position) : la passerelle inclusive vaut passerelle de choix",
         "userTask, inclusiveGateway",
         _attendu(decisions=["Instruire la demande"], inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Instruire la demande", "P2")],
                  enseignement="Une passerelle inclusive applique aussi un verdict : "
                  "elle corrobore la tâche qui la précède, comme l'exclusive."),
         lane_h=320,
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Instruire la demande", col=1,
                  lit=["Demande d'agrément"], decision=True),
             dict(cle="g", e="passerelle", nom="Contrôles requis", col=2, type="inclusive"),
             dict(cle="c1", e="tache", nom="Inspecter les pièces", col=3, type="task"),
             dict(cle="c2", e="tache", nom="Visiter les locaux", col=3, dy=120, type="task"),
             dict(cle="f1", e="fin", nom="Contrôles effectués", col=4)],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"),
               dict(s="g", t="c1", nom="documentaire"), dict(s="g", t="c2", nom="physique"),
               dict(s="c1", t="f1"), dict(s="c2", t="f1")])

_ajouter("B05-ordonner-nest-pas-alimenter", "Ordonner n'est pas alimenter",
         "P4 raffiné : deux décisions en séquence sans donnée partagée → aucun arc",
         "deux userTask décisionnelles, passerelles, données distinctes",
         _attendu(decisions=["Vérifier la recevabilité de la demande",
                             "Évaluer le risque de l'opérateur"],
                  inputs=["Demande d'agrément", "Historique des contrôles"],
                  arcs=[("Demande d'agrément", "Vérifier la recevabilité de la demande", "P2"),
                        ("Historique des contrôles", "Évaluer le risque de l'opérateur", "P2")],
                  enseignement="Le flux de séquence ordonne les décisions mais ne les "
                  "alimente pas : sans donnée produite puis lue, pas d'exigence "
                  "d'information entre elles."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d1", e="tache", nom="Vérifier la recevabilité de la demande", col=1,
                  lit=["Demande d'agrément"], decision=True),
             dict(cle="g1", e="passerelle", nom="Demande recevable ?", col=2),
             dict(cle="f2", e="fin", nom="Demande rejetée", col=2, rangee="bas"),
             dict(cle="d2", e="tache", nom="Évaluer le risque de l'opérateur", col=3,
                  lit_magasin=["Historique des contrôles"], decision=True),
             dict(cle="g2", e="passerelle", nom="Risque acceptable ?", col=4),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=5),
             dict(cle="f3", e="fin", nom="Contrôle renforcé", col=4, rangee="bas")],
         flux=[dict(s="s", t="d1"), dict(s="d1", t="g1"),
               dict(s="g1", t="d2", nom="oui"), dict(s="g1", t="f2", nom="non"),
               dict(s="d2", t="g2"), dict(s="g2", t="f1", nom="oui"),
               dict(s="g2", t="f3", nom="non")])

_ajouter("B06-branches-paralleles", "Branches parallèles",
         "P2 raffiné : donnée produite sur une branche, lue sur l'autre → donnée d'entrée, pas d'arc P4",
         "parallelGateway, deux couloirs, dataOutputAssociation, dataInputAssociation",
         _attendu(decisions=["Évaluer la garantie financière", "Statuer sur la demande"],
                  inputs=["Garantie proposée", "Avis financier"],
                  arcs=[("Garantie proposée", "Évaluer la garantie financière", "P2"),
                        ("Avis financier", "Statuer sur la demande", "P2")],
                  points=["ressource", "ressource"],
                  enseignement="Sans atteignabilité par les flux de séquence entre les deux "
                  "branches, la donnée lue est traitée comme lue de l'extérieur : "
                  "donnée d'entrée, et non dépendance entre décisions."),
         lanes=["Service financier", "Service juridique"],
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="gs", e="passerelle", col=1, type="parallele"),
             dict(cle="d1", e="tache", nom="Évaluer la garantie financière", col=2,
                  lit=["Garantie proposée"], ecrit="Avis financier", decision=True),
             dict(cle="d2", e="tache", nom="Statuer sur la demande", col=2, lane=1,
                  lit=["Avis financier"], decision=True),
             dict(cle="gj", e="passerelle", col=3, type="parallele"),
             dict(cle="f", e="fin", nom="Demande traitée", col=4)],
         flux=[dict(s="s", t="gs"), dict(s="gs", t="d1"), dict(s="gs", t="d2"),
               dict(s="d1", t="gj"), dict(s="d2", t="gj"), dict(s="gj", t="f")])

_ajouter("B07-circuit", "Circuit entre deux décisions",
         "Garde d'acyclicité : boucle de réexamen où chaque décision nourrit l'autre",
         "deux userTask décisionnelles, flux de retour, données croisées",
         _attendu(decisions=["Évaluer la demande", "Contrôler les observations"],
                  arcs=[("Contrôler les observations", "Évaluer la demande", "P4")],
                  points=["circuit"], verdict="point-expert",
                  enseignement="Chaque décision produit une donnée que l'autre lit : le "
                  "second arc P4 fermerait un circuit, il est écarté et le sens réel "
                  "de la dépendance est soumis à l'expert."),
         lane_h=340,
         donnees=[dict(nom="Rapport de contrôle", col=3, dy=225)],
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d1", e="tache", nom="Évaluer la demande", col=1,
                  lit=["Rapport de contrôle"], ecrit="Avis d'instruction",
                  decision=True),
             dict(cle="g", e="passerelle", nom="Avis favorable ?", col=2),
             dict(cle="f", e="fin", nom="Agrément délivré", col=3),
             dict(cle="d2", e="tache", nom="Contrôler les observations", col=2, dy=130,
                  lit=["Avis d'instruction"], ecrit="Rapport de contrôle",
                  decision=True)],
         flux=[dict(s="s", t="d1"), dict(s="d1", t="g"), dict(s="g", t="f", nom="oui"),
               dict(s="g", t="d2", nom="non", etiquette="droite"),
               dict(s="d2", t="d1", mode="retour")])

_ajouter("B08-injectivite", "Injectivité des correspondances",
         "δ et ι injectives : une donnée lue par deux décisions, une annotation reliée à deux décisions",
         "deux userTask décisionnelles, dataObjectReference partagé, textAnnotation partagée",
         _attendu(decisions=["Vérifier la recevabilité de la demande", "Statuer sur l'agrément"],
                  inputs=["Demande d'agrément"],
                  sources=["Réglementation FIMEX en vigueur"],
                  arcs=[("Demande d'agrément", "Vérifier la recevabilité de la demande", "P2"),
                        ("Demande d'agrément", "Statuer sur l'agrément", "P2"),
                        ("Réglementation FIMEX en vigueur", "Vérifier la recevabilité de la demande", "P6"),
                        ("Réglementation FIMEX en vigueur", "Statuer sur l'agrément", "P6")],
                  points=["annotation"],
                  enseignement="Une source déjà traduite n'est jamais dupliquée : une seule "
                  "donnée d'entrée et une seule source de connaissance, reliées deux fois."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d1", e="tache", nom="Vérifier la recevabilité de la demande", col=1,
                  lit=["Demande d'agrément"], decision=True),
             dict(cle="d2", e="tache", nom="Statuer sur l'agrément", col=2,
                  lit=["Demande d'agrément"], decision=True),
             dict(cle="g2", e="passerelle", nom="Agrément accordé ?", col=3),
             dict(cle="f1", e="fin", nom="Agrément délivré", col=4),
             dict(cle="f3", e="fin", nom="Agrément refusé", col=3, rangee="bas")],
         flux=[dict(s="s", t="d1"), dict(s="d1", t="d2"),
               dict(s="d2", t="g2"), dict(s="g2", t="f1", nom="oui"),
               dict(s="g2", t="f3", nom="non")],
         annotations=[dict(texte="Réglementation FIMEX en vigueur", sur=["d1", "d2"], col=1.5)])

_ajouter("B09-sous-processus-replie", "Sous-processus replié",
         "Définition des candidates : un sous-processus replié est une activité de décision possible",
         "subProcess (replié), dataObjectReference, exclusiveGateway",
         _attendu(decisions=["Instruire le dossier d'agrément"], inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Instruire le dossier d'agrément", "P2")],
                  enseignement="Le sous-processus replié est traité comme une activité "
                  "candidate ; la passerelle qui le suit le corrobore."),
         squelette=_chaine_simple("Instruire le dossier d'agrément", lit=["Demande d'agrément"],
                                  type_="subProcess"))

_ajouter("B10-sous-processus-deplie", "Sous-processus déplié",
         "Dépliage : nœuds internes remontés, couloir hérité, frontière sur la façade",
         "subProcess (déplié) avec contenu, boundaryEvent sur la façade, lane",
         _attendu(decisions=["Vérifier la conformité des pièces"],
                  inputs=["Demande d'agrément", "Pièce complémentaire reçue (optionnel)"],
                  arcs=[("Demande d'agrément", "Vérifier la conformité des pièces", "P2"),
                        ("Pièce complémentaire reçue (optionnel)",
                         "Vérifier la conformité des pièces", "P3")],
                  points=["ressource"],
                  enseignement="Le sous-processus déplié disparaît au profit de ses activités ; "
                  "la frontière posée sur sa façade vaut pour la décision qu'il contient, "
                  "et le couloir de la façade lui est hérité."),
         lanes=["Agent instructeur", "Secrétariat"], lane_h=300,
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0, dy=35),
             dict(cle="sp", e="sous_processus", nom="Instruction du dossier", cols=(1, 3),
                  contenu=[
                      dict(cle="is", e="depart", nom="", col=1, dy=65),
                      dict(cle="d", e="tache", nom="Vérifier la conformité des pièces", col=2,
                           lit=["Demande d'agrément"], dx_lectures=-165, dy=65,
                           decision=True),
                      dict(cle="ie", e="fin", nom="", col=3, dy=65)],
                  flux=[dict(s="is", t="d"), dict(s="d", t="ie")]),
             dict(cle="b", e="frontiere", nom="Pièce complémentaire reçue", sur="sp",
                  message=True),
             dict(cle="h", e="tache", nom="Verser la pièce au dossier", col=4, lane=1, type="task"),
             dict(cle="f3", e="fin", nom="Pièce versée", col=5, lane=1),
             dict(cle="g", e="passerelle", nom="Pièces conformes ?", col=5, dy=35),
             dict(cle="f1", e="fin", nom="Dossier instruit", col=6, dy=35),
             dict(cle="f2", e="fin", nom="Dossier rejeté", col=5, rangee="bas", dy=35)],
         flux=[dict(s="s", t="sp"), dict(s="sp", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non"),
               dict(s="b", t="h", mode="descente"), dict(s="h", t="f3")])

_ajouter("B11-annotation-non-decisionnelle", "Annotation non décisionnelle écartée",
         "γ = ⊥ : annotation décorative écartée automatiquement, avec motif",
         "textAnnotation, association, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  ecartes=["annotation"],
                  enseignement="Une annotation sans valeur décisionnelle (logo, cachet, mise "
                  "en forme) est écartée sans question à l'expert, et tracée."),
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  annotation="Apposer le logo et le cachet officiel"))

_ajouter("B12-ressource-systeme", "Ressource système écartée",
         "ω = ⊥ : un couloir « système » exécute la règle sans la gouverner",
         "lane « Système d'information », businessRuleTask, exclusiveGateway",
         _attendu(decisions=["Contrôler la cohérence de la déclaration"],
                  inputs=["Déclaration d'importation"],
                  arcs=[("Déclaration d'importation", "Contrôler la cohérence de la déclaration", "P2")],
                  ecartes=["ressource"],
                  enseignement="L'indice « système » suffit à ω : la ressource est écartée "
                  "comme simple exécutant, sans question à l'expert."),
         lanes=["Système d'information du guichet"],
         squelette=_chaine_simple("Contrôler la cohérence de la déclaration",
                                  lit=["Déclaration d'importation"], type_="businessRuleTask"))

_ajouter("B13-collaboration-flux-de-message", "Collaboration et flux de message",
         "Π4 / P3 : le flux de message inter-pools rend l'événement récepteur porteur",
         "deux participants, messageFlow, startEvent sans définition, sendTask",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  inputs=["Demande de l'opérateur"],
                  arcs=[("Demande de l'opérateur", "Vérifier la recevabilité de la demande", "P3")],
                  enseignement="Sans définition de message, l'événement de départ n'est porteur "
                  "que parce qu'un flux de message venu de l'autre pool l'atteint : la "
                  "charge utile vient du partenaire."),
         elements=[
             dict(cle="s", e="depart", nom="Demande de l'opérateur", col=1),
             dict(cle="d", e="tache", nom="Vérifier la recevabilité de la demande", col=2,
                  decision=True),
             dict(cle="g", e="passerelle", nom="Demande recevable ?", col=3),
             dict(cle="f1", e="fin", nom="Demande acceptée", col=4),
             dict(cle="f2", e="fin", nom="Demande rejetée", col=3, rangee="bas")],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non")],
         pool2=dict(pool="Opérateur économique", nom="Dépôt d'une demande",
                    elements=[
                        dict(cle="os", e="depart", nom="Besoin d'agrément", col=0),
                        dict(cle="ot", e="tache", nom="Déposer la demande", col=1,
                             type="sendTask"),
                        dict(cle="of", e="fin", nom="Demande transmise", col=2)],
                    flux=[dict(s="os", t="ot"), dict(s="ot", t="of")]),
         messages=[dict(s="ot", t="s")])

# ---------------------------------------------------------------- famille C
_ajouter("C01-tache-generique", "Tâche générique devant une passerelle",
         "Hors définition : une tâche non typée n'est pas candidate, même corroborée",
         "task (générique), exclusiveGateway",
         _attendu(points=["hors-definition"], verdict="limite",
                  enseignement="La définition des candidates retient les tâches utilisateur, "
                  "les tâches de règle métier et les sous-processus repliés : la tâche "
                  "générique corroborée par la "
                  "passerelle est signalée hors définition, le DRD est vide et le "
                  "diagnostic invite à la retyper."),
         squelette=_chaine_simple("Examiner la demande", lit=["Demande d'agrément"],
                                  type_="task", decision=False))

_ajouter("C02-tache-de-service", "Tâche de service au verbe décisionnel",
         "Hors définition : une tâche de service qui décide de fait",
         "serviceTask, dataStoreReference, exclusiveGateway",
         _attendu(points=["hors-definition"], verdict="limite",
                  enseignement="Une tâche de service peut prendre une décision automatisée "
                  "(contrôle de cohérence) ; elle est signalée mais non retenue : angle "
                  "mort de la définition de référence."),
         squelette=_chaine_simple("Contrôler la cohérence de la déclaration",
                                  lit_magasin=["Référentiel tarifaire"], type_="serviceTask",
                                  decision=False))

_ajouter("C03-appel-d-activite", "Appel d'activité corroboré",
         "Hors définition : un appel d'activité (processus réutilisable) n'est pas candidat",
         "callActivity, exclusiveGateway",
         _attendu(points=["hors-definition"], verdict="limite",
                  enseignement="La décision est prise dans un processus appelé que le modèle "
                  "ne montre pas : l'appel est signalé, la décision ne peut être extraite "
                  "sans le modèle appelé."),
         squelette=_chaine_simple("Évaluer le dossier de l'opérateur",
                                  type_="callActivity", decision=False))

_ajouter("C04-decision-dans-les-conditions", "Décision encodée dans les conditions des flux",
         "Non couvert : cascade de passerelles conditionnées sans activité décisionnelle",
         "serviceTask, deux exclusiveGateway, conditionExpression",
         _attendu(points=["hors-definition"], verdict="limite",
                  enseignement="La logique de décision réside dans les expressions de "
                  "condition des flux (approche par le flux de contrôle) ; l'algorithme "
                  "ne lit pas les conditions et ne voit aucune activité de décision."),
         elements=[
             dict(cle="s", e="depart", nom="Déclaration déposée", col=0),
             dict(cle="t", e="tache", nom="Calculer le montant des droits", col=1,
                  type="serviceTask"),
             dict(cle="g1", e="passerelle", nom="Montant élevé ?", col=2),
             dict(cle="g2", e="passerelle", nom="Pays à risque ?", col=3),
             dict(cle="f1", e="fin", nom="Contrôle documentaire", col=2, rangee="bas"),
             dict(cle="f2", e="fin", nom="Contrôle physique", col=4),
             dict(cle="f3", e="fin", nom="Contrôle renforcé", col=3, rangee="bas")],
         flux=[dict(s="s", t="t"), dict(s="t", t="g1"),
               dict(s="g1", t="f1", nom="montant ≤ 5 M", condition="montant <= 5000000"),
               dict(s="g1", t="g2", nom="montant > 5 M", condition="montant > 5000000"),
               dict(s="g2", t="f2", nom="non", condition="not(paysARisque)"),
               dict(s="g2", t="f3", nom="oui", condition="paysARisque")])

_ajouter("C05-passerelle-d-evenements", "Passerelle d'événements après une tâche",
         "Non couvert : la passerelle d'événements n'est pas un indice de position",
         "userTask, eventBasedGateway, intermediateCatchEvent (message, minuterie)",
         _attendu(points=["candidat"], verdict="limite",
                  enseignement="La passerelle d'événements attend un événement au lieu "
                  "d'appliquer un verdict : elle ne corrobore pas la tâche qui la précède, "
                  "qui reste soumise à l'expert."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Instruire la demande", col=1,
                  lit=["Demande d'agrément"]),
             dict(cle="g", e="passerelle", col=2, type="evenements"),
             dict(cle="e1", e="inter", nom="Réponse de l'opérateur reçue", col=3, message=True),
             dict(cle="e2", e="inter", nom="Délai de 30 jours écoulé", col=3, rangee="bas",
                  minuterie=True),
             dict(cle="f1", e="fin", nom="Demande complétée", col=4),
             dict(cle="f2", e="fin", nom="Demande classée", col=4, rangee="bas")],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"), dict(s="g", t="e1"),
               dict(s="g", t="e2"), dict(s="e1", t="f1"), dict(s="e2", t="f2")])

_ajouter("C06-frontiere-minuterie", "Frontière de minuterie",
         "Non porteur : une frontière de minuterie n'apporte aucune donnée",
         "boundaryEvent + timerEventDefinition, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  inputs=["Demande d'agrément"],
                  arcs=[("Demande d'agrément", "Vérifier la recevabilité de la demande", "P2")],
                  points=["ressource"],
                  enseignement="Seuls les événements à message ou à signal portent une "
                  "charge utile ; le délai d'instruction n'est pas une donnée d'entrée, "
                  "même s'il conditionne le résultat."),
         lanes=["Chef de service", "Secrétariat"],
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Vérifier la recevabilité de la demande", col=1,
                  lit=["Demande d'agrément"], decision=True),
             dict(cle="b", e="frontiere", nom="Délai de 15 jours", sur="d", interrompt=True),
             dict(cle="g", e="passerelle", nom="Demande recevable ?", col=2),
             dict(cle="f1", e="fin", nom="Demande acceptée", col=3),
             dict(cle="f2", e="fin", nom="Demande rejetée", col=2, rangee="bas"),
             dict(cle="h", e="tache", nom="Relancer le demandeur", col=2, lane=1, type="task"),
             dict(cle="f3", e="fin", nom="Demande relancée", col=3, lane=1)],
         flux=[dict(s="s", t="d"), dict(s="d", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non"),
               dict(s="b", t="h", mode="descente"), dict(s="h", t="f3")])

_ajouter("C07-decision-sans-lecture", "Décision sans donnée lue",
         "Décision isolée : aucune lecture, seule une écriture → aucune exigence",
         "businessRuleTask, dataOutputAssociation",
         _attendu(decisions=["Évaluer la demande d'agrément"],
                  enseignement="Le DRD contient une décision sans aucune exigence : le modèle "
                  "ne dit pas ce qu'elle consomme. La limite est celle du modèle source, "
                  "l'algorithme ne peut pas inventer les entrées."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Évaluer la demande d'agrément", col=1,
                  type="businessRuleTask", ecrit="Avis d'évaluation", decision=True),
             dict(cle="t", e="tache", nom="Notifier l'avis", col=2, type="sendTask"),
             dict(cle="f", e="fin", nom="Avis notifié", col=3)],
         flux=[dict(s="s", t="d"), dict(s="d", t="t"), dict(s="t", t="f")])

_ajouter("C08-annotation-ambigue", "Annotation ambiguë",
         "γ indéterminé : une annotation sans indice n'est pas qualifiée",
         "textAnnotation, association, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  points=["annotation"], verdict="limite",
                  enseignement="Le lexique de γ ne reconnaît ni autorité ni règle : la "
                  "question « donnée ou source de connaissance ? » est posée à l'expert, "
                  "limite assumée des heuristiques lexicales."),
         squelette=_chaine_simple("Vérifier la recevabilité de la demande",
                                  annotation="Tenir compte du contexte particulier du demandeur"))

_ajouter("C09-verbe-hors-lexique", "Verbe absent du lexique de décision",
         "κ (lexique) : « valider » est volontairement exclu de Λ",
         "userTask, dataObjectReference, sans passerelle",
         _attendu(points=["candidat"], verdict="limite",
                  enseignement="« Valider » ne figure pas dans Λ (valider un formulaire ne "
                  "décide rien) : sans passerelle, la tâche n'est pas corroborée et reste "
                  "soumise à l'expert. Le lexique est un paramètre, pas une vérité."),
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="d", e="tache", nom="Valider le dossier de l'opérateur", col=1,
                  lit=["Dossier de l'opérateur"]),
             dict(cle="t", e="tache", nom="Archiver le dossier", col=2, type="task"),
             dict(cle="f", e="fin", nom="Dossier archivé", col=3)],
         flux=[dict(s="s", t="d"), dict(s="d", t="t"), dict(s="t", t="f")])

_ajouter("C10-donnee-d-entree-du-processus", "Donnée d'entrée déclarée au niveau du processus",
         "Non couvert : ioSpecification / dataInput du processus ignorés par le parseur",
         "ioSpecification, dataInput, dataInputAssociation, userTask, exclusiveGateway",
         _attendu(decisions=["Vérifier la recevabilité de la demande"],
                  verdict="limite",
                  enseignement="La donnée d'entrée déclarée par l'ioSpecification du "
                  "processus n'est ni un objet ni un magasin : l'association qui la lit "
                  "vise un identifiant inconnu (anomalie signalée) et la décision reste "
                  "sans exigence."),
         entrees_processus=[dict(cle="io", nom="Demande d'agrément", col=2)],
         elements=[
             dict(cle="s", e="depart", nom="Demande déposée", col=0),
             dict(cle="t1", e="tache", nom="Enregistrer la demande", col=1, type="task"),
             dict(cle="d", e="tache", nom="Vérifier la recevabilité de la demande", col=2,
                  lit_io=["io"], decision=True),
             dict(cle="g", e="passerelle", nom="Demande recevable ?", col=3),
             dict(cle="f1", e="fin", nom="Demande acceptée", col=4),
             dict(cle="f2", e="fin", nom="Demande rejetée", col=3, rangee="bas")],
         flux=[dict(s="s", t="t1"), dict(s="t1", t="d"), dict(s="d", t="g"),
               dict(s="g", t="f1", nom="oui"), dict(s="g", t="f2", nom="non")])


def construire_tous() -> List[Tuple[Dict, str, List[str]]]:
    """(méta, xml, décisions attendues) pour chaque pattern, en mémoire."""
    return [(m,) + Constructeur(m).construire() for m in MODELES]


def principal() -> int:
    os.makedirs(DOSSIER, exist_ok=True)
    for meta, xml, gold in construire_tous():
        base = os.path.join(DOSSIER, meta["fichier"])
        io.open(base + ".bpmn", "w", encoding="utf-8", newline="\n").write(xml)
        with io.open(base + ".gold", "w", encoding="utf-8", newline="\n") as f:
            f.write("# décisions attendues — %s\n" % meta["titre"])
            for d in gold:
                f.write(d + "\n")
        attendu = dict(meta["attendu"])
        attendu = {"id": meta["fichier"][:3], "titre": meta["titre"],
                   "pattern": meta["pattern"], "elements_bpmn": meta["elements_bpmn"],
                   **attendu}
        with io.open(base + ".attendu.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump(attendu, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("écrit : %s.bpmn (%d décision(s) attendue(s))" % (meta["fichier"], len(gold)))
    print("\n%d patterns dans %s" % (len(MODELES), DOSSIER))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
