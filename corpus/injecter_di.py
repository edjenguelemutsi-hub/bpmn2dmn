# -*- coding: utf-8 -*-
"""Injecte la mise en page BPMNDI dans les modèles du corpus qui n'en ont
pas. Chaque fichier est lu en entier avant d'être réécrit."""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from bpmn2dmn.miseenpage import ajouter_di

for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "*.bpmn"))):
    contenu = io.open(f, encoding="utf-8").read()
    if "BPMNDiagram" in contenu:
        print("déjà en page :", os.path.basename(f))
        continue
    nouveau = ajouter_di(contenu)
    io.open(f, "w", encoding="utf-8").write(nouveau)
    print("mise en page :", os.path.basename(f))
