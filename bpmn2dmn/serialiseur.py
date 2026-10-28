# -*- coding: utf-8 -*-
"""
Sérialiseur Mf -> DMN 1.3 + DMNDI, dernière boîte avant le visualiseur.

Le fichier produit s'ouvre directement dans Camunda Modeler 5.x (onglet
DRD) ou sur demo.bpmn.io/dmn : espaces de noms de la norme OMG DMN 1.3
(20191111), soit le format des DRD du dossier (fimex-drd.dmn).

La mise en page est calculée par couches : chaque décision reçoit la
couche 1 + max(couche de ses décisions requises), les décisions
dépendantes montent ; données d'entrée, sources et BKM sont posés en bas
ou en flanc de leur décision. Une exigence est tracée en flèche droite
et n'est déroutée orthogonalement que si la droite traverse un symbole.

`positionner` enchaîne les étapes de la mise en page (couches, abscisses,
sources, routage, écartement des pointes) ; `serialiser_dmn` écrit les
éléments MODEL puis le bloc DMNDI.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape, quoteattr

from .metamodeles import (BKM, DECISION, INPUT_DATA, KNOWLEDGE_SOURCE, Mf)
from .qualification import normaliser

NS_MODEL = "https://www.omg.org/spec/DMN/20191111/MODEL/"
NS_DMNDI = "https://www.omg.org/spec/DMN/20191111/DMNDI/"
NS_DC = "http://www.omg.org/spec/DMN/20180521/DC/"
NS_DI = "http://www.omg.org/spec/DMN/20180521/DI/"

# dimensions de base (celles de dmn-js / Camunda Modeler) et plafonds
DIMS = {DECISION: (180, 80), INPUT_DATA: (135, 45),
        KNOWLEDGE_SOURCE: (140, 63), BKM: (150, 46)}
LARG_MAX = {DECISION: 260, INPUT_DATA: 210,
            KNOWLEDGE_SOURCE: 230, BKM: 230}
MARGE = 40
_LARG_CAR = 6.6                  # largeur moyenne d'un caractère (12 px)
ECART = 6.0                      # espace entre deux pointes de flèche voisines

Point = Tuple[float, float]
Rect = Tuple[float, float, float, float]
Arc = Tuple[str, str]


def _dimensions(type_: str, nom: str) -> Tuple[float, float]:
    """Taille du symbole adaptée à son libellé : la largeur s'étire jusqu'au
    plafond du type, puis la hauteur absorbe les lignes supplémentaires."""
    base_w, base_h = DIMS[type_]
    n = len(nom or "")
    w = base_w
    if n > 24:
        w = min(LARG_MAX[type_], base_w + (n - 24) * 2.4)
    utile = max(w - 28, 40)                    # marge interne du libellé
    lignes = max(1, -(-int(n * _LARG_CAR) // int(utile)))
    h = max(base_h, 18 + lignes * 16 + 10)
    return round(w), round(h)


def _sur(s: str) -> str:
    """Identifiant XML sûr (NCName)."""
    s = re.sub(r"[^A-Za-z0-9_.\-]", "_", s or "n")
    return s if re.match(r"[A-Za-z_]", s) else "n" + s


# caractères que XML 1.0 n'admet dans aucun texte, même échappés
_INTERDITS_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def texte_xml(s: str) -> str:
    """Texte débarrassé des caractères interdits par XML 1.0, à passer
    avant tout échappement (un renommage peut en contenir)."""
    return _INTERDITS_XML.sub("", s or "")


# ----------------------------------------------------------------------
# mise en page
# ----------------------------------------------------------------------
def positionner(mf: Mf) -> Tuple[Dict[str, Rect], Dict[Arc, List[Point]]]:
    """Calcule (x, y, largeur, hauteur) pour chaque nœud de V_f, et le
    tracé (waypoints) de chaque exigence. Retourne (pos, routes)."""
    dims: Dict[str, Tuple[float, float]] = {
        n.id: _dimensions(n.type, n.nom) for n in mf.noeuds.values()}
    dec_ids = [n.id for n in mf.decisions]
    requises = _decisions_requises(mf, dec_ids)
    couche = _couches(dec_ids, requises)
    grille = _Grille(mf, dims, dec_ids, couche)

    pos: Dict[str, Rect] = {}
    x_dec = _abscisses_decisions(dec_ids, requises, dims, couche, grille.pas_x)
    for d in dec_ids:
        w, h = dims[d]
        pos[d] = (x_dec[d] - w / 2,
                  grille.y_rangee(couche[d]) + (grille.h_rangee - h) / 2, w, h)

    cote_de = _PoseurDeSources(mf, pos, dims, couche, grille).placer()
    routes = _router(mf, pos, couche, cote_de, grille)
    return pos, routes


def _decisions_requises(mf: Mf, dec_ids: List[str]) -> Dict[str, List[str]]:
    """Pour chaque décision, ses décisions requises (IR décision -> décision)."""
    requises: Dict[str, List[str]] = {d: [] for d in dec_ids}
    for u, v in mf.arcs:
        if u in requises and v in requises:
            requises[v].append(u)
    return requises


def _couches(dec_ids: List[str], requises: Dict[str, List[str]]) -> Dict[str, int]:
    """Couche de chaque décision : 1 + max(couche des requises), soit le
    plus long chemin sur les IR décision -> décision. Parcours en
    profondeur avec pile explicite (une chaîne de plusieurs milliers de
    décisions dépasserait la pile d'appels) ; chaque cadre garde le
    maximum des couches déjà connues de ses requises, une requise en cours
    de visite (cycle signalé ailleurs) ne comptant pour rien."""
    couche: Dict[str, int] = {}
    for depart in dec_ids:
        if depart in couche:
            continue
        en_cours = {depart}
        pile = [[depart, iter(requises[depart]), 0]]
        while pile:
            cadre = pile[-1]
            d, restantes, maxi = cadre
            for r in restantes:
                if r in couche:
                    maxi = max(maxi, couche[r])
                elif r not in en_cours:
                    cadre[2] = maxi
                    en_cours.add(r)
                    pile.append([r, iter(requises[r]), 0])
                    break
            else:
                couche[d] = 1 + maxi
                en_cours.discard(d)
                pile.pop()
                if pile:
                    pile[-1][2] = max(pile[-1][2], couche[d])
    return couche


class _Grille:
    """Pas horizontal et vertical calculés sur les symboles (taille
    variable) ; la couche L monte, les sources (I, KS, BKM) sont tout en bas."""

    def __init__(self, mf: Mf, dims: Dict[str, Tuple[float, float]],
                 dec_ids: List[str], couche: Dict[str, int]):
        self.pas_x = max([dims[d][0] for d in dec_ids] or [180]) + 80
        self.h_rangee = max([dims[n.id][1] for n in mf.noeuds.values()] or [80])
        self.pas_y = self.h_rangee + 110
        self.max_couche = max(couche.values(), default=1)

    def y_rangee(self, couche_l: int) -> float:
        """Bord haut de la rangée de la couche donnée."""
        return MARGE + (self.max_couche - couche_l) * self.pas_y


def _abscisses_decisions(dec_ids: List[str], requises: Dict[str, List[str]],
                         dims: Dict[str, Tuple[float, float]],
                         couche: Dict[str, int], pas_x: float) -> Dict[str, float]:
    """Centre x de chaque décision, couche par couche, au barycentre de ses
    requises ; la première couche garde l'ordre de création."""
    par_couche: Dict[int, List[str]] = {}
    for d in dec_ids:
        par_couche.setdefault(couche[d], []).append(d)

    x_dec: Dict[str, float] = {}
    for c in sorted(par_couche):
        rang = par_couche[c]
        if c == min(par_couche):
            ordre = rang
        else:
            def bary(d):
                bas = [x_dec[r] for r in requises[d] if r in x_dec]
                return sum(bas) / len(bas) if bas else 1e9
            ordre = sorted(rang, key=lambda d: (bary(d), d))
        occupes: List[float] = []
        for d in ordre:
            bas = [x_dec[r] for r in requises[d] if r in x_dec]
            cx = (sum(bas) / len(bas)) if bas \
                else (MARGE + pas_x / 2 + len(occupes) * pas_x)
            cx = max(cx, MARGE + dims[d][0] / 2)
            while any(abs(cx - o) < pas_x for o in occupes):
                cx += pas_x
            occupes.append(cx)
            x_dec[d] = cx
    return x_dec


class _PoseurDeSources:
    """Placement des sources, convention du DRD de référence (fimex-drd) :
    BKM à gauche de sa décision, source de connaissance issue d'une
    ressource (P5) à droite, données d'entrée et sources issues
    d'annotations (P6) sur la rangée du bas au barycentre de leurs
    cibles. Si un flanc est occupé, repli sur le bas."""

    def __init__(self, mf: Mf, pos: Dict[str, Rect],
                 dims: Dict[str, Tuple[float, float]],
                 couche: Dict[str, int], grille: _Grille):
        self.mf = mf
        self.pos = pos                     # complété en place
        self.dims = dims
        self.couche = couche
        self.grille = grille
        self.cibles: Dict[str, List[str]] = {}
        for u, v in mf.arcs:
            self.cibles.setdefault(u, []).append(v)
        self.y_bas = grille.y_rangee(0)
        self.poses_bas: List[Tuple[float, float]] = []   # intervalles occupés
        self.cote_de: Dict[str, str] = {}   # élément posé en flanc -> sa décision

    def placer(self) -> Dict[str, str]:
        """Pose toutes les sources et retourne, pour celles posées en
        flanc, la décision à laquelle elles sont adossées."""
        restants = []
        for n in self.mf.bkms:
            if not self.poser_en_flanc(n, gauche=True):
                restants.append(n)
        for n in self.mf.sources:
            if not (n.pattern == "P5" and self.poser_en_flanc(n, gauche=False)):
                restants.append(n)
        restants.extend(self.mf.inputs)
        for n in sorted(restants, key=lambda n: (self.bary_cibles(n.id), n.id)):
            w, h = self.dims[n.id]
            cx = self.caser(self.bary_cibles(n.id)
                            if self.bary_cibles(n.id) < 1e8 else MARGE, w)
            self.pos[n.id] = (cx - w / 2,
                              self.y_bas + (self.grille.h_rangee - h) / 2, w, h)
        return self.cote_de

    def caser(self, cx_voulu: float, w: float) -> float:
        """Abscisse libre sur la rangée du bas. On travaille en entiers :
        avec un barycentre fractionnaire, le test de chevauchement peut
        rester vrai à un ULP près sans que cx ne bouge, et la boucle ne
        progresse plus."""
        cx = round(max(MARGE + w / 2, cx_voulu))
        bouge, garde = True, 0
        while bouge:
            garde += 1
            if garde > 10000:
                raise RuntimeError(
                    "caser bloqué : cx=%r w=%r poses_bas=%r"
                    % (cx, w, self.poses_bas))
            bouge = False
            for a, b in self.poses_bas:
                if cx - w / 2 < b + 46 and cx + w / 2 > a - 46:
                    # ceil et non round : round(x.5) arrondit au pair, parfois
                    # vers le bas, et la progression ne serait plus stricte
                    cx = math.ceil(b + 46 + w / 2)
                    bouge = True
        self.poses_bas.append((cx - w / 2, cx + w / 2))
        return cx

    def libre(self, x: float, y: float, w: float, h: float) -> bool:
        for px, py, pw, ph in self.pos.values():
            if x < px + pw + 24 and x + w > px - 24 and \
               y < py + ph + 20 and y + h > py - 20:
                return False
        return True

    def poser_en_flanc(self, n, gauche: bool) -> bool:
        """S'adosser à la cible de la couche la plus basse ; les autres
        arcs monteront par les couloirs génériques."""
        cs = [c for c in self.cibles.get(n.id, []) if c in self.pos]
        if not cs:
            return False
        cible = min(cs, key=lambda c: (self.couche.get(c, 0), self.pos[c][0]))
        w, h = self.dims[n.id]
        tx, ty, tw, th = self.pos[cible]
        x = (tx - 60 - w) if gauche else (tx + tw + 60)
        y = ty + (th - h) / 2
        if not self.libre(x, y, w, h):
            return False
        self.pos[n.id] = (x, y, w, h)
        self.cote_de[n.id] = cible
        return True

    def bary_cibles(self, nid: str) -> float:
        cs = [self.pos[c][0] + self.pos[c][2] / 2
              for c in self.cibles.get(nid, []) if c in self.pos]
        return sum(cs) / len(cs) if cs else 1e9


# ----------------------------------------------------------------------
# routage des exigences
# ----------------------------------------------------------------------
def _ancrage(source: Rect, cible: Rect) -> Tuple[Point, Point]:
    """Bord de départ tourné vers la cible, bord d'arrivée tourné vers la
    source (flèche droite)."""
    sx, sy, sw, sh = source
    tx, ty, tw, th = cible
    csx, csy = sx + sw / 2, sy + sh / 2
    ctx, cty = tx + tw / 2, ty + th / 2
    if abs(ctx - csx) * sh > abs(cty - csy) * sw:
        p1 = (sx + (sw if ctx > csx else 0), csy)
    else:
        p1 = (csx, sy + (sh if cty > csy else 0))
    if abs(ctx - csx) * th > abs(cty - csy) * tw:
        p2 = (tx + (tw if csx > ctx else 0), cty)
    else:
        p2 = (ctx, ty + (th if csy > cty else 0))
    return p1, p2


def _coupe(p1: Point, p2: Point, rect: Rect, marge: float = 8.0) -> bool:
    """Le segment p1-p2 traverse-t-il le rectangle (élargi) ?
    Découpage de Liang-Barsky."""
    x0, y0, w, h = rect
    xmin, ymin = x0 - marge, y0 - marge
    xmax, ymax = x0 + w + marge, y0 + h + marge
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p1[0] - xmin), (dx, xmax - p1[0]),
                 (-dy, p1[1] - ymin), (dy, ymax - p1[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 < t1


def _obstacles(pos: Dict[str, Rect], p1: Point, p2: Point, u: str, v: str) -> List[str]:
    """Les symboles, autres que les extrémités, que le segment traverse."""
    return [nid for nid, rect in pos.items()
            if nid not in (u, v) and _coupe(p1, p2, rect)]


def _router(mf: Mf, pos: Dict[str, Rect], couche: Dict[str, int],
            cote_de: Dict[str, str], grille: _Grille) -> Dict[Arc, List[Point]]:
    """Chaque exigence est une flèche droite de bord à bord (le style des
    DRD Camunda du dossier) ; si cette droite traverse un symbole, et
    seulement dans ce cas, l'arête est déroutée par un détour orthogonal
    qui contourne l'obstacle."""
    routes: Dict[Arc, List[Point]] = {}
    rangee_de: Dict[str, int] = {n.id: couche[n.id] for n in mf.decisions}
    for n in list(mf.inputs) + list(mf.sources) + list(mf.bkms):
        rangee_de[n.id] = couche[cote_de[n.id]] if n.id in cote_de else 0

    # répartition des points d'ancrage quand plusieurs arêtes déroutées
    # arrivent par le bas d'une même cible
    compte_bas: Dict[str, int] = {}
    # flèches droites mises de côté : leurs pointes sont écartées ensuite
    directes: List[Tuple[Arc, Point, Point]] = []

    for u, v in mf.arcs:
        p1, p2 = _ancrage(pos[u], pos[v])
        # arête de flanc (BKM ou source adossée) : horizontale directe ;
        # sinon flèche droite si elle ne traverse rien
        if cote_de.get(u) == v or not _obstacles(pos, p1, p2, u, v):
            directes.append(((u, v), p1, p2))
            continue
        k = compte_bas.get(v, 0)
        compte_bas[v] = k + 1
        routes[(u, v)] = _detour_orthogonal(pos, u, v, k, rangee_de, grille)

    _ecarter_pointes(directes, pos)
    for (u, v), p1, p2 in directes:
        routes[(u, v)] = [p1, p2]
    return routes


def _detour_orthogonal(pos: Dict[str, Rect], u: str, v: str, k: int,
                       rangee_de: Dict[str, int], grille: _Grille) -> List[Point]:
    """Montée depuis le haut de la source, contournement des rangées
    barrées, entrée par le bas de la cible sur un point d'ancrage décalé
    (k-ième arête déroutée arrivant sur cette cible)."""
    ux, uy, uw, _ = pos[u]
    vx, vy, vw, vh = pos[v]
    d_x = vx + 24 + (k * 28) % max(vw - 48, 28)
    points: List[Point] = [(ux + uw / 2, uy)]
    x = ux + uw / 2
    for r in range(rangee_de[u] + 1, rangee_de[v]):
        canal = grille.y_rangee(r) + grille.h_rangee + 24 + (k % 4) * 12
        gene = [nid for nid, rect in pos.items()
                if rangee_de.get(nid) == r
                and rect[0] - 16 < x < rect[0] + rect[2] + 16]
        if gene:
            px, _, pw, _ = pos[gene[0]]
            nx = px - 24 if abs(x - px) <= abs(x - px - pw) else px + pw + 24
            points.append((x, canal))
            points.append((nx, canal))
            x = nx
    canal_v = vy + vh + 22 + (k % 4) * 12
    if abs(x - d_x) > 1:
        points.append((x, canal_v))
        points.append((d_x, canal_v))
    points.append((d_x, vy + vh))
    nets = [points[0]]
    for p in points[1:]:
        if p != nets[-1]:
            nets.append(p)
    return nets


def _ecarter_pointes(directes: List[Tuple[Arc, Point, Point]],
                     pos: Dict[str, Rect]) -> None:
    """Plusieurs flèches droites arrivant par le même bord d'un symbole
    convergeraient toutes vers le milieu de ce bord. Chaque groupe est
    réparti autour du centre du bord avec un petit pas, dans l'ordre
    latéral des sources (aucun croisement induit) ; l'écart est annulé si,
    à lui seul, il faisait traverser un symbole. Les pointes restent quasi
    jointives, juste discernables."""
    groupes: Dict[Tuple[str, str], List[int]] = {}
    for i, ((u, v), p1, p2) in enumerate(directes):
        tx, ty, tw, th = pos[v]
        if abs(p2[1] - ty) < 0.5:
            bord = "haut"
        elif abs(p2[1] - (ty + th)) < 0.5:
            bord = "bas"
        elif abs(p2[0] - tx) < 0.5:
            bord = "gauche"
        else:
            bord = "droite"
        groupes.setdefault((v, bord), []).append(i)

    for (v, bord), indices in groupes.items():
        if len(indices) < 2:
            continue
        tx, ty, tw, th = pos[v]
        horizontal = bord in ("haut", "bas")      # répartition selon x
        longueur = max((tw if horizontal else th) - 24, 0)
        pas = min(ECART, longueur / max(len(indices) - 1, 1))
        indices.sort(key=lambda i: directes[i][1][0 if horizontal else 1])
        for rang, i in enumerate(indices):
            (u, _), p1, p2 = directes[i]
            d = (rang - (len(indices) - 1) / 2.0) * pas
            if horizontal:
                p2b = (min(max(p2[0] + d, tx + 12), tx + tw - 12), p2[1])
            else:
                p2b = (p2[0], min(max(p2[1] + d, ty + 12), ty + th - 12))
            if not _obstacles(pos, p1, p2b, u, v):
                directes[i] = ((u, v), p1, p2b)


# ----------------------------------------------------------------------
# écriture du document DMN
# ----------------------------------------------------------------------
def serialiser_dmn(mf: Mf, nom_definitions: str = "", namespace: str = "") -> str:
    """Mf -> document DMN 1.3 complet (MODEL + DMNDI), prêt pour Camunda."""
    pos, routes = positionner(mf)
    nom = texte_xml(nom_definitions or (mf.nom or "Modèle de décision"))
    ns = texte_xml(namespace or "http://bpmn2dmn/genere")
    noms = {n.id: texte_xml(n.nom) for n in mf.noeuds.values()}
    exigences = _Exigences(mf)

    L = _entete_definitions(nom, ns)
    L.extend(_elements_decisions(mf, noms, exigences))
    L.extend(_elements_bkm(mf, noms, exigences))
    L.extend('  <inputData id="%s" name=%s/>' % (n.id, quoteattr(noms[n.id]))
             for n in mf.inputs)
    L.extend(_elements_sources(mf, noms, exigences))
    L.extend(_bloc_dmndi(nom, pos, routes, exigences.arcs_ids))
    L.append('</definitions>')
    return "\n".join(L) + "\n"


def _entete_definitions(nom: str, ns: str) -> List[str]:
    """Prologue XML et balise ouvrante <definitions> avec ses espaces de noms."""
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<definitions xmlns="%s"' % NS_MODEL,
        '             xmlns:dmndi="%s"' % NS_DMNDI,
        '             xmlns:dc="%s"' % NS_DC,
        '             xmlns:di="%s"' % NS_DI,
        '             id="Definitions_%s"' % _sur(nom)[:40],
        '             name=%s' % quoteattr(nom),
        '             namespace=%s' % quoteattr(ns),
        '             exporter="bpmn2dmn" exporterVersion="1.0">',
    ]


class _Exigences:
    """Genre (IR, KR, AR) et identifiant de chaque exigence, numérotée dans
    l'ordre d'écriture ; `arcs_ids` conserve cet ordre pour le DMNDI."""
    ORDRE_GENRES = {"IR": 0, "KR": 1, "AR": 2}

    def __init__(self, mf: Mf):
        self.entrants: Dict[str, List[Arc]] = {}
        for u, v in mf.arcs:
            self.entrants.setdefault(v, []).append((u, v))
        self.ir, self.kr = set(mf.IR), set(mf.KR)
        self.compteurs = {"ir": 0, "kr": 0, "ar": 0}
        self.arcs_ids: Dict[Arc, Tuple[str, str]] = {}

    def genre(self, arc: Arc) -> str:
        return "IR" if arc in self.ir else ("KR" if arc in self.kr else "AR")

    def entrants_tries(self, nid: str) -> List[Arc]:
        """Le XSD OMG (tDecision, tBusinessKnowledgeModel) impose une
        séquence informationRequirement*, knowledgeRequirement*,
        authorityRequirement* : les exigences sont regroupées par genre."""
        return sorted(self.entrants.get(nid, []),
                      key=lambda a: self.ORDRE_GENRES[self.genre(a)])

    def numeroter(self, arc: Arc) -> Tuple[str, str]:
        """Attribue à l'exigence son identifiant (ir1, kr1, ar1...) et son genre."""
        genre = self.genre(arc)
        cle = genre.lower()
        self.compteurs[cle] += 1
        aid = "%s%d" % (cle, self.compteurs[cle])
        self.arcs_ids[arc] = (aid, genre)
        return aid, genre


def _elements_decisions(mf: Mf, noms: Dict[str, str],
                        exigences: _Exigences) -> List[str]:
    """Les <decision> avec leurs exigences d'information, de connaissance
    et d'autorité."""
    L: List[str] = []
    for n in mf.decisions:
        L.append('  <decision id="%s" name=%s>' % (n.id, quoteattr(noms[n.id])))
        for arc in exigences.entrants_tries(n.id):
            u = arc[0]
            aid, genre = exigences.numeroter(arc)
            tu = mf.noeuds[u].type
            if genre == "IR":
                ref = "requiredDecision" if tu == DECISION else "requiredInput"
                L.append('    <informationRequirement id="%s">'
                         '<%s href="#%s"/></informationRequirement>'
                         % (aid, ref, u))
            elif genre == "KR":
                L.append('    <knowledgeRequirement id="%s">'
                         '<requiredKnowledge href="#%s"/>'
                         '</knowledgeRequirement>' % (aid, u))
            else:
                L.append('    <authorityRequirement id="%s">'
                         '<requiredAuthority href="#%s"/>'
                         '</authorityRequirement>' % (aid, u))
        if n.id in mf.logique:
            L.extend(_table_de_decision(mf, n.id, noms))
        L.append('  </decision>')
    return L


def _variable(nom: str) -> str:
    """Un nom de variable FEEL lisible tiré d'un libellé : « Dossier
    constitué » -> dossierConstitue."""
    if re.match(r"^[A-Za-z_][\w.]*$", nom or ""):
        return nom                                   # déjà un identifiant
    mots = re.findall(r"[a-z0-9]+", normaliser(nom))
    if not mots:
        return "valeur"
    tete = mots[0].lower()
    return tete + "".join(m[:1].upper() + m[1:].lower() for m in mots[1:])


def _table_de_decision(mf: Mf, did: str, noms: Dict[str, str]) -> List[str]:
    """Extension « logique » : la table de décision squelette d'une
    décision. Entrées : les données d'entrée et décisions dont elle dépend ;
    sortie : le verdict, dont les valeurs admises sont les branches de la
    passerelle qui suit l'activité ; une règle par branche, ses conditions
    laissées à compléter (« - »). La politique UNIQUE est celle attendue
    d'une table achevée : les règles squelettes se recouvrent tant que les
    conditions ne sont pas remplies."""
    logique = mf.logique[did]
    entrees = [u for u, v in mf.arcs if v == did
               and mf.noeuds[u].type in (INPUT_DATA, DECISION)]
    branches = logique["branches"]
    L = ['    <decisionTable id="%s_table" hitPolicy="UNIQUE">' % did]
    for k, u in enumerate(entrees, start=1):
        L.append('      <input id="%s_entree%d" label=%s>'
                 '<inputExpression id="%s_entree%d_expr" typeRef="string">'
                 '<text>%s</text></inputExpression></input>'
                 % (did, k, quoteattr(noms[u]), did, k,
                    escape(_variable(mf.noeuds[u].nom))))
    valeurs = ",".join('"%s"' % b["sortie"].replace('"', "'") for b in branches)
    L.append('      <output id="%s_sortie" label=%s name=%s typeRef="string">'
             '<outputValues id="%s_sortie_valeurs"><text>%s</text></outputValues>'
             '</output>'
             % (did, quoteattr(logique["passerelle"]),
                quoteattr(_variable(mf.noeuds[did].nom)), did, escape(valeurs)))
    for r, b in enumerate(branches, start=1):
        cellules = "".join('<inputEntry id="%s_regle%d_e%d"><text>-</text></inputEntry>'
                           % (did, r, k) for k in range(1, len(entrees) + 1))
        description = ('<description>%s</description>' % escape(b["condition"])
                       if b["condition"] else "")
        L.append('      <rule id="%s_regle%d">%s%s<outputEntry id="%s_regle%d_s">'
                 '<text>"%s"</text></outputEntry></rule>'
                 % (did, r, description, cellules, did, r,
                    escape(b["sortie"].replace('"', "'"))))
    L.append('    </decisionTable>')
    return L


def _elements_bkm(mf: Mf, noms: Dict[str, str],
                  exigences: _Exigences) -> List[str]:
    """Les <businessKnowledgeModel> avec leurs exigences de connaissance
    et d'autorité."""
    L: List[str] = []
    for n in mf.bkms:
        L.append('  <businessKnowledgeModel id="%s" name=%s>'
                 % (n.id, quoteattr(noms[n.id])))
        for arc in exigences.entrants_tries(n.id):
            aid, genre = exigences.numeroter(arc)
            balise = ("knowledgeRequirement", "requiredKnowledge") \
                if genre == "KR" else ("authorityRequirement",
                                       "requiredAuthority")
            L.append('    <%s id="%s"><%s href="#%s"/></%s>'
                     % (balise[0], aid, balise[1], arc[0], balise[0]))
        L.append('  </businessKnowledgeModel>')
    return L


def _elements_sources(mf: Mf, noms: Dict[str, str],
                      exigences: _Exigences) -> List[str]:
    """Les <knowledgeSource>, avec leurs exigences d'autorité s'il y en a."""
    L: List[str] = []
    for n in mf.sources:
        entr = exigences.entrants.get(n.id, [])
        if entr:
            L.append('  <knowledgeSource id="%s" name=%s>'
                     % (n.id, quoteattr(noms[n.id])))
            for arc in entr:
                aid, _ = exigences.numeroter(arc)
                L.append('    <authorityRequirement id="%s">'
                         '<requiredAuthority href="#%s"/>'
                         '</authorityRequirement>' % (aid, arc[0]))
            L.append('  </knowledgeSource>')
        else:
            L.append('  <knowledgeSource id="%s" name=%s/>'
                     % (n.id, quoteattr(noms[n.id])))
    return L


def _bloc_dmndi(nom: str, pos: Dict[str, Rect], routes: Dict[Arc, List[Point]],
                arcs_ids: Dict[Arc, Tuple[str, str]]) -> List[str]:
    """Le bloc DMNDI : une forme par nœud, une arête par exigence."""
    L = ['  <dmndi:DMNDI>',
         '    <dmndi:DMNDiagram id="DRD_%s">' % _sur(nom)[:36]]
    for nid, (x, y, w, h) in pos.items():
        L.append('      <dmndi:DMNShape id="s_%s" dmnElementRef="%s">'
                 % (nid, nid))
        L.append('        <dc:Bounds x="%d" y="%d" width="%d" height="%d"/>'
                 % (round(x), round(y), round(w), round(h)))
        L.append('      </dmndi:DMNShape>')
    for arc, (aid, _) in arcs_ids.items():
        u, v = arc
        if u not in pos or v not in pos:
            continue
        chemin = routes.get(arc) or [
            (pos[u][0] + pos[u][2] / 2, pos[u][1]),
            (pos[v][0] + pos[v][2] / 2, pos[v][1] + pos[v][3])]
        L.append('      <dmndi:DMNEdge id="e_%s" dmnElementRef="%s">' % (aid, aid))
        L.append('        ' + "".join('<di:waypoint x="%d" y="%d"/>'
                                      % (round(a), round(b))
                                      for a, b in chemin))
        L.append('      </dmndi:DMNEdge>')
    L.append('    </dmndi:DMNDiagram>')
    L.append('  </dmndi:DMNDI>')
    return L
