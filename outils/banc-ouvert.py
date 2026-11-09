# -*- coding: utf-8 -*-
"""
Banc d'essai ouvert : le transformateur sur des collections de modèles BPMN
écrits par d'autres.

Deux collections publiques, téléchargées par `outils/telecharger-banc.py`
dans `banc-ouvert/sources/` (non versionnées) :

  bfr   camunda/bpmn-for-research : 3 739 diagrammes dessinés par les
        participants de formations BPMN (cours en anglais et en allemand,
        quatre exercices, plus le corrigé de chaque exercice) ; usage
        académique, lien vers le dépôt à conserver ;
  miwg  bpmn-miwg/bpmn-miwg-test-suite : les 22 modèles de référence du
        groupe d'interopérabilité de l'OMG.

Pour chaque modèle : lecture (ou échec et son motif), puis trois
variantes de la transformation : la référence (candidats = tâches
utilisateur, tâches de règle métier, sous-processus repliés), l'extension
« definition-etendue » (toute activité corroborée par les deux indices
devient décision, un seul indice la soumet à l'expert ; nécessaire sur ces
collections où la tâche générique domine) et cette extension avec
l'indice sémantique s'il est installé ; pour chacune : invariants,
relecture du DMN, aller-retour T(T⁻¹(M)) = M, déterminisme, durées, et
toutes les grandeurs du registre (candidats, indices de corroboration,
sommets, exigences, points soumis à l'expert). Résultats :
`banc-ouvert/resultats.csv` (une ligne par modèle et par variante) et
`banc-ouvert/synthese.md` (tableaux par collection, par langue, par
exercice ; distribution de la charge laissée à l'expert ; modèles en échec).
Aucune référence experte n'existe pour ces modèles : le banc mesure la
robustesse de la chaîne et la charge de l'expert, pas la précision.

    python -X utf8 outils/banc-ouvert.py [--sources DOSSIER] [--sortie DOSSIER]
                                         [--sans-semantique] [--limite N]
"""
import argparse
import csv
import glob
import os
import statistics
import sys
import time
from collections import Counter, OrderedDict, defaultdict

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn import semantique  # noqa: E402
from bpmn2dmn.inverse import inverser  # noqa: E402
from bpmn2dmn.metriques import NOMS_COLONNES, mesurer  # noqa: E402
from bpmn2dmn.parseur import ErreurParseur, parser_bpmn  # noqa: E402
from bpmn2dmn.qualification import Arbitrages, kappa  # noqa: E402
from bpmn2dmn.serialiseur import serialiser_dmn  # noqa: E402
from bpmn2dmn.transformation import TYPES_DA, transformer  # noqa: E402
from bpmn2dmn.validation import equivalents, verifier_dmn_serialise, verifier_invariants  # noqa: E402

COLONNES_BANC = ["collection", "langue", "exercice", "genre", "fichier", "variante",
                 "lu", "erreur", "determinisme", "activites_generiques_corroborees",
                 "da_semantique", "da_semantique_seul", "activites_semantique"]


def _contexte(chemin, sources):
    rel = os.path.relpath(chemin, sources).replace(os.sep, "/")
    parties = rel.split("/")
    if parties[0] == "bfr" and len(parties) >= 5:
        return {"collection": "bfr", "langue": parties[1], "exercice": parties[2],
                "genre": parties[3], "fichier": parties[4]}
    return {"collection": parties[0], "langue": "EN", "exercice": "", "genre": "reference",
            "fichier": parties[-1]}


