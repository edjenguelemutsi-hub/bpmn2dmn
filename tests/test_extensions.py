# -*- coding: utf-8 -*-
"""
Tests des extensions de l'algorithme (bpmn2dmn/extensions.py) : chacune
sur un petit modèle construit pour elle, et la garantie que, sans
extension, l'algorithme de référence produit exactement les sorties
figées (corpus, jeux, FIMEX, BPCO).
"""
import glob
import hashlib
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer, _variables_condition
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import inverser, parser_dmn
from bpmn2dmn.qualification import Arbitrages, indice_gouvernance
from bpmn2dmn.extensions import (EXTENSIONS, TOUTES, normaliser_extensions,
                                 variante)
from bpmn2dmn.validation import (equivalents, verifier_dmn_serialise,
                                 verifier_invariants)

# empreintes des sorties de référence, relevées le 8 septembre 2026 avant
# l'introduction des extensions : l'algorithme sans extension doit les
# redonner à l'identique
EMPREINTES_REFERENCE = {
    "corpus/fimex.bpmn":
        "82c38d67359745c64ef273291d6da691cafae448a48a0962fd49d162c3374997",
    "corpus/copd.bpmn":
        "67d1ec5ee047c020fb5ba7968e59ffdce2366f732509e18841d5fc2bde1b81b4",
    "jeux-test-camunda/01-credit-bancaire.bpmn":
        "b77972258ca89b7642b07c8bf6b8022522494a81d6898c11cb36a720eb42b5fb",
}


def _bpmn(corps: str, nom: str = "Essai") -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" id="d" '
            'targetNamespace="http://essai">'
            '<bpmn:process id="p" name="%s">%s</bpmn:process></bpmn:definitions>'
            % (nom, corps))


def _flux(s, t, nom="", condition=""):
    cond = ('<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">%s'
            '</bpmn:conditionExpression>' % condition) if condition else ""
    return ('<bpmn:sequenceFlow id="f_%s_%s" sourceRef="%s" targetRef="%s"%s>%s'
            '</bpmn:sequenceFlow>' % (s, t, s, t, ' name="%s"' % nom if nom else "", cond))


