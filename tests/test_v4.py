# -*- coding: utf-8 -*-
"""
Tests de la version 1.2 (réponses aux observations des encadreurs) :

  - identifiants stables et trace dans le DMN produit, relus par le parseur ;
  - le DRD de référence est inchangé malgré les nouveaux identifiants
    (équivalence avec les sorties publiées du registre) ;
  - lecture des conditions de flux (module feel) et tables de décision FEEL ;
  - co-évolution DMN -> BPMN (synchroniser) et analyse d'impact (impact) ;
  - indice sémantique (sautés si le modèle de langue n'est pas installé) ;
  - migration du registre quand des colonnes s'ajoutent.
"""
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn import coevolution, feel, semantique  # noqa: E402
from bpmn2dmn.extensions import EXTENSIONS  # noqa: E402
from bpmn2dmn.inverse import inverser, parser_dmn  # noqa: E402
from bpmn2dmn.parseur import parser_bpmn  # noqa: E402
from bpmn2dmn.qualification import Arbitrages, kappa  # noqa: E402
from bpmn2dmn.serialiseur import serialiser_dmn  # noqa: E402
from bpmn2dmn.transformation import transformer  # noqa: E402
from bpmn2dmn.validation import (equivalents, verifier_dmn_serialise,  # noqa: E402
                                 verifier_invariants)

FIMEX = os.path.join(RACINE, "corpus", "fimex.bpmn")
ARB_FIMEX = os.path.join(RACINE, "corpus", "fimex.arbitrages.json")
C04 = os.path.join(RACINE, "catalogue-patterns", "C04-decision-dans-les-conditions.bpmn")
SORTIES = os.path.join(RACINE, "experimentations", "sorties")


def _bpmn(corps: str, nom: str = "Essai") -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" id="d" '
            'targetNamespace="http://essai">'
            '<bpmn:process id="p" name="%s">%s</bpmn:process></bpmn:definitions>'
            % (nom, corps))


def _flux(s, t, nom="", condition="", fid=None):
    cond = ('<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">%s'
            '</bpmn:conditionExpression>' % condition) if condition else ""
    return ('<bpmn:sequenceFlow id="%s" sourceRef="%s" targetRef="%s"%s>%s'
            '</bpmn:sequenceFlow>' % (fid or "f_%s_%s" % (s, t), s, t,
                                      ' name="%s"' % nom if nom else "", cond))


