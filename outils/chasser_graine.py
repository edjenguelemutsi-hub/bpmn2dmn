# -*- coding: utf-8 -*-
"""Chasse à la graine bloquante : exécute la chaîne complète graine par
graine en chronométrant chacune, et nomme celle qui dépasse le seuil.
Usage : python -u outils/chasser_graine.py <debut> <fin>"""
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import inverser
from bpmn2dmn.generateur import generer
from bpmn2dmn.qualification import Arbitrages
from bpmn2dmn.validation import equivalents

debut, fin = int(sys.argv[1]), int(sys.argv[2])
verbeux = (fin - debut) <= 200
for graine in range(debut, fin + 1):
    if verbeux:
        print("essai %d" % graine, flush=True)
    t0 = time.time()
    bpmn, _ = generer(graine)
    mi = parser_bpmn(bpmn, est_texte=True)
    mf = transformer(mi)
    t1 = time.time()
    dmn = serialiser_dmn(mf)
    t2 = time.time()
    if mf.decisions:
        bpmn2, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True),
                          Arbitrages.depuis_json(arb))
        equivalents(mf, mf2)
    t3 = time.time()
    total = t3 - t0
    if total > 2.0:
        print("graine lente %d : total %.1fs (T %.1fs, sérial. %.1fs, "
              "inverse %.1fs)" % (graine, total, t1 - t0, t2 - t1, t3 - t2))
    if graine % 100 == 0:
        print("... %d ok" % graine)
print("balayage terminé %d..%d" % (debut, fin))
