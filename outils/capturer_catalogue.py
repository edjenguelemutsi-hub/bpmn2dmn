# -*- coding: utf-8 -*-
"""
Figures du catalogue de patterns : chaque diagramme BPMN et chaque DRD
produit sont rendus en headless par bpmn-js / dmn-js (les moteurs de
Camunda Modeler) et capturés en PNG dans `catalogue-patterns/figures/`.
Le rendu est contrôlé (titre « RENDU-OK », nombre d'avertissements) avant
la capture : un fichier qui ne s'importe pas proprement est signalé.

Usage :  python outils/capturer_catalogue.py [motif]
         (motif facultatif : « A0 », « B07 »… pour ne capturer qu'une partie)
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
DOSSIER = os.path.join(RACINE, "catalogue-patterns")
FIGURES = os.path.join(DOSSIER, "figures")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PAGE_TMP = os.path.join(RACINE, "ui", "capture-tmp.html")

PAGE_BPMN = """<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#fff"><div id="b" style="width:%dpx;height:%dpx"></div>
<script src="lib/bpmn-navigated-viewer.min.js"></script>
<script>
const BPMN = %s;
(async () => {
  try {
    const v = new BpmnJS({container: "#b"});
    const r = await v.importXML(BPMN);
    v.get("canvas").zoom("fit-viewport", "auto");
    document.title = "RENDU-OK " + (r.warnings || []).length + " avert";
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
"""

PAGE_DMN = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="lib/dmn-js-shared.css">
<link rel="stylesheet" href="lib/dmn-js-drd.css">
<style>.dmn-definitions{display:none!important}</style></head>
<body style="margin:0;background:#fff"><div id="d" style="width:%dpx;height:%dpx"></div>
<script src="lib/dmn-navigated-viewer.min.js"></script>
<script>
const DMN = %s;
(async () => {
  try {
    const v = new DmnJS({container: "#d"});
    const r = await v.importXML(DMN);
    const av = v.getActiveViewer();
    if (av && av.get) av.get("canvas").zoom("fit-viewport", "auto");
    document.title = "RENDU-OK " + (r.warnings || []).length + " avert";
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
"""


def _taille(texte: str, genre: str):
    """Une fenêtre proportionnée au diagramme, pour des figures lisibles."""
    if genre == "bpmn":
        m = re.search(r'bpmnElement="Pool_1"[^>]*><dc:Bounds x="\d+" y="\d+" '
                      r'width="(\d+)" height="(\d+)"', texte)
        pools = texte.count('bpmnElement="Pool_')
        if m:
            w = int(m.group(1)) + 80
            h = int(m.group(2)) * pools + 80 + (70 if pools > 1 else 0)
            return max(700, min(w, 1900)), max(360, min(h, 1100))
        return 1400, 700
    return 900, 520


def rendre(texte: str, genre: str, capture: str) -> str:
    w, h = _taille(texte, genre)
    page = (PAGE_BPMN if genre == "bpmn" else PAGE_DMN) % (w, h, json.dumps(texte))
    io.open(PAGE_TMP, "w", encoding="utf-8").write(page)
    res = subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                          "--allow-file-access-from-files", "--hide-scrollbars",
                          "--window-size=%d,%d" % (w, h),
                          "--virtual-time-budget=12000",
                          "--screenshot=" + capture, PAGE_TMP],
                         capture_output=True)
    res = subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                          "--allow-file-access-from-files",
                          "--virtual-time-budget=10000", "--dump-dom", PAGE_TMP],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    m = re.search(r"<title>([^<]*)</title>", res.stdout or "")
    return m.group(1) if m else "pas de titre"


def principal() -> int:
    motif = sys.argv[1] if len(sys.argv) > 1 else ""
    os.makedirs(FIGURES, exist_ok=True)
    echecs = 0
    for chemin in sorted(glob.glob(os.path.join(DOSSIER, "*.bpmn"))):
        nom = os.path.splitext(os.path.basename(chemin))[0]
        if motif and not nom.startswith(motif):
            continue
        verdict = rendre(io.open(chemin, encoding="utf-8").read(), "bpmn",
                         os.path.join(FIGURES, nom + ".bpmn.png"))
        print("%-46s %s" % (nom + ".bpmn", verdict))
        if "RENDU-OK 0" not in verdict:
            echecs += 1
        dmn = os.path.join(DOSSIER, "resultats", nom + ".drd.dmn")
        if os.path.exists(dmn):
            verdict = rendre(io.open(dmn, encoding="utf-8").read(), "dmn",
                             os.path.join(FIGURES, nom + ".drd.png"))
            print("%-46s %s" % (nom + ".drd.dmn", verdict))
            if "RENDU-OK 0" not in verdict:
                echecs += 1
    if os.path.exists(PAGE_TMP):
        os.remove(PAGE_TMP)
    print("\n%s" % ("toutes les figures rendues sans avertissement" if not echecs
                    else "%d rendu(s) à revoir" % echecs))
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
