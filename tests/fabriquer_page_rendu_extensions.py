# -*- coding: utf-8 -*-
"""Fabrique ui/test-rendu-extensions.html : vérification headless du rendu
d'un DMN produit avec toutes les extensions de l'algorithme (tables de
décision squelettes, données d'entrée P7 après arbitrage).

Le DMN est celui du modèle corpus/credit-bancaire.bpmn. Le <title> de la
page reçoit « RENDU-OK dmn=<formes> vues=drd,decisionTable,... » si dmn-js
importe le fichier et ouvre les tables, « RENDU-ECHEC <message> » sinon.

    python tests/fabriquer_page_rendu_extensions.py
    msedge --headless=new --disable-gpu --allow-file-access-from-files
           --virtual-time-budget=8000 --dump-dom file:///.../ui/test-rendu-extensions.html
"""
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
from bpmn2dmn.extensions import TOUTES
from bpmn2dmn.qualification import Arbitrages

mi = parser_bpmn(os.path.join(RACINE, "corpus", "credit-bancaire.bpmn"))
premier = transformer(mi, extensions=TOUTES)
arbitrages = Arbitrages.depuis_json({"annotations": {
    p.cle: "I" for p in premier.a_confirmer if p.categorie == "condition"}})
dmn = serialiser_dmn(transformer(mi, arbitrages, TOUTES))

page = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="lib/dmn-js-shared.css">
<link rel="stylesheet" href="lib/dmn-js-drd.css"></head><body>
<div id="d" style="width:1400px;height:800px"></div>
<script src="lib/bpmn-navigated-viewer.min.js"></script>
<script src="lib/dmn-navigated-viewer.min.js"></script>
<script>
const DMN = %s;
(async () => {
  try {
    const vd = new DmnJS({container: "#d"});
    await vd.importXML(DMN);
    const nb = document.querySelectorAll("#d .djs-shape").length;
    const vues = vd.getViews().map(v => v.type).join(",");
    document.title = "RENDU-OK dmn=" + nb + " vues=" + vues;
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
""" % json.dumps(dmn)

sortie = os.path.join(RACINE, "ui", "test-rendu-extensions.html")
io.open(sortie, "w", encoding="utf-8").write(page)
print("page de test écrite :", sortie, "(%d table(s) de décision)"
      % dmn.count("<decisionTable"))
