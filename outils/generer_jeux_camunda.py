# -*- coding: utf-8 -*-
"""
Générateur des jeux d'essai Camunda Modeler, avec une mise en page soignée.

Produit dans `jeux-test-camunda/` dix processus BPMN 2.0 avec une mise en
page calculée aux standards visuels de Camunda Modeler :

  - un pool horizontal avec couloirs nommés (bandes de 260 px) ;
  - le flux principal de gauche à droite, une rangée de tâches centrée
    par couloir, espacement constant ;
  - flux de séquence orthogonaux (coude à mi-chemin entre les nœuds
    lors d'un changement de couloir) ;
  - objets/magasins de données alignés au-dessus des tâches qui les
    lisent, associations verticales, points d'ancrage décalés pour que
    les flèches ne se chevauchent jamais ;
  - annotations dans la bande basse du couloir, sous leur tâche ;
  - branches de rejet des passerelles : descente verticale vers un
    événement de fin dédié, libellés dégagés.

Chaque fichier est accompagné de sa référence experte `.gold`.
Usage :  python outils/generer_jeux_camunda.py
"""
from __future__ import annotations

import io
import os
import sys
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
DOSSIER = os.path.join(RACINE, "jeux-test-camunda")

# constantes de mise en page (px)
POOL_X, POOL_Y = 160, 80
BANDEAU = 30              # bandeau vertical du libellé de couloir
LANE_H = 260
X_DEPART = 240
ECART = 70                # espace horizontal entre éléments du flux
L_TACHE, H_TACHE = 130, 80
L_GW = 50
L_EVT = 36
L_DATA, H_DATA = 36, 50
L_STORE, H_STORE = 50, 50
L_ANNOT, H_ANNOT = 200, 48

Y_TACHES = 140            # centre de la rangée principale (relatif au couloir)
Y_DONNEES = 45            # centre de la rangée des données
Y_BAS = 206               # centre des fins de rejet (label sous l'événement)
Y_ANNOT = 224             # centre des annotations (bande basse)
ECART_DONNEES = 125       # entraxe minimal entre nœuds de données (labels à droite)


