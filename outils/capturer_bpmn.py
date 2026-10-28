# -*- coding: utf-8 -*-
"""Capture d'écran headless d'un fichier BPMN rendu par bpmn-js.
Usage : python outils/capturer_bpmn.py <fichier.bpmn> <capture.png>"""
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
bpmn = io.open(os.path.join(RACINE, fichier), encoding="utf-8").read()

page = """<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0"><div id="b" style="width:1580px;height:980px"></div>
<script src="lib/bpmn-navigated-viewer.min.js"></script>
<script>
const BPMN = %s;
(async () => {
  try {
    const v = new BpmnJS({container: "#b"});
    await v.importXML(BPMN);
    v.get("canvas").zoom("fit-viewport", "auto");
    document.title = "RENDU-OK";
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
""" % json.dumps(bpmn)
chemin_page = os.path.join(RACINE, "ui", "capture-tmp.html")
io.open(chemin_page, "w", encoding="utf-8").write(page)

subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                "--allow-file-access-from-files",
                "--window-size=1600,1000", "--virtual-time-budget=12000",
                "--screenshot=" + capture, chemin_page],
               capture_output=True)
print("capture :", capture)
