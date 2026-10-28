# -*- coding: utf-8 -*-
"""
Le registre des expérimentations : une ligne par extraction, écrite
automatiquement.

Chaque fois qu'un modèle BPMN est transformé (ligne de commande,
application web, validation du corpus, catalogue de patterns), le registre
ajoute une ligne au fichier `registre.csv` du dossier des expérimentations
et régénère le classeur `registre.xlsx` (trois feuilles : les
expérimentations, une synthèse, le dictionnaire des colonnes). La ligne
porte le code de référence du modèle et toutes les grandeurs de
`metriques.COLONNES`. Le DRD produit, le rapport et le modèle source sont
conservés dans `sorties/` sous le numéro de l'expérience, pour que chaque
ligne reste vérifiable.

Le dossier est `transformateur/experimentations/` (à côté de l'exécutable
en version autonome) ; la variable d'environnement BPMN2DMN_REGISTRE le
déplace, BPMN2DMN_SANS_REGISTRE=1 suspend l'enregistrement.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional

from . import __version__
from .classeur import ecrire_classeur
from .metamodeles import Mf, Mi
from .metriques import COLONNES, NOMS_COLONNES, mesurer

NOM_CSV = "registre.csv"
NOM_XLSX = "registre.xlsx"
NOM_CAMPAGNES = "campagnes.csv"
NOM_DICTIONNAIRE = "dictionnaire-colonnes.md"
SEPARATEUR = ";"

COLONNES_CAMPAGNES = ("horodatage", "contexte", "graine_debut", "modeles",
                      "modeles_verifies", "decisions", "exigences",
                      "points_expert", "divergences", "duree_s", "processus",
                      "version")

_verrou_processus = threading.Lock()


def desactive() -> bool:
    return os.environ.get("BPMN2DMN_SANS_REGISTRE", "").strip().lower() in (
        "1", "oui", "true", "yes")


def dossier_par_defaut() -> str:
    env = os.environ.get("BPMN2DMN_REGISTRE", "").strip()
    if env:
        return env
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                            "experimentations")
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(racine, "experimentations")


def abreger(nom: str, longueur: int = 24) -> str:
    """Un nom de fichier ramené à des lettres, chiffres et tirets."""
    base = os.path.splitext(os.path.basename(nom or ""))[0]
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower()
    return (base or "modele")[:longueur].rstrip("-")


def empreinte(texte: str) -> str:
    """Empreinte SHA-256 abrégée du contenu, fins de ligne normalisées."""
    normalise = (texte or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()[:8]


def code_modele(nom: str, texte: str) -> str:
    return "%s-%s" % (abreger(nom), empreinte(texte))


def _signature(mi: Mi) -> str:
    """À défaut du texte BPMN, une description canonique de Mi."""
    parts = [mi.nom]
    parts.extend("%s|%s|%s|%s" % (n.id, n.type, n.nom, n.ressource or "")
                 for n in sorted(mi.noeuds.values(), key=lambda n: n.id))
    parts.extend("%s|%s|%s" % (d.id, d.categorie, d.nom)
                 for d in sorted(mi.donnees.values(), key=lambda d: d.id))
    parts.extend("%s>%s" % (s, t) for s, t, _ in sorted(mi.flux_sequence))
    parts.extend("%s~%s" % (s, t) for s, t in sorted(mi.flux_donnees))
    return "\n".join(parts)


def _nombre_arbitrages(arbitrages) -> int:
    if arbitrages is None:
        return 0
    return sum(len(getattr(arbitrages, champ, {}) or {})
               for champ in ("candidats", "ressources", "annotations", "renommages"))


def _valeur_csv(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _valeur_typee(s: str):
    """Relecture d'une cellule CSV : entier, décimal ou texte."""
    if s is None or s == "":
        return ""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


