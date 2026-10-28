# -*- coding: utf-8 -*-
"""Fabrique ui/test-rendu.html : page de vérification headless du rendu.

Embarque le DRD produit (essais/fimex.drd.dmn) et le BPMN inverse
(essais/fimex.inverse.bpmn) puis les fait importer par dmn-js et bpmn-js.
Le résultat est écrit dans le <title> : « RENDU-OK dmn=<n> bpmn=<m> »
(nombre de formes dessinées) ou « RENDU-ECHEC <message> ».
"""
import io
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)

dmn = io.open(os.path.join(RACINE, "essais", "fimex.drd.dmn"),
              encoding="utf-8").read()
bpmn = io.open(os.path.join(RACINE, "essais", "fimex.inverse.bpmn"),
               encoding="utf-8").read()

page = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="lib/dmn-js-shared.css">
<link rel="stylesheet" href="lib/dmn-js-drd.css"></head><body>
<div id="d" style="width:1400px;height:800px"></div>
<div id="b" style="width:1400px;height:600px"></div>
<script src="lib/bpmn-navigated-viewer.min.js"></script>
<script src="lib/dmn-navigated-viewer.min.js"></script>
<script>
const DMN = %s;
const BPMN = %s;
(async () => {
  try {
    const vd = new DmnJS({container: "#d"});
    await vd.importXML(DMN);
    const nb = document.querySelectorAll("#d .djs-shape").length;
    const vb = new BpmnJS({container: "#b"});
    await vb.importXML(BPMN);
    const nb2 = document.querySelectorAll("#b .djs-shape").length;
    document.title = "RENDU-OK dmn=" + nb + " bpmn=" + nb2;
  } catch (e) { document.title = "RENDU-ECHEC " + (e.message || e); }
})();
</script></body></html>
""" % (json.dumps(dmn), json.dumps(bpmn))

sortie = os.path.join(RACINE, "ui", "test-rendu.html")
io.open(sortie, "w", encoding="utf-8").write(page)
print("page de test écrite :", sortie)
