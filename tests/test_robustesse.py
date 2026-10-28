# -*- coding: utf-8 -*-
"""
Cas limites relevés lors des essais de l'application : lexique par mots
entiers, lecture stricte des arbitrages, mise en page d'un processus à
boucles, refus des requêtes mal formées par le serveur.

    python -m unittest tests.test_robustesse
"""
import json
import os
import re
import sys
import threading
import unittest
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn.metamodeles import NoeudFlux
from bpmn2dmn.miseenpage import ajouter_di, possede_di
from bpmn2dmn.qualification import (Arbitrages, contient_indice, gamma,
                                    indice_lexical, omega)

FIMEX = os.path.join(RACINE, "corpus", "fimex.bpmn")


def _tache(nom):
    return NoeudFlux(id="t", type="userTask", nom=nom)


class TestLexiqueParMotsEntiers(unittest.TestCase):

    def test_frontieres_de_mot(self):
        self.assertTrue(contient_indice("evaluer le dossier", "evaluer"))
        self.assertFalse(contient_indice("transplanter le greffon", "plan"))
        self.assertFalse(contient_indice("information reglementaire", "format"))
        self.assertTrue(contient_indice("hospitalize if: symptoms", "hospitalize if"))
        self.assertTrue(contient_indice("calcul si retard", "si "))
        self.assertFalse(contient_indice("le site", "si "))

    def test_indice_lexical(self):
        self.assertTrue(indice_lexical(_tache("Évaluer la demande")))
        self.assertTrue(indice_lexical(_tache("Faire évaluer la demande")))
        self.assertFalse(indice_lexical(_tache("Transplanter le greffon")))
        self.assertFalse(indice_lexical(_tache("Raccorder le client")))
        self.assertFalse(indice_lexical(_tache("Désaffecter le local")))

    def test_ressources_humaines_non_confondues_avec_un_systeme(self):
        self.assertEqual(omega("Chef de service"), "indetermine")
        self.assertEqual(omega("Service juridique"), "indetermine")
        self.assertEqual(omega("M. Cabot"), "indetermine")
        self.assertEqual(omega("Système de scoring"), "non")
        self.assertEqual(omega("Robot de tri"), "non")

    def test_annotations(self):
        self.assertEqual(gamma("a", "Information réglementaire à consulter"),
                         "indetermine")
        self.assertEqual(gamma("a", "Police d'assurance"), "indetermine")
        self.assertEqual(gamma("a", "Barème des redevances"), "BKM")
        self.assertEqual(gamma("a", "Hospitalize if: symptoms are acute"), "KS")
        self.assertEqual(gamma("a", "Police de caractères : Arial"), "non")


class TestArbitragesStricts(unittest.TestCase):

    def test_verdicts_textuels_toleres(self):
        arb = Arbitrages.depuis_json({"candidats": {"T1": "false", "T2": True}})
        self.assertEqual(arb.candidats, {"T1": False, "T2": True})

    def test_verdict_invalide_refuse(self):
        with self.assertRaises(TypeError):
            Arbitrages.depuis_json({"candidats": {"T1": "peut-être"}})

    def test_renommage_non_textuel_refuse(self):
        with self.assertRaises(TypeError):
            Arbitrages.depuis_json({"renommages": {"T1": 5}})

    def test_type_inattendu_refuse(self):
        for mauvais in (12, [1, 2], None):
            with self.assertRaises(TypeError):
                Arbitrages.depuis_json(mauvais)


class TestMiseEnPageAvecBoucles(unittest.TestCase):

    def test_fimex_sans_di_se_termine(self):
        with open(FIMEX, encoding="utf-8") as f:
            texte = f.read()
        sans_di = re.sub(r"<bpmndi:BPMNDiagram.*?</bpmndi:BPMNDiagram>", "",
                         texte, flags=re.S)
        self.assertFalse(possede_di(sans_di))
        avec_di = ajouter_di(sans_di)
        self.assertTrue(possede_di(avec_di))
        self.assertGreater(avec_di.count("BPMNShape"), 40)

    def test_boucle_simple(self):
        xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
               '<process id="p"><startEvent id="s"/>'
               '<userTask id="a" name="Instruire"/>'
               '<userTask id="b" name="Compléter"/>'
               '<sequenceFlow id="f1" sourceRef="s" targetRef="a"/>'
               '<sequenceFlow id="f2" sourceRef="a" targetRef="b"/>'
               '<sequenceFlow id="f3" sourceRef="b" targetRef="a"/>'
               '</process></definitions>')
        self.assertIn("BPMNShape", ajouter_di(xml))