class _Verrou:
    """Verrou de fichier portable : plusieurs processus (application web,
    ligne de commande, campagne) peuvent écrire dans le même registre."""

    def __init__(self, chemin: str, attente: float = 10.0):
        self.chemin = chemin
        self.attente = attente
        self.fd = None

    def __enter__(self):
        _verrou_processus.acquire()
        limite = time.time() + self.attente
        while True:
            try:
                self.fd = os.open(self.chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.chemin) > 60:
                        os.remove(self.chemin)           # verrou abandonné
                        continue
                except OSError:
                    pass
                if time.time() > limite:
                    _verrou_processus.release()
                    raise TimeoutError("registre verrouillé : " + self.chemin)
                time.sleep(0.025)

    def __exit__(self, *exc):
        try:
            if self.fd is not None:
                os.close(self.fd)
            os.remove(self.chemin)
        except OSError:
            pass
        _verrou_processus.release()


class Registre:
    """Le registre d'un dossier d'expérimentations."""

    def __init__(self, dossier: Optional[str] = None, conserver_sorties: bool = True):
        self.dossier = os.path.abspath(dossier or dossier_par_defaut())
        self.conserver_sorties = conserver_sorties
        self.chemin_csv = os.path.join(self.dossier, NOM_CSV)
        self.chemin_xlsx = os.path.join(self.dossier, NOM_XLSX)
        self.chemin_campagnes = os.path.join(self.dossier, NOM_CAMPAGNES)
        self.dossier_sorties = os.path.join(self.dossier, "sorties")

    # ------------------------------------------------------------------
    # enregistrement
    # ------------------------------------------------------------------
    def enregistrer(self, mi: Mi, mf: Mf, contexte: str, fichier: Optional[str] = None,
                    texte_bpmn: Optional[str] = None, arbitrages=None,
                    dmn: Optional[str] = None, rapport: Optional[dict] = None,
                    reference: Optional[List[str]] = None,
                    durees: Optional[Dict[str, float]] = None,
                    aller_retour: Optional[bool] = None,
                    variante: str = "reference",
                    nom: Optional[str] = None) -> "OrderedDict[str, object]":
        """Ajoute une ligne et retourne-la (identification comprise).
        `fichier` est un chemin (la référence experte .gold voisine est lue
        si elle existe) ; `nom` un simple nom d'affichage, quand le modèle
        arrive en mémoire (application web)."""
        chemin_source = fichier if fichier and os.path.isfile(fichier) else None
        if texte_bpmn is None and chemin_source:
            with open(chemin_source, encoding="utf-8", errors="replace") as f:
                texte_bpmn = f.read()
        if reference is None and chemin_source:
            reference = lire_reference(chemin_source)
        ligne = mesurer(mi, mf, arbitrages=arbitrages, reference=reference, dmn=dmn,
                        aller_retour=aller_retour, durees=durees)
        nom_affiche = nom or (os.path.basename(fichier) if fichier else (
            mi.source if mi.source and mi.source != "<mémoire>" else "<mémoire>"))
        code = code_modele(fichier or nom or mi.nom,
                           texte_bpmn if texte_bpmn is not None else _signature(mi))
        ligne["horodatage"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ligne["code_modele"] = code
        ligne["fichier"] = nom_affiche
        ligne["modele"] = mi.nom
        ligne["contexte"] = contexte
        ligne["arbitrages"] = _nombre_arbitrages(arbitrages)
        ligne["variante"] = variante or "reference"
        ligne["version"] = __version__

        os.makedirs(self.dossier, exist_ok=True)
        with _Verrou(os.path.join(self.dossier, "registre.verrou")):
            numero = self._prochain_numero()
            ligne["experience"] = "EXP-%06d" % numero
            self._ajouter_csv(ligne)
            if self.conserver_sorties:
                self._conserver(ligne["experience"], code, texte_bpmn, dmn, rapport)
            self.ecrire_excel()
            self._ecrire_dictionnaire()
        return ligne

    def journal_campagne(self, contexte: str, graine_debut: int, modeles: int,
                         modeles_verifies: int, decisions: int, exigences: int,
                         points_expert: int, divergences: int, duree_s: float,
                         processus: int = 1) -> dict:
        """Une campagne massive tient en une ligne de `campagnes.csv` : ses
        millions de modèles n'ont pas leur place dans le registre détaillé."""
        ligne = OrderedDict([
            ("horodatage", datetime.now().strftime("%Y-%m-%dT%H:%M:%S")),
            ("contexte", contexte), ("graine_debut", graine_debut),
            ("modeles", modeles), ("modeles_verifies", modeles_verifies),
            ("decisions", decisions), ("exigences", exigences),
            ("points_expert", points_expert), ("divergences", divergences),
            ("duree_s", round(duree_s, 1)), ("processus", processus),
            ("version", __version__)])
        os.makedirs(self.dossier, exist_ok=True)
        with _Verrou(os.path.join(self.dossier, "registre.verrou")):
            nouveau = not os.path.exists(self.chemin_campagnes)
            with open(self.chemin_campagnes, "a", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=SEPARATEUR, lineterminator="\n")
                if nouveau:
                    w.writerow(COLONNES_CAMPAGNES)
                w.writerow([_valeur_csv(ligne[c]) for c in COLONNES_CAMPAGNES])
            self.ecrire_excel()
        return ligne

    def _prochain_numero(self) -> int:
        if not os.path.exists(self.chemin_csv):
            return 1
        dernier = 0
        with open(self.chemin_csv, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f, delimiter=SEPARATEUR):
                if row and row[0].startswith("EXP-"):
                    try:
                        dernier = max(dernier, int(row[0][4:]))
                    except ValueError:
                        pass
        return dernier + 1

    def _ajouter_csv(self, ligne) -> None:
        nouveau = True
        if os.path.exists(self.chemin_csv):
            with open(self.chemin_csv, encoding="utf-8-sig", newline="") as f:
                entete = next(csv.reader(f, delimiter=SEPARATEUR), [])
            if entete == NOMS_COLONNES:
                nouveau = False
            else:
                # colonnes d'une version antérieure : l'ancien fichier est
                # conservé sous un autre nom, rien n'est perdu
                horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
                os.replace(self.chemin_csv, os.path.join(
                    self.dossier, "registre-ancien-%s.csv" % horodatage))
        with open(self.chemin_csv, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=SEPARATEUR, lineterminator="\n")
            if nouveau:
                w.writerow(NOMS_COLONNES)
            w.writerow([_valeur_csv(ligne[c]) for c in NOMS_COLONNES])

    def _conserver(self, experience: str, code: str, texte_bpmn, dmn, rapport) -> None:
        os.makedirs(self.dossier_sorties, exist_ok=True)
        base = os.path.join(self.dossier_sorties, "%s_%s" % (experience, code))
        if dmn is not None:
            with open(base + ".drd.dmn", "w", encoding="utf-8") as f:
                f.write(dmn)
        if rapport is not None:
            with open(base + ".rapport.json", "w", encoding="utf-8") as f:
                json.dump(rapport, f, ensure_ascii=False, indent=2)
        if texte_bpmn is not None:
            with open(base + ".bpmn", "w", encoding="utf-8") as f:
                f.write(texte_bpmn)

    # ------------------------------------------------------------------
    # lecture et synthèse
    # ------------------------------------------------------------------
    def lignes(self) -> List["OrderedDict[str, object]"]:
        if not os.path.exists(self.chemin_csv):
            return []
        with open(self.chemin_csv, encoding="utf-8-sig", newline="") as f:
            lecteur = csv.reader(f, delimiter=SEPARATEUR)
            entete = next(lecteur, [])
            return [OrderedDict(zip(entete, [_valeur_typee(v) for v in row]))
                    for row in lecteur if row]

    def campagnes(self) -> List["OrderedDict[str, object]"]:
        if not os.path.exists(self.chemin_campagnes):
            return []
        with open(self.chemin_campagnes, encoding="utf-8-sig", newline="") as f:
            lecteur = csv.reader(f, delimiter=SEPARATEUR)
            entete = next(lecteur, [])
            return [OrderedDict(zip(entete, [_valeur_typee(v) for v in row]))
                    for row in lecteur if row]

    def synthese(self) -> dict:
        lignes = self.lignes()
        contextes: Dict[str, int] = {}
        modeles = set()
        for l in lignes:
            contextes[str(l.get("contexte", ""))] = contextes.get(str(l.get("contexte", "")), 0) + 1
            modeles.add(l.get("code_modele"))
        return {
            "nombre": len(lignes),
            "modeles_distincts": len(modeles),
            "par_contexte": contextes,
            "moyennes": {c: _moyenne(lignes, c) for c in (
                "decisions", "donnees_entree", "sources_connaissance", "bkm",
                "ef_exigences", "points_expert", "questions_par_decision",
                "taux_corroboration", "precision", "rappel", "duree_totale_ms")},
            "campagnes": len(self.campagnes()),
        }

    # ------------------------------------------------------------------
    # classeur Excel et dictionnaire
    # ------------------------------------------------------------------
    def ecrire_excel(self) -> str:
        lignes = self.lignes()
        largeurs = [16 if c in ("experience", "horodatage", "contexte", "variante")
                    else 28 if c in ("code_modele", "fichier", "modele")
                    else 11 for c in NOMS_COLONNES]
        feuilles = [
            ("Expérimentations", NOMS_COLONNES,
             [[l.get(c, "") for c in NOMS_COLONNES] for l in lignes], largeurs),
            ("Synthèse", ("grandeur", "nombre", "moyenne", "minimum", "maximum", "somme"),
             _lignes_synthese(lignes), [42, 10, 12, 12, 12, 12]),
            ("Dictionnaire", ("colonne", "groupe", "libellé", "définition"),
             [[c[0], c[1], c[2], c[3]] for c in COLONNES], [26, 26, 36, 90]),
        ]
        campagnes = self.campagnes()
        if campagnes:
            feuilles.append(("Campagnes", COLONNES_CAMPAGNES,
                             [[l.get(c, "") for c in COLONNES_CAMPAGNES] for l in campagnes],
                             [18] + [12] * (len(COLONNES_CAMPAGNES) - 1)))
        chemin_tmp = self.chemin_xlsx + ".tmp"
        ecrire_classeur(chemin_tmp, feuilles,
                        titre="Registre des expérimentations BPMN vers DMN",
                        auteur="Edjenguele Mutsi Francis Hervé")
        try:
            os.replace(chemin_tmp, self.chemin_xlsx)
        except PermissionError:
            # classeur ouvert dans Excel : une copie datée est déposée à côté
            os.replace(chemin_tmp, self.chemin_xlsx[:-5] + "-%s.xlsx"
                       % datetime.now().strftime("%Y%m%d-%H%M%S"))
        return self.chemin_xlsx

    def _ecrire_dictionnaire(self) -> None:
        chemin = os.path.join(self.dossier, NOM_DICTIONNAIRE)
        contenu = dictionnaire_markdown()
        if os.path.exists(chemin):
            with open(chemin, encoding="utf-8") as f:
                if f.read() == contenu:
                    return
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)


