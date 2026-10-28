# -*- coding: utf-8 -*-
"""
Validation de conformité contre les schémas XSD de l'OMG :
  - les DMN produits par le transformateur  -> DMN13.xsd (spéc. DMN 1.3)
  - les BPMN produits (inverse, jeux d'essai) -> BPMN20.xsd (spéc. BPMN 2.0)

Usage : python outils/valider_xsd.py
(nécessite lxml et build-xsd/ ; outil de contrôle du développeur, l'application
elle-même n'en a pas besoin et reste sans dépendance)
"""
import glob
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from lxml import etree

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.generateur import generer
from bpmn2dmn.miseenpage import ajouter_di

XSD_DMN = etree.XMLSchema(etree.parse(
    os.path.join(RACINE, "build-xsd", "dmn", "DMN13.xsd")))
XSD_BPMN = etree.XMLSchema(etree.parse(
    os.path.join(RACINE, "build-xsd", "bpmn", "BPMN20.xsd")))

echecs = []
compteurs = {"dmn": 0, "bpmn": 0}


def valider(texte: str, schema, genre: str, nom: str) -> None:
    compteurs[genre] += 1
    doc = etree.fromstring(texte.encode("utf-8"))
    if not schema.validate(doc):
        echecs.append((genre, nom,
                       [str(e) for e in schema.error_log[:3]]))


# 1. les DMN produits sur tous les corpus
for chemin in (sorted(glob.glob(os.path.join(RACINE, "corpus", "*.bpmn")))
               + sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda",
                                               "*.bpmn")))):
    mi = parser_bpmn(chemin)
    dmn = serialiser_dmn(transformer(mi))
    valider(dmn, XSD_DMN, "dmn", "DRD de " + os.path.basename(chemin))

# 1 bis. les mêmes corpus avec toutes les extensions de l'algorithme
# (tables de décision squelettes, P7 après arbitrage...)
from bpmn2dmn.extensions import TOUTES
from bpmn2dmn.qualification import Arbitrages
for chemin in (sorted(glob.glob(os.path.join(RACINE, "corpus", "*.bpmn")))
               + sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda",
                                               "*.bpmn")))
               + sorted(glob.glob(os.path.join(RACINE, "catalogue-patterns",
                                               "*.bpmn")))):
    mi = parser_bpmn(chemin)
    mf = transformer(mi, extensions=TOUTES)
    # les points « condition » sont arbitrés en données d'entrée pour
    # exercer P7 dans le document
    arb = Arbitrages.depuis_json({"annotations": {
        p.cle: "I" for p in mf.a_confirmer if p.categorie == "condition"}})
    dmn = serialiser_dmn(transformer(mi, arb, TOUTES))
    valider(dmn, XSD_DMN, "dmn", "DRD (extensions) de " + os.path.basename(chemin))

# 2. les DMN de 100 modèles générés
for graine in range(7000, 7100):
    bpmn, _ = generer(graine)
    dmn = serialiser_dmn(transformer(parser_bpmn(bpmn, est_texte=True)))
    valider(dmn, XSD_DMN, "dmn", "DRD graine %d" % graine)

# 3. les BPMN produits par l'inverse
from bpmn2dmn.inverse import inverser
for chemin in sorted(glob.glob(os.path.join(RACINE, "essais", "drd-jeux",
                                            "*.dmn"))):
    from bpmn2dmn.inverse import parser_dmn
    mf = parser_dmn(chemin)
    bpmn, _ = inverser(mf)
    valider(bpmn, XSD_BPMN, "bpmn",
            "inverse de " + os.path.basename(chemin))

# 4. les BPMN des jeux d'essai + mise en page auto
for chemin in sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda",
                                            "*.bpmn"))):
    valider(io.open(chemin, encoding="utf-8").read(), XSD_BPMN, "bpmn",
            os.path.basename(chemin))
bpmn_gen, _ = generer(4242)
valider(ajouter_di(bpmn_gen), XSD_BPMN, "bpmn",
        "modèle généré + mise en page auto")

# bilan
print("Validation XSD OMG : %d documents DMN 1.3, %d documents BPMN 2.0"
      % (compteurs["dmn"], compteurs["bpmn"]))
if not echecs:
    print("Tous les documents sont conformes aux schémas de l'OMG.")
else:
    for genre, nom, erreurs in echecs:
        print(" ECHEC [%s] %s" % (genre.upper(), nom))
        for e in erreurs:
            print("      " + e[:150])
    print(" %d document(s) non conforme(s)." % len(echecs))
sys.exit(1 if echecs else 0)
