#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cli.py — le transformateur BPMN <-> DMN en ligne de commande.

USAGE (depuis le dossier transformateur/) :

  python cli.py transformer <modele.bpmn> [-o sortie.dmn] [-a arbitrages.json]
      Chaîne complète : parseur -> Mi -> T -> Mf -> DRD.dmn (+ rapport).

  python cli.py inverser <modele.dmn> [-o sortie.bpmn]
      Chemin retour : DRD -> squelette BPMN + arbitrages d'aller-retour.

  python cli.py valider [chemins .bpmn ...]
      Valide sur le corpus (références expertes .gold) — même rapport que
      mon premier prototype, invariants formels en plus.

  python cli.py generer <n> [-d dossier] [--graine G]
      Écrit n modèles BPMN de la banque de tests + leur oracle.

  python cli.py campagne <n> [--graine G]
      Campagne massive : n modèles générés, chacun soumis à toute la
      chaîne (invariants, oracle, sérialisation relue, aller-retour
      T(T_inv(Mf)) = Mf). S'arrête à la première divergence.

  python cli.py servir [-p port]
      Lance l'application web interactive (interface graphique).

  python cli.py registre [--dernieres N] [--excel]
      Synthèse du registre des expérimentations (experimentations/) :
      chaque extraction lancée par « transformer », « valider » ou
      l'application web y ajoute automatiquement une ligne (CSV + Excel).
      Options communes : --sans-registre (ne rien enregistrer),
      --registre DOSSIER (autre dossier de registre).

  python cli.py extensions
      Liste les extensions de l'algorithme (désactivées par défaut) ;
      « transformer » et « valider » les activent avec
      --extensions nom1,nom2 (ou --extensions toutes).