def _empreinte(mf) -> str:
    r = {"dmn": serialiser_dmn(mf), "arcs": mf.arcs,
         "noeuds": [(n.id, n.type, n.nom, n.pattern) for n in mf.noeuds.values()],
         "pe": [p.as_tuple() for p in mf.a_confirmer],
         "ec": [p.as_tuple() for p in mf.ecartes]}
    return hashlib.sha256(json.dumps(r, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class TestRegistreDesExtensions(unittest.TestCase):
    def test_sept_extensions_nommees(self):
        self.assertEqual(len(EXTENSIONS), 7)
        for nom in EXTENSIONS:
            self.assertRegex(nom, r"^[a-z-]+$")
        self.assertEqual(normaliser_extensions("logique, noms-suggeres"),
                         frozenset({"logique", "noms-suggeres"}))
        self.assertEqual(normaliser_extensions("toutes"), TOUTES)
        self.assertEqual(normaliser_extensions(None), frozenset())
        self.assertEqual(normaliser_extensions("logique+conditions-passerelle"),
                         frozenset({"logique", "conditions-passerelle"}))
        with self.assertRaises(ValueError):
            normaliser_extensions("inconnue")
        self.assertEqual(variante(()), "reference")
        self.assertEqual(variante(["logique", "definition-etendue"]),
                         "extensions:definition-etendue+logique")


class TestSansExtensionReference(unittest.TestCase):
    """Sans extension, rien ne change : sorties identiques aux empreintes."""

    def test_empreintes_du_corpus(self):
        for rel, attendue in EMPREINTES_REFERENCE.items():
            mf = transformer(parser_bpmn(os.path.join(RACINE, rel)))
            self.assertEqual(mf.extensions, ())
            self.assertEqual(_empreinte(mf), attendue, rel)

    def test_champs_neutres_dans_le_rapport(self):
        from cli import rapport_json
        mf = transformer(parser_bpmn(os.path.join(RACINE, "corpus", "fimex.bpmn")))
        r = rapport_json(mf)
        for cle in ("extensions", "variante", "suggestions_noms", "logique"):
            self.assertNotIn(cle, r)


class TestDefinitionEtendue(unittest.TestCase):
    MODELE = _bpmn(
        '<bpmn:startEvent id="s"/>'
        '<bpmn:serviceTask id="t1" name="Contrôler la cohérence du dossier"/>'
        '<bpmn:exclusiveGateway id="g" name="Dossier cohérent ?"/>'
        '<bpmn:task id="t2" name="Instruire la demande"/>'
        '<bpmn:exclusiveGateway id="g2" name="Demande recevable ?"/>'
        '<bpmn:endEvent id="e"/><bpmn:endEvent id="e2"/><bpmn:endEvent id="e3"/>'
        + _flux("s", "t1") + _flux("t1", "g") + _flux("g", "t2", "oui")
        + _flux("g", "e2", "non") + _flux("t2", "g2") + _flux("g2", "e", "oui")
        + _flux("g2", "e3", "non"))

    def test_reference_signale_hors_definition(self):
        mf = transformer(parser_bpmn(self.MODELE, est_texte=True))
        self.assertEqual(mf.decisions, [])
        self.assertEqual({p.categorie for p in mf.a_confirmer}, {"hors-definition"})

    def test_deux_indices_retenus_un_indice_soumis(self):
        mf = transformer(parser_bpmn(self.MODELE, est_texte=True),
                         extensions={"definition-etendue"})
        self.assertEqual([d.nom for d in mf.decisions],
                         ["Contrôler la cohérence du dossier"])
        self.assertIn("definition-etendue", mf.motifs_corroboration["D1"])
        candidats = [p for p in mf.a_confirmer if p.categorie == "candidat"]
        self.assertEqual([p.objet for p in candidats], ["Instruire la demande"])
        self.assertIn("hors de la définition", candidats[0].motif)
        self.assertEqual(mf.extensions, ("definition-etendue",))

    def test_arbitrage_retient_ou_ecarte(self):
        mi = parser_bpmn(self.MODELE, est_texte=True)
        mf = transformer(mi, Arbitrages.depuis_json({"candidats": {"t2": True}}),
                         {"definition-etendue"})
        self.assertEqual(len(mf.decisions), 2)
        mf = transformer(mi, Arbitrages.depuis_json({"candidats": {"t2": False}}),
                         {"definition-etendue"})
        self.assertEqual(len(mf.decisions), 1)
        self.assertEqual([p.categorie for p in mf.ecartes], ["candidat"])


class TestConditionsPasserelle(unittest.TestCase):
    MODELE = _bpmn(
        '<bpmn:startEvent id="s"/>'
        '<bpmn:userTask id="t" name="Évaluer la demande"/>'
        '<bpmn:exclusiveGateway id="g" name="Montant élevé ?"/>'
        '<bpmn:exclusiveGateway id="g2" name="Pays à risque ?"/>'
        '<bpmn:endEvent id="e1"/><bpmn:endEvent id="e2"/><bpmn:endEvent id="e3"/>'
        + _flux("s", "t") + _flux("t", "g")
        + _flux("g", "e1", "faible", "${montant &lt;= 5000000}")
        + _flux("g", "g2", "élevé", "montant &gt; 5000000 and not(exonere)")
        + _flux("g2", "e2", "non", "not(dossier.paysARisque)")
        + _flux("g2", "e3", "oui", 'dossier.paysARisque = "oui"'))

    def test_variables_lues(self):
        self.assertEqual(_variables_condition('${montant > 5 and not(x)} or y = "a"'),
                         ["montant", "x", "y"])
        self.assertEqual(_variables_condition("contains(nom, 'a') and dossier.type"),
                         ["nom", "dossier.type"])
        self.assertEqual(_variables_condition(""), [])

    def test_conditions_lues_par_le_parseur(self):
        mi = parser_bpmn(self.MODELE, est_texte=True)
        self.assertEqual(mi.conditions[("g", "e1")], "${montant <= 5000000}")
        self.assertEqual(len(mi.conditions), 4)

    def test_proposees_puis_creees_apres_arbitrage(self):
        mi = parser_bpmn(self.MODELE, est_texte=True)
        ref = transformer(mi)
        self.assertEqual(ref.inputs, [])
        mf = transformer(mi, extensions={"conditions-passerelle"})
        self.assertEqual(mf.inputs, [])                  # rien sans arbitrage
        variables = [p.objet for p in mf.a_confirmer if p.categorie == "condition"]
        self.assertEqual(variables, ["montant", "exonere", "dossier.paysARisque"])
        self.assertTrue(all(p.proposition == "I" for p in mf.a_confirmer
                            if p.categorie == "condition"))
        arb = Arbitrages.depuis_json({"annotations": {
            "condition:montant": "I", "condition:dossier.paysARisque": "I",
            "condition:exonere": "non"}})
        mf = transformer(mi, arb, {"conditions-passerelle"})
        self.assertEqual([n.nom for n in mf.inputs], ["montant", "dossier.paysARisque"])
        self.assertEqual({mf.arcs_origine[a] for a in mf.arcs}, {"P7"})
        self.assertEqual([p.objet for p in mf.ecartes], ["exonere"])
        self.assertEqual(verifier_invariants(mf), [])
        dmn = serialiser_dmn(mf)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])

    def test_injectivite_par_variable(self):
        modele = _bpmn(
            '<bpmn:startEvent id="s"/>'
            '<bpmn:userTask id="t1" name="Évaluer la demande"/>'
            '<bpmn:exclusiveGateway id="g1"/>'
            '<bpmn:userTask id="t2" name="Statuer sur la demande"/>'
            '<bpmn:exclusiveGateway id="g2"/><bpmn:endEvent id="e"/>'
            '<bpmn:endEvent id="e2"/><bpmn:endEvent id="e3"/>'
            + _flux("s", "t1") + _flux("t1", "g1") + _flux("g1", "t2", "", "montant &gt; 1")
            + _flux("g1", "e2", "", "montant &lt;= 1") + _flux("t2", "g2")
            + _flux("g2", "e", "", "montant &gt; 2") + _flux("g2", "e3", "", "montant &lt;= 2"))
        arb = Arbitrages.depuis_json({"annotations": {"condition:montant": "I"}})
        mf = transformer(parser_bpmn(modele, est_texte=True), arb,
                         {"conditions-passerelle"})
        self.assertEqual(len(mf.inputs), 1)
        self.assertEqual(len(mf.arcs), 2)


