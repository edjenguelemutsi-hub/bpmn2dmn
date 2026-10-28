# -*- coding: utf-8 -*-
"""Vérifie que chaque fichier de jeux-test-camunda/ s'importe sans erreur
dans bpmn-js (titre RENDU-OK) : contrôle headless en lot."""
import glob
import io
import json
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

echecs = 0
for chemin in sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda",
                                            "*.bpmn"))):
    bpmn = io.open(chemin, encoding="utf-8").read()
    page = ('<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
            '<div id="b" style="width:1500px;height:900px"></div>'
            '<script src="lib/bpmn-navigated-viewer.min.js"></script>'
            '<script>const B=%s;(async()=>{try{const v=new BpmnJS('
            '{container:"#b"});const r=await v.importXML(B);'
            'document.title="RENDU-OK "+(r.warnings||[]).length+" avert";}'
            'catch(e){document.title="RENDU-ECHEC "+(e.message||e);}})();'
            '</script></body></html>' % json.dumps(bpmn))
    ptmp = os.path.join(RACINE, "ui", "capture-tmp.html")
    io.open(ptmp, "w", encoding="utf-8").write(page)
    res = subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                          "--allow-file-access-from-files",
                          "--virtual-time-budget=10000", "--dump-dom", ptmp],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    m = re.search(r"<title>([^<]*)</title>", res.stdout or "")
    verdict = m.group(1) if m else "pas de titre"
    print("%-38s %s" % (os.path.basename(chemin), verdict))
    if "RENDU-OK" not in verdict:
        echecs += 1
sys.exit(1 if echecs else 0)