"""
from __future__ import annotations

import argparse
import glob as globmod
import io
import json
import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bpmn2dmn.parseur import parser_bpmn, ErreurParseur
from bpmn2dmn.transformation import expliquer_drd_vide, transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import parser_dmn, inverser, ErreurDMN
from bpmn2dmn.generateur import generer
from bpmn2dmn.extensions import (EXTENSIONS, normaliser_extensions, texte_liste,
                                 variante)
from bpmn2dmn.qualification import Arbitrages, VIDE
from bpmn2dmn.registre import Registre, desactive, texte_synthese
from bpmn2dmn.validation import (comparer_a_oracle, equivalents,
                                 mesurer_decisions, verifier_dmn_serialise,
                                 verifier_invariants)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# rapports (texte pour la console, dict pour le JSON et l'application)
def rapport_texte(mf, mi=None) -> str:
    L = []
    L.append("-" * 74)
    L.append(" MODÈLE : %s" % mf.nom)
    L.append("-" * 74)
    if mf.extensions:
        L.append("  Extensions actives : %s" % ", ".join(mf.extensions))
    r = mf.resume()
    L.append("  DRD extrait")
    L.append("    décisions .................. %d  %s"
             % (r["decisions"], [n.nom for n in mf.decisions]))
    L.append("    données d'entrée ........... %d  %s"
             % (r["inputs"], [n.nom for n in mf.inputs]))
    L.append("    sources de connaissance .... %d  %s"
             % (r["sources"], [n.nom for n in mf.sources]))
    L.append("    modèles de conn. métier .... %d  %s"
             % (r["bkm"], [n.nom for n in mf.bkms]))
    L.append("    exigences d'information .... %d" % r["IR"])
    L.append("    exigences d'autorité ....... %d" % r["AR"])
    L.append("    exigences de connaissance .. %d" % r["KR"])
    L.append("  Vérification")
    L.append("    graphe acyclique ........... %s"
             % ("oui" if mf.acyclique() else "non (cycle)"))
    inv = verifier_invariants(mf)
    L.append("    invariants formels ......... %s"
             % ("8/8 respectés" if not inv else "violés : " + " ; ".join(inv)))
    L.append("  Périmètre d'automatisation")
    L.append("    points à confirmer ......... %d" % len(mf.a_confirmer))
    for p in mf.a_confirmer:
        L.append("        [?] %-12s %-48s %s"
                 % (p.categorie, p.objet[:48], p.motif))
    L.append("    éléments écartés ........... %d" % len(mf.ecartes))
    for p in mf.ecartes:
        L.append("        [x] %-12s %-48s %s"
                 % (p.categorie, p.objet[:48], p.motif))
    if mi is not None and mi.anomalies:
        L.append("  Anomalies du modèle source (non bloquantes)")
        for a in mi.anomalies:
            L.append("        [!] %s" % a)
    diagnostic = expliquer_drd_vide(mi, mf) if mi is not None else ""
    if diagnostic:
        L.append("  Pourquoi le DRD est vide")
        L.extend("        " + ligne
                 for ligne in textwrap.wrap(diagnostic, 66))
    if mf.suggestions_noms:
        L.append("  Noms de décision suggérés (extension noms-suggeres)")
        for aid, nom in mf.suggestions_noms.items():
            L.append("        %-12s %s" % (aid, nom))
    if mf.logique:
        L.append("  Tables de décision squelettes (extension logique) : %d"
                 % len(mf.logique))
    return "\n".join(L)


def rapport_json(mf) -> dict:
    r = _rapport_json_base(mf)
    if mf.extensions:
        r["extensions"] = list(mf.extensions)
        r["variante"] = variante(mf.extensions)
    if mf.suggestions_noms:
        r["suggestions_noms"] = dict(mf.suggestions_noms)
    if mf.logique:
        r["logique"] = {did: {"passerelle": l["passerelle"],
                              "branches": [b["sortie"] for b in l["branches"]]}
                        for did, l in mf.logique.items()}
    return r


def _rapport_json_base(mf) -> dict:
    return {
        "nom": mf.nom,
        "resume": mf.resume(),
        "decisions": [{"id": n.id, "nom": n.nom, "origine": n.origine,
                       "motif": mf.motifs_corroboration.get(n.id, "")}
                      for n in mf.decisions],
        "inputs": [{"id": n.id, "nom": n.nom, "pattern": n.pattern}
                   for n in mf.inputs],
        "sources": [{"id": n.id, "nom": n.nom, "pattern": n.pattern}
                    for n in mf.sources],
        "bkms": [{"id": n.id, "nom": n.nom} for n in mf.bkms],
        "IR": mf.IR, "KR": mf.KR, "AR": mf.AR,
        "acyclique": mf.acyclique(),
        "invariants_violes": verifier_invariants(mf),
        "a_confirmer": [{"cle": p.cle, "categorie": p.categorie,
                         "objet": p.objet, "motif": p.motif,
                         "proposition": p.proposition}
                        for p in mf.a_confirmer],
        "ecartes": [{"cle": p.cle, "categorie": p.categorie,
                     "objet": p.objet, "motif": p.motif}
                    for p in mf.ecartes],
    }


def _ecrire(chemin: str, contenu: str) -> None:
    dossier = os.path.dirname(os.path.abspath(chemin))
    os.makedirs(dossier, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)


def _registre(args):
    """Le registre des expérimentations, sauf s'il est suspendu
    (--sans-registre ou BPMN2DMN_SANS_REGISTRE=1)."""
    dossier = getattr(args, "registre", None)
    if getattr(args, "sans_registre", False):
        return None
    if desactive() and not dossier:
        return None                # un dossier explicite l'emporte sur l'environnement
    return Registre(dossier)


def _enregistrer(registre, mi, mf, contexte, chemin, arb, dmn, durees):
    """Ajoute la ligne au registre ; un incident d'enregistrement est
    signalé mais n'interrompt jamais l'extraction."""
    if registre is None:
        return None
    try:
        ligne = registre.enregistrer(mi, mf, contexte, fichier=chemin, arbitrages=arb,
                                     dmn=dmn, rapport=rapport_json(mf), durees=durees,
                                     variante=variante(mf.extensions))
    except Exception as e:
        print("  Registre : enregistrement impossible (%s)" % e)
        return None
    print("  Registre : expérimentation %s (code %s) ajoutée à %s"
          % (ligne["experience"], ligne["code_modele"],
             os.path.relpath(registre.chemin_csv)))
    return ligne


# les commandes
def _extensions_demandees(args):
    """Les extensions de l'option --extensions, ou une erreur lisible."""
    return normaliser_extensions(getattr(args, "extensions", None))


def cmd_transformer(args) -> int:
    try:
        ext = _extensions_demandees(args)
        arb = (Arbitrages.depuis_json(args.arbitrages) if args.arbitrages
               else VIDE)
        mi = parser_bpmn(args.modele)
    except (ErreurParseur, OSError, ValueError, TypeError) as e:
        print("ERREUR : %s" % e)
        return 1
    t0 = time.perf_counter()
    mf = transformer(mi, arb, ext)
    t1 = time.perf_counter()
    dmn = serialiser_dmn(mf)
    t2 = time.perf_counter()
    sortie = args.sortie or os.path.splitext(args.modele)[0] + ".drd.dmn"
    _ecrire(sortie, dmn)
    print(rapport_texte(mf, mi))
    print("\n  DRD écrit : %s" % sortie)
    problemes = verifier_dmn_serialise(dmn, mf)
    print("  Relecture du DMN produit ..... %s"
          % ("conforme" if not problemes else "problèmes : "
             + " ; ".join(problemes)))
    if args.json:
        _ecrire(args.json, json.dumps(rapport_json(mf),
                                      ensure_ascii=False, indent=2))
        print("  Rapport JSON : %s" % args.json)
    _enregistrer(_registre(args), mi, mf, "ligne de commande", args.modele, arb, dmn,
                 {"transformation": (t1 - t0) * 1000, "serialisation": (t2 - t1) * 1000,
                  "totale": (t2 - t0) * 1000})
    return 0