def _moyenne(lignes, colonne):
    valeurs = [l[colonne] for l in lignes
               if isinstance(l.get(colonne), (int, float)) and not isinstance(l.get(colonne), bool)]
    return round(sum(valeurs) / len(valeurs), 3) if valeurs else ""


def _lignes_synthese(lignes) -> List[List[object]]:
    out: List[List[object]] = [
        ["Expérimentations enregistrées", len(lignes), "", "", "", ""],
        ["Modèles distincts (codes de référence)",
         len({l.get("code_modele") for l in lignes}), "", "", "", ""],
    ]
    contextes: Dict[str, int] = {}
    for l in lignes:
        c = str(l.get("contexte", ""))
        contextes[c] = contextes.get(c, 0) + 1
    for c, n in sorted(contextes.items()):
        out.append(["  dont contexte « %s »" % c, n, "", "", "", ""])
    out.append(["", "", "", "", "", ""])
    for nom, groupe, libelle, _ in COLONNES:
        if nom in ("experience", "horodatage", "code_modele", "fichier", "modele",
                   "contexte", "variante", "version"):
            continue
        valeurs = [l[nom] for l in lignes
                   if isinstance(l.get(nom), (int, float)) and not isinstance(l.get(nom), bool)]
        if not valeurs:
            continue
        out.append(["%s : %s" % (groupe, libelle), len(valeurs),
                    round(sum(valeurs) / len(valeurs), 3), min(valeurs), max(valeurs),
                    round(sum(valeurs), 3)])
    return out