class TestEvenementsConditionnelsEtDonneesProcessus(unittest.TestCase):
    CONDITIONNEL = _bpmn(
        '<bpmn:startEvent id="s"/>'
        '<bpmn:intermediateCatchEvent id="ev" name="Seuil atteint">'
        '<bpmn:conditionalEventDefinition id="cd"><bpmn:condition>x &gt; 3'
        '</bpmn:condition></bpmn:conditionalEventDefinition></bpmn:intermediateCatchEvent>'
        '<bpmn:userTask id="t" name="Évaluer la demande"/>'
        '<bpmn:boundaryEvent id="err" attachedToRef="t" name="Erreur">'
        '<bpmn:errorEventDefinition id="ed"/></bpmn:boundaryEvent>'
        '<bpmn:boundaryEvent id="tm" attachedToRef="t" cancelActivity="false" name="Délai">'
        '<bpmn:timerEventDefinition id="td"/></bpmn:boundaryEvent>'
        '<bpmn:endEvent id="e"/>'
        + _flux("s", "ev") + _flux("ev", "t") + _flux("t", "e"))

    def test_conditionnel_porteur_minuterie_et_erreur_non(self):
        mi = parser_bpmn(self.CONDITIONNEL, est_texte=True)
        self.assertEqual(mi.definitions_evenements["ev"], ["conditionalEventDefinition"])
        self.assertEqual(transformer(mi).inputs, [])
        mf = transformer(mi, extensions={"evenements-conditionnels"})
        self.assertEqual([n.nom for n in mf.inputs], ["Seuil atteint"])
        self.assertEqual(mf.inputs[0].pattern, "P3")
        self.assertFalse(mi.noeuds["ev"].porteur_donnees)   # le Mi lu reste intact

    def test_donnees_du_processus(self):
        modele = _bpmn(
            '<bpmn:ioSpecification id="io"><bpmn:dataInput id="di" name="Demande d\'agrément"/>'
            '<bpmn:inputSet id="is"><bpmn:dataInputRefs>di</bpmn:dataInputRefs></bpmn:inputSet>'
            '<bpmn:outputSet id="os"/></bpmn:ioSpecification>'
            '<bpmn:startEvent id="s"/>'
            '<bpmn:userTask id="t" name="Vérifier la recevabilité">'
            '<bpmn:property id="pr" name="__targetRef_placeholder"/>'
            '<bpmn:dataInputAssociation id="a"><bpmn:sourceRef>di</bpmn:sourceRef>'
            '<bpmn:targetRef>pr</bpmn:targetRef></bpmn:dataInputAssociation></bpmn:userTask>'
            '<bpmn:endEvent id="e"/>' + _flux("s", "t") + _flux("t", "e"))
        mi = parser_bpmn(modele, est_texte=True)
        self.assertEqual(mi.donnees_processus, {"di": "Demande d'agrément"})
        self.assertEqual(mi.flux_donnees_ecartes, [("di", "t")])
        self.assertEqual(len(mi.anomalies), 1)
        self.assertEqual(transformer(mi).inputs, [])
        mf = transformer(mi, extensions={"donnees-processus"})
        self.assertEqual([n.nom for n in mf.inputs], ["Demande d'agrément"])
        self.assertEqual(mf.inputs[0].pattern, "P2")
        self.assertNotIn("di", mi.donnees)                # copie, Mi intact