def cmd_inverser(args) -> int:
    try:
        mf = parser_dmn(args.modele)
    except (ErreurDMN, OSError) as e:
        print("ERREUR : %s" % e)
        return 1
    bpmn, arbitrages = inverser(mf)
    sortie = args.sortie or os.path.splitext(args.modele)[0] + ".inverse.bpmn"
    _ecrire(sortie, bpmn)
    chemin_arb = os.path.splitext(sortie)[0] + ".arbitrages.json"
    _ecrire(chemin_arb, json.dumps(arbitrages, ensure_ascii=False, indent=2))
    print(" DRD lu : %d décisions, %d données, %d sources, %d BKM, %d arcs"
          % (len(mf.decisions), len(mf.inputs), len(mf.sources),
             len(mf.bkms), len(mf.arcs)))
    print(" Squelette BPMN écrit : %s" % sortie)
    print(" Arbitrages d'aller-retour : %s" % chemin_arb)
    # preuve immédiate : T(T_inv(Mf)) = Mf ?
    mi2 = parser_bpmn(bpmn, est_texte=True)
    mf2 = transformer(mi2, Arbitrages.depuis_json(arbitrages))
    ok, ecarts = equivalents(mf, mf2)
    print(" Aller-retour T(T_inv(M)) = M : %s"
          % ("vérifié" if ok else "échec — " + " ; ".join(ecarts)))
    return 0 if ok else 1


def cmd_valider(args) -> int:
    chemins = []
    for motif in (args.chemins or ["corpus/*.bpmn"]):
        chemins.extend(sorted(globmod.glob(motif)))
    if not chemins:
        print("Aucun modèle .bpmn trouvé.")
        return 1
    print("Validation — dérivation BPMN -> DMN (exigences de décision)")
    try:
        ext = _extensions_demandees(args)
    except ValueError as e:
        print("ERREUR : %s" % e)
        return 1
    if ext:
        print("Extensions actives : %s" % ", ".join(sorted(ext)))
    tot = {"vp": 0, "fp": 0, "fn": 0, "modeles": 0, "inv": 0}
    registre = _registre(args)
    for c in chemins:
        t0 = time.perf_counter()
        mi = parser_bpmn(c)
        t1 = time.perf_counter()
        mf = transformer(mi, VIDE, ext)
        t2 = time.perf_counter()
        dmn = serialiser_dmn(mf)
        t3 = time.perf_counter()
        print()
        print(rapport_texte(mf, mi))
        _enregistrer(registre, mi, mf, "validation corpus", c, VIDE, dmn,
                     {"analyse": (t1 - t0) * 1000, "transformation": (t2 - t1) * 1000,
                      "serialisation": (t3 - t2) * 1000, "totale": (t3 - t0) * 1000})
        tot["modeles"] += 1
        tot["inv"] += 0 if not verifier_invariants(mf) else 1
        ref = _lire_gold(c)
        if ref is not None:
            m = mesurer_decisions([n.nom for n in mf.decisions], ref)
            tot["vp"] += m["vraies"]
            tot["fp"] += len(m["a_tort"])
            tot["fn"] += len(m["manquees"])
            print("  Mesure vs référence experte")
            print("    attendues / détectées ...... %d / %d"
                  % (m["attendues"], m["detectees"]))
            if m["a_tort"]:
                print("    détectées à tort ........... %s" % m["a_tort"])
            if m["manquees"]:
                print("    manquées ................... %s" % m["manquees"])
            print("    précision / rappel ......... %.0f%% / %.0f%%"
                  % (100 * m["precision"], 100 * m["rappel"]))
    print()
    att = tot["vp"] + tot["fn"]
    print(" Synthèse : %d modèles ; invariants violés sur %d"
          % (tot["modeles"], tot["inv"]))
    if att:
        prec = tot["vp"] / (tot["vp"] + tot["fp"]) if tot["vp"] + tot["fp"] else 0
        print(" détection : %d attendues, %d correctes, %d à tort, %d manquées"
              % (att, tot["vp"], tot["fp"], tot["fn"]))
        print(" précision / rappel : %.0f%% / %.0f%%"
              % (100 * prec, 100 * tot["vp"] / att))
    return 0


