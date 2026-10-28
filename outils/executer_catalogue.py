# -*- coding: utf-8 -*-
"""
Exécution du catalogue de patterns : chaque diagramme de
`catalogue-patterns/` est lu, transformé sans arbitrage, sérialisé en DMN,
comparé au DRD attendu (`.attendu.json`) et validé contre les schémas XSD
de l'OMG lorsque lxml est disponible. Le tableau récapitulatif est écrit
dans `catalogue-patterns/LISEZ-MOI.md`, les sorties dans
`catalogue-patterns/resultats/`.

Chaque exécution est consignée dans le registre des expérimentations
(contexte « catalogue de patterns »), sauf --sans-registre.

Usage :  python outils/executer_catalogue.py
         python outils/executer_catalogue.py --extensions toutes
             (variante avec extensions : consignée dans le registre, sans
              comparaison à l'attendu de référence ni écriture de fichiers)
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
from typing import Dict, List, Tuple

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn.extensions import normaliser_extensions, variante
from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.registre import Registre, desactive
from bpmn2dmn.transformation import expliquer_drd_vide, transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.validation import verifier_dmn_serialise, verifier_invariants
from cli import rapport_json

DOSSIER = os.path.join(RACINE, "catalogue-patterns")
RESULTATS = os.path.join(DOSSIER, "resultats")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def observe(mi, mf) -> Dict:
    """Le DRD produit, dans le vocabulaire de l'attendu (noms et patterns)."""
    noms = {n.id: n.nom for n in mf.noeuds.values()}
    return {
        "decisions": sorted(n.nom for n in mf.decisions),
        "inputs": sorted(n.nom for n in mf.inputs),
        "sources": sorted(n.nom for n in mf.sources),
        "bkms": sorted(n.nom for n in mf.bkms),
        "arcs": sorted([noms[u], noms[v], mf.arcs_origine.get((u, v), "")]
                       for u, v in mf.arcs),
        "points_experts": sorted(p.categorie for p in mf.a_confirmer),
        "ecartes": sorted(p.categorie for p in mf.ecartes),
        "acyclique": mf.acyclique(),
        "invariants_violes": verifier_invariants(mf),
        "anomalies_source": list(mi.anomalies),
        "diagnostic_vide": expliquer_drd_vide(mi, mf),
    }


def comparer(attendu: Dict, obs: Dict) -> List[str]:
    """Les écarts entre le DRD attendu et le DRD observé."""
    ecarts = []
    for cle in ("decisions", "inputs", "sources", "bkms", "points_experts", "ecartes"):
        if sorted(attendu.get(cle, [])) != obs[cle]:
            ecarts.append("%s : attendu %s, obtenu %s"
                          % (cle, sorted(attendu.get(cle, [])), obs[cle]))
    arcs_att = sorted(list(a) for a in attendu.get("arcs", []))
    if arcs_att != obs["arcs"]:
        ecarts.append("arcs : attendu %s, obtenu %s" % (arcs_att, obs["arcs"]))
    if obs["invariants_violes"]:
        ecarts.append("invariants violés : %s" % obs["invariants_violes"])
    if not obs["acyclique"]:
        ecarts.append("graphe cyclique")
    return ecarts


def _schemas():
    try:
        from lxml import etree
    except ImportError:
        return None
    return (etree,
            etree.XMLSchema(etree.parse(os.path.join(RACINE, "build-xsd", "bpmn", "BPMN20.xsd"))),
            etree.XMLSchema(etree.parse(os.path.join(RACINE, "build-xsd", "dmn", "DMN13.xsd"))))


def valider_xsd(schemas, texte: str, genre: str) -> List[str]:
    if schemas is None:
        return []
    etree, xsd_bpmn, xsd_dmn = schemas
    schema = xsd_bpmn if genre == "bpmn" else xsd_dmn
    doc = etree.fromstring(texte.encode("utf-8"))
    if schema.validate(doc):
        return []
    return [str(e) for e in schema.error_log[:3]]


