# -*- coding: utf-8 -*-
"""Capture d'écran headless d'un fichier DMN rendu par dmn-js.
Usage : python outils/capturer_dmn.py <fichier.dmn> <capture.png>"""
import io
import json
import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

fichier = sys.argv[1]
capture = os.path.abspath(sys.argv[2])
dmn = io.open(os.path.join(RACINE, fichier), encoding="utf-8").read()

page = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="lib/dmn-js-shared.css">
<link rel="stylesheet" href="lib/dmn-js-drd.css">
<style>.dmn-definitions{display:none!important}</style></head>
<body style="margin:0"><div id="d" style="width:1580px;height:980px"></div>
<script src="lib/dmn-navigated-viewer.min.js"></script>
<script>
const DMN = %s;
(async () => {
  try {
    const v = new DmnJS({container: "#d"});
    await v.importXML(DMN);
    const av = v.getActiveViewer();
    if (av && av.get) av.get("canvas").zoom("fit-viewport", "auto");
    document.title = "RENDU-OK";
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
""" % json.dumps(dmn)
chemin_page = os.path.join(RACINE, "ui", "capture-tmp.html")
io.open(chemin_page, "w", encoding="utf-8").write(page)

subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                "--allow-file-access-from-files",
                "--window-size=1600,1000", "--virtual-time-budget=12000",
                "--screenshot=" + capture, chemin_page],
               capture_output=True)
print("capture :", capture)