def _lire_gold(chemin_bpmn):
    ref = os.path.splitext(chemin_bpmn)[0] + ".gold"
    if not os.path.exists(ref):
        return None
    with open(ref, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def cmd_generer(args) -> int:
    dossier = args.dossier or "banque"
    os.makedirs(dossier, exist_ok=True)
    for i in range(args.n):
        seed = args.graine + i
        bpmn, attendu = generer(seed)
        base = os.path.join(dossier, "modele-%06d" % seed)
        with open(base + ".bpmn", "w", encoding="utf-8") as f:
            f.write(bpmn)
        with open(base + ".attendu.json", "w", encoding="utf-8") as f:
            json.dump(attendu.as_dict(), f, ensure_ascii=False, indent=2)
        with open(base + ".gold", "w", encoding="utf-8") as f:
            f.write("# décisions attendues (oracle du générateur)\n")
            for d in attendu.decisions:
                f.write(d + "\n")
    print("%d modèles écrits dans %s/ (graines %d à %d)"
          % (args.n, dossier, args.graine, args.graine + args.n - 1))
    return 0


def cmd_campagne(args) -> int:
    """Campagne de vérification massive : chaque graine parcourt toute la
    chaîne ; la première divergence arrête la campagne (graine affichée)."""
    debut = args.graine
    n = args.n
    stats = {"ok": 0, "modeles": 0, "decisions": 0, "arcs": 0, "confirmer": 0}
    depart = time.perf_counter()
    for i in range(n):
        seed = debut + i
        bpmn, attendu = generer(seed)
        # 1. parseur
        mi = parser_bpmn(bpmn, est_texte=True)
        # 2. transformation + invariants
        mf = transformer(mi)
        inv = verifier_invariants(mf)
        if inv:
            print("Échec graine %d — invariants : %s" % (seed, inv))
            return 1
        # 3. oracle
        ecarts = comparer_a_oracle(mf, attendu)
        if ecarts:
            print("Échec graine %d — oracle : %s" % (seed, ecarts))
            return 1
        # 4. sérialisation DMN relue
        dmn = serialiser_dmn(mf)
        problemes = verifier_dmn_serialise(dmn, mf)
        if problemes:
            print("Échec graine %d — sérialisation : %s" % (seed, problemes))
            return 1
        # 5. aller-retour complet T(T_inv(Mf)) = Mf
        if mf.decisions:
            bpmn2, arb = inverser(mf)
            mi2 = parser_bpmn(bpmn2, est_texte=True)
            mf2 = transformer(mi2, Arbitrages.depuis_json(arb))
            ok, ecarts2 = equivalents(mf, mf2)
            if not ok:
                print("Échec graine %d — aller-retour : %s" % (seed, ecarts2))
                return 1
        # 6. déterminisme : deux exécutions -> même résultat
        mf_bis = transformer(parser_bpmn(bpmn, est_texte=True))
        ok, _ = equivalents(mf, mf_bis)
        if not ok or serialiser_dmn(mf_bis) != dmn:
            print("Échec graine %d — non déterministe" % seed)
            return 1
        stats["ok"] += 1
        stats["modeles"] += 1
        stats["decisions"] += len(mf.decisions)
        stats["arcs"] += len(mf.arcs)
        stats["confirmer"] += len(mf.a_confirmer)
        if (i + 1) % max(1, n // 20) == 0 or i == n - 1:
            print("  ... %d / %d modèles vérifiés (graines %d–%d)"
                  % (i + 1, n, debut, seed))
    print("Campagne terminée : %d modèles, %d décisions, %d exigences —"
          % (stats["modeles"], stats["decisions"], stats["arcs"]))
    print("oracle exact, invariants 8/8, sérialisation relue, aller-retour")
    print("T(T_inv(M)) = M et déterminisme vérifiés sur chaque modèle.")
    registre = _registre(args)
    if registre is not None:
        registre.journal_campagne("campagne", debut, n, stats["ok"], stats["decisions"],
                                  stats["arcs"], stats["confirmer"], 0,
                                  time.perf_counter() - depart)
        print("Campagne consignée dans %s" % os.path.relpath(registre.chemin_campagnes))
    return 0


def cmd_extensions(args) -> int:
    print(texte_liste())
    return 0


def cmd_registre(args) -> int:
    registre = Registre(args.registre)
    if not os.path.exists(registre.chemin_csv):
        print("Aucune expérimentation enregistrée pour l'instant (%s)."
              % registre.dossier)
        print("Chaque « transformer », « valider » ou extraction dans "
              "l'application web en ajoutera une.")
        return 0
    print(texte_synthese(registre))
    if args.dernieres:
        lignes = registre.lignes()[-args.dernieres:]
        print()
        print("  %-11s %-20s %-28s %-18s %4s %4s %4s %4s %4s %5s"
              % ("expérience", "date", "fichier", "contexte", "D", "I", "KS",
                 "BKM", "E_f", "expert"))
        for l in lignes:
            print("  %-11s %-20s %-28s %-18s %4s %4s %4s %4s %4s %5s"
                  % (l["experience"], l["horodatage"], str(l["fichier"])[:28],
                     str(l["contexte"])[:18], l["decisions"], l["donnees_entree"],
                     l["sources_connaissance"], l["bkm"], l["ef_exigences"],
                     l["points_expert"]))
    if args.excel:
        print("  Classeur régénéré : %s" % registre.ecrire_excel())
    return 0


def cmd_servir(args) -> int:
    import app
    return app.servir(args.port, ouvrir=not args.sans_navigateur,
                      reseau=args.reseau, registre_dossier=args.registre,
                      sans_registre=args.sans_registre)


def _options_registre(sous_commande) -> None:
    sous_commande.add_argument("--sans-registre", action="store_true",
                               help="ne pas consigner l'exécution dans le registre "
                                    "des expérimentations")
    sous_commande.add_argument("--registre", metavar="DOSSIER",
                               help="dossier du registre (par défaut : "
                                    "experimentations/)")


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description="Transformateur BPMN <-> DMN")
    sous = p.add_subparsers(dest="commande", required=True)

    t = sous.add_parser("transformer", help="BPMN -> DRD (DMN)")
    t.add_argument("modele")
    t.add_argument("-o", "--sortie")
    t.add_argument("-a", "--arbitrages")
    t.add_argument("--json", help="écrire aussi le rapport JSON")
    t.add_argument("--extensions", metavar="NOMS",
                   help="extensions de l'algorithme à activer, séparées par "
                        "des virgules (« toutes » pour toutes ; voir « extensions »)")
    _options_registre(t)
    t.set_defaults(fonc=cmd_transformer)

    i = sous.add_parser("inverser", help="DRD (DMN) -> BPMN")
    i.add_argument("modele")
    i.add_argument("-o", "--sortie")
    i.set_defaults(fonc=cmd_inverser)

    v = sous.add_parser("valider", help="valider sur le corpus (.gold)")
    v.add_argument("chemins", nargs="*")
    v.add_argument("--extensions", metavar="NOMS",
                   help="extensions de l'algorithme à activer")
    _options_registre(v)
    v.set_defaults(fonc=cmd_valider)

    e = sous.add_parser("extensions",
                        help="lister les extensions de l'algorithme")
    e.set_defaults(fonc=cmd_extensions)

    g = sous.add_parser("generer", help="générer la banque de tests")
    g.add_argument("n", type=int)
    g.add_argument("-d", "--dossier")
    g.add_argument("--graine", type=int, default=1)
    g.set_defaults(fonc=cmd_generer)

    c = sous.add_parser("campagne", help="campagne de vérification massive")
    c.add_argument("n", type=int)
    c.add_argument("--graine", type=int, default=1)
    _options_registre(c)
    c.set_defaults(fonc=cmd_campagne)

    s = sous.add_parser("servir", help="application web interactive")
    s.add_argument("-p", "--port", type=int, default=8765)
    s.add_argument("--reseau", action="store_true",
                   help="rendre l'application accessible aux autres "
                        "ordinateurs du réseau local")
    s.add_argument("--sans-navigateur", action="store_true",
                   help="ne pas ouvrir le navigateur au démarrage")
    _options_registre(s)
    s.set_defaults(fonc=cmd_servir)

    r = sous.add_parser("registre", help="synthèse du registre des expérimentations")
    r.add_argument("--dernieres", type=int, metavar="N",
                   help="afficher les N dernières expérimentations")
    r.add_argument("--excel", action="store_true",
                   help="régénérer le classeur registre.xlsx")
    r.add_argument("--registre", metavar="DOSSIER",
                   help="dossier du registre (par défaut : experimentations/)")
    r.set_defaults(fonc=cmd_registre)

    args = p.parse_args(argv)
    return args.fonc(args)


if __name__ == "__main__":
    sys.exit(principal())
