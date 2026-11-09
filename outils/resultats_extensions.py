# -*- coding: utf-8 -*-
"""
Effet des extensions sur le catalogue de patterns : chaque diagramme de
`catalogue-patterns/` est transformé sans extension puis avec toutes les
extensions (les variables de condition proposées par P7 sont acceptées par
arbitrage pour que l'effet apparaisse), et le tableau comparatif est écrit
dans `catalogue-patterns/resultats-extensions/LISEZ-MOI.md`, les sorties
(`.drd.dmn`, `.rapport.json`) dans le même dossier. Rien n'est consigné dans
le registre des expérimentations.

    python -X utf8 outils/resultats_extensions.py
"""
import glob
import io
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn.extensions import TOUTES  # noqa: E402
from bpmn2dmn.parseur import parser_bpmn  # noqa: E402
from bpmn2dmn.qualification import Arbitrages  # noqa: E402
from bpmn2dmn.serialiseur import serialiser_dmn  # noqa: E402
from bpmn2dmn.transformation import transformer  # noqa: E402
from bpmn2dmn import semantique  # noqa: E402

sys.path.insert(0, RACINE)
from cli import rapport_json  # noqa: E402

DOSSIER = os.path.join(RACINE, "catalogue-patterns", "resultats-extensions")


def resume(mf):
    r = mf.resume()
    return "%d/%d/%d/%d/%d/%d" % (r["decisions"], r["inputs"], r["sources"], r["bkm"],
                                  len(mf.arcs), len(mf.a_confirmer))


def principal() -> int:
    os.makedirs(DOSSIER, exist_ok=True)
    extensions = set(TOUTES)
    sans_semantique = not semantique.disponible()
    if sans_semantique:
        extensions.discard("indice-semantique")
    L = ["# Effet des extensions sur le catalogue de patterns", "",
         "Chaque diagramme est transformé avec **toutes** les extensions actives%s ; les "
         "variables de condition proposées (P7) sont acceptées par un arbitrage pour que "
         "l'effet apparaisse dans le DRD. Colonnes : référence (algorithme sans extension) "
         "puis avec extensions, D / I / KS / BKM / exigences / points soumis à l'expert ; "
         "puis les tables de décision produites (règles écrites en FEEL sur le total, "
         "tables exécutables). Sorties dans ce dossier (`.drd.dmn`, `.rapport.json`). "
         "Regénération : `python -X utf8 outils/resultats_extensions.py`."
         % (" (sauf l'indice sémantique, modèle de langue absent)" if sans_semantique else ""),
         "",
         "| Id | Référence D/I/KS/BKM/E/expert | Avec extensions | Tables (règles FEEL / total, exécutables) | Changement |",
         "|---|---|---|---|---|"]
    totaux = {"tables": 0, "regles": 0, "feel": 0, "exec": 0, "gagnent_decision": 0,
              "noms": 0, "proposes_semantique": 0}
    for chemin in sorted(glob.glob(os.path.join(RACINE, "catalogue-patterns", "*.bpmn"))):
        ident = os.path.basename(chemin)[:3]
        mi = parser_bpmn(chemin)
        ref = transformer(mi)
        pre = transformer(mi, extensions=extensions)
        arb = Arbitrages.depuis_json({"annotations": {
            p.cle: "I" for p in pre.a_confirmer if p.categorie == "condition"}})
        mf = transformer(mi, arb, extensions)
        dmn = serialiser_dmn(mf)
        base = os.path.join(DOSSIER, os.path.basename(chemin)[:-5])
        with io.open(base + ".drd.dmn", "w", encoding="utf-8") as f:
            f.write(dmn)
        with io.open(base + ".rapport.json", "w", encoding="utf-8") as f:
            json.dump(rapport_json(mf), f, ensure_ascii=False, indent=2)
        r1, r2 = ref.resume(), mf.resume()
        changements = []
        for cle, nom in (("decisions", "décisions"), ("inputs", "données d'entrée"),
                         ("sources", "sources"), ("bkm", "BKM")):
            if r1[cle] != r2[cle]:
                changements.append("%s %d → %d" % (nom, r1[cle], r2[cle]))
        if len(ref.arcs) != len(mf.arcs):
            changements.append("exigences %d → %d" % (len(ref.arcs), len(mf.arcs)))
        if len(ref.a_confirmer) != len(mf.a_confirmer):
            changements.append("points expert %d → %d" % (len(ref.a_confirmer), len(mf.a_confirmer)))
        tables = list(mf.logique.values())
        regles = sum(len(t["regles"]) for t in tables)
        feel = sum(t["regles_lues"] for t in tables)
        execs = sum(1 for t in tables if t["executable"])
        if tables:
            changements.append("%d table(s), %d/%d règle(s) FEEL%s"
                               % (len(tables), feel, regles,
                                  ", exécutable(s) : %d" % execs if execs else ""))
        if mf.suggestions_noms:
            changements.append("%d nom(s) suggéré(s)" % len(mf.suggestions_noms))
        proposes = sum(1 for p in mf.a_confirmer if p.proposition == "décision (indice sémantique)")
        if proposes:
            changements.append("%d candidat(s) proposé(s) par l'indice sémantique" % proposes)
        totaux["tables"] += len(tables)
        totaux["regles"] += regles
        totaux["feel"] += feel
        totaux["exec"] += execs
        totaux["gagnent_decision"] += 1 if r2["decisions"] > r1["decisions"] else 0
        totaux["noms"] += len(mf.suggestions_noms)
        totaux["proposes_semantique"] += proposes
        L.append("| %s | %s | %s | %s | %s |" % (
            ident, resume(ref), resume(mf),
            ("%d / %d, %d" % (feel, regles, execs)) if tables else "-",
            "; ".join(changements) or "aucun"))
    L += ["",
          "Total : %d tables de décision, %d règles dont %d écrites en FEEL, %d tables "
          "exécutables ; %d patterns gagnent au moins une décision ; %d noms suggérés ; "
          "%d candidats proposés par le seul indice sémantique."
          % (totaux["tables"], totaux["regles"], totaux["feel"], totaux["exec"],
             totaux["gagnent_decision"], totaux["noms"], totaux["proposes_semantique"]), ""]
    with io.open(os.path.join(DOSSIER, "LISEZ-MOI.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[-3:]))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
