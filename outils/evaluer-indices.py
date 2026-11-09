# -*- coding: utf-8 -*-
"""
Évalue, sur les modèles du corpus qui ont une référence experte (.gold),
les variantes du prédicat de corroboration kappa :

  position            : passerelle exclusive ou inclusive à la suite
  lexique             : verbe du lexique fermé Λ dans le libellé
  semantique          : indice sémantique (modèle de langue léger)
  reference           : position ou lexique (l'outil tel que publié)
  position+semantique : le lexique remplacé par l'indice sémantique
  les trois           : position, lexique ou indice sémantique

Pour chaque variante : décisions retenues parmi les candidats DA
(tâches utilisateur, tâches de règle métier, sous-processus repliés),
précision et rappel contre la référence, par groupe de modèles et au
total ; puis le détail des erreurs. Aucun paramètre n'est réglé ici :
le classifieur et son seuil viennent de l'apprentissage sur les
exemples écrits à la main.

    python -X utf8 outils/evaluer-indices.py [--sortie rapport.md] [motifs .bpmn ...]
"""
import argparse
import glob
import os
import sys
from collections import OrderedDict

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn  # noqa: E402
from bpmn2dmn.qualification import indice_lexical, indice_position, normaliser  # noqa: E402
from bpmn2dmn.transformation import TYPES_DA  # noqa: E402
from bpmn2dmn import semantique  # noqa: E402

VARIANTES = OrderedDict([
    ("position", lambda p, l, s: p),
    ("lexique", lambda p, l, s: l),
    ("semantique", lambda p, l, s: s),
    ("reference (position ou lexique)", lambda p, l, s: p or l),
    ("position ou semantique", lambda p, l, s: p or s),
    ("position, lexique ou semantique", lambda p, l, s: p or l or s),
])


def lire_gold(chemin_bpmn):
    ref = os.path.splitext(chemin_bpmn)[0] + ".gold"
    if not os.path.exists(ref):
        return None
    with open(ref, encoding="utf-8") as f:
        return {normaliser(l) for l in f if l.strip() and not l.startswith("#")}


def principal() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("motifs", nargs="*",
                   default=["corpus/*.bpmn", "jeux-test-camunda/*.bpmn"])
    p.add_argument("--sortie", help="rapport Markdown")
    args = p.parse_args()
    if not semantique.disponible():
        print(semantique.motif_indisponible())
        return 1
    ind = semantique.instance()

    chemins = []
    for m in args.motifs:
        chemins.extend(sorted(glob.glob(os.path.join(RACINE, m))))
    lignes = []            # (groupe, modele, aid, libelle, gold, p, l, s, score)
    for c in chemins:
        gold = lire_gold(c)
        if gold is None:
            continue
        mi = parser_bpmn(c)
        groupe = os.path.basename(os.path.dirname(c))
        candidats = [(aid, a) for aid, a in mi.activites.items()
                     if a.type in TYPES_DA or a.type == "subProcess"]
        scores = ind.scores([a.nom for _, a in candidats])
        for (aid, a), sc in zip(candidats, scores):
            lignes.append((groupe, os.path.basename(c), aid, a.nom,
                           normaliser(a.nom) in gold,
                           indice_position(mi, aid), indice_lexical(a),
                           sc >= ind.seuil, sc))

    groupes = sorted({l[0] for l in lignes})
    L = ["# Variantes du prédicat kappa sur le corpus de référence", "",
         "Candidats DA : %d ; décisions de la référence : %d ; modèles : %d."
         % (len(lignes), sum(1 for l in lignes if l[4]), len({l[1] for l in lignes})),
         "Classifieur sémantique : seuil %.2f, %d exemples d'apprentissage, "
         "validation croisée précision %.3f / rappel %.3f."
         % (ind.seuil, ind.parametres["apprentissage"]["exemples"],
            ind.parametres["validation_croisee"]["precision"],
            ind.parametres["validation_croisee"]["rappel"]), "",
         "| Variante | " + " | ".join("%s (P / R)" % g for g in groupes)
         + " | Total (P / R) | retenues | à tort | manquées |",
         "|---|" + "---|" * (len(groupes) + 4)]
    for nom, f in VARIANTES.items():
        cellules = []
        for g in groupes + [None]:
            sel = [l for l in lignes if g is None or l[0] == g]
            vp = sum(1 for l in sel if f(l[5], l[6], l[7]) and l[4])
            fp = sum(1 for l in sel if f(l[5], l[6], l[7]) and not l[4])
            fn = sum(1 for l in sel if not f(l[5], l[6], l[7]) and l[4])
            prec = 100.0 * vp / (vp + fp) if vp + fp else 0.0
            rap = 100.0 * vp / (vp + fn) if vp + fn else 0.0
            cellules.append("%.1f / %.1f" % (prec, rap))
            if g is None:
                total = (vp + fp, fp, fn)
        L.append("| %s | %s | %d | %d | %d |" % (nom, " | ".join(cellules), *total))
    L += ["", "## Erreurs de l'indice sémantique seul", "",
          "| Modèle | Libellé | Référence | Score |", "|---|---|---|---|"]
    for l in lignes:
        if l[7] != l[4]:
            L.append("| %s | %s | %s | %.3f |" % (l[1], l[3], "décision" if l[4] else "non",
                                                  l[8]))
    L += ["", "## Tous les candidats", "",
          "| Modèle | Libellé | Référence | position | lexique | sémantique (score) |",
          "|---|---|---|---|---|---|"]
    for l in lignes:
        L.append("| %s | %s | %s | %s | %s | %s (%.3f) |"
                 % (l[1], l[3], "oui" if l[4] else "non", "oui" if l[5] else "non",
                    "oui" if l[6] else "non", "oui" if l[7] else "non", l[8]))
    texte = "\n".join(L) + "\n"
    print(texte if not args.sortie else "\n".join(L[:12]))
    if args.sortie:
        with open(args.sortie, "w", encoding="utf-8") as f:
            f.write(texte)
        print("rapport écrit :", args.sortie)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
