# -*- coding: utf-8 -*-
"""
Le catalogue de patterns, figé : chaque diagramme est reconstruit en
mémoire par le générateur, transformé sans arbitrage, et le DRD obtenu est
comparé au DRD attendu déclaré avec le pattern. Les fichiers livrés dans
`catalogue-patterns/` doivent en outre être identiques à ce que le
générateur produit, et conformes au schéma BPMN 2.0 de l'OMG (si lxml est
installé).

    python -m unittest tests.test_catalogue -v        (depuis transformateur/)
"""
import io
import os
import sys
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "outils"))

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.validation import verifier_dmn_serialise

import generer_catalogue_patterns as gen
import executer_catalogue as exe

FAMILLES = {"A": "patterns de référence", "B": "raffinements et gardes",
            "C": "limites"}


class TestCatalogue(unittest.TestCase):
    """Un contrôle par pattern, regroupés par famille."""

    @classmethod
    def setUpClass(cls):
        cls.construits = gen.construire_tous()
        cls.schemas = exe._schemas()

    def _verifier_famille(self, lettre):
        patterns = [(m, xml, gold) for m, xml, gold in self.construits
                    if m["fichier"].startswith(lettre)]
        self.assertTrue(patterns)
        for meta, xml, gold in patterns:
            with self.subTest(pattern=meta["fichier"]):
                mi = parser_bpmn(xml, est_texte=True)
                mf = transformer(mi)
                obs = exe.observe(mi, mf)
                self.assertEqual(exe.comparer(meta["attendu"], obs), [],
                                 "DRD différent de l'attendu")
                self.assertEqual(sorted(gold), sorted(meta["attendu"]["decisions"]),
                                 "référence experte incohérente avec l'attendu")
                dmn = serialiser_dmn(mf)
                self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
                self.assertEqual(exe.valider_xsd(self.schemas, xml, "bpmn"), [])
                if mf.decisions:
                    self.assertEqual(exe.valider_xsd(self.schemas, dmn, "dmn"), [])

    def test_famille_A_patterns_de_reference(self):
        self._verifier_famille("A")

    def test_famille_B_raffinements_et_gardes(self):
        self._verifier_famille("B")

    def test_famille_C_limites(self):
        self._verifier_famille("C")

    def test_trente_quatre_patterns_et_trois_verdicts(self):
        self.assertEqual(len(self.construits), 34)
        verdicts = {m["attendu"]["verdict_attendu"] for m, _, _ in self.construits}
        self.assertEqual(verdicts, {"conforme", "point-expert", "limite"})
        ids = [m["fichier"][:3] for m, _, _ in self.construits]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), 34)

    def test_fichiers_livres_identiques_au_generateur(self):
        """Les diagrammes du dossier sont bien ceux que le générateur produit."""
        for meta, xml, _ in self.construits:
            chemin = os.path.join(gen.DOSSIER, meta["fichier"] + ".bpmn")
            with self.subTest(pattern=meta["fichier"]):
                self.assertTrue(os.path.exists(chemin), "fichier absent")
                self.assertEqual(io.open(chemin, encoding="utf-8").read(), xml)

    def test_diagnostic_du_drd_vide_pour_les_limites(self):
        """Les cas hors définition expliquent pourquoi le DRD est vide."""
        for meta, xml, _ in self.construits:
            if not meta["fichier"].startswith(("C01", "C02", "C03", "C04")):
                continue
            with self.subTest(pattern=meta["fichier"]):
                mi = parser_bpmn(xml, est_texte=True)
                mf = transformer(mi)
                self.assertEqual(mf.decisions, [])
                self.assertIn("retypez", exe.observe(mi, mf)["diagnostic_vide"])

    def test_anomalie_donnee_d_entree_du_processus(self):
        """C10 : l'association vers la donnée d'entrée du processus est
        signalée comme anomalie non bloquante, sans exigence produite."""
        for meta, xml, _ in self.construits:
            if meta["fichier"].startswith("C10"):
                mi = parser_bpmn(xml, est_texte=True)
                self.assertTrue(any("identifiant inconnu" in a for a in mi.anomalies))
                self.assertEqual(transformer(mi).arcs, [])


if __name__ == "__main__":
    unittest.main()