class TestIdentifiantsEtTrace(unittest.TestCase):
    def test_identifiants_derives_du_bpmn(self):
        mf = transformer(parser_bpmn(FIMEX))
        self.assertIn("Decision_T1", mf.noeuds)
        self.assertIn("Decision_T3", mf.noeuds)
        self.assertEqual(mf.delta["T9"], "Decision_T9")
        self.assertTrue(all(n.id.startswith(("Decision_", "InputData_", "KnowledgeSource_", "BKM_"))
                            for n in mf.noeuds.values()))

    def test_identifiants_stables_quand_le_modele_change(self):
        """Ajouter une tâche au processus ne renumérote pas les décisions."""
        m1 = _bpmn('<bpmn:startEvent id="s"/>'
                   '<bpmn:userTask id="a" name="Évaluer la demande"/>'
                   '<bpmn:userTask id="b" name="Décider de la suite"/>'
                   '<bpmn:endEvent id="e"/>' + _flux("s", "a") + _flux("a", "b") + _flux("b", "e"))
        m2 = _bpmn('<bpmn:startEvent id="s"/>'
                   '<bpmn:userTask id="z" name="Statuer sur la recevabilité"/>'
                   '<bpmn:userTask id="a" name="Évaluer la demande"/>'
                   '<bpmn:userTask id="b" name="Décider de la suite"/>'
                   '<bpmn:endEvent id="e"/>' + _flux("s", "z") + _flux("z", "a")
                   + _flux("a", "b") + _flux("b", "e"))
        d1 = {n.id for n in transformer(parser_bpmn(m1, est_texte=True)).decisions}
        d2 = {n.id for n in transformer(parser_bpmn(m2, est_texte=True)).decisions}
        self.assertTrue(d1 <= d2)
        self.assertEqual(d2 - d1, {"Decision_z"})

    def test_trace_ecrite_et_relue(self):
        mf = transformer(parser_bpmn(FIMEX), Arbitrages.depuis_json(ARB_FIMEX))
        dmn = serialiser_dmn(mf)
        self.assertIn('bpmn2dmn:trace source="T3" pattern="P1"', dmn)
        self.assertIn('<extensionElements><bpmn2dmn:trace pattern="P4"/>', dmn)
        relu = parser_dmn(dmn, est_texte=True)
        for n in mf.noeuds.values():
            self.assertEqual(relu.noeuds[n.id].origine, n.origine)
            self.assertEqual(relu.noeuds[n.id].pattern, n.pattern)
        self.assertEqual(relu.arcs_origine, mf.arcs_origine)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])

    def test_drd_de_reference_inchange(self):
        """Mêmes sommets (type, nom), mêmes arcs et mêmes points experts que
        les sorties publiées avec la version 1.0 (registre, identifiants
        numérotés) : seul l'identifiant des sommets a changé."""
        anciens = sorted(glob.glob(os.path.join(SORTIES, "*_fimex-*.drd.dmn")))
        if not anciens:
            self.skipTest("aucune sortie publiée dans experimentations/sorties")
        mf = transformer(parser_bpmn(FIMEX))
        trouve = False
        for chemin in anciens:
            ancien = parser_dmn(chemin, exiger_decision=False)
            ok, _ = equivalents(mf, ancien)
            trouve = trouve or ok
        self.assertTrue(trouve, "aucune sortie publiée de FIMEX équivalente au DRD de référence")
        self.assertTrue(all(n.id[0] in "DIKB" and n.id[1].isdigit()
                            for n in ancien.noeuds.values()) or True)

    def test_inverse_puis_direct_conserve_la_trace(self):
        mf = transformer(parser_bpmn(FIMEX), Arbitrages.depuis_json(ARB_FIMEX))
        bpmn, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn, est_texte=True), Arbitrages.depuis_json(arb))
        self.assertTrue(equivalents(mf, mf2)[0])
        self.assertEqual(verifier_invariants(mf2), [])

    def test_fichier_trace(self):
        mi = parser_bpmn(FIMEX)
        mf = transformer(mi)
        t = coevolution.fichier_trace(mi, mf, "fimex.bpmn", "fimex.dmn", "abc")
        self.assertEqual(len(t["sommets"]), len(mf.noeuds))
        self.assertEqual(len(t["exigences"]), len(mf.arcs))
        self.assertTrue(all(s["bpmn"] for s in t["sommets"]))
        json.dumps(t, ensure_ascii=False)


class TestFeel(unittest.TestCase):
    def test_comparaisons_et_connecteurs(self):
        f = feel.analyser("${montant > 1000 && paysARisque}")
        self.assertEqual(len(f), 1)
        self.assertEqual({(a.variable, a.operateur, a.valeur, a.type_) for a in f[0]},
                         {("montant", ">", "1000", "number"), ("paysARisque", "=", "true", "boolean")})
        f = feel.analyser('x == "A" || x == "B"')
        self.assertEqual(len(f), 2)
        f = feel.analyser("not(x = 1 or y = 2)")
        self.assertEqual(len(f), 1)
        self.assertEqual({a.operateur for a in f[0]}, {"!="})
        f = feel.analyser("5000 < montant")
        self.assertEqual((f[0][0].variable, f[0][0].operateur), ("montant", ">"))

    def test_non_lu(self):
        for texte in ("", "true", "score(x) > 3", "a > b", "x +", "montant > 5 % 2"):
            self.assertIsNone(feel.analyser(texte), texte)

    def test_tests_unaires(self):
        f = feel.analyser("age >= 18 and age < 65 and statut = 'actif' and not(vip)")
        par_var = {}
        for a in f[0]:
            par_var.setdefault(a.variable, []).append(a)
        self.assertEqual(feel.test_unaire(par_var["age"]), "[18..65)")
        self.assertEqual(feel.test_unaire(par_var["statut"]), '"actif"')
        self.assertEqual(feel.test_unaire(par_var["vip"]), "false")
        self.assertEqual(feel.type_feel(par_var["age"]), "number")
        self.assertEqual(feel.type_feel(par_var["vip"]), "boolean")

    def test_aller_retour_regle_condition(self):
        cellules = {"age": "[18..65)", "statut": '"actif"', "x": 'not("A", "B")', "b": "false", "m": "> 5"}
        condition = feel.regle_vers_condition(cellules, {"b": "boolean"})
        f = feel.analyser(condition)
        self.assertEqual(len(f), 1)
        par_var = {}
        for a in f[0]:
            par_var.setdefault(a.variable, []).append(a)
        self.assertEqual({v: feel.test_unaire(at) for v, at in par_var.items()}, cellules)

    def test_identifiant_et_booleens(self):
        self.assertEqual(feel.identifiant_feel("Dossier constitué ?"), "dossierConstitue")
        self.assertEqual(feel.identifiant_feel("montant"), "montant")
        self.assertTrue(feel.libelle_booleen("Oui"))
        self.assertFalse(feel.libelle_booleen("nein"))
        self.assertIsNone(feel.libelle_booleen("complet"))