class Constructeur:
    def __init__(self, meta: Dict):
        self.meta = meta
        self.lanes: List[str] = meta["lanes"]
        self.M: List[str] = []          # éléments du process
        self.DI: List[str] = []         # arêtes DI
        self.pos: Dict[str, Tuple[float, float, float, float]] = {}
        self.membres: Dict[int, List[str]] = {i: [] for i in range(len(self.lanes))}
        self.x = X_DEPART
        self.n = 0
        self.donnees: Dict[str, str] = {}      # nom -> id (objets déjà posés)
        self.gold: List[str] = []
        self.dernier: Optional[str] = None     # dernier nœud du flux principal
        self.lane_du: Dict[str, int] = {}
        self.libelle_attente = ""              # « oui » à poser sur le flux suivant

    # identifiants
    def nid(self, p: str) -> str:
        self.n += 1
        return "%s%d" % (p, self.n)

    # géométrie
    def lane_top(self, i: int) -> float:
        return POOL_Y + i * LANE_H

    def centre(self, eid: str) -> Tuple[float, float]:
        x, y, w, h = self.pos[eid]
        return x + w / 2, y + h / 2

    def poser(self, eid: str, w: float, h: float, lane: int,
              rangee: float = Y_TACHES, x: Optional[float] = None) -> None:
        cy = self.lane_top(lane) + rangee
        px = self.x if x is None else x
        self.pos[eid] = (px, cy - h / 2, w, h)
        if x is None:
            self.x += w + ECART
        self.lane_du[eid] = lane

    # arêtes
    def _edge(self, eid: str, points: List[Tuple[float, float]]) -> None:
        wp = "".join('<di:waypoint x="%d" y="%d"/>' % (round(a), round(b))
                     for a, b in points)
        self.DI.append('      <bpmndi:BPMNEdge id="di_%s" bpmnElement="%s">%s'
                       '</bpmndi:BPMNEdge>' % (eid, eid, wp))

    def flux(self, s: str, t: str, nom: str = "") -> None:
        fid = self.nid("flux")
        attr = " name=%s" % quoteattr(nom) if nom else ""
        self.M.append('      <bpmn:sequenceFlow id="%s" sourceRef="%s" '
                      'targetRef="%s"%s/>' % (fid, s, t, attr))
        sx, sy, sw, sh = self.pos[s]
        tx, ty, tw, th = self.pos[t]
        scx, scy = sx + sw / 2, sy + sh / 2
        tcx, tcy = tx + tw / 2, ty + th / 2
        if abs(scy - tcy) < 2:                              # même rangée
            self._edge(fid, [(sx + sw, scy), (tx, tcy)])
        elif abs(scx - tcx) < 2:                            # même colonne
            if tcy > scy:
                self._edge(fid, [(scx, sy + sh), (tcx, ty)])
            else:
                self._edge(fid, [(scx, sy), (tcx, ty + th)])
        else:                                               # coude orthogonal
            mx = (sx + sw + tx) / 2
            self._edge(fid, [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)])

    def flux_descente(self, s: str, t: str) -> None:
        """Frontière -> tâche d'un couloir inférieur : descente verticale
        depuis le bas de la frontière, puis entrée par la gauche."""
        fid = self.nid("flux")
        self.M.append('      <bpmn:sequenceFlow id="%s" sourceRef="%s" '
                      'targetRef="%s"/>' % (fid, s, t))
        sx, sy, sw, sh = self.pos[s]
        tx, ty, tw, th = self.pos[t]
        scx = sx + sw / 2
        tcy = ty + th / 2
        self._edge(fid, [(scx, sy + sh), (scx, tcy), (tx, tcy)])

    def flux_vertical_bas(self, s: str, t: str, nom: str = "") -> None:
        """Passerelle -> fin de rejet placée juste dessous."""
        fid = self.nid("flux")
        attr = " name=%s" % quoteattr(nom) if nom else ""
        self.M.append('      <bpmn:sequenceFlow id="%s" sourceRef="%s" '
                      'targetRef="%s"%s/>' % (fid, s, t, attr))
        sx, sy, sw, sh = self.pos[s]
        tx, ty, tw, th = self.pos[t]
        self._edge(fid, [(sx + sw / 2, sy + sh), (tx + tw / 2, ty)])

    # données
    def objet(self, nom: str, magasin: bool, x_centre: float,
              lane: int) -> str:
        """Pose (ou retrouve) un nœud de données dans la rangée haute."""
        if nom in self.donnees:
            return self.donnees[nom]
        oid = self.nid("donnee")
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
        # éviter le chevauchement avec un nœud (et son libellé, placé à
        # droite) déjà posé sur la rangée des données de ce couloir
        x = x_centre - w / 2
        rangs = [p for p in self.pos.values()
                 if abs((p[1] + p[3] / 2)
                        - (self.lane_top(lane) + Y_DONNEES)) < 4]
        while any(abs(x - p[0]) < ECART_DONNEES for p in rangs):
            x += ECART_DONNEES
        self.pos[oid] = (x, self.lane_top(lane) + Y_DONNEES - h / 2, w, h)
        self.est_donnee = getattr(self, "est_donnee", set())
        self.est_donnee.add(oid)
        return oid

    def association_lecture(self, oid: str, tid: str, rang: int,
                            pid_prop: str) -> str:
        aid = self.nid("lecture")
        ox, oy, ow, oh = self.pos[oid]
        tx, ty, tw, th = self.pos[tid]
        dock_x = tx + tw / 2 - 30 + rang * 26      # ancrages décalés
        ocx = ox + ow / 2
        if abs(ocx - dock_x) < 6:
            self._edge(aid, [(ocx, oy + oh), (dock_x, ty)])
        else:
            my = ty - 18
            self._edge(aid, [(ocx, oy + oh), (ocx, my), (dock_x, my),
                             (dock_x, ty)])
        #  le XSD BPMN 2.0 exige un targetRef : propriété interne de la tâche
        return ('        <bpmn:dataInputAssociation id="%s">'
                '<bpmn:sourceRef>%s</bpmn:sourceRef>'
                '<bpmn:targetRef>%s</bpmn:targetRef>'
                '</bpmn:dataInputAssociation>' % (aid, oid, pid_prop))

    def association_ecriture(self, tid: str, oid: str) -> str:
        aid = self.nid("ecriture")
        ox, oy, ow, oh = self.pos[oid]
        tx, ty, tw, th = self.pos[tid]
        dock_x = tx + tw / 2 + 44
        ocx = ox + ow / 2
        if abs(ocx - dock_x) < 6:
            self._edge(aid, [(dock_x, ty), (ocx, oy + oh)])
        else:
            my = ty - 26
            self._edge(aid, [(dock_x, ty), (dock_x, my), (ocx, my),
                             (ocx, oy + oh)])
        return ('        <bpmn:dataOutputAssociation id="%s">'
                '<bpmn:targetRef>%s</bpmn:targetRef>'
                '</bpmn:dataOutputAssociation>' % (aid, oid))

    def annoter(self, tid: str, texte: str) -> None:
        anid = self.nid("annot")
        self.M.append('      <bpmn:textAnnotation id="%s"><bpmn:text>%s'
                      '</bpmn:text></bpmn:textAnnotation>'
                      % (anid, escape(texte)))
        tx, ty, tw, th = self.pos[tid]
        lane = self.lane_du[tid]
        ax = tx + tw / 2 - L_ANNOT / 2
        ay = self.lane_top(lane) + Y_ANNOT - H_ANNOT / 2
        self.pos[anid] = (ax, ay, L_ANNOT, H_ANNOT)
        aid = self.nid("assocannot")
        self.M.append('      <bpmn:association id="%s" sourceRef="%s" '
                      'targetRef="%s"/>' % (aid, anid, tid))
        self._edge(aid, [(ax + L_ANNOT / 2, ay), (tx + tw / 2, ty + th)])

    # éléments
    def construire(self) -> Tuple[str, List[str]]:
        m = self.meta
        for e in m["elements"]:
            genre = e["e"]
            if genre == "depart":
                eid = self.nid("depart")
                contenu = ('<bpmn:messageEventDefinition id="%s_md"/>' % eid) \
                    if e.get("message") else ""
                self.M.append('      <bpmn:startEvent id="%s" name=%s>%s'
                              '</bpmn:startEvent>'
                              % (eid, quoteattr(e["nom"]), contenu))
                self.poser(eid, L_EVT, L_EVT, e["lane"])
                self.membres[e["lane"]].append(eid)
                self.dernier = eid

            elif genre in ("tache", "decision"):
                tid = self.nid("tache")
                type_ = e.get("type", "userTask")
                lane = e["lane"]
                self.poser(tid, L_TACHE, H_TACHE, lane)
                self.membres[lane].append(tid)
                contenu: List[str] = []
                cx, _ = self.centre(tid)
                pid_prop = self.nid("prop")
                for k, nom_d in enumerate(e.get("lit", [])):
                    oid = self.objet(nom_d, False, cx - 40 + k * ECART_DONNEES,
                                     lane)
                    contenu.append(self.association_lecture(oid, tid, k,
                                                            pid_prop))
                for k, nom_d in enumerate(e.get("lit_magasin", [])):
                    oid = self.objet(nom_d, True,
                                     cx - 40 + (len(e.get("lit", [])) + k)
                                     * ECART_DONNEES, lane)
                    contenu.append(self.association_lecture(
                        oid, tid, len(e.get("lit", [])) + k, pid_prop))
                if contenu:            # propriété cible exigée par le XSD
                    contenu.insert(0, '<bpmn:property id="%s" '
                                      'name="__targetRef_placeholder"/>'
                                      % pid_prop)
                if e.get("ecrit"):
                    oid = self.objet(e["ecrit"], False, cx + 150, lane)
                    contenu.append(self.association_ecriture(tid, oid))
                self.M.append('      <bpmn:%s id="%s" name=%s>%s</bpmn:%s>'
                              % (type_, tid, quoteattr(e["nom"]),
                                 "".join(contenu), type_))
                if self.dernier:
                    self.flux(self.dernier, tid, self.libelle_attente)
                    self.libelle_attente = ""
                self.dernier = tid
                if genre == "decision":
                    self.gold.append(e["nom"])
                if e.get("annotation"):
                    self.annoter(tid, e["annotation"])

                # -- passerelle de verdict éventuelle
                gw = e.get("gw")
                if gw:
                    gid = self.nid("passerelle")
                    balise = "inclusiveGateway" if gw.get("inclusive") \
                        else "exclusiveGateway"
                    self.M.append('      <bpmn:%s id="%s" name=%s/>'
                                  % (balise, gid, quoteattr(gw["nom"])))
                    self.poser(gid, L_GW, L_GW, lane)
                    self.est_passerelle = getattr(self, "est_passerelle", set())
                    self.est_passerelle.add(gid)
                    self.membres[lane].append(gid)
                    self.flux(tid, gid)
                    fid_fin = self.nid("fin")
                    self.M.append('      <bpmn:endEvent id="%s" name=%s/>'
                                  % (fid_fin, quoteattr(gw["fin_non"])))
                    gx, _ = self.centre(gid)
                    self.poser(fid_fin, L_EVT, L_EVT, lane, Y_BAS,
                               x=gx - L_EVT / 2)
                    self.membres[lane].append(fid_fin)
                    self.flux_vertical_bas(gid, fid_fin, gw["non"])
                    self.dernier = gid
                    self.libelle_attente = gw.get("oui", "")

                # -- événement-frontière éventuel (message non interrupteur)
                bd = e.get("boundary")
                if bd:
                    bid = self.nid("bord")
                    self.M.append('      <bpmn:boundaryEvent id="%s" name=%s '
                                  'attachedToRef="%s" cancelActivity="false">'
                                  '<bpmn:messageEventDefinition id="%s_md"/>'
                                  '</bpmn:boundaryEvent>'
                                  % (bid, quoteattr(bd["nom"]), tid, bid))
                    tx, ty, tw, th = self.pos[tid]
                    self.pos[bid] = (tx + tw - 50, ty + th - L_EVT / 2,
                                     L_EVT, L_EVT)
                    self.lane_du[bid] = lane
                    self.membres[lane].append(bid)
                    hid = self.nid("tache")
                    hlane = bd["lane"]
                    self.poser(hid, L_TACHE, H_TACHE, hlane)
                    self.membres[hlane].append(hid)
                    self.M.append('      <bpmn:userTask id="%s" name=%s>'
                                  '</bpmn:userTask>'
                                  % (hid, quoteattr(bd["tache"])))
                    self.flux_descente(bid, hid)
                    fid2 = self.nid("fin")
                    self.M.append('      <bpmn:endEvent id="%s" name=%s/>'
                                  % (fid2, quoteattr(bd["fin"])))
                    hx, hy = self.centre(hid)
                    self.poser(fid2, L_EVT, L_EVT, hlane, Y_TACHES)
                    self.membres[hlane].append(fid2)
                    self.flux(hid, fid2)

            elif genre == "fin":
                eid = self.nid("fin")
                self.M.append('      <bpmn:endEvent id="%s" name=%s/>'
                              % (eid, quoteattr(e["nom"])))
                lane = e.get("lane", self.lane_du.get(self.dernier, 0))
                self.poser(eid, L_EVT, L_EVT, lane)
                self.membres[lane].append(eid)
                self.flux(self.dernier, eid, self.libelle_attente)
                self.libelle_attente = ""
                self.dernier = eid

        return self.document(), self.gold

    # document
    def document(self) -> str:
        largeur = self.x + 40 - POOL_X
        hauteur = len(self.lanes) * LANE_H
        pid = "Process_1"
        L = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<bpmn:definitions '
             'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
             'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
             'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
             'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
             'id="Definitions_1" targetNamespace="http://bpmn2dmn/jeux" '
             'exporter="bpmn2dmn" exporterVersion="1.0">',
             '  <bpmn:collaboration id="Collab_1">',
             '    <bpmn:participant id="Pool_1" name=%s processRef="%s"/>'
             % (quoteattr(self.meta["pool"]), pid),
             '  </bpmn:collaboration>',
             '  <bpmn:process id="%s" name=%s isExecutable="false">'
             % (pid, quoteattr(self.meta["nom"]))]
        L.append('    <bpmn:laneSet id="Lanes_1">')
        for i, nom in enumerate(self.lanes):
            L.append('      <bpmn:lane id="Lane_%d" name=%s>'
                     % (i + 1, quoteattr(nom)))
            for eid in self.membres[i]:
                L.append('        <bpmn:flowNodeRef>%s</bpmn:flowNodeRef>' % eid)
            L.append('      </bpmn:lane>')
        L.append('    </bpmn:laneSet>')
        #  conformité XSD : artefacts (annotations, associations) en dernier
        artefacts = [l for l in self.M if "<bpmn:textAnnotation" in l
                     or "<bpmn:association " in l]
        L.extend(l for l in self.M if l not in artefacts)
        L.extend(artefacts)
        L.append('  </bpmn:process>')
        L.append('  <bpmndi:BPMNDiagram id="Diagramme_1">')
        L.append('    <bpmndi:BPMNPlane id="Plan_1" bpmnElement="Collab_1">')
        L.append('      <bpmndi:BPMNShape id="di_Pool_1" bpmnElement="Pool_1" '
                 'isHorizontal="true"><dc:Bounds x="%d" y="%d" width="%d" '
                 'height="%d"/></bpmndi:BPMNShape>'
                 % (POOL_X, POOL_Y, largeur, hauteur))
        for i in range(len(self.lanes)):
            L.append('      <bpmndi:BPMNShape id="di_Lane_%d" '
                     'bpmnElement="Lane_%d" isHorizontal="true">'
                     '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>'
                     '</bpmndi:BPMNShape>'
                     % (i + 1, i + 1, POOL_X + BANDEAU, self.lane_top(i),
                        largeur - BANDEAU, LANE_H))
        donnees = getattr(self, "est_donnee", set())
        passerelles = getattr(self, "est_passerelle", set())
        for eid, (x, y, w, h) in self.pos.items():
            label = ""
            if eid in donnees:
                # libellé à droite du nœud : il ne barre plus les flèches
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" '
                         'width="110" height="28"/></bpmndi:BPMNLabel>'
                         % (round(x + w + 6), round(y + h / 2 - 14)))
            elif eid in passerelles:
                # libellé au-dessus du losange : dégagé de la branche basse
                label = ('<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" '
                         'width="150" height="26"/></bpmndi:BPMNLabel>'
                         % (round(x + w / 2 - 75), round(y - 32)))
            L.append('      <bpmndi:BPMNShape id="di_%s" bpmnElement="%s">'
                     '<dc:Bounds x="%d" y="%d" width="%d" height="%d"/>%s'
                     '</bpmndi:BPMNShape>'
                     % (eid, eid, round(x), round(y), round(w), round(h),
                        label))
        L.extend(self.DI)
        L.append('    </bpmndi:BPMNPlane>')
        L.append('  </bpmndi:BPMNDiagram>')
        L.append('</bpmn:definitions>')
        return "\n".join(L) + "\n"


