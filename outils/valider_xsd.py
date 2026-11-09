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

# 5. les BPMN mis à jour par la co-évolution (version 1.2) : sur chaque jeu
# d'essai Camunda (fichiers conformes au schéma), la première décision est
# renommée, une donnée et une source nouvelles lui sont ajoutées, une décision
# nouvelle qui la requiert est insérée, la première règle de sa table est
# écrite ; le BPMN mis à jour doit rester conforme et redonner le DRD modifié
from bpmn2dmn import coevolution
from bpmn2dmn.metamodeles import DECISION
for chemin in sorted(glob.glob(os.path.join(RACINE, "jeux-test-camunda", "*.bpmn"))):
    texte = io.open(chemin, encoding="utf-8").read()
    mf0 = transformer(parser_bpmn(chemin), extensions={"logique"})
    if not mf0.decisions:
        continue
    d0 = mf0.decisions[0]
    dmn0 = serialiser_dmn(mf0)
    valider(dmn0, XSD_DMN, "dmn", "DRD avec trace et tables de " + os.path.basename(chemin))
    dmn1 = dmn0.replace('<decision id="%s" name=%s>' % (d0.id, '"%s"' % d0.nom),
                        '<decision id="%s" name="%s (revue)">'
                        '<informationRequirement id="irN"><requiredInput href="#InputData_nouvelle"/>'
                        '</informationRequirement>'
                        '<authorityRequirement id="arN"><requiredAuthority href="#KnowledgeSource_manuel"/>'
                        '</authorityRequirement>' % (d0.id, d0.nom), 1)
    dmn1 = dmn1.replace(
        '<dmndi:DMNDI>',
        '<inputData id="InputData_nouvelle" name="Avis du service juridique"/>'
        '<knowledgeSource id="KnowledgeSource_manuel" name="Manuel de procédure"/>'
        '<decision id="Decision_nouvelle" name="Apprécier le risque du dossier">'
        '<informationRequirement id="irZ"><requiredDecision href="#%s"/>'
        '</informationRequirement></decision><dmndi:DMNDI>' % d0.id)
    if d0.id in mf0.logique and mf0.logique[d0.id]["entrees"]:
        dmn1 = dmn1.replace('<inputEntry id="%s_regle1_e1"><text>-</text></inputEntry>' % d0.id,
                            '<inputEntry id="%s_regle1_e1"><text>"complet"</text></inputEntry>' % d0.id)
    bpmn_sync, _, rapport_sync = coevolution.synchroniser(texte, dmn1, Arbitrages(), {"logique"})
    valider(bpmn_sync, XSD_BPMN, "bpmn", "co-évolution sur " + os.path.basename(chemin))
    if not rapport_sync.coherent:
        echecs.append(("bpmn", "cohérence de la co-évolution sur " + os.path.basename(chemin),
                       rapport_sync.ecarts))

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
