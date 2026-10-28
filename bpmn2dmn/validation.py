# -*- coding: utf-8 -*-
"""
Validation : invariants formels, mesure contre une référence experte,
comparaison à l'oracle du générateur, équivalence d'aller-retour.

Les invariants vérifiés sur tout Mf produit sont les propriétés démontrées
dans le cadre formel ; une violation est un défaut de l'implémentation,
non une affaire d'interprétation :

  I1  typage total : chaque sommet a un type de Tf ;
  I2  partition exacte : IR ∪ KR ∪ AR = E_f, deux à deux disjoints ;
  I3  délimitation AR : tout arc résiduel a des extrémités
      admissibles pour une exigence d'autorité ;
  I4  cibles des IR : jamais une donnée d'entrée ;
  I5  acyclicité de (V_f, E_f) ;
  I6  pas d'arc pendant (les deux extrémités existent) ;
  I7  pas de doublon d'arc ni de sommet ;
  I8  injectivité : delta et iota n'envoient jamais deux sources sur la
      même image.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .inverse import parser_dmn
from .metamodeles import (DECISION, INPUT_DATA, KNOWLEDGE_SOURCE, Mf,
                          TYPES_MF)
from .qualification import normaliser


def verifier_invariants(mf: Mf) -> List[str]:
    """Retourne la liste des violations (vide = conforme)."""
    v: List[str] = []
    # I1
    for n in mf.noeuds.values():
        if n.type not in TYPES_MF:
            v.append("I1 : type inconnu « %s » sur %s" % (n.type, n.id))
    # I6, I7
    if len(set(mf.arcs)) != len(mf.arcs):
        v.append("I7 : arcs dupliqués dans E_f")
    for u, w in mf.arcs:
        if u not in mf.noeuds or w not in mf.noeuds:
            v.append("I6 : arc pendant (%s, %s)" % (u, w))
    # I2
    if not mf.partition_exacte():
        v.append("I2 : {IR, KR, AR} n'est pas une partition de E_f")
    # I3 : délimitation de la forme directe
    for u, w in mf.AR:
        tu, tw = mf.noeuds[u].type, mf.noeuds[w].type
        ok = (tu == KNOWLEDGE_SOURCE and tw != INPUT_DATA) or \
             (tu in (INPUT_DATA, DECISION) and tw == KNOWLEDGE_SOURCE)
        if not ok:
            v.append("I3 : arc résiduel inadmissible %s(%s) -> %s(%s)"
                     % (u, tu, w, tw))
    # I4
    for u, w in mf.arcs:
        if mf.noeuds[w].type == INPUT_DATA:
            v.append("I4 : un arc arrive sur la donnée d'entrée %s" % w)
    # I5
    if not mf.acyclique():
        v.append("I5 : le graphe (V_f, E_f) contient un cycle")
    # I8
    for fonc, nom in ((mf.delta, "delta"), (mf.iota, "iota")):
        images = list(fonc.values())
        if len(set(images)) != len(images):
            v.append("I8 : %s n'est pas injective" % nom)
    return v


def mesurer_decisions(detectees: List[str], reference: List[str]) -> Dict:
    """Précision et rappel des décisions détectées contre la référence
    experte (.gold : noms des décisions attendues)."""
    d = {normaliser(x) for x in detectees}
    r = {normaliser(x) for x in reference}
    vp, fp, fn = d & r, d - r, r - d
    return {"attendues": len(r), "detectees": len(d),
            "vraies": len(vp), "a_tort": sorted(fp), "manquees": sorted(fn),
            "precision": len(vp) / len(d) if d else (1.0 if not r else 0.0),
            "rappel": len(vp) / len(r) if r else 1.0}


def comparer_a_oracle(mf: Mf, attendu) -> List[str]:
    """Compare le Mf produit au ModeleAttendu du générateur.
    Retourne les divergences (vide = accord exact)."""
    ecarts: List[str] = []

    def cmp_ensemble(nom, produits, attendus):
        p = sorted({normaliser(x) for x in produits})
        a = sorted({normaliser(x) for x in attendus})
        if p != a:
            manque = [x for x in a if x not in p]
            trop = [x for x in p if x not in a]
            if manque:
                ecarts.append("%s manquants : %s" % (nom, manque))
            if trop:
                ecarts.append("%s en trop : %s" % (nom, trop))

    cmp_ensemble("décisions", [n.nom for n in mf.decisions],
                 attendu.decisions)
    cmp_ensemble("données d'entrée", [n.nom for n in mf.inputs],
                 attendu.inputs)
    cmp_ensemble("sources", [n.nom for n in mf.sources], attendu.sources)
    cmp_ensemble("BKM", [n.nom for n in mf.bkms], attendu.bkms)

    # arcs par paires de noms
    def paires(arcs):
        return sorted((normaliser(mf.noeuds[u].nom),
                       normaliser(mf.noeuds[v].nom)) for u, v in arcs)

    for genre, produits, attendus in (
            ("IR", paires(mf.IR),
             sorted((normaliser(a), normaliser(b)) for a, b in attendu.ir)),
            ("KR", paires(mf.KR),
             sorted((normaliser(a), normaliser(b)) for a, b in attendu.kr)),
            ("AR", paires(mf.AR),
             sorted((normaliser(a), normaliser(b)) for a, b in attendu.ar))):
        if produits != attendus:
            ecarts.append("%s : produit %s ≠ attendu %s"
                          % (genre, produits, attendus))

    # candidats non corroborés : soumis à l'expert, jamais perdus
    soumis = {normaliser(p.objet) for p in mf.a_confirmer
              if p.categorie == "candidat"}
    attendus_c = {normaliser(x) for x in attendu.candidats_non_corrobores}
    perdus = attendus_c - soumis
    if perdus:
        ecarts.append("candidats non soumis à l'expert : %s" % sorted(perdus))
    return ecarts


def equivalents(mf1: Mf, mf2: Mf) -> Tuple[bool, List[str]]:
    """Deux DRD sont équivalents s'il existe une bijection entre leurs
    sommets préservant type et nom, sous laquelle les ensembles d'arcs
    coïncident. Comparaison par (type, nom normalisé)."""
    ecarts: List[str] = []

    def signature_noeuds(mf: Mf):
        return sorted((n.type, normaliser(n.nom)) for n in mf.noeuds.values())

    if signature_noeuds(mf1) != signature_noeuds(mf2):
        s1, s2 = signature_noeuds(mf1), signature_noeuds(mf2)
        ecarts.append("sommets : %s ≠ %s"
                      % ([x for x in s1 if x not in s2],
                         [x for x in s2 if x not in s1]))

    def signature_arcs(mf: Mf):
        return sorted(((mf.noeuds[u].type, normaliser(mf.noeuds[u].nom)),
                       (mf.noeuds[v].type, normaliser(mf.noeuds[v].nom)))
                      for u, v in mf.arcs)

    if signature_arcs(mf1) != signature_arcs(mf2):
        a1, a2 = signature_arcs(mf1), signature_arcs(mf2)
        ecarts.append("arcs : %s ≠ %s"
                      % ([x for x in a1 if x not in a2],
                         [x for x in a2 if x not in a1]))
    return (not ecarts, ecarts)


def verifier_dmn_serialise(texte_dmn: str, mf: Mf) -> List[str]:
    """Relit le DMN produit et vérifie qu'il restitue exactement Mf
    (sommets, typage, arcs) et que sa mise en page couvre tous les nœuds."""
    problemes: List[str] = []
    try:
        relu = parser_dmn(texte_dmn, est_texte=True, exiger_decision=False)
    except Exception as e:
        return ["DMN illisible après sérialisation : %s" % e]
    ok, ecarts = equivalents(mf, relu)
    if not ok:
        problemes.extend("aller-retour sérialiseur : " + e for e in ecarts)
    formes = set(re.findall(r'dmnElementRef="([^"]+)"', texte_dmn))
    for nid in mf.noeuds:
        if nid not in formes:
            problemes.append("DMNDI : nœud %s sans forme" % nid)
    return problemes
