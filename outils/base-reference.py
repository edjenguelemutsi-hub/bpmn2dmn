# -*- coding: utf-8 -*-
"""
Bases de référence naïves pour la détection des décisions, et notation des
arcs du DRD de FIMEX contre sa référence.

Sur les vingt modèles du corpus de validation (`corpus/*.bpmn` et
`jeux-test-camunda/*.bpmn`, références `.gold`), le script compare la
détection de l'outil (type de la définition de référence ET prédicat de
corroboration kappa) à des détecteurs réduits à un seul critère :

  type seul        tâche utilisateur, tâche de règle métier ou
                   sous-processus replié (l'ensemble DA de l'équation 3.2) ;
  position seule   toute activité suivie d'une passerelle exclusive ou
                   inclusive (indice de position de kappa), quel que soit
                   son type ;
  lexique seul     toute activité dont le libellé contient un verbe du
                   lexique Λ (indice lexical de kappa), quel que soit son
                   type ;
  type + position, type + lexique : les deux indices de kappa pris
                   séparément, sur DA ;
  outil            DA ∩ (position ∨ lexique) = DA*, sans arbitrage.

La mesure est celle de `cli.py valider` (`validation.mesurer_decisions` :
comparaison des libellés normalisés, précision et rappel), cumulée sur le
corpus (micro-moyenne), puis séparément sur les deux modèles qui ne sont
pas construits pour la banque de tests (FIMEX, BPCO) et sur les
dix-huit autres.

Second volet : les arcs. Le seul DRD de référence disponible sous forme de
fichier est `corpus/fimex-drd-reference.dmn` (chapitres 2 et 3). Les
arcs produits par l'outil sur FIMEX, avant et après arbitrage, y sont
comparés par (type, libellé) de leurs deux extrémités ; avant arbitrage,
les trois renommages du fichier d'arbitrages sont appliqués aux seules
décisions, pour ne noter que la structure. La notation est donnée deux
fois : libellés stricts, puis libellés alignés pour la source et le BKM
dont la référence abrège le texte d'annotation (table ALIGNEMENT_FIMEX,
imprimée avec la sortie). Le DRD publié de la BPCO n'existe qu'en
figure : il n'est pas noté.

Sortie figée : essais/base-reference-2026-09-17.txt

Aucune ligne n'est ajoutée au registre des expérimentations.

Usage :  python outils/base-reference.py [> sortie.txt]
"""
from __future__ import annotations

import glob
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn import __version__                                # noqa: E402
from bpmn2dmn.inverse import parser_dmn                          # noqa: E402
from bpmn2dmn.metamodeles import DECISION, Mf                    # noqa: E402
from bpmn2dmn.parseur import parser_bpmn                         # noqa: E402
from bpmn2dmn.qualification import (VIDE, Arbitrages,            # noqa: E402
                                    indice_lexical, indice_position,
                                    normaliser)
from bpmn2dmn.transformation import TYPES_DA, transformer        # noqa: E402
from bpmn2dmn.validation import mesurer_decisions                # noqa: E402

NON_CONSTRUITS = ("fimex.bpmn", "copd.bpmn")

# Libellés reformulés par la référence FIMEX pour deux sommets qui ne sont
# pas des décisions : l'outil garde le texte de l'annotation, la référence
# un nom court. L'alignement est déclaré ici et imprimé avec la sortie.
ALIGNEMENT_FIMEX = {
    "reglementation fimex : pieces exigees, criteres de recevabilite":
        "reglementation fimex",
    "regle : cotation automatique, aleatoire et equitable entre les agents "
    "actifs": "regle de cotation aleatoire equitable",
}

DETECTEURS = (
    ("type seul (DA)",
     lambda mi, aid, a: a.type in TYPES_DA or a.type == "subProcess"),
    ("position seule",
     lambda mi, aid, a: indice_position(mi, aid)),
    ("lexique seul",
     lambda mi, aid, a: indice_lexical(a)),
    ("type + position",
     lambda mi, aid, a: (a.type in TYPES_DA or a.type == "subProcess")
     and indice_position(mi, aid)),
    ("type + lexique",
     lambda mi, aid, a: (a.type in TYPES_DA or a.type == "subProcess")
     and indice_lexical(a)),
    ("outil : type + (position ou lexique)",
     lambda mi, aid, a: (a.type in TYPES_DA or a.type == "subProcess")
     and (indice_position(mi, aid) or indice_lexical(a))),
)


def lire_gold(chemin_bpmn):
    ref = os.path.splitext(chemin_bpmn)[0] + ".gold"
    with open(ref, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def pourcent(n, d):
    return "%5.1f %%" % (100.0 * n / d) if d else "   —   "


def corpus():
    chemins = sorted(glob.glob(os.path.join(RACINE, "corpus", "*.bpmn")))
    chemins += sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda",
                                             "*.bpmn")))
    return chemins