class TestRolesGouvernants(unittest.TestCase):
    def test_indice(self):
        self.assertTrue(indice_gouvernance("Chef de service"))
        self.assertTrue(indice_gouvernance("Comité de crédit"))
        self.assertTrue(indice_gouvernance("Credit Committee"))
        self.assertFalse(indice_gouvernance("Agent instructeur"))
        self.assertFalse(indice_gouvernance("Directeurs"))   # mots entiers

    def test_source_proposee(self):
        chemin = os.path.join(RACINE, "catalogue-patterns", "A09-role-du-couloir.bpmn")
        if not os.path.exists(chemin):
            self.skipTest("catalogue absent")
        mi = parser_bpmn(chemin)
        ref = transformer(mi)
        self.assertEqual(ref.sources, [])
        mf = transformer(mi, extensions={"roles-gouvernants"})
        self.assertEqual([n.nom for n in mf.sources], ["Chef de service"])
        points = [p for p in mf.a_confirmer if p.categorie == "ressource"]
        self.assertEqual(points[0].proposition, "KS (indice lexical)")
        # l'expert garde le dernier mot
        mf = transformer(mi, Arbitrages.depuis_json(
            {"ressources": {"Chef de service": "non"}}), {"roles-gouvernants"})
        self.assertEqual(mf.sources, [])


class TestNomsSuggeresEtLogique(unittest.TestCase):
    MODELE = _bpmn(
        '<bpmn:startEvent id="s"/>'
        '<bpmn:dataObjectReference id="d" name="Dossier constitué"/>'
        '<bpmn:userTask id="t" name="Instruire le dossier">'
        '<bpmn:property id="pr" name="__targetRef_placeholder"/>'
        '<bpmn:dataInputAssociation id="a"><bpmn:sourceRef>d</bpmn:sourceRef>'
        '<bpmn:targetRef>pr</bpmn:targetRef></bpmn:dataInputAssociation></bpmn:userTask>'
        '<bpmn:exclusiveGateway id="g" name="Dossier complet ?"/>'
        '<bpmn:endEvent id="e1" name="Accepté"/><bpmn:endEvent id="e2" name="Retourné"/>'
        + _flux("s", "t") + _flux("t", "g") + _flux("g", "e1", "complet", "complet")
        + _flux("g", "e2", "incomplet"))

    def test_nom_suggere(self):
        mi = parser_bpmn(self.MODELE, est_texte=True)
        mf = transformer(mi, extensions={"noms-suggeres"})
        self.assertEqual(mf.suggestions_noms, {"t": "Décider si dossier complet"})
        self.assertEqual(mf.decisions[0].nom, "Instruire le dossier")   # delta intact
        mf = transformer(mi, Arbitrages.depuis_json({"renommages": {"t": "X"}}),
                         {"noms-suggeres"})
        self.assertEqual(mf.suggestions_noms, {})

    def test_table_de_decision_squelette(self):
        mi = parser_bpmn(self.MODELE, est_texte=True)
        mf = transformer(mi, extensions={"logique"})
        self.assertEqual(mf.logique["D1"]["branches"][0]["sortie"], "complet")
        self.assertEqual(mf.logique["D1"]["branches"][1]["sortie"], "incomplet")
        dmn = serialiser_dmn(mf)
        self.assertIn('<decisionTable id="D1_table" hitPolicy="UNIQUE">', dmn)
        self.assertIn("dossierConstitue", dmn)
        self.assertIn('<text>"complet","incomplet"</text>', dmn)
        racine = ET.fromstring(dmn)
        ns = "{https://www.omg.org/spec/DMN/20191111/MODEL/}"
        table = racine.find(".//%sdecisionTable" % ns)
        self.assertIsNotNone(table)
        self.assertEqual(len(table.findall("%srule" % ns)), 2)
        self.assertEqual(len(table.findall("%sinput" % ns)), 1)
        # le DRD est inchangé : mêmes sommets et arcs que la référence,
        # relecture du DMN et aller-retour conformes
        ref = transformer(mi)
        self.assertTrue(equivalents(ref, mf)[0])
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
        relu = parser_dmn(dmn, est_texte=True)
        self.assertTrue(equivalents(ref, relu)[0])
        bpmn2, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True), Arbitrages.depuis_json(arb))
        self.assertTrue(equivalents(mf, mf2)[0])

    def test_xsd_si_lxml(self):
        try:
            from lxml import etree
        except ImportError:
            self.skipTest("lxml absent")
        xsd = etree.XMLSchema(etree.parse(os.path.join(RACINE, "build-xsd", "dmn",
                                                       "DMN13.xsd")))
        mi = parser_bpmn(self.MODELE, est_texte=True)
        for ext in ({"logique"}, TOUTES):
            dmn = serialiser_dmn(transformer(mi, extensions=ext))
            self.assertTrue(xsd.validate(etree.fromstring(dmn.encode("utf-8"))),
                            str(xsd.error_log[:2]))