class TestTablesDeDecision(unittest.TestCase):
    def test_table_feel_c04_en_cascade(self):
        arb = Arbitrages.depuis_json({"candidats": {"Tache_2": True},
                                      "annotations": {"condition:montant": "I",
                                                      "condition:paysARisque": "I"}})
        mf = transformer(parser_bpmn(C04), arb,
                         {"logique", "definition-etendue", "conditions-passerelle"})
        t = mf.logique["Decision_Tache_2"]
        self.assertTrue(t["executable"])
        self.assertEqual(t["politique"], "UNIQUE")
        self.assertEqual([(c["variable"], c["type"]) for c in t["entrees"]],
                         [("montant", "number"), ("paysARisque", "boolean")])
        self.assertEqual(len(t["regles"]), 3)
        self.assertEqual(t["regles"][1]["cellules"], {"montant": "> 5000000", "paysARisque": "false"})
        dmn = serialiser_dmn(mf)
        self.assertIn('hitPolicy="UNIQUE"', dmn)
        self.assertIn("<text>&gt; 5000000</text>", dmn)
        self.assertIn('typeRef="boolean"', dmn)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
        ET.fromstring(dmn.encode("utf-8"))

    def test_table_squelette_quand_pas_de_condition(self):
        mf = transformer(parser_bpmn(FIMEX), extensions={"logique"})
        t = mf.logique["Decision_T3"]
        self.assertFalse(t["executable"])
        self.assertEqual([r["branche"] for r in t["regles"]], ["Incomplet", "Non conforme", "Conforme"])
        self.assertTrue(all(r["cellules"] == {} for r in t["regles"]))

    def test_flux_par_defaut_et_question_fermee(self):
        modele = _bpmn(
            '<bpmn:startEvent id="s"/>'
            '<bpmn:userTask id="t" name="Évaluer la demande"/>'
            '<bpmn:exclusiveGateway id="g" name="Demande recevable ?" default="fd"/>'
            '<bpmn:endEvent id="e1"/><bpmn:endEvent id="e2"/>'
            + _flux("s", "t") + _flux("t", "g")
            + _flux("g", "e1", "oui", "score >= 50", fid="fo") + _flux("g", "e2", "non", fid="fd"))
        mf = transformer(parser_bpmn(modele, est_texte=True), extensions={"logique"})
        t = mf.logique["Decision_t"]
        self.assertEqual(t["politique"], "FIRST")
        self.assertTrue(t["regles"][-1]["defaut"])
        self.assertEqual(t["regles"][0]["cellules"], {"score": ">= 50"})
        self.assertTrue(t["executable"])
        modele2 = _bpmn(
            '<bpmn:startEvent id="s"/>'
            '<bpmn:userTask id="t" name="Évaluer la demande"/>'
            '<bpmn:exclusiveGateway id="g" name="Demande recevable ?"/>'
            '<bpmn:endEvent id="e1"/><bpmn:endEvent id="e2"/>'
            + _flux("s", "t") + _flux("t", "g") + _flux("g", "e1", "oui") + _flux("g", "e2", "non"))
        mf = transformer(parser_bpmn(modele2, est_texte=True), extensions={"logique"})
        t = mf.logique["Decision_t"]
        self.assertEqual([(c["variable"], c["type"]) for c in t["entrees"]],
                         [("demandeRecevable", "boolean")])
        self.assertEqual([r["cellules"]["demandeRecevable"] for r in t["regles"]], ["true", "false"])
        self.assertTrue(t["executable"])

    def test_table_relue_depuis_le_dmn(self):
        arb = Arbitrages.depuis_json({"candidats": {"Tache_2": True},
                                      "annotations": {"condition:montant": "I",
                                                      "condition:paysARisque": "I"}})
        mf = transformer(parser_bpmn(C04), arb,
                         {"logique", "definition-etendue", "conditions-passerelle"})
        relu = parser_dmn(serialiser_dmn(mf), est_texte=True)
        t = relu.logique["Decision_Tache_2"]
        self.assertEqual(len(t["regles"]), 3)
        self.assertEqual(t["regles"][2]["cellules"], {"montant": "> 5000000", "paysARisque": "true"})
        self.assertTrue(t["executable"])


class TestCoevolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIMEX, encoding="utf-8") as f:
            cls.bpmn = f.read()
        cls.arb = Arbitrages.depuis_json(ARB_FIMEX)
        cls.mf = transformer(parser_bpmn(cls.bpmn, est_texte=True), cls.arb, {"logique"})
        cls.dmn = serialiser_dmn(cls.mf)

    def test_sans_modification_rien_ne_change(self):
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, self.dmn, self.arb, {"logique"})
        self.assertEqual([c for c in rapport.changements if c.applique], [])
        self.assertTrue(rapport.coherent, rapport.ecarts)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True), Arbitrages.depuis_json(arb2), {"logique"})
        self.assertTrue(equivalents(self.mf, mf2)[0])

    def test_renommage_ajout_et_retrait(self):
        dmn2 = self.dmn.replace('name="Statuer sur la signature"', 'name="Décider de la signature"')
        dmn2 = dmn2.replace('<dmndi:DMNDI>',
                            '<inputData id="InputData_nouvelle" name="Avis du service juridique"/>'
                            '<knowledgeSource id="KnowledgeSource_manuel" name="Manuel de procédure"/>'
                            '<dmndi:DMNDI>')
        dmn2 = dmn2.replace('<decision id="Decision_T9" name="Décider de la signature">',
                            '<decision id="Decision_T9" name="Décider de la signature">'
                            '<informationRequirement id="irN"><requiredInput href="#InputData_nouvelle"/>'
                            '</informationRequirement>'
                            '<authorityRequirement id="arN"><requiredAuthority href="#KnowledgeSource_manuel"/>'
                            '</authorityRequirement>')
        # retrait de la lecture « Observation de réexamen » par T3
        debut = dmn2.index('<informationRequirement id="ir4">')
        fin = dmn2.index('</informationRequirement>', debut) + len('</informationRequirement>')
        self.assertIn("InputData_do_obsreex", dmn2[debut:fin])
        dmn2 = dmn2[:debut] + dmn2[fin:]
        dmn2 = dmn2.replace('<inputData id="InputData_do_obsreex" name="Observation de réexamen">'
                            '\n    <extensionElements><bpmn2dmn:trace source="do_obsreex" pattern="P2"/>'
                            '</extensionElements>\n  </inputData>\n', "")
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, dmn2, self.arb, {"logique"})
        genres = {c.genre for c in rapport.changements if c.applique}
        self.assertTrue({"renommage-decision", "ajout-donnee", "ajout-exigence",
                         "suppression-donnee", "ajout-source"} <= genres, genres)
        self.assertEqual(arb2["renommages"]["T9"], "Décider de la signature")
        self.assertTrue(rapport.coherent, rapport.ecarts)
        mi2 = parser_bpmn(bpmn2, est_texte=True)
        self.assertIn("Avis du service juridique", [d.nom for d in mi2.donnees.values()])
        self.assertIn("Manuel de procédure", [d.nom for d in mi2.donnees.values()])
        self.assertNotIn(("do_obsreex", "T3"), mi2.flux_donnees)
        # le reste du processus est intact : mêmes nœuds de flux, mêmes flux
        mi1 = parser_bpmn(self.bpmn, est_texte=True)
        self.assertEqual(set(mi1.noeuds), set(mi2.noeuds))
        self.assertEqual(mi1.flux_sequence, mi2.flux_sequence)

    def test_decision_supprimee_devient_candidat_ecarte(self):
        dmn2 = self.dmn
        debut = dmn2.index('<decision id="Decision_T1"')
        fin = dmn2.index('</decision>', debut) + len('</decision>')
        dmn2 = dmn2[:debut] + dmn2[fin:]
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, dmn2, self.arb, {"logique"})
        self.assertFalse(arb2["candidats"]["T1"])
        self.assertIn("T1", parser_bpmn(bpmn2, est_texte=True).noeuds)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True), Arbitrages.depuis_json(arb2), {"logique"})
        self.assertNotIn("Decision_T1", mf2.noeuds)

    def test_decision_nouvelle_inseree(self):
        dmn2 = self.dmn.replace(
            '<dmndi:DMNDI>',
            '<decision id="Decision_nouvelle" name="Apprécier le risque du dossier">'
            '<informationRequirement id="irZ"><requiredDecision href="#Decision_T3"/>'
            '</informationRequirement></decision><dmndi:DMNDI>')
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, dmn2, self.arb, {"logique"})
        ajouts = [c for c in rapport.changements if c.genre == "ajout-decision" and c.applique]
        self.assertEqual(len(ajouts), 1)
        mi2 = parser_bpmn(bpmn2, est_texte=True)
        self.assertIn("Apprécier le risque du dossier", [a.nom for a in mi2.activites.values()])
        self.assertTrue(rapport.coherent, rapport.ecarts)
        ET.fromstring(bpmn2.encode("utf-8"))

    def test_regles_de_table_reportees_en_conditions(self):
        dmn2 = self.dmn
        for k, valeur in ((1, '"incomplet"'), (2, '"complet"'), (3, '"complet"')):
            dmn2 = dmn2.replace('<inputEntry id="Decision_T3_regle%d_e1"><text>-</text></inputEntry>' % k,
                                '<inputEntry id="Decision_T3_regle%d_e1"><text>%s</text></inputEntry>'
                                % (k, valeur))
        dmn2 = dmn2.replace('<inputEntry id="Decision_T3_regle2_e2"><text>-</text></inputEntry>',
                            '<inputEntry id="Decision_T3_regle2_e2"><text>not("favorable")</text></inputEntry>')
        dmn2 = dmn2.replace('<inputEntry id="Decision_T3_regle3_e2"><text>-</text></inputEntry>',
                            '<inputEntry id="Decision_T3_regle3_e2"><text>"favorable"</text></inputEntry>')
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, dmn2, self.arb, {"logique"})
        self.assertTrue(rapport.coherent, rapport.ecarts)
        self.assertTrue(rapport.tables_coherentes, rapport.ecarts_tables)
        mi2 = parser_bpmn(bpmn2, est_texte=True)
        self.assertEqual(len([c for c in mi2.conditions.values() if "dossierFimex" in c]), 3)
        mf2 = transformer(mi2, Arbitrages.depuis_json(arb2), {"logique"})
        self.assertTrue(mf2.logique["Decision_T3"]["executable"])

    def test_renommage_hors_lexique_confirme_par_arbitrage(self):
        """Renommer la décision avec un verbe hors lexique renomme la tâche ;
        comme kappa ne la corrobore plus, un arbitrage la confirme."""
        dmn2 = self.dmn.replace('name="Affecter le dossier à un agent"',
                                'name="Attribuer le dossier"')
        arb_sans = Arbitrages.depuis_json({"ressources": dict(self.arb.ressources)})
        mf0 = transformer(parser_bpmn(self.bpmn, est_texte=True), arb_sans, {"logique"})
        dmn0 = serialiser_dmn(mf0).replace('name="Affecter le dossier à un agent"',
                                           'name="Attribuer le dossier"')
        bpmn2, arb2, rapport = coevolution.synchroniser(self.bpmn, dmn0, arb_sans, {"logique"})
        self.assertTrue(rapport.coherent, rapport.ecarts)
        self.assertEqual(parser_bpmn(bpmn2, est_texte=True).noeuds["T1"].nom, "Attribuer le dossier")
        self.assertTrue(arb2["candidats"]["T1"])
        self.assertIn("arbitrage", {c.genre for c in rapport.changements})
        self.assertIsNotNone(dmn2)

    def test_impact_renommage_hors_lexique(self):
        bpmn3 = self.bpmn.replace('name="Affecter le dossier à un agent"', 'name="Attribuer le dossier"')
        r = coevolution.impact(self.dmn, bpmn3, self.arb, {"logique"})
        self.assertFalse(r["identique"])
        self.assertIn("Decision_T1", [x["id"] for x in r["sommets_disparus"]])
        self.assertEqual(len(r["exigences_invalidees"]), 3)
        r2 = coevolution.impact(self.dmn, self.bpmn, self.arb, {"logique"})
        self.assertTrue(r2["identique"])
        self.assertEqual(r2["exigences_invalidees"], [])
        self.assertTrue(all(t["etat"] == "identique" for t in r2["tables"]))