def dictionnaire_markdown() -> str:
    L = ["# Dictionnaire des colonnes du registre des expérimentations", "",
         "Chaque ligne de `registre.csv` (séparateur « ; », UTF-8, point décimal) et de la "
         "feuille « Expérimentations » de `registre.xlsx` décrit une extraction. "
         "Les colonnes suivent l'ordre ci-dessous. Une cellule vide signifie "
         "« non applicable » (par exemple : pas de référence experte).", ""]
    groupe_courant = None
    for nom, groupe, libelle, definition in COLONNES:
        if groupe != groupe_courant:
            L.append("")
            L.append("## " + groupe)
            L.append("")
            L.append("| Colonne | Libellé | Définition |")
            L.append("|---|---|---|")
            groupe_courant = groupe
        L.append("| `%s` | %s | %s |" % (nom, libelle.replace("|", "\\|"),
                                          definition.replace("|", "\\|")))
    L.append("")
    L.append("## Campagnes (`campagnes.csv`)")
    L.append("")
    L.append("Une ligne par campagne massive : " + ", ".join(
        "`%s`" % c for c in COLONNES_CAMPAGNES) + ".")
    L.append("")
    L.append("## Sorties conservées (`sorties/`)")
    L.append("")
    L.append("Pour chaque expérience `EXP-nnnnnn_<code>` : le modèle BPMN soumis (`.bpmn`), "
             "le DRD produit (`.drd.dmn`) et le rapport détaillé (`.rapport.json`).")
    L.append("")
    return "\n".join(L)