class TestServeur(unittest.TestCase):
    """Le serveur répond proprement aux requêtes mal formées."""

    @classmethod
    def setUpClass(cls):
        import app
        import shutil
        import tempfile
        from bpmn2dmn.registre import Registre
        # les extractions des tests vont dans un registre temporaire
        cls.dossier_registre = tempfile.mkdtemp(prefix="registre-tests-")
        cls.ancien_registre = app.REGISTRE
        app.REGISTRE = Registre(cls.dossier_registre)
        cls.serveur = app.Serveur(("127.0.0.1", 0), app.Requetes)
        cls.port = cls.serveur.server_address[1]
        cls.fil = threading.Thread(target=cls.serveur.serve_forever,
                                   daemon=True)
        cls.fil.start()
        cls.ouvreur = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        import app
        import shutil
        cls.serveur.shutdown()
        cls.serveur.server_close()
        app.REGISTRE = cls.ancien_registre
        shutil.rmtree(cls.dossier_registre, ignore_errors=True)

    def _post(self, chemin, corps):
        if not isinstance(corps, bytes):
            corps = json.dumps(corps).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, chemin), data=corps,
            headers={"Content-Type": "application/json"})
        try:
            with self.ouvreur.open(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _get(self, chemin):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, chemin))
        try:
            with self.ouvreur.open(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_sante(self):
        """La page interroge /api/sante au chargement pour détecter un
        serveur arrêté : la réponse doit être un JSON positif."""
        code, corps = self._get("/api/sante")
        self.assertEqual(code, 200)
        rep = json.loads(corps.decode("utf-8"))
        self.assertTrue(rep["ok"])
        self.assertIn("python", rep)

    def test_page_servie(self):
        code, corps = self._get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"alerteNavigateur", corps)
        self.assertIn(b"__applicationPrete", corps)

    def test_json_non_objet(self):
        for corps in ([1, 2, 3], "bonjour", None):
            code, rep = self._post("/api/transformer", corps)
            self.assertEqual(code, 400)
            self.assertFalse(rep["ok"])

    def test_arbitrages_non_objet(self):
        with open(FIMEX, encoding="utf-8") as f:
            bpmn = f.read()
        for mauvais in ("C:/Windows/win.ini", 12, [1]):
            code, rep = self._post("/api/transformer",
                                   {"bpmn": bpmn, "arbitrages": mauvais})
            self.assertEqual(code, 422)
        code, rep = self._post("/api/transformer",
                               {"bpmn": bpmn, "arbitrages": {"candidats": {}}})
        self.assertEqual(code, 200)
        self.assertTrue(rep["ok"])

    def test_port_deja_pris(self):
        import app
        with self.assertRaises(OSError):
            app.Serveur(("127.0.0.1", self.port), app.Requetes)

    def test_diagnostic_drd_vide(self):
        """Un modèle sans activité candidate (tâches génériques) produit un
        DRD vide ET un diagnostic qui nomme la tâche devant la passerelle ;
        un modèle avec décisions n'en produit aucun."""
        generique = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  id="d" targetNamespace="http://t">
  <bpmn:process id="p" name="Annulation">
    <bpmn:startEvent id="s"/>
    <bpmn:task id="t1" name="Initier la demande"/>
    <bpmn:task id="t2" name="Traiter la demande (instruction)"/>
    <bpmn:exclusiveGateway id="g" name="Décision"/>
    <bpmn:serviceTask id="t3" name="Générer une attestation"/>
    <bpmn:endEvent id="e1"/><bpmn:endEvent id="e2"/>
    <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t1"/>
    <bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="t2"/>
    <bpmn:sequenceFlow id="f3" sourceRef="t2" targetRef="g"/>
    <bpmn:sequenceFlow id="f4" sourceRef="g" targetRef="t3"/>
    <bpmn:sequenceFlow id="f5" sourceRef="g" targetRef="e1"/>
    <bpmn:sequenceFlow id="f6" sourceRef="t3" targetRef="e2"/>
    <bpmn:textAnnotation id="a1"><bpmn:text>Système</bpmn:text></bpmn:textAnnotation>
  </bpmn:process>