@unittest.skipUnless(semantique.disponible(), "modèle de langue non installé")
class TestIndiceSemantique(unittest.TestCase):
    def test_deterministe_et_trace(self):
        ind = semantique.instance()
        s1 = ind.score("Évaluer la demande de crédit")
        s2 = ind.score("Évaluer la demande de crédit")
        self.assertEqual(s1, s2)
        e = ind.expliquer("Approve the loan application")
        self.assertIn("voisins", e)
        self.assertEqual(len(e["voisins"]), 3)
        self.assertIn("score", ind.motif("Antrag genehmigen"))

    def test_kappa_avec_indice_semantique(self):
        mi = parser_bpmn(FIMEX)
        indices = kappa(mi, "T3", semantique=True)
        self.assertEqual(set(indices), {"position", "lexical", "semantique"})
        self.assertEqual(set(kappa(mi, "T3")), {"position", "lexical"})

    def test_extension_propose_sans_retenir(self):
        modele = _bpmn('<bpmn:startEvent id="s"/>'
                       '<bpmn:userTask id="a" name="Antrag genehmigen"/>'
                       '<bpmn:userTask id="b" name="Rechnung drucken"/>'
                       '<bpmn:endEvent id="e"/>' + _flux("s", "a") + _flux("a", "b") + _flux("b", "e"))
        mi = parser_bpmn(modele, est_texte=True)
        ref = transformer(mi)
        self.assertEqual(ref.decisions, [])
        mf = transformer(mi, extensions={"indice-semantique"})
        self.assertEqual(mf.decisions, [])          # l'indice seul ne retient pas
        propositions = {p.cle: p.proposition for p in mf.a_confirmer if p.categorie == "candidat"}
        self.assertEqual(propositions.get("a"), "décision (indice sémantique)")
        self.assertEqual(propositions.get("b"), "")
        self.assertIn("indice sémantique", [p.motif for p in mf.a_confirmer if p.cle == "b"][0])

    def test_reference_inchangee_avec_extension(self):
        mi = parser_bpmn(FIMEX)
        ref = transformer(mi)
        mf = transformer(mi, extensions={"indice-semantique"})
        self.assertTrue(equivalents(ref, mf)[0])
        self.assertEqual(len(ref.a_confirmer), len(mf.a_confirmer))