# les dix processus
MODELES: List[Dict] = [
 dict(fichier="01-credit-bancaire", pool="Banque commerciale",
      nom="Instruction d'une demande de crédit",
      lanes=["Chargé de clientèle", "Comité de crédit"],
      elements=[
        dict(e="depart", nom="Demande de crédit reçue", lane=0, message=True),
        dict(e="tache", nom="Saisir les informations du client", lane=0),
        dict(e="decision", nom="Vérifier la complétude du dossier", lane=0,
             lit=["Demande de crédit"], ecrit="Dossier constitué",
             gw=dict(nom="Dossier complet ?", oui="complet", non="incomplet",
                     fin_non="Demande retournée")),
        dict(e="decision", nom="Évaluer la solvabilité du demandeur", lane=0,
             lit=["Dossier constitué"], lit_magasin=["Centrale des risques"],
             ecrit="Avis de solvabilité",
             annotation="Calcul du score interne selon la grille en vigueur"),
        dict(e="decision", nom="Statuer sur l'octroi du crédit", lane=1,
             lit=["Avis de solvabilité"],
             annotation="Réglementation prudentielle COBAC applicable",
             gw=dict(nom="Octroi accepté ?", oui="accord", non="refus",
                     fin_non="Crédit non accordé")),
        dict(e="tache", nom="Notifier la réponse au client", lane=0,
             type="sendTask"),
        dict(e="fin", nom="Crédit octroyé", lane=0),
      ]),

 dict(fichier="02-sinistre-assurance", pool="Compagnie d'assurance",
      nom="Traitement d'une déclaration de sinistre",
      lanes=["Gestionnaire sinistres", "Expert automobile"],
      elements=[
        dict(e="depart", nom="Déclaration reçue", lane=0, message=True),
        dict(e="tache", nom="Enregistrer la déclaration", lane=0),
        dict(e="decision", nom="Vérifier la validité de la garantie", lane=0,
             lit=["Constat amiable"], lit_magasin=["Base des contrats"],
             gw=dict(nom="Garantie acquise ?", oui="acquise", non="exclue",
                     fin_non="Sinistre non couvert")),
        dict(e="tache", nom="Missionner l'expert", lane=0, type="sendTask"),
        dict(e="decision", nom="Évaluer le montant des dommages", lane=1,
             lit=["Rapport d'expertise"], ecrit="Montant évalué",
             annotation="Barème d'indemnisation par type de dommage"),
        dict(e="decision", nom="Statuer sur l'indemnisation", lane=0,
             lit=["Montant évalué"],
             annotation="Code CIMA des assurances, livre II",
             gw=dict(nom="Indemnisation due ?", oui="due", non="contestée",
                     fin_non="Dossier transmis au contentieux")),
        dict(e="fin", nom="Sinistre indemnisé", lane=0),
      ]),

 dict(fichier="03-admission-hopital", pool="Centre hospitalier",
      nom="Admission d'un patient aux urgences",
      lanes=["Infirmier d'accueil", "Médecin urgentiste", "Brancardier"],
      elements=[
        dict(e="depart", nom="Patient enregistré", lane=0, message=True),
        dict(e="tache", nom="Mesurer les constantes vitales", lane=0),
        dict(e="decision", nom="Coter la gravité du patient", lane=0,
             lit=["Fiche de constantes"], ecrit="Niveau de tri",
             annotation="Score de gravité calculé selon l'échelle de tri"),
        dict(e="decision", nom="Examiner le patient", lane=1,
             lit=["Niveau de tri", "Dossier médical"],
             boundary=dict(nom="Lit disponible", lane=2,
                           tache="Installer le patient au lit",
                           fin="Patient installé"),
             gw=dict(nom="Hospitalisation requise ?", oui="hospitaliser",
                     non="soins ambulatoires",
                     fin_non="Patient orienté en consultation")),
        dict(e="tache", nom="Rédiger le compte rendu d'admission", lane=1),
        dict(e="fin", nom="Patient hospitalisé", lane=1),
      ]),

 dict(fichier="04-recrutement", pool="Direction des ressources humaines",
      nom="Instruction d'une candidature",
      lanes=["Assistant RH", "Responsable du recrutement"],
      elements=[
        dict(e="depart", nom="Candidature reçue", lane=0, message=True),
        dict(e="tache", nom="Enregistrer la candidature", lane=0),
        dict(e="decision", nom="Vérifier l'éligibilité de la candidature",
             lane=0, lit=["Dossier de candidature"],
             lit_magasin=["Référentiel des postes"],
             gw=dict(nom="Profil éligible ?", oui="éligible", non="hors profil",
                     fin_non="Candidature non retenue")),
        dict(e="tache", nom="Convoquer le candidat", lane=0, type="sendTask"),
        dict(e="decision", nom="Apprécier l'entretien du candidat", lane=1,
             lit=["Fiche d'entretien"], ecrit="Note d'entretien",
             annotation="Grille de notation des entretiens en vigueur",
             gw=dict(nom="Candidat retenu ?", oui="retenu", non="écarté",
                     fin_non="Candidat remercié")),
        dict(e="fin", nom="Candidat recruté", lane=1),
      ]),

 dict(fichier="05-marche-public", pool="Commission de passation des marchés",
      nom="Évaluation des offres d'un appel d'offres",
      lanes=["Secrétariat de la commission", "Sous-commission d'analyse"],
      elements=[
        dict(e="depart", nom="Offres réceptionnées", lane=0),
        dict(e="tache", nom="Ouvrir les plis en séance", lane=0),
        dict(e="decision", nom="Vérifier la conformité administrative",
             lane=0, lit=["Offre administrative"],
             annotation="Code des marchés publics, articles 45 à 52",
             gw=dict(nom="Offre recevable ?", oui="recevable",
                     non="irrecevable", fin_non="Offre écartée")),
        dict(e="decision", nom="Évaluer l'offre technique", lane=1,
             lit=["Offre technique"], ecrit="Note technique",
             annotation="Pondération technique et financière des offres"),
        dict(e="decision", nom="Évaluer l'offre financière", lane=1,
             lit=["Offre financière"], ecrit="Note financière"),
        dict(e="decision", nom="Statuer sur l'attribution du marché", lane=1,
             lit=["Note technique", "Note financière"],
             gw=dict(nom="Marché attribué ?", oui="attribué", non="infructueux",
                     fin_non="Appel d'offres déclaré infructueux",
                     inclusive=True)),
        dict(e="tache", nom="Notifier l'attributaire", lane=0, type="sendTask"),
        dict(e="fin", nom="Marché notifié", lane=0),
      ]),

 dict(fichier="06-dedouanement", pool="Bureau des douanes",
      nom="Mainlevée d'une déclaration en douane",
      lanes=["Inspecteur des douanes", "Système SYDONIA"],
      elements=[
        dict(e="depart", nom="Déclaration déposée", lane=1, message=True),
        dict(e="tache", nom="Générer la liquidation automatique", lane=1,
             type="serviceTask"),
        dict(e="decision", nom="Vérifier les documents joints", lane=0,
             lit=["Déclaration en détail", "Facture commerciale"],
             annotation="Procédure du circuit de visite en vigueur",
             gw=dict(nom="Documents conformes ?", oui="conformes",
                     non="litige", fin_non="Déclaration en contentieux")),
        dict(e="decision", nom="Apprécier la valeur en douane", lane=0,
             lit_magasin=["Fichier des valeurs"], ecrit="Valeur retenue",
             annotation="Apposer le cachet du bureau sur le bon"),
        dict(e="tache", nom="Encaisser les droits et taxes", lane=1,
             type="serviceTask"),
        dict(e="fin", nom="Mainlevée accordée", lane=1),
      ]),

 dict(fichier="07-bourse-etudes", pool="Université — Service des bourses",
      nom="Attribution d'une bourse d'études",
      lanes=["Guichet des bourses", "Commission d'attribution"],
      elements=[
        dict(e="depart", nom="Dossier de bourse déposé", lane=0, message=True),
        dict(e="tache", nom="Enregistrer le dossier", lane=0),
        dict(e="decision", nom="Vérifier les pièces du dossier", lane=0,
             lit=["Dossier de bourse"],
             gw=dict(nom="Dossier recevable ?", oui="recevable",
                     non="incomplet", fin_non="Dossier retourné")),
        dict(e="decision", nom="Coter le mérite académique", lane=1,
             lit=["Relevés de notes"], ecrit="Note de mérite",
             annotation="Barème de cotation du mérite académique"),
        dict(e="decision", nom="Statuer sur l'attribution de la bourse",
             lane=1, lit=["Note de mérite"],
             lit_magasin=["Fichier des boursiers"],
             annotation="Arrêté ministériel fixant les quotas de bourses",
             gw=dict(nom="Bourse accordée ?", oui="accordée", non="ajournée",
                     fin_non="Demande ajournée")),
        dict(e="tache", nom="Notifier le bénéficiaire", lane=0,
             type="sendTask"),
        dict(e="fin", nom="Bourse attribuée", lane=0),
      ]),

 dict(fichier="08-permis-construire", pool="Commune urbaine",
      nom="Instruction d'un permis de construire",
      lanes=["Guichet unique", "Service de l'urbanisme"],
      elements=[
        dict(e="depart", nom="Demande de permis déposée", lane=0,
             message=True),
        dict(e="tache", nom="Enregistrer la demande", lane=0),
        dict(e="decision", nom="Vérifier la complétude des pièces", lane=0,
             lit=["Dossier de demande"],
             gw=dict(nom="Pièces complètes ?", oui="complètes",
                     non="manquantes", fin_non="Demande retournée")),
        dict(e="decision", nom="Examiner la conformité au plan d'urbanisme",
             lane=1, lit=["Plans architecturaux"],
             lit_magasin=["Plan d'occupation des sols"],
             ecrit="Avis d'urbanisme",
             annotation="Norme d'urbanisme et servitudes applicables"),
        dict(e="decision", nom="Statuer sur la délivrance du permis", lane=1,
             lit=["Avis d'urbanisme"],
             gw=dict(nom="Permis délivré ?", oui="délivré", non="refusé",
                     fin_non="Permis refusé")),
        dict(e="tache", nom="Établir l'arrêté municipal", lane=1),
        dict(e="fin", nom="Permis délivré", lane=1),
      ]),

 dict(fichier="09-visa-sejour", pool="Consulat général",
      nom="Délivrance d'un visa de séjour",
      lanes=["Agent consulaire", "Consul adjoint"],
      elements=[
        dict(e="depart", nom="Demande de visa déposée", lane=0, message=True),
        dict(e="tache", nom="Numériser les pièces du dossier", lane=0),
        dict(e="decision", nom="Vérifier l'authenticité des documents",
             lane=0, lit=["Passeport", "Justificatifs de séjour"],
             ecrit="Avis documentaire",
             annotation="Convention consulaire et accords bilatéraux"),
        dict(e="tache", nom="Convoquer le demandeur à l'entretien", lane=0,
             type="sendTask"),
        dict(e="decision", nom="Statuer sur la délivrance du visa", lane=1,
             lit=["Avis documentaire", "Compte rendu d'entretien"],
             gw=dict(nom="Visa accordé ?", oui="accordé", non="refusé",
                     fin_non="Visa refusé")),
        dict(e="tache", nom="Apposer la vignette au passeport", lane=0),
        dict(e="fin", nom="Visa délivré", lane=0),
      ]),

 dict(fichier="10-subvention-agricole", pool="Ministère de l'agriculture",
      nom="Attribution d'une subvention agricole",
      lanes=["Délégation départementale", "Comité technique", "Plateforme e-Subvention"],
      elements=[
        dict(e="depart", nom="Demande de subvention reçue", lane=2,
             message=True),
        dict(e="tache", nom="Contrôle automatique du formulaire", lane=2,
             type="serviceTask"),
        dict(e="decision", nom="Vérifier l'éligibilité de l'exploitation",
             lane=0, lit=["Dossier d'exploitation"],
             lit_magasin=["Registre des exploitants"],
             gw=dict(nom="Exploitation éligible ?", oui="éligible",
                     non="inéligible", fin_non="Demande rejetée")),
        dict(e="tache", nom="Programmer la visite de terrain", lane=0),
        dict(e="decision", nom="Apprécier le projet agricole", lane=1,
             lit=["Rapport de visite"], ecrit="Note du projet",
             annotation="Grille de notation des projets agricoles"),
        dict(e="decision", nom="Statuer sur le montant de la subvention",
             lane=1, lit=["Note du projet"],
             annotation="Décret fixant les plafonds de subvention",
             gw=dict(nom="Subvention accordée ?", oui="accordée",
                     non="ajournée", fin_non="Demande ajournée")),
        dict(e="tache", nom="Mettre en paiement la subvention", lane=2,
             type="serviceTask"),
        dict(e="fin", nom="Subvention versée", lane=2),
      ]),
]


