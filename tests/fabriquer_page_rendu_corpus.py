# -*- coding: utf-8 -*-
"""Page de vérification headless pour un modèle du corpus :
usage : python tests/fabriquer_page_rendu_corpus.py corpus/credit-bancaire.bpmn
Produit ui/test-rendu-corpus.html (BPMN + DRD extrait côte à côte)."""
import io
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn

chemin = sys.argv[1] if len(sys.argv) > 1 else "corpus/credit-bancaire.bpmn"
bpmn = io.open(os.path.join(RACINE, chemin), encoding="utf-8").read()
mf = transformer(parser_bpmn(bpmn, est_texte=True))
dmn = serialiser_dmn(mf)

page = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="lib/dmn-js-shared.css">
<link rel="stylesheet" href="lib/dmn-js-drd.css"></head><body>
<div id="b" style="width:1450px;height:700px;border-bottom:2px solid #999"></div>
<div id="d" style="width:1450px;height:750px"></div>
<script src="lib/bpmn-navigated-viewer.min.js"></script>
<script src="lib/dmn-navigated-viewer.min.js"></script>
<script>
const BPMN = %s, DMN = %s;
(async () => {
  try {
    const vb = new BpmnJS({container: "#b"});
    await vb.importXML(BPMN);
    vb.get("canvas").zoom("fit-viewport", "auto");
    const vd = new DmnJS({container: "#d"});
    await vd.importXML(DMN);
    const av = vd.getActiveViewer();
    if (av && av.get) av.get("canvas").zoom("fit-viewport", "auto");
    document.title = "RENDU-OK";
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
""" % (json.dumps(bpmn), json.dumps(dmn))
io.open(os.path.join(RACINE, "ui", "test-rendu-corpus.html"),
        "w", encoding="utf-8").write(page)
print("OK :", chemin, "-", len(mf.decisions), "décisions")