def executer_un(chemin_bpmn: str, schemas=None, ecrire: bool = True,
                registre=None, extensions=frozenset()) -> Tuple[Dict, Dict, List[str]]:
    """Transforme un pattern ; retourne (attendu, observé, écarts). Avec des
    extensions, l'attendu de référence ne s'applique plus : seuls les
    invariants sont contrôlés, et la ligne du registre porte la variante."""
    base = os.path.splitext(chemin_bpmn)[0]
    with io.open(base + ".attendu.json", encoding="utf-8") as f:
        attendu = json.load(f)
    texte = io.open(chemin_bpmn, encoding="utf-8").read()
    t0 = time.perf_counter()
    mi = parser_bpmn(chemin_bpmn)
    t1 = time.perf_counter()
    mf = transformer(mi, extensions=extensions)
    t2 = time.perf_counter()
    dmn = serialiser_dmn(mf)
    t3 = time.perf_counter()
    obs = observe(mi, mf)
    ecarts = comparer(attendu, obs) if not extensions else (
        ["invariants violés : %s" % obs["invariants_violes"]]
        if obs["invariants_violes"] else [])
    if registre is not None:
        registre.enregistrer(mi, mf, "catalogue de patterns", fichier=chemin_bpmn,
                             dmn=dmn, rapport=rapport_json(mf),
                             variante=variante(mf.extensions),
                             durees={"analyse": (t1 - t0) * 1000,
                                     "transformation": (t2 - t1) * 1000,
                                     "serialisation": (t3 - t2) * 1000,
                                     "totale": (t3 - t0) * 1000})
    ecarts += ["DMN relu : " + p for p in verifier_dmn_serialise(dmn, mf)]
    ecarts += ["XSD BPMN : " + e for e in valider_xsd(schemas, texte, "bpmn")]
    if mf.decisions:
        ecarts += ["XSD DMN : " + e for e in valider_xsd(schemas, dmn, "dmn")]
    if ecrire:
        os.makedirs(RESULTATS, exist_ok=True)
        nom = os.path.basename(base)
        io.open(os.path.join(RESULTATS, nom + ".drd.dmn"), "w", encoding="utf-8",
                newline="\n").write(dmn)
        rapport = dict(obs, resume=mf.resume(),
                       points=[{"categorie": p.categorie, "objet": p.objet,
                                "motif": p.motif, "proposition": p.proposition}
                               for p in mf.a_confirmer],
                       ecartes_detail=[{"categorie": p.categorie, "objet": p.objet,
                                        "motif": p.motif} for p in mf.ecartes])
        with io.open(os.path.join(RESULTATS, nom + ".rapport.json"), "w",
                     encoding="utf-8", newline="\n") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return attendu, obs, ecarts


