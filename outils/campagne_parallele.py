# -*- coding: utf-8 -*-
"""
Campagne de vérification massive répartie sur plusieurs processus.

Chaque graine subit les mêmes six contrôles que `cli.py campagne`
(parseur, transformation + invariants, oracle, sérialisation relue,
aller-retour T(T_inv(M)) = M, déterminisme). Les graines sont découpées
en lots distribués aux processus ; la première divergence arrête tout
et affiche la graine fautive, rejouable avec `generer(graine)`.

    python outils/campagne_parallele.py 10000000 --graine 1 --processus 10 --journal essais/campagne.log
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn.generateur import generer        
from bpmn2dmn.inverse import inverser          
from bpmn2dmn.parseur import parser_bpmn       
from bpmn2dmn.qualification import Arbitrages  
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.validation import (comparer_a_oracle, equivalents, 
                                 verifier_dmn_serialise,
                                 verifier_invariants)


def verifier_graine(seed: int):
    """Retourne (None, stats) si tout est conforme, sinon (message, None)."""
    bpmn, attendu = generer(seed)
    mi = parser_bpmn(bpmn, est_texte=True)
    mf = transformer(mi)
    inv = verifier_invariants(mf)
    if inv:
        return "graine %d - invariants : %s" % (seed, inv), None
    ecarts = comparer_a_oracle(mf, attendu)
    if ecarts:
        return "graine %d - oracle : %s" % (seed, ecarts), None
    dmn = serialiser_dmn(mf)
    problemes = verifier_dmn_serialise(dmn, mf)
    if problemes:
        return "graine %d - sérialisation : %s" % (seed, problemes), None
    if mf.decisions:
        bpmn2, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts2 = equivalents(mf, mf2)
        if not ok:
            return "graine %d - aller-retour : %s" % (seed, ecarts2), None
    mf_bis = transformer(parser_bpmn(bpmn, est_texte=True))
    ok, _ = equivalents(mf, mf_bis)
    if not ok or serialiser_dmn(mf_bis) != dmn:
        return "graine %d - non déterministe" % seed, None
    return None, (len(mf.decisions), len(mf.arcs), len(mf.a_confirmer))


def verifier_lot(lot):
    debut, fin = lot
    decisions = arcs = confirmer = 0
    for seed in range(debut, fin):
        erreur, stats = verifier_graine(seed)
        if erreur:
            return erreur, (debut, fin), (decisions, arcs, confirmer)
        decisions += stats[0]
        arcs += stats[1]
        confirmer += stats[2]
    return None, (debut, fin), (decisions, arcs, confirmer)


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description="campagne massive multiprocessus")
    p.add_argument("n", type=int)
    p.add_argument("--graine", type=int, default=1)
    p.add_argument("--processus", type=int, default=max(1, os.cpu_count() - 2))
    p.add_argument("--lot", type=int, default=2000)
    p.add_argument("--journal")
    p.add_argument("--sans-registre", action="store_true",
                   help="ne pas consigner la campagne dans experimentations/campagnes.csv")
    args = p.parse_args(argv)

    sortie = open(args.journal, "a", encoding="utf-8", buffering=1) if args.journal else None

    def ecrire(texte):
        print(texte, flush=True)
        if sortie:
            sortie.write(texte + "\n")

    lots = [(d, min(d + args.lot, args.graine + args.n))
            for d in range(args.graine, args.graine + args.n, args.lot)]
    ecrire("Campagne : %d modèles (graines %d à %d), %d processus, lots de %d"
           % (args.n, args.graine, args.graine + args.n - 1, args.processus, args.lot))
    t0 = time.time()
    total = {"modeles": 0, "decisions": 0, "arcs": 0, "confirmer": 0}
    prochain_rapport = 0
    code = 0
    with mp.Pool(args.processus) as bassin:
        for erreur, (d, f), (nd, na, nc) in bassin.imap_unordered(verifier_lot, lots):
            if erreur:
                ecrire("ECHEC " + erreur)
                code = 1
                bassin.terminate()
                break
            total["modeles"] += f - d
            total["decisions"] += nd
            total["arcs"] += na
            total["confirmer"] += nc
            if total["modeles"] >= prochain_rapport:
                ecoule = time.time() - t0
                ecrire("  %d / %d modèles (%.0f modèles/s, %.0f s écoulées)"
                       % (total["modeles"], args.n, total["modeles"] / max(ecoule, 1e-9), ecoule))
                prochain_rapport += max(args.lot, args.n // 100)
    ecoule = time.time() - t0
    if code == 0:
        ecrire("Campagne terminée sans divergence : %d modèles, %d décisions, "
               "%d exigences, %d points soumis à l'expert, en %.0f s (%.0f modèles/s)."
               % (total["modeles"], total["decisions"], total["arcs"],
                  total["confirmer"], ecoule, total["modeles"] / max(ecoule, 1e-9)))
    else:
        ecrire("Campagne arrêtée après %d modèles." % total["modeles"])
    if not args.sans_registre:
        # une ligne par campagne dans le registre des expérimentations
        from bpmn2dmn.registre import Registre, desactive
        if not desactive():
            registre = Registre()
            registre.journal_campagne("campagne parallèle", args.graine, args.n,
                                      total["modeles"], total["decisions"],
                                      total["arcs"], total["confirmer"], code,
                                      ecoule, args.processus)
            ecrire("Campagne consignée dans %s" % registre.chemin_campagnes)
    if sortie:
        sortie.close()
    return code


if __name__ == "__main__":
    sys.exit(principal())