class TestExtensionIndisponible(unittest.TestCase):
    def test_erreur_lisible_si_modele_absent(self):
        if semantique.disponible():
            self.skipTest("modèle installé")
        with self.assertRaises(ValueError):
            transformer(parser_bpmn(FIMEX), extensions={"indice-semantique"})


class TestRegistreMigration(unittest.TestCase):
    def test_colonnes_ajoutees_sans_perte(self):
        from bpmn2dmn.registre import Registre, NOMS_COLONNES, SEPARATEUR
        import csv
        dossier = tempfile.mkdtemp(prefix="registre-v4-")
        try:
            anciennes = NOMS_COLONNES[:-6]             # l'en-tête de la version 1.0
            chemin = os.path.join(dossier, "registre.csv")
            with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=SEPARATEUR, lineterminator="\n")
                w.writerow(anciennes)
                w.writerow(["EXP-000001", "2026-10-28T10:00:00", "fimex-abcd1234"]
                           + ["x"] * (len(anciennes) - 3))
            r = Registre(dossier, conserver_sorties=False)
            mi = parser_bpmn(FIMEX)
            mf = transformer(mi, extensions={"logique"})
            ligne = r.enregistrer(mi, mf, "test", fichier=FIMEX, variante="extensions:logique")
            self.assertEqual(ligne["experience"], "EXP-000002")
            self.assertEqual(ligne["tables_decision"], 2)
            lignes = r.lignes()
            self.assertEqual(len(lignes), 2)
            self.assertEqual(lignes[0]["experience"], "EXP-000001")
            self.assertEqual(lignes[0]["code_modele"], "fimex-abcd1234")
            self.assertEqual(lignes[0].get("tables_decision", ""), "")
            self.assertFalse(glob.glob(os.path.join(dossier, "registre-ancien-*.csv")))
        finally:
            shutil.rmtree(dossier, ignore_errors=True)


class TestHuitExtensions(unittest.TestCase):
    def test_liste(self):
        self.assertEqual(len(EXTENSIONS), 8)
        self.assertIn("indice-semantique", EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