def _resume_drd(obs: Dict) -> str:
    r = "%d D / %d I / %d KS / %d BKM" % (len(obs["decisions"]), len(obs["inputs"]),
                                          len(obs["sources"]), len(obs["bkms"]))
    par = {"P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0}
    for _, _, p in obs["arcs"]:
        par[p] = par.get(p, 0) + 1
    arcs = ", ".join("%s×%d" % (p, n) for p, n in sorted(par.items()) if n)
    pts = ", ".join(obs["points_experts"]) or "aucun"
    ec = ", ".join(obs["ecartes"])
    return "%s ; arcs : %s ; à arbitrer : %s%s" % (
        r, arcs or "aucun", pts, (" ; écarté : " + ec) if ec else "")


def ecrire_lisezmoi(lignes: List[Tuple[Dict, Dict, List[str]]]) -> None:
    VERDICTS = {"conforme": "conforme", "point-expert": "point d'arbitrage",
                "limite": "limite"}
    L = ["# Catalogue de patterns BPMN de la transformation vers DMN", "",
         "Chaque pattern reconnu (ou non) par l'algorithme de transformation est",
         "illustré par un diagramme BPMN 2.0 minimal, prêt à ouvrir dans Camunda",
         "Modeler ou à déposer dans l'application, accompagné de sa référence",
         "experte (`.gold`) et du DRD attendu (`.attendu.json`). Le DRD produit et",
         "le rapport de chaque exécution sont dans `resultats/`, les figures",
         "(BPMN et DRD) dans `figures/`. Les limites établies et les améliorations",
         "qui en découlent sont détaillées dans `LIMITES-ET-AMELIORATIONS.md`.", "",
         "Trois familles : **A** les patterns de référence de l'article pivot",
         "(Π1 à Π6) tels que la correspondance P1 à P6 les reprend ; **B** les",
         "raffinements et gardes propres à l'algorithme ; **C** les limites",
         "établies (cas hors définition ou non couverts).", "",
         "Rejouer :", "", "```",
         "python outils/generer_catalogue_patterns.py    # les diagrammes et attendus",
         "python outils/executer_catalogue.py            # exécution, comparaison, ce tableau",
         "python outils/capturer_catalogue.py            # figures BPMN et DRD",
         "python -m unittest tests.test_catalogue        # vérification figée",
         "```", ""]
    n_ok = sum(1 for _, _, e in lignes if not e)
    L.append("Exécution : **%d / %d** patterns conformes à l'attendu." % (n_ok, len(lignes)))
    L.append("")
    L.append("| Id | Pattern | Éléments BPMN mis en jeu | Ce que produit l'algorithme | Verdict | Enseignement |")
    L.append("|---|---|---|---|---|---|")
    for att, obs, ecarts in lignes:
        verdict = VERDICTS.get(att["verdict_attendu"], att["verdict_attendu"])
        if ecarts:
            verdict += " (écart : %s)" % " ; ".join(ecarts)
        L.append("| %s | **%s** — %s | %s | %s | %s | %s |" % (
            att["id"], att["titre"], att["pattern"], att["elements_bpmn"],
            _resume_drd(obs), verdict, att["enseignement"]))
    L.append("")
    L.append("Verdicts : *conforme* = règle fermée appliquée sans intervention ; "
             "*point d'arbitrage* = règle ouverte, l'algorithme propose et l'expert "
             "tranche ; *limite* = cas hors définition ou non couvert, signalé mais "
             "non transformé.")
    with io.open(os.path.join(DOSSIER, "LISEZ-MOI.md"), "w", encoding="utf-8",
                 newline="\n") as f:
        f.write("\n".join(L) + "\n")


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description="exécution du catalogue de patterns")
    p.add_argument("--extensions", metavar="NOMS",
                   help="extensions de l'algorithme (« toutes » ou noms séparés "
                        "par des virgules) : variante consignée dans le registre")
    p.add_argument("--sans-registre", action="store_true",
                   help="ne pas consigner dans le registre des expérimentations")
    p.add_argument("--registre", metavar="DOSSIER", help="dossier du registre")
    args = p.parse_args(argv)
    extensions = normaliser_extensions(args.extensions)
    registre = None
    if not args.sans_registre and (args.registre or not desactive()):
        registre = Registre(args.registre)
    schemas = _schemas()
    if schemas is None:
        print("lxml absent : validation XSD sautée")
    chemins = sorted(glob.glob(os.path.join(DOSSIER, "*.bpmn")))
    if not chemins:
        print("Aucun diagramme : lancer d'abord outils/generer_catalogue_patterns.py")
        return 1
    lignes = []
    echecs = 0
    if extensions:
        print("Variante : %s (sans comparaison à l'attendu de référence)"
              % variante(extensions))
    for c in chemins:
        att, obs, ecarts = executer_un(c, schemas, ecrire=not extensions,
                                       registre=registre, extensions=extensions)
        lignes.append((att, obs, ecarts))
        print("%-42s %-16s %s" % (os.path.basename(c), att["verdict_attendu"],
                                  "conforme" if not ecarts else "ÉCART"))
        for e in ecarts:
            print("      " + e)
            echecs += 1
    if not extensions:
        ecrire_lisezmoi(lignes)
        print("\n%d / %d patterns conformes à l'attendu ; tableau écrit dans %s"
              % (len(lignes) - sum(1 for l in lignes if l[2]), len(lignes),
                 os.path.join(DOSSIER, "LISEZ-MOI.md")))
    if registre is not None:
        print("Registre : %d lignes consignées dans %s"
              % (len(lignes), os.path.relpath(registre.chemin_csv)))
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