def principal() -> int:
    os.makedirs(DOSSIER, exist_ok=True)
    lignes_lisezmoi = []
    for meta in MODELES:
        xml, gold = Constructeur(meta).construire()
        base = os.path.join(DOSSIER, meta["fichier"])
        io.open(base + ".bpmn", "w", encoding="utf-8").write(xml)
        with io.open(base + ".gold", "w", encoding="utf-8") as f:
            f.write("# décisions attendues — %s\n" % meta["nom"])
            for d in gold:
                f.write(d + "\n")
        lignes_lisezmoi.append("| `%s.bpmn` | %s | %d |"
                               % (meta["fichier"], meta["nom"], len(gold)))
        print("écrit : %s.bpmn (%d décisions attendues)"
              % (meta["fichier"], len(gold)))

    with io.open(os.path.join(DOSSIER, "LISEZ-MOI.md"), "w",
                 encoding="utf-8") as f:
        f.write("# Jeux d'essai Camunda Modeler\n\n"
                "Dix processus BPMN 2.0 à mise en page soignée, prêts à\n"
                "ouvrir dans **Camunda Modeler** (Fichier → Ouvrir) ou à\n"
                "déposer dans l'application du transformateur\n"
                "(`python cli.py servir`). Chaque fichier a sa référence\n"
                "experte `.gold` (décisions attendues) :\n"
                "`python cli.py valider \"jeux-test-camunda/*.bpmn\"`.\n\n"
                "Régénération : `python outils/generer_jeux_camunda.py`.\n\n"
                "| Fichier | Processus | Décisions |\n|---|---|---|\n"
                + "\n".join(lignes_lisezmoi) + "\n")
    print("\n%d fichiers dans %s" % (len(MODELES), DOSSIER))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