</bpmn:definitions>"""
        code, rep = self._post("/api/transformer", {"bpmn": generique})
        self.assertEqual(code, 200)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["rapport"]["resume"]["decisions"], 0)
        diag = rep["rapport"]["diagnostic_vide"]
        self.assertIn("Aucune activité candidate", diag)
        self.assertIn("2 tâches génériques", diag)
        self.assertIn("1 tâche de service", diag)
        self.assertIn("« Traiter la demande (instruction) » précède une "
                      "passerelle exclusive", diag)
        self.assertIn("annotation", diag)
        # la tâche générique devant la passerelle est aussi signalée comme
        # point hors définition, au même titre qu'une tâche de service
        hors = [p for p in rep["rapport"]["a_confirmer"]
                if p["categorie"] == "hors-definition"]
        self.assertEqual([p["objet"] for p in hors],
                         ["Traiter la demande (instruction)"])
        self.assertIn("TÂCHE GÉNÉRIQUE", hors[0]["motif"])
        with open(FIMEX, encoding="utf-8") as f:
            code, rep = self._post("/api/transformer", {"bpmn": f.read()})
        self.assertEqual(rep["rapport"]["diagnostic_vide"], "")

    def test_mise_en_page_sur_processus_a_boucles(self):
        with open(FIMEX, encoding="utf-8") as f:
            texte = f.read()
        sans_di = re.sub(r"<bpmndi:BPMNDiagram.*?</bpmndi:BPMNDiagram>", "",
                         texte, flags=re.S)
        code, rep = self._post("/api/miseenpage", {"bpmn": sans_di})
        self.assertEqual(code, 200)
        self.assertTrue(rep["ajoutee"])


class TestCompatibiliteNavigateurs(unittest.TestCase):
    """Sur un Mac, un Safari un peu ancien refuse toute page dont le script
    emploie une syntaxe postérieure à 2017 : une seule occurrence suffit à
    rendre tous les boutons muets. Le script de la page est donc tenu à
    l'écart de ces constructions (les bibliothèques vendorisées, elles,
    exigent Safari 11.1 ou plus)."""

    INTERDITS = [
        (r"\?\?", "opérateur ?? (Safari 13.1)"),
        (r"[A-Za-z0-9_)\]]\?\.[A-Za-z(\[]", "chaînage optionnel ?. (Safari 13.1)"),
        (r"\?\?=|\|\|=|&&=", "affectation logique (Safari 14)"),
        (r"\bthis\.#|\bstatic\s*\{", "champs privés / blocs statiques (Safari 14.1/16.4)"),
        (r"\(\?<[=!]", "regex à lookbehind (Safari 16.4)"),
        (r"\.replaceAll\(", "String.replaceAll (Safari 13.1)"),
        (r"\.at\(", "Array.at (Safari 15.4)"),
        (r"\bstructuredClone\(", "structuredClone (Safari 15.4)"),
        (r"Object\.hasOwn\(", "Object.hasOwn (Safari 15.4)"),
        (r"\.findLast\(", "Array.findLast (Safari 15.4)"),
    ]

    def test_script_de_la_page_sans_syntaxe_recente(self):
        with open(os.path.join(RACINE, "ui", "index.html"),
                  encoding="utf-8") as f:
            page = f.read()
        scripts = re.findall(r"<script>(.*?)</script>", page, flags=re.S)
        self.assertGreaterEqual(len(scripts), 2)
        for motif, quoi in self.INTERDITS:
            for s in scripts:
                self.assertIsNone(re.search(motif, s),
                                  "index.html emploie : " + quoi)

    def test_bibliotheques_sans_champs_statiques(self):
        """dmn-js déclarait des champs de classe (syntaxe de 2022, Safari
        14.1 au minimum) : réécrits par outils/abaisser_champs_classe.js.
        Toute nouvelle copie des bibliothèques doit être adaptée de même."""
        for nom in ("bpmn-navigated-viewer.min.js",
                    "dmn-navigated-viewer.min.js"):
            with open(os.path.join(RACINE, "ui", "lib", nom),
                      encoding="utf-8") as f:
                lib = f.read()
            self.assertIsNone(re.search(r"static [$\w]+\s*=", lib),
                              nom + " : champ statique de classe")
            self.assertIsNone(re.search(r"\?\?|[\w)\]]\?\.[A-Za-z_$(\[]", lib),
                              nom + " : opérateur ?? ou ?.")

    def test_garde_fou_present(self):
        with open(os.path.join(RACINE, "ui", "index.html"),
                  encoding="utf-8") as f:
            page = f.read()
        self.assertIn('id="alerteNavigateur"', page)
        self.assertIn("window.__applicationPrete = true", page)
        # le garde-fou précède les bibliothèques : il doit capter leurs
        # éventuelles erreurs de chargement
        self.assertLess(page.index("alerteNavigateur"),
                        page.index("bpmn-navigated-viewer.min.js"))


if __name__ == "__main__":
    unittest.main()
