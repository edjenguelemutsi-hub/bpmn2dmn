# -*- coding: utf-8 -*-
"""
Télécharge les deux collections ouvertes du banc d'essai dans
`banc-ouvert/sources/` (non versionnées) : camunda/bpmn-for-research
(3 739 diagrammes, usage académique, lien à conserver) et les modèles de
référence du BPMN MIWG de l'OMG (22 modèles).

    python -X utf8 outils/telecharger-banc.py

Les chemins sont raccourcis (dossiers courts, fichier réduit à son
empreinte) pour rester sous la limite de longueur des chemins Windows ;
`bfr/correspondance.csv` garde le chemin d'origine de chaque fichier.
"""
import csv
import io
import os
import re
import sys
import zipfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(RACINE, "banc-ouvert", "sources")


def _court(nom_fichier):
    base = nom_fichier[:-5]
    m = re.search(r"([0-9a-f]{32})$", base)
    if m:
        return m.group(1)[:12] + ".bpmn"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", base)[:40] + ".bpmn"


def principal():
    import requests
    os.makedirs(SOURCES, exist_ok=True)
    dossier = os.path.join(SOURCES, "bfr")
    if not os.path.isdir(dossier):
        print("camunda/bpmn-for-research : téléchargement de l'archive...")
        r = requests.get("https://github.com/camunda/bpmn-for-research/archive/refs/heads/master.zip",
                         timeout=600)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        os.makedirs(dossier)
        lignes, n = [], 0
        for info in z.infolist():
            if not info.filename.endswith(".bpmn"):
                continue
            parties = info.filename.split("/")
            if len(parties) < 6:
                continue
            langue = {"English": "EN", "German": "DE"}.get(parties[2], parties[2][:2])
            genre = "solution" if parties[4].startswith("03") else (
                "resultats" if parties[4].startswith("02") else "autre")
            rel = os.path.join(langue, parties[3][:2], genre, _court(parties[-1]))
            cible = os.path.join(dossier, rel)
            k = 1
            while os.path.exists(cible):
                k += 1
                cible = os.path.join(dossier, rel[:-5] + "_%d.bpmn" % k)
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            with open(cible, "wb") as f:
                f.write(z.read(info))
            lignes.append((os.path.relpath(cible, dossier), info.filename))
            n += 1
        with open(os.path.join(dossier, "correspondance.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["chemin_local", "chemin_origine"])
            w.writerows(lignes)
        with open(os.path.join(dossier, "SOURCE.txt"), "w", encoding="utf-8") as f:
            f.write("https://github.com/camunda/bpmn-for-research (branche master)\n"
                    "Conditions d'utilisation : usage académique et de recherche seulement, "
                    "lien vers le dépôt à conserver, pas d'usage commercial.\n"
                    "%d fichiers .bpmn ; chemins d'origine dans correspondance.csv.\n"
                    "EN = cours en anglais, DE = cours en allemand ; 01 à 04 = les quatre exercices ; "
                    "resultats = diagrammes des participants, solution = corrigé.\n" % n)
        print(n, "modèles")
    else:
        print("déjà présent :", dossier)
    dossier = os.path.join(SOURCES, "miwg")
    if not os.path.isdir(dossier):
        os.makedirs(dossier)
        r = requests.get("https://api.github.com/repos/bpmn-miwg/bpmn-miwg-test-suite/git/trees/master?recursive=1",
                         timeout=120)
        r.raise_for_status()
        n = 0
        for x in r.json()["tree"]:
            p = x["path"]
            if p.startswith("Reference/") and p.endswith(".bpmn"):
                rr = requests.get("https://raw.githubusercontent.com/bpmn-miwg/bpmn-miwg-test-suite/master/" + p,
                                  timeout=120)
                rr.raise_for_status()
                with open(os.path.join(dossier, os.path.basename(p)), "wb") as f:
                    f.write(rr.content)
                n += 1
        with open(os.path.join(dossier, "SOURCE.txt"), "w", encoding="utf-8") as f:
            f.write("https://github.com/bpmn-miwg/bpmn-miwg-test-suite (dossier Reference)\n"
                    "Modèles de référence du BPMN Model Interchange Working Group de l'OMG ; %d fichiers.\n" % n)
        print(n, "modèles MIWG")
    else:
        print("déjà présent :", dossier)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