def _mesurer_modele(chemin, sources, avec_semantique):
    ctx = _contexte(chemin, sources)
    lignes = []
    t0 = time.perf_counter()
    try:
        mi = parser_bpmn(chemin)
    except (ErreurParseur, OSError, ValueError) as e:
        ligne = OrderedDict((c, "") for c in COLONNES_BANC + NOMS_COLONNES)
        ligne.update(ctx)
        ligne["variante"] = "reference"
        ligne["lu"] = 0
        ligne["erreur"] = str(e)[:120]
        return [ligne]
    t1 = time.perf_counter()
    variantes = [("reference", frozenset()),
                 ("extensions:definition-etendue", frozenset({"definition-etendue"}))]
    if avec_semantique:
        variantes.append(("extensions:definition-etendue+indice-semantique",
                          frozenset({"definition-etendue", "indice-semantique"})))
    for nom_variante, ext in variantes:
        t2 = time.perf_counter()
        mf = transformer(mi, Arbitrages(), ext)
        t3 = time.perf_counter()
        dmn = serialiser_dmn(mf)
        t4 = time.perf_counter()
        aller_retour = None
        if mf.decisions:
            try:
                bpmn2, arb = inverser(mf)
                mf2 = transformer(parser_bpmn(bpmn2, est_texte=True), Arbitrages.depuis_json(arb))
                aller_retour = equivalents(mf, mf2)[0]
            except Exception:                      # pragma: no cover
                aller_retour = False
        ligne = mesurer(mi, mf, reference=None, dmn=dmn, aller_retour=aller_retour,
                        durees={"analyse": (t1 - t0) * 1000, "transformation": (t3 - t2) * 1000,
                                "serialisation": (t4 - t3) * 1000,
                                "totale": (t1 - t0 + t4 - t2) * 1000})
        for c, v in ctx.items():
            ligne[c] = v
        ligne["variante"] = nom_variante
        ligne["lu"] = 1
        ligne["erreur"] = ""
        mf_bis = transformer(mi, Arbitrages(), ext)
        ligne["determinisme"] = 1 if equivalents(mf, mf_bis)[0] and serialiser_dmn(mf_bis) == dmn else 0
        # les activités hors définition (tâches génériques, nombreuses dans
        # ces collections) corroborées par un indice : décisions de fait que
        # la définition de référence ne retient pas
        ligne["activites_generiques_corroborees"] = sum(
            1 for p in mf.a_confirmer if p.categorie == "hors-definition")
        if "indice-semantique" in ext:
            # l'indice sémantique sur toutes les activités, pas seulement DA
            ind = semantique.instance()
            noms = [a.nom for a in mi.activites.values()]
            scores = ind.scores(noms) if noms else []
            ligne["activites_semantique"] = sum(1 for s in scores if s >= ind.seuil)
        lignes.append(ligne)
    return lignes


def _pct(n, d):
    return "%.1f" % (100.0 * n / d) if d else "-"


def _moy(valeurs):
    v = [float(x) for x in valeurs if x not in ("", None)]
    return "%.2f" % statistics.mean(v) if v else "-"