def lire_reference(chemin_bpmn: str) -> Optional[List[str]]:
    """Le fichier .gold voisin d'un modèle : les décisions attendues."""
    chemin = os.path.splitext(chemin_bpmn)[0] + ".gold"
    if not os.path.exists(chemin):
        return None
    with open(chemin, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def texte_synthese(registre: Registre) -> str:
    """La synthèse du registre, pour la console."""
    s = registre.synthese()
    L = ["Registre des expérimentations : %s" % registre.dossier,
         "  expérimentations enregistrées ... %d" % s["nombre"],
         "  modèles distincts ................ %d" % s["modeles_distincts"]]
    for c, n in sorted(s["par_contexte"].items()):
        L.append("    %-30s %d" % (c, n))
    if s["nombre"]:
        L.append("  moyennes par expérimentation")
        for cle, libelle in (("decisions", "décisions"),
                             ("donnees_entree", "données d'entrée"),
                             ("sources_connaissance", "sources de connaissance"),
                             ("bkm", "BKM"), ("ef_exigences", "exigences"),
                             ("points_expert", "points soumis à l'expert"),
                             ("questions_par_decision", "questions par décision"),
                             ("taux_corroboration", "taux de corroboration"),
                             ("precision", "précision (avec référence)"),
                             ("rappel", "rappel (avec référence)"),
                             ("duree_totale_ms", "durée totale (ms)")):
            L.append("    %-30s %s" % (libelle, s["moyennes"][cle]))
    if s["campagnes"]:
        L.append("  campagnes massives ............... %d" % s["campagnes"])
    L.append("  fichiers : %s, %s" % (NOM_CSV, NOM_XLSX))
    return "\n".join(L)