class TestIntegration(unittest.TestCase):
    def test_ligne_de_commande(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        import cli
        dossier = tempfile.mkdtemp(prefix="ext-")
        sortie = os.path.join(dossier, "s.dmn")
        chemin = os.path.join(RACINE, "corpus", "credit-bancaire.bpmn")
        with redirect_stdout(io.StringIO()) as tampon:
            code = cli.principal(["transformer", chemin, "-o", sortie,
                                  "--extensions", "toutes", "--registre", dossier])
        self.assertEqual(code, 0)
        self.assertIn("Extensions actives", tampon.getvalue())
        with open(sortie, encoding="utf-8") as f:
            self.assertIn("decisionTable", f.read())
        from bpmn2dmn.registre import Registre
        self.assertTrue(Registre(dossier).lignes()[0]["variante"].startswith("extensions:"))
        with redirect_stdout(io.StringIO()) as tampon:
            code = cli.principal(["transformer", chemin, "-o", sortie,
                                  "--extensions", "inconnue", "--sans-registre"])
        self.assertEqual(code, 1)
        with redirect_stdout(io.StringIO()) as tampon:
            self.assertEqual(cli.principal(["extensions"]), 0)
        self.assertIn("logique", tampon.getvalue())

    def test_application_web(self):
        import json as js
        import shutil
        import tempfile
        import threading
        import urllib.request
        import app
        from bpmn2dmn.registre import Registre
        dossier = tempfile.mkdtemp(prefix="ext-web-")
        ancien = app.REGISTRE
        app.REGISTRE = Registre(dossier)
        serveur = app.Serveur(("127.0.0.1", 0), app.Requetes)
        port = serveur.server_address[1]
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            def post(corps):
                req = urllib.request.Request(
                    "http://127.0.0.1:%d/api/transformer" % port,
                    data=js.dumps(corps).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                try:
                    with ouvreur.open(req, timeout=30) as r:
                        return r.status, js.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    return e.code, js.loads(e.read().decode("utf-8"))
            statut, d = post({"bpmn": TestNomsSuggeresEtLogique.MODELE,
                              "extensions": ["noms-suggeres", "logique"]})
            self.assertEqual(statut, 200)
            self.assertEqual(d["rapport"]["variante"], "extensions:logique+noms-suggeres")
            self.assertIn("t", d["rapport"]["suggestions_noms"])
            self.assertIn("decisionTable", d["dmn"])
            self.assertTrue(d["rapport"]["experimentation"]["experience"].startswith("EXP-"))
            statut, d = post({"bpmn": TestNomsSuggeresEtLogique.MODELE,
                              "extensions": ["inconnue"]})
            self.assertEqual(statut, 422)
            with ouvreur.open("http://127.0.0.1:%d/api/extensions" % port, timeout=30) as r:
                self.assertEqual(len(js.loads(r.read().decode("utf-8"))["extensions"]), 7)
        finally:
            serveur.shutdown()
            serveur.server_close()
            app.REGISTRE = ancien
            shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