def volet_decisions(chemins):
    print("1. DÉTECTION DES DÉCISIONS — bases de référence naïves")
    print("=" * 72)
    groupes = {"corpus (20 modèles)": lambda c: True,
               "FIMEX + BPCO (non construits)":
                   lambda c: os.path.basename(c) in NON_CONSTRUITS,
               "18 modèles construits":
                   lambda c: os.path.basename(c) not in NON_CONSTRUITS}
    totaux = {(g, n): [0, 0, 0] for g in groupes for n, _ in DETECTEURS}
    n_act = n_da = 0
    controle_outil = True
    detail = []
    for c in chemins:
        mi = parser_bpmn(c)
        gold = lire_gold(c)
        acts = mi.activites
        n_act += len(acts)
        n_da += sum(1 for a in acts.values()
                    if a.type in TYPES_DA or a.type == "subProcess")
        ligne = [os.path.relpath(c, RACINE).replace("\\", "/"),
                 len(acts), len(gold)]
        for nom, pred in DETECTEURS:
            det = [a.nom for aid, a in acts.items() if pred(mi, aid, a)]
            m = mesurer_decisions(det, gold)
            fp, fn = len(m["a_tort"]), len(m["manquees"])
            ligne.append("%d/%d/%d" % (m["vraies"], fp, fn))
            for g, filtre in groupes.items():
                if filtre(c):
                    t = totaux[(g, nom)]
                    t[0] += m["vraies"]
                    t[1] += fp
                    t[2] += fn
            if nom.startswith("outil"):
                mf = transformer(mi, VIDE)
                if sorted(normaliser(n.nom) for n in mf.decisions) != \
                        sorted(normaliser(x) for x in det):
                    controle_outil = False
        detail.append(ligne)

    print("Contrôles : %d modèles, |A| = %d, |DA| = %d ; détecteur « outil » "
          "identique à la sortie de transformer() : %s"
          % (len(chemins), n_act, n_da, "oui" if controle_outil else "NON"))
    print()
    for g in groupes:
        print("-- %s" % g)
        print("   %-38s %5s %5s %5s  %9s  %9s"
              % ("détecteur", "VP", "FP", "FN", "précision", "rappel"))
        for nom, _ in DETECTEURS:
            vp, fp, fn = totaux[(g, nom)]
            print("   %-38s %5d %5d %5d  %9s  %9s"
                  % (nom, vp, fp, fn, pourcent(vp, vp + fp),
                     pourcent(vp, vp + fn)))
        print()
    print("Détail par modèle (VP/FP/FN), colonnes dans l'ordre des "
          "détecteurs ci-dessus :")
    for ligne in detail:
        print("   %-40s |A|=%2d gold=%d  %s"
              % (ligne[0], ligne[1], ligne[2], "  ".join(ligne[3:])))
    print()


def signature_arcs(mf: Mf, renommer=None, aligner=None):
    renommer = renommer or {}
    aligner = aligner or {}

    def cle(nid):
        n = mf.noeuds[nid]
        nom = renommer.get(nid, n.nom) if n.type == DECISION else n.nom
        nom = normaliser(nom)
        return (n.type, aligner.get(nom, nom))

    return {(cle(u), cle(v)) for u, v in mf.arcs}


def noter(produits, reference, titre):
    vp = produits & reference
    fp = produits - reference
    fn = reference - produits
    print("   %-28s produits %2d, référence %2d, communs %2d  "
          "précision %s  rappel %s"
          % (titre, len(produits), len(reference), len(vp),
             pourcent(len(vp), len(produits)),
             pourcent(len(vp), len(reference))))
    for u, v in sorted(fp):
        print("      en trop  : %s « %s » -> %s « %s »" % (u[0], u[1],
                                                         v[0], v[1]))
    for u, v in sorted(fn):
        print("      manquant : %s « %s » -> %s « %s »" % (u[0], u[1],
                                                         v[0], v[1]))


def volet_arcs():
    print("2. ARCS DU DRD — FIMEX contre corpus/fimex-drd-reference.dmn")
    print("=" * 72)
    mi = parser_bpmn(os.path.join(RACINE, "corpus", "fimex.bpmn"))
    ref = parser_dmn(os.path.join(RACINE, "corpus",
                                  "fimex-drd-reference.dmn"))
    arb = Arbitrages.depuis_json(os.path.join(RACINE, "corpus",
                                              "fimex.arbitrages.json"))
    s_ref = signature_arcs(ref)
    apres = transformer(mi, arb)
    avant = transformer(mi, VIDE)
    renommer = {did: arb.renommages[aid] for aid, did in avant.delta.items()
                if aid in arb.renommages}
    print("Référence : %d sommets, %d arcs." % (len(ref.noeuds),
                                                 len(ref.arcs)))
    print()
    print("a) libellés stricts")
    noter(signature_arcs(avant, renommer), s_ref,
          "avant arbitrage (noms seuls)")
    noter(signature_arcs(apres), s_ref, "après arbitrage")
    print()
    print("b) libellés alignés (sources et BKM reformulés par la référence) :")
    for k, v in ALIGNEMENT_FIMEX.items():
        print("      « %s »  ->  « %s »" % (k, v))
    noter(signature_arcs(avant, renommer, ALIGNEMENT_FIMEX), s_ref,
          "avant arbitrage (noms seuls)")
    noter(signature_arcs(apres, None, ALIGNEMENT_FIMEX), s_ref,
          "après arbitrage")
    print()
    print("BPCO : le DRD publié par Bazhenova et al. n'existe qu'en figure ; "
          "ses arcs ne sont pas notés.")


def principal():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print("Bases de référence — bpmn2dmn %s — outils/base-reference.py"
          % __version__)
    print()
    volet_decisions(corpus())
    volet_arcs()


if __name__ == "__main__":
    principal()
