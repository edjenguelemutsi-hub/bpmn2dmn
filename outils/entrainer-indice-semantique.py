# -*- coding: utf-8 -*-
"""
Apprend le classifieur de l'indice sémantique de kappa et écrit
`bpmn2dmn/modeles/classifieur-semantique.json`.

    python -X utf8 outils/entrainer-indice-semantique.py [--C 1.0] [--plis 5]

Lecture des exemples dans `bpmn2dmn/modeles/exemples-indice-semantique.txt`,
plongement par le modèle MiniLM multilingue (ONNX), régression logistique,
validation croisée stratifiée pour mesurer et fixer le seuil. Le fichier
produit suffit ensuite à l'outil : l'apprentissage n'est jamais rejoué à
l'exécution, l'indice est déterministe.
"""
import argparse
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn import semantique  # noqa: E402


def principal() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--C", type=float, default=1.0)
    p.add_argument("--plis", type=int, default=5)
    p.add_argument("--sortie", default=semantique.CHEMIN_CLASSIFIEUR)
    args = p.parse_args()
    if not semantique.modele_present():
        print(semantique.motif_indisponible())
        return 1
    exemples = semantique.lire_exemples()
    print("%d exemples (%d décisions, %d non-décisions)"
          % (len(exemples), sum(1 for c, _ in exemples if c == "D"),
             sum(1 for c, _ in exemples if c == "N")))
    parametres = semantique.entrainer(exemples, C=args.C, plis=args.plis)
    cv = parametres["validation_croisee"]
    print("validation croisée (%d plis) : seuil %.2f, précision %.3f, rappel %.3f, "
          "exactitude %.3f (vp %d, fp %d, fn %d, vn %d)"
          % (cv["plis"], cv["seuil"], cv["precision"], cv["rappel"], cv["exactitude"],
             cv["vp"], cv["fp"], cv["fn"], cv["vn"]))
    for e in cv["erreurs"]:
        print("   erreur hors pli : %s  %-50s score %.3f" % (e["classe"], e["texte"][:50], e["score"]))
    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(parametres, f, ensure_ascii=False, indent=1)
    print("classifieur écrit :", args.sortie)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