def _tableau(lignes, cle, titre):
    groupes = defaultdict(list)
    for l in lignes:
        groupes[l[cle]].append(l)
    L = ["### %s" % titre, "",
         "| %s | modèles | lus | activités | candidats DA | retenus DA* | position seule | lexique seul | deux | non corroborés | hors définition corroborées | décisions | exigences | points expert | questions par décision | modèles sans décision |"
         % cle,
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in sorted(groupes):
        G = groupes[g]
        lus = [l for l in G if l["lu"] == 1 or l["lu"] == "1"]
        n_dec = sum(int(l["decisions"]) for l in lus)
        n_pe = sum(int(l["points_expert"]) for l in lus)
        L.append("| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %s | %d |" % (
            g, len(G), len(lus),
            sum(int(l["activites"]) for l in lus),
            sum(int(l["da_candidats"]) for l in lus),
            sum(int(l["da_retenus"]) for l in lus),
            sum(int(l["da_position_seule"]) for l in lus),
            sum(int(l["da_lexical_seul"]) for l in lus),
            sum(int(l["da_deux_indices"]) for l in lus),
            sum(int(l["da_non_corrobores"]) for l in lus),
            sum(int(l["activites_generiques_corroborees"]) for l in lus),
            n_dec, sum(int(l["ef_exigences"]) for l in lus), n_pe,
            "%.2f" % (n_pe / n_dec) if n_dec else "-",
            sum(1 for l in lus if int(l["decisions"]) == 0)))
    return L


def principal() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default=os.path.join(RACINE, "banc-ouvert", "sources"))
    p.add_argument("--sortie", default=os.path.join(RACINE, "banc-ouvert"))
    p.add_argument("--sans-semantique", action="store_true")
    p.add_argument("--limite", type=int, default=0, help="ne traiter que N modèles (essai)")
    args = p.parse_args()
    chemins = sorted(glob.glob(os.path.join(args.sources, "**", "*.bpmn"), recursive=True))
    if not chemins:
        print("aucun modèle dans", args.sources, "(lancer outils/telecharger-banc.py)")
        return 1
    if args.limite:
        chemins = chemins[:args.limite]
    avec_semantique = not args.sans_semantique and semantique.disponible()
    if not args.sans_semantique and not avec_semantique:
        print(semantique.motif_indisponible(), "-> variante de référence seulement")
    os.makedirs(args.sortie, exist_ok=True)
    lignes = []
    depart = time.perf_counter()
    for i, c in enumerate(chemins, start=1):
        lignes.extend(_mesurer_modele(c, args.sources, avec_semantique))
        if i % 250 == 0 or i == len(chemins):
            print("  %d / %d modèles (%.0f s)" % (i, len(chemins), time.perf_counter() - depart))
    chemin_csv = os.path.join(args.sortie, "resultats.csv")
    with open(chemin_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        colonnes = COLONNES_BANC + NOMS_COLONNES
        w.writerow(colonnes)
        for l in lignes:
            w.writerow([l.get(c, "") for c in colonnes])
    print("résultats :", chemin_csv)

    ref = [l for l in lignes if l["variante"] == "reference"]
    lus = [l for l in ref if l["lu"] == 1]
    echecs = [l for l in ref if l["lu"] != 1]
    etendue = [l for l in lignes if l["variante"] == "extensions:definition-etendue" and l["lu"] == 1]
    sem = [l for l in lignes if "indice-semantique" in l["variante"] and l["lu"] == 1]
    L = ["# Banc d'essai ouvert : synthèse", "",
         "Modèles : %d (%d lus, %d en échec de lecture) ; durée totale %.0f s."
         % (len(ref), len(lus), len(echecs), time.perf_counter() - depart),
         "Variantes : référence et « definition-etendue » sur tous les modèles lus ; "
         "« definition-etendue + indice-semantique » : %s." % (
             "oui" if sem else "non (modèle de langue absent ou désactivé)"),
         ""]
    L += ["## Robustesse de la chaîne (variante de référence)", "",
          "| contrôle | modèles concernés | conformes | taux |", "|---|---|---|---|"]
    for cle, titre, concernes in (
            ("invariants_violes", "invariants 8/8 respectés", lambda l: True),
            ("dmn_relu_conforme", "DMN produit relu conforme", lambda l: True),
            ("acyclique", "DRD sans circuit", lambda l: True),
            ("aller_retour", "aller-retour T(T⁻¹(M)) = M", lambda l: l["aller_retour"] != ""),
            ("determinisme", "deux exécutions identiques", lambda l: True)):
        base = [l for l in lus if concernes(l)]
        if cle == "invariants_violes":
            ok = sum(1 for l in base if int(l[cle]) == 0)
        else:
            ok = sum(1 for l in base if str(l[cle]) == "1")
        L.append("| %s | %d | %d | %s %% |" % (titre, len(base), ok, _pct(ok, len(base))))
    L += ["", "Durée moyenne d'une extraction complète : %s ms (maximum %s ms)." % (
        _moy([l["duree_totale_ms"] for l in lus]),
        max((float(l["duree_totale_ms"]) for l in lus), default=0)), ""]
    L += ["## Variante de référence", ""]
    L += _tableau(lus, "collection", "Par collection") + [""]
    L += _tableau([l for l in lus if l["collection"] == "bfr"], "langue",
                  "bpmn-for-research, par langue du cours") + [""]
    L += ["## Variante « definition-etendue »", "",
          "Les activités de tout type sont candidates dès qu'un indice les corrobore ; "
          "retenues avec les deux indices, soumises à l'expert avec un seul. Les colonnes "
          "« position seule », « lexique seul » et « deux » comptent les décisions retenues "
          "selon les indices de la définition de référence ; « non corroborés » compte les "
          "candidats soumis à l'expert.", ""]
    L += _tableau(etendue, "collection", "Par collection") + [""]
    L += _tableau([l for l in etendue if l["collection"] == "bfr"], "langue",
                  "bpmn-for-research, par langue du cours") + [""]
    L += _tableau([l for l in etendue if l["collection"] == "bfr"], "exercice",
                  "bpmn-for-research, par exercice") + [""]
    L += _tableau([l for l in etendue if l["collection"] == "bfr"], "genre",
                  "bpmn-for-research, diagrammes des participants et corrigés") + [""]
    L += ["### Robustesse de la chaîne avec « definition-etendue »", "",
          "| contrôle | modèles concernés | conformes | taux |", "|---|---|---|---|"]
    for cle, titre, concernes in (
            ("invariants_violes", "invariants 8/8 respectés", lambda l: True),
            ("dmn_relu_conforme", "DMN produit relu conforme", lambda l: True),
            ("acyclique", "DRD sans circuit", lambda l: True),
            ("aller_retour", "aller-retour T(T⁻¹(M)) = M (modèles avec décision)",
             lambda l: l["aller_retour"] != ""),
            ("determinisme", "deux exécutions identiques", lambda l: True)):
        base = [l for l in etendue if concernes(l)]
        ok = sum(1 for l in base if int(l[cle]) == 0) if cle == "invariants_violes" \
            else sum(1 for l in base if str(l[cle]) == "1")
        L.append("| %s | %d | %d | %s %% |" % (titre, len(base), ok, _pct(ok, len(base))))
    L.append("")
    pe_e = [int(l["points_expert"]) for l in etendue]
    qpd_e = [float(l["questions_par_decision"]) for l in etendue if l["questions_par_decision"] != ""]
    L += ["Charge laissée à l'expert avec « definition-etendue » : points soumis par modèle, "
          "moyenne %s, médiane %s, maximum %d ; questions par décision inférée : moyenne %s, "
          "médiane %s ; modèles avec au moins une décision : %d sur %d."
          % (_moy(pe_e), statistics.median(pe_e) if pe_e else "-", max(pe_e) if pe_e else 0,
             _moy(qpd_e), ("%.2f" % statistics.median(qpd_e)) if qpd_e else "-",
             sum(1 for l in etendue if int(l["decisions"]) > 0), len(etendue)), ""]
    # types d'activités : la définition de référence (tâches utilisateur, de règle métier)
    types = Counter()
    for l in lus:
        types["userTask"] += int(l["activites_utilisateur"])
        types["businessRuleTask"] += int(l["activites_regle_metier"])
        types["task"] += int(l["activites_generiques"])
        types["serviceTask"] += int(l["activites_service"])
        types["autres"] += int(l["activites_autres"])
    total_act = sum(types.values())
    L += ["## Types d'activités rencontrés", "",
          "| type | activités | part |", "|---|---|---|"]
    for t, n in types.most_common():
        L.append("| %s | %d | %s %% |" % (t, n, _pct(n, total_act)))
    L += ["", "La définition de référence des candidats (tâches utilisateur, tâches de règle "
          "métier, sous-processus repliés) ne couvre que %s %% des activités de ces collections, "
          "où la tâche générique domine ; les activités hors définition corroborées par un indice "
          "sont comptées à part (colonne « hors définition corroborées »), l'extension "
          "« definition-etendue » les retient." % _pct(types["userTask"] + types["businessRuleTask"],
                                                     total_act), ""]
    # charge laissée à l'expert
    pe = [int(l["points_expert"]) for l in lus]
    qpd = [float(l["questions_par_decision"]) for l in lus if l["questions_par_decision"] != ""]
    L += ["## Charge laissée à l'expert (variante de référence)", "",
          "Points soumis à l'expert par modèle : moyenne %s, médiane %s, maximum %d ; "
          "questions par décision inférée (modèles avec au moins une décision) : moyenne %s, "
          "médiane %s." % (_moy(pe), statistics.median(pe) if pe else "-", max(pe) if pe else 0,
                           _moy(qpd), ("%.2f" % statistics.median(qpd)) if qpd else "-"), ""]
    dist = Counter(min(int(l["points_expert"]), 10) for l in lus)
    L += ["| points soumis à l'expert | modèles |", "|---|---|"]
    for k in range(0, 11):
        if dist.get(k):
            L.append("| %s | %d |" % ("10 et plus" if k == 10 else k, dist[k]))
    L.append("")
    if sem:
        L += ["## Variante « definition-etendue + indice-semantique »", "",
              "L'indice sémantique ne retient jamais seul : il propose. Sur une activité "
              "hors définition, il compte comme second indice avec la position. Les colonnes "
              "donnent, par langue, les activités que le modèle de langue juge décisionnelles, "
              "les candidats que le seul indice sémantique propose à l'expert, et l'effet sur "
              "les décisions retenues et les points soumis à l'expert.", "",
              "| collection / langue | modèles | activités | jugées décisionnelles par l'indice | candidats DA | proposés par le seul indice sémantique | décisions retenues (étendue) | décisions retenues (étendue + sémantique) | points expert (étendue) | points expert (étendue + sémantique) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for cle in ("bfr/EN", "bfr/DE", "miwg"):
            def groupe(liste):
                return [l for l in liste if (l["collection"] + "/" + l["langue"]
                                             if l["collection"] == "bfr" else l["collection"]) == cle]
            G, E = groupe(sem), groupe(etendue)
            L.append("| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
                cle, len(G), sum(int(l["activites"]) for l in G),
                sum(int(l["activites_semantique"] or 0) for l in G),
                sum(int(l["da_candidats"]) for l in G),
                sum(int(l["da_semantique_seul"] or 0) for l in G),
                sum(int(l["decisions"]) for l in E), sum(int(l["decisions"]) for l in G),
                sum(int(l["points_expert"]) for l in E), sum(int(l["points_expert"]) for l in G)))
        L.append("")
    if echecs:
        motifs = Counter(l["erreur"].split(":")[0] for l in echecs)
        L += ["## Modèles non lus", "", "| motif | modèles |", "|---|---|"]
        for m, n in motifs.most_common():
            L.append("| %s | %d |" % (m, n))
        L.append("")
    chemin_md = os.path.join(args.sortie, "synthese.md")
    with open(chemin_md, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("synthèse :", chemin_md)
    print("\n".join(L[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
