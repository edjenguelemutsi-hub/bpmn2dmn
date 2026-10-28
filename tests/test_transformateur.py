# -*- coding: utf-8 -*-
"""
Suite de tests du transformateur BPMN <-> DMN.

    python -m unittest discover -s tests -v        (depuis transformateur/)

Fige :
  - les résultats de référence de mes travaux (FIMEX arbitré, BPCO) ;
  - les invariants formels sur tout Mf produit ;
  - la robustesse du parseur (namespaces, références pendantes,
    sous-processus, événements-frontière, associations inversées) ;
  - les fonctions de qualification kappa / omega / gamma et l'arbitrage ;
  - la sérialisation DMN relue à l'identique + DMNDI complet ;
  - l'aller-retour T(T_inv(Mf)) = Mf ;
  - une campagne générative (échantillon) avec oracle indépendant ;
  - le déterminisme strict.
"""
import os
import sys
import unittest
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn, ErreurParseur
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import inverser, parser_dmn
from bpmn2dmn.generateur import generer
from bpmn2dmn.miseenpage import ajouter_di, possede_di
from bpmn2dmn.qualification import (Arbitrages, gamma, kappa, normaliser,
                                    omega)
from bpmn2dmn.validation import (comparer_a_oracle, equivalents,
                                 mesurer_decisions, verifier_dmn_serialise,
                                 verifier_invariants)

# les deux modèles historiques, livrés dans le corpus (fimex.bpmn est la
# copie exacte de sources-figures/rendu-bpmn-js/fimex.bpmn ; copd.bpmn
# celle de prototype/corpus/copd.bpmn, mise en page BPMNDI en plus)
FIMEX = os.path.join(RACINE, "corpus", "fimex.bpmn")
COPD = os.path.join(RACINE, "corpus", "copd.bpmn")

ARBITRAGES_FIMEX = {
    "candidats": {},
    "ressources": {"Agent de traitement": "non", "Agent signataire": "KS"},
    "annotations": {},
    "renommages": {"T1": "Affecter le dossier à un agent",
                   "T3": "Statuer sur la conformité du dossier",
                   "T9": "Statuer sur la signature"},
}


class TestFimex(unittest.TestCase):
    """Le cas d'étude FIMEX : résultats du premier prototype (sans arbitrage)
    et du DRD de référence (avec arbitrages de l'expert)."""

    @classmethod
    def setUpClass(cls):
        cls.mi = parser_bpmn(FIMEX)
        cls.mf = transformer(cls.mi)

    def test_decisions_detectees(self):
        noms = sorted(normaliser(n.nom) for n in self.mf.decisions)
        self.assertEqual(noms, sorted([
            "affecter le dossier a un agent",
            "verifier la conformite documentaire",
            "consulter la demande et la decision"]))

    def test_composition_drd(self):
        r = self.mf.resume()
        self.assertEqual((r["decisions"], r["inputs"], r["sources"],
                          r["bkm"]), (3, 4, 1, 1))
        self.assertEqual((r["IR"], r["AR"], r["KR"]), (5, 1, 1))

    def test_invariants(self):
        self.assertEqual(verifier_invariants(self.mf), [])

    def test_acyclique_et_partition(self):
        self.assertTrue(self.mf.acyclique())
        self.assertTrue(self.mf.partition_exacte())

    def test_perimetre_expert(self):
        self.assertEqual(len(self.mf.a_confirmer), 10)
        self.assertEqual(len(self.mf.ecartes), 1)
        self.assertEqual(self.mf.ecartes[0].objet, "Système e-GOV")

    def test_mesure_gold(self):
        m = mesurer_decisions([n.nom for n in self.mf.decisions],
                              ["Affecter le dossier a un agent",
                               "Verifier la conformite documentaire",
                               "Consulter la demande et la decision"])
        self.assertEqual((m["precision"], m["rappel"]), (1.0, 1.0))

    def test_avec_arbitrages_reproduit_la_reference(self):
        """DRD de référence : |V_f| = 10, |E_f| = 8, IR=5, KR=1, AR=2, arc (d2,d3)."""
        mf = transformer(self.mi, Arbitrages.depuis_json(ARBITRAGES_FIMEX))
        r = mf.resume()
        self.assertEqual((r["decisions"], r["inputs"], r["sources"],
                          r["bkm"]), (3, 4, 2, 1))
        self.assertEqual((r["IR"], r["KR"], r["AR"]), (5, 1, 2))
        self.assertEqual(len(mf.noeuds), 10)
        self.assertEqual(len(mf.arcs), 8)
        noms = {n.id: normaliser(n.nom) for n in mf.noeuds.values()}
        arcs_noms = {(noms[u], noms[v]) for u, v in mf.IR}
        self.assertIn(("statuer sur la conformite du dossier",
                       "statuer sur la signature"), arcs_noms)  # P4 raffiné
        self.assertEqual(verifier_invariants(mf), [])

    def test_p4_exige_donnee_partagee(self):
        """« Ordonner n'est pas alimenter » : d1 (Affecter) précède d2 mais ne
        partage aucune donnée -> aucun arc d1 -> d2."""
        noms = {n.id: normaliser(n.nom) for n in self.mf.noeuds.values()}
        arcs = {(noms[u], noms[v]) for u, v in self.mf.arcs}
        self.assertNotIn(("affecter le dossier a un agent",
                          "verifier la conformite documentaire"), arcs)


class TestCopd(unittest.TestCase):
    """Le second modèle du corpus historique (Bazhenova et al. 2019)."""

    @classmethod
    def setUpClass(cls):
        cls.mf = transformer(parser_bpmn(COPD))

    def test_composition(self):
        r = self.mf.resume()
        self.assertEqual(r["decisions"], 4)
        self.assertEqual(r["inputs"], 4)
        self.assertEqual(r["sources"], 3)
        self.assertEqual(r["bkm"], 0)
        self.assertEqual((r["IR"], r["AR"], r["KR"]), (5, 3, 0))

    def test_boundary_optionnel(self):
        noms = [n.nom for n in self.mf.inputs]
        self.assertIn("Free time slot (optionnel)", noms)

    def test_invariants(self):
        self.assertEqual(verifier_invariants(self.mf), [])


class TestParseur(unittest.TestCase):
    def test_namespace_par_defaut(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p" name="Essai">
            <userTask id="t1" name="Vérifier la demande"/>
            <exclusiveGateway id="g1"/>
            <sequenceFlow id="f1" sourceRef="t1" targetRef="g1"/>
          </process>
        </definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertIn("t1", mi.activites)
        mf = transformer(mi)
        self.assertEqual(len(mf.decisions), 1)

    def test_prefixe_exotique(self):
        xml = """<?xml version="1.0"?>
        <x:definitions xmlns:x="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <x:process id="p"><x:task id="t" name="Faire"/></x:process>
        </x:definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertIn("t", mi.activites)

    def test_reference_pendante_signalee(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <userTask id="t1" name="Évaluer le dossier"/>
            <sequenceFlow id="f1" sourceRef="t1" targetRef="fantome"/>
          </process>
        </definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertTrue(mi.anomalies)
        self.assertEqual(len(transformer(mi).decisions), 1)   # pas de plantage

    def test_xml_malforme(self):
        with self.assertRaises(ErreurParseur):
            parser_bpmn("<definitions><oops>", est_texte=True)

    def test_sans_processus(self):
        with self.assertRaises(ErreurParseur):
            parser_bpmn("<definitions xmlns='http://www.omg.org/spec/BPMN/"
                        "20100524/MODEL'/>", est_texte=True)

    def test_sous_processus_deplie(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <subProcess id="sp" name="Instruction">
              <userTask id="t1" name="Évaluer la recevabilité"/>
            </subProcess>
          </process>
        </definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertIn("t1", mi.activites)          # remontée
        self.assertNotIn("sp", mi.activites)       # la façade n'est pas une activité
        self.assertEqual(len(transformer(mi).decisions), 1)

    def test_sous_processus_replie_candidat(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p"><subProcess id="sp" name="Instruire le dossier"/>
          </process>
        </definitions>"""
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual(len(mf.decisions), 0)
        self.assertTrue(any(p.categorie == "candidat"
                            for p in mf.a_confirmer))

    def test_boundary_beta(self):
        """P3 : une frontière non interruptrice porteuse (message) produit
        une donnée « (optionnel) » ; une frontière non porteuse (minuterie)
        ne produit rien — conformité stricte à la spécification."""
        gabarit = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <userTask id="t1" name="Évaluer la demande"/>
            <boundaryEvent id="b1" name="Complément reçu" attachedToRef="t1"
                           cancelActivity="false">%s</boundaryEvent>
          </process>
        </definitions>"""
        mi = parser_bpmn(gabarit % '<messageEventDefinition id="m1"/>',
                         est_texte=True)
        self.assertEqual(mi.beta.get("b1"), "t1")
        mf = transformer(mi)
        self.assertIn("Complément reçu (optionnel)",
                      [n.nom for n in mf.inputs])
        mf2 = transformer(parser_bpmn(
            gabarit % '<timerEventDefinition id="m1"/>', est_texte=True))
        self.assertEqual(len(mf2.inputs), 0)     # minuterie : rien

    def test_association_deux_sens(self):
        gabarit = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <userTask id="t1" name="Évaluer la demande"/>
            <textAnnotation id="a1"><text>Barème de calcul des points</text>
            </textAnnotation>
            <association id="as1" sourceRef="%s" targetRef="%s"/>
          </process>
        </definitions>"""
        for s, t in (("a1", "t1"), ("t1", "a1")):
            mf = transformer(parser_bpmn(gabarit % (s, t), est_texte=True))
            self.assertEqual(len(mf.bkms), 1, "sens %s->%s" % (s, t))

    def test_nom_sur_objet_reference(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <dataObject id="obj" name="Dossier complet"/>
            <dataObjectReference id="ref" dataObjectRef="obj"/>
            <userTask id="t1" name="Vérifier le dossier">
              <dataInputAssociation id="d1">
                <sourceRef>ref</sourceRef>
              </dataInputAssociation>
            </userTask>
          </process>
        </definitions>"""
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual([n.nom for n in mf.inputs], ["Dossier complet"])


class TestQualification(unittest.TestCase):
    def test_omega(self):
        self.assertEqual(omega("Système e-GOV"), "non")
        self.assertEqual(omega("Plateforme en ligne"), "non")
        self.assertEqual(omega("Agent instructeur"), "indetermine")
        arb = Arbitrages.depuis_json({"ressources": {"Agent instructeur": "KS"}})
        self.assertEqual(omega("Agent instructeur", arb), "KS")

    def test_gamma(self):
        self.assertEqual(gamma("a", "Réglementation FIMEX applicable"), "KS")
        self.assertEqual(gamma("a", "Calcul du barème de cotation"), "BKM")
        self.assertEqual(gamma("a", "Apposer le logo officiel"), "non")
        self.assertEqual(gamma("a", "Voir avec le chef"), "indetermine")
        arb = Arbitrages.depuis_json({"annotations": {"a": "I"}})
        self.assertEqual(gamma("a", "Voir avec le chef", arb), "I")

    def test_kappa_lexical_et_position(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <userTask id="lex" name="Évaluer le dossier"/>
            <userTask id="pos" name="Comité de traitement"/>
            <userTask id="rien" name="Saisir les observations"/>
            <exclusiveGateway id="g"/>
            <sequenceFlow id="f1" sourceRef="lex" targetRef="pos"/>
            <sequenceFlow id="f2" sourceRef="pos" targetRef="g"/>
            <sequenceFlow id="f3" sourceRef="g" targetRef="rien"/>
          </process>
        </definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertEqual(kappa(mi, "lex"), {"position": False, "lexical": True})
        self.assertEqual(kappa(mi, "pos"), {"position": True, "lexical": False})
        self.assertEqual(kappa(mi, "rien"),
                         {"position": False, "lexical": False})
        mf = transformer(mi)
        self.assertEqual(len(mf.decisions), 2)
        self.assertEqual([p.objet for p in mf.a_confirmer
                          if p.categorie == "candidat"],
                         ["Saisir les observations"])


class TestSerialisation(unittest.TestCase):
    def test_dmn_relu_identique_et_valide(self):
        mf = transformer(parser_bpmn(FIMEX),
                         Arbitrages.depuis_json(ARBITRAGES_FIMEX))
        dmn = serialiser_dmn(mf)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
        racine = ET.fromstring(dmn)                 # XML bien formé
        self.assertTrue(racine.tag.endswith("definitions"))
        self.assertIn("https://www.omg.org/spec/DMN/20191111/MODEL/",
                      racine.tag)

    def test_arcs_di_presents(self):
        mf = transformer(parser_bpmn(FIMEX))
        dmn = serialiser_dmn(mf)
        self.assertEqual(dmn.count("DMNEdge"), 2 * len(mf.arcs))


class TestInverse(unittest.TestCase):
    def test_aller_retour_fimex(self):
        mf = transformer(parser_bpmn(FIMEX),
                         Arbitrages.depuis_json(ARBITRAGES_FIMEX))
        bpmn, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts = equivalents(mf, mf2)
        self.assertTrue(ok, ecarts)

    def test_bpmn_inverse_bien_forme(self):
        mf = transformer(parser_bpmn(FIMEX))
        bpmn, _ = inverser(mf)
        racine = ET.fromstring(bpmn)
        self.assertTrue(racine.tag.endswith("definitions"))
        self.assertIn("BPMNDiagram", bpmn)


class TestCampagneEchantillon(unittest.TestCase):
    """Échantillon de la campagne massive (la campagne complète se lance
    par `python cli.py campagne 10000`)."""

    def test_echantillon(self):
        for seed in range(500, 650):
            bpmn, attendu = generer(seed)
            mi = parser_bpmn(bpmn, est_texte=True)
            mf = transformer(mi)
            self.assertEqual(verifier_invariants(mf), [],
                             "graine %d" % seed)
            self.assertEqual(comparer_a_oracle(mf, attendu), [],
                             "graine %d" % seed)
            dmn = serialiser_dmn(mf)
            self.assertEqual(verifier_dmn_serialise(dmn, mf), [],
                             "graine %d" % seed)
            if mf.decisions:
                bpmn2, arb = inverser(mf)
                mf2 = transformer(parser_bpmn(bpmn2, est_texte=True),
                                  Arbitrages.depuis_json(arb))
                ok, ecarts = equivalents(mf, mf2)
                self.assertTrue(ok, "graine %d : %s" % (seed, ecarts))

    def test_graine_2002783_arrondi_flottant(self):
        """Régression : un barycentre en tiers (577,833…) faisait boucler
        la mise en page à l'infini (test de chevauchement vrai à un ULP
        près sans progression). Corrigé par coordonnées entières +
        arrondi au plafond — la chaîne complète doit aboutir."""
        bpmn, _ = generer(2002783)
        mf = transformer(parser_bpmn(bpmn, est_texte=True))
        dmn = serialiser_dmn(mf)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
        bpmn2, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts = equivalents(mf, mf2)
        self.assertTrue(ok, ecarts)

    def test_determinisme(self):
        bpmn, _ = generer(4242)
        d1 = serialiser_dmn(transformer(parser_bpmn(bpmn, est_texte=True)))
        d2 = serialiser_dmn(transformer(parser_bpmn(bpmn, est_texte=True)))
        self.assertEqual(d1, d2)


class TestRelectureDuCode(unittest.TestCase):
    """Cas limites relevés à la relecture du code."""

    def test_h1_ordre_xsd_des_exigences(self):
        """XSD tDecision : informationRequirement*, puis knowledgeRequirement*,
        puis authorityRequirement* — jamais entremêlés."""
        import re
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <dataObjectReference id="o1" name="Dossier"/>
            <userTask id="t1" name="Évaluer la demande">
              <dataInputAssociation id="d1"><sourceRef>o1</sourceRef>
              </dataInputAssociation>
              <dataOutputAssociation id="d2"><targetRef>r1</targetRef>
              </dataOutputAssociation>
            </userTask>
            <dataObjectReference id="r1" name="Résultat"/>
            <userTask id="t2" name="Statuer sur la demande">
              <dataInputAssociation id="d3"><sourceRef>r1</sourceRef>
              </dataInputAssociation>
              <dataInputAssociation id="d4"><sourceRef>o2</sourceRef>
              </dataInputAssociation>
            </userTask>
            <dataObjectReference id="o2" name="Avis technique"/>
            <sequenceFlow id="f1" sourceRef="t1" targetRef="t2"/>
            <textAnnotation id="a1"><text>Réglementation applicable</text>
            </textAnnotation>
            <textAnnotation id="a2"><text>Barème de calcul du score</text>
            </textAnnotation>
            <association id="as1" sourceRef="a1" targetRef="t2"/>
            <association id="as2" sourceRef="a2" targetRef="t2"/>
          </process>
        </definitions>"""
        mf = transformer(parser_bpmn(xml, est_texte=True))
        dmn = serialiser_dmn(mf)
        for bloc in re.findall(r"<decision .*?</decision>", dmn, re.S):
            genres = re.findall(r"<(informationRequirement|"
                                r"knowledgeRequirement|"
                                r"authorityRequirement)", bloc)
            rangs = [{"informationRequirement": 0, "knowledgeRequirement": 1,
                      "authorityRequirement": 2}[g] for g in genres]
            self.assertEqual(rangs, sorted(rangs), bloc)

    def test_m1_annotations_homonymes_et_longues(self):
        """Deux annotations d'autorité distinctes aux 60 premiers caractères
        identiques donnent deux sources, aux noms complets."""
        prefixe = "Réglementation générale des importations en zone franche "
        t1 = prefixe + "— annexe 1"
        t2 = prefixe + "— annexe 2"
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <userTask id="ta" name="Évaluer la demande"/>
            <userTask id="tb" name="Statuer sur la demande"/>
            <textAnnotation id="a1"><text>%s</text></textAnnotation>
            <textAnnotation id="a2"><text>%s</text></textAnnotation>
            <association id="s1" sourceRef="a1" targetRef="ta"/>
            <association id="s2" sourceRef="a2" targetRef="tb"/>
          </process>
        </definitions>""" % (t1, t2)
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual(sorted(n.nom for n in mf.sources), sorted([t1, t2]))

    def test_m2_aller_retour_drd_externe(self):
        """DRD étranger : BKM sans préfixe « Règle : », KS homonymes,
        identifiants exotiques — l'aller-retour reste exact."""
        drd = """<?xml version="1.0"?>
        <definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
                     id="d" name="Externe" namespace="http://x">
          <decision id="d.1" name="Statuer sur l'indemnisation">
            <informationRequirement id="i1">
              <requiredInput href="#in1"/></informationRequirement>
            <knowledgeRequirement id="k1">
              <requiredKnowledge href="#b1"/></knowledgeRequirement>
            <authorityRequirement id="r1">
              <requiredAuthority href="#s1"/></authorityRequirement>
          </decision>
          <decision id="d-1" name="Fixer le montant">
            <informationRequirement id="i2">
              <requiredDecision href="#d.1"/></informationRequirement>
            <authorityRequirement id="r2">
              <requiredAuthority href="#s2"/></authorityRequirement>
          </decision>
          <inputData id="in1" name="Rapport d'expertise"/>
          <businessKnowledgeModel id="b1"
              name="Barème d'indemnisation par type de dommage"/>
          <knowledgeSource id="s1" name="Expert métier"/>
          <knowledgeSource id="s2" name="Expert métier"/>
        </definitions>"""
        mf = parser_dmn(drd, est_texte=True)
        bpmn, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts = equivalents(mf, mf2)
        self.assertTrue(ok, ecarts)

    def test_b2_callactivity_signalee(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <callActivity id="c1" name="Statuer sur la demande"/>
          </process>
        </definitions>"""
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertTrue(any(p.categorie == "hors-definition"
                            for p in mf.a_confirmer))

    def test_garde_acyclicite_p4(self):
        """Deux décisions qui s'échangent mutuellement des objets : l'arc
        qui fermerait le circuit est écarté et signalé à l'expert
        (garde d'acyclicité) — le DRD reste acyclique."""
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p">
            <dataObjectReference id="o1" name="Avis A"/>
            <dataObjectReference id="o2" name="Avis B"/>
            <userTask id="a" name="Évaluer le volet technique">
              <dataInputAssociation id="d1"><sourceRef>o2</sourceRef>
              </dataInputAssociation>
              <dataOutputAssociation id="d2"><targetRef>o1</targetRef>
              </dataOutputAssociation></userTask>
            <userTask id="b" name="Évaluer le volet financier">
              <dataInputAssociation id="d3"><sourceRef>o1</sourceRef>
              </dataInputAssociation>
              <dataOutputAssociation id="d4"><targetRef>o2</targetRef>
              </dataOutputAssociation></userTask>
            <sequenceFlow id="f1" sourceRef="a" targetRef="b"/>
            <sequenceFlow id="f2" sourceRef="b" targetRef="a"/>
          </process>
        </definitions>"""
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertTrue(mf.acyclique())
        self.assertEqual(verifier_invariants(mf), [])
        self.assertEqual(len([1 for u, v in mf.arcs
                              if mf.noeuds[u].type == "Decision"]), 1)
        self.assertTrue(any(p.categorie == "circuit"
                            for p in mf.a_confirmer))

    def test_b3_collision_id_entre_pools(self):
        xml = """<?xml version="1.0"?>
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <process id="p1"><userTask id="T" name="Évaluer A"/></process>
          <process id="p2"><userTask id="T" name="Décider B"/></process>
        </definitions>"""
        mi = parser_bpmn(xml, est_texte=True)
        self.assertEqual(mi.noeuds["T"].nom, "Évaluer A")   # premier conservé
        self.assertTrue(any("dupliqué" in a for a in mi.anomalies))


class TestMiseEnPage(unittest.TestCase):
    def test_ajout_di(self):
        bpmn, _ = generer(7)
        self.assertFalse(possede_di(bpmn))
        avec = ajouter_di(bpmn)
        self.assertTrue(possede_di(avec))
        ET.fromstring(avec)                        # reste bien formé
        # tous les nœuds de flux ont une forme
        mi = parser_bpmn(avec, est_texte=True)
        for nid in mi.noeuds:
            self.assertIn('bpmnElement="%s"' % nid, avec)
        # le modèle transformé reste identique
        ok, _ = equivalents(transformer(parser_bpmn(bpmn, est_texte=True)),
                            transformer(mi))
        self.assertTrue(ok)


class TestCasLimites(unittest.TestCase):
    """Sous-processus dépliés, données sur branches parallèles, très
    grands modèles, identifiants et caractères hostiles."""

    NS = 'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'

    def test_sous_processus_deplie_relie_au_flux(self):
        """A écrit un avis, B le lit depuis un sous-processus : P4 pose
        l'arc décision A -> décision B, et B, dernier nœud du sous-processus
        suivi d'une passerelle exclusive, est corroborée par sa position."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <startEvent id="s"/>
            <dataObjectReference id="o" name="Avis technique"/>
            <userTask id="A" name="Évaluer le volet technique">
              <dataOutputAssociation id="w"><targetRef>o</targetRef>
              </dataOutputAssociation>
            </userTask>
            <subProcess id="SP" name="Instruction">
              <startEvent id="s2"/>
              <userTask id="B" name="Comité de traitement">
                <dataInputAssociation id="r"><sourceRef>o</sourceRef>
                </dataInputAssociation>
              </userTask>
              <sequenceFlow id="i1" sourceRef="s2" targetRef="B"/>
            </subProcess>
            <exclusiveGateway id="g" name="Recevable ?"/>
            <endEvent id="e"/>
            <sequenceFlow id="f1" sourceRef="s" targetRef="A"/>
            <sequenceFlow id="f2" sourceRef="A" targetRef="SP"/>
            <sequenceFlow id="f3" sourceRef="SP" targetRef="g"/>
            <sequenceFlow id="f4" sourceRef="g" targetRef="e"/>
          </process>
        </definitions>""" % self.NS
        mi = parser_bpmn(xml, est_texte=True)
        self.assertNotIn("SP", mi.successeurs("A"))
        self.assertIn("s2", mi.successeurs("A"))
        self.assertEqual(mi.successeurs("B"), ["g"])
        self.assertEqual(mi.predecesseurs("g"), ["B"])
        self.assertTrue(kappa(mi, "B")["position"])
        mf = transformer(mi)
        self.assertEqual(len(mf.decisions), 2)
        self.assertIn((mf.delta["A"], mf.delta["B"]), mf.arcs)
        self.assertEqual(mf.arcs_origine[(mf.delta["A"], mf.delta["B"])], "P4")
        self.assertEqual(len(mf.inputs), 0)     # l'avis est un IR d -> d
        self.assertEqual(verifier_invariants(mf), [])

    def test_sous_processus_imbriques_et_frontiere(self):
        """Deux niveaux d'imbrication : le flux traverse les deux façades ;
        une frontière porteuse posée sur la façade externe alimente la
        décision interne ; le couloir se transmet sur deux niveaux."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <laneSet id="ls"><lane id="l" name="Agent">
              <flowNodeRef>sp1</flowNodeRef></lane></laneSet>
            <startEvent id="s"/>
            <subProcess id="sp1" name="Externe">
              <subProcess id="sp2" name="Interne">
                <userTask id="t" name="Évaluer la demande"/>
              </subProcess>
            </subProcess>
            <boundaryEvent id="b" name="Pièce reçue" attachedToRef="sp1"
                           cancelActivity="false">
              <messageEventDefinition id="m"/>
            </boundaryEvent>
            <exclusiveGateway id="g"/>
            <sequenceFlow id="f1" sourceRef="s" targetRef="sp1"/>
            <sequenceFlow id="f2" sourceRef="sp1" targetRef="g"/>
          </process>
        </definitions>""" % self.NS
        mi = parser_bpmn(xml, est_texte=True)
        self.assertEqual(sorted(mi.flux_sequence),
                         [("s", "t", ""), ("t", "g", "")])
        self.assertEqual(mi.noeuds["t"].ressource, "Agent")
        self.assertEqual(mi.contenu("sp1"), ["sp2", "t"])
        mf = transformer(mi)
        self.assertEqual([n.nom for n in mf.inputs],
                         ["Pièce reçue (optionnel)"])
        self.assertEqual(verifier_invariants(mf), [])

    def test_p2_donnee_produite_sur_branche_parallele(self):
        """d1 écrit O et d2 lit O sur deux branches parallèles : d1 ne
        précède pas d2, P4 ne pose rien, O doit rester une donnée d'entrée
        de d2 plutôt que de disparaître."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <dataObjectReference id="o" name="Observations"/>
            <parallelGateway id="pg"/>
            <userTask id="d1" name="Évaluer le volet technique">
              <dataOutputAssociation id="w"><targetRef>o</targetRef>
              </dataOutputAssociation>
            </userTask>
            <userTask id="d2" name="Évaluer le volet financier">
              <dataInputAssociation id="r"><sourceRef>o</sourceRef>
              </dataInputAssociation>
            </userTask>
            <sequenceFlow id="f1" sourceRef="pg" targetRef="d1"/>
            <sequenceFlow id="f2" sourceRef="pg" targetRef="d2"/>
          </process>
        </definitions>""" % self.NS
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual([n.nom for n in mf.inputs], ["Observations"])
        self.assertIn((mf.iota["o"], mf.delta["d2"]), mf.arcs)
        self.assertEqual(len([1 for u, v in mf.arcs
                              if mf.noeuds[u].type == "Decision"]), 0)
        # en séquence, la même donnée redevient un IR décision -> décision
        xml2 = xml.replace('sourceRef="pg" targetRef="d2"',
                           'sourceRef="d1" targetRef="d2"')
        mf2 = transformer(parser_bpmn(xml2, est_texte=True))
        self.assertEqual(len(mf2.inputs), 0)
        self.assertIn((mf2.delta["d1"], mf2.delta["d2"]), mf2.arcs)

    def test_donnee_directe_et_flux_de_donnees_inconnu(self):
        """Une association vers un <dataObject> sans référence produit
        quand même une donnée d'entrée ; une cible inexistante est
        signalée sans bloquer."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <dataStore id="ds" name="Registre des opérateurs"/>
          <process id="p">
            <dataObject id="obj" name="Dossier complet"/>
            <userTask id="t" name="Vérifier le dossier">
              <dataInputAssociation id="d1"><sourceRef>obj</sourceRef>
              </dataInputAssociation>
              <dataInputAssociation id="d2"><sourceRef>ds</sourceRef>
              </dataInputAssociation>
              <dataInputAssociation id="d3"><sourceRef>fantome</sourceRef>
              </dataInputAssociation>
            </userTask>
          </process>
        </definitions>""" % self.NS
        mi = parser_bpmn(xml, est_texte=True)
        self.assertEqual(mi.donnees["obj"].categorie, "objet")
        self.assertEqual(mi.donnees["ds"].categorie, "magasin")
        self.assertTrue(any("flux de données" in a and "fantome" in a
                            for a in mi.anomalies))
        mf = transformer(mi)
        self.assertEqual(sorted(n.nom for n in mf.inputs),
                         ["Dossier complet", "Registre des opérateurs"])

    def test_candidats_homonymes_distincts(self):
        """Deux tâches homonymes non corroborées : deux points à arbitrer,
        chacun sous sa propre clé."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <userTask id="t1" name="Saisir les observations"/>
            <userTask id="t2" name="Saisir les observations"/>
          </process>
        </definitions>""" % self.NS
        mf = transformer(parser_bpmn(xml, est_texte=True))
        candidats = [p for p in mf.a_confirmer if p.categorie == "candidat"]
        self.assertEqual(sorted(p.cle for p in candidats), ["t1", "t2"])

    def test_tache_de_service_signalee_par_le_lexique(self):
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <serviceTask id="s1" name="Évaluer le score automatiquement"/>
          </process>
        </definitions>""" % self.NS
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual([p.cle for p in mf.a_confirmer
                          if p.categorie == "hors-definition"], ["s1"])

    def test_chaine_de_1500_decisions_en_ordre_inverse(self):
        """Couches du sérialiseur et tri topologique de l'inverse sans
        récursion : D1 requiert D2, qui requiert D3... jusqu'à D1500."""
        from bpmn2dmn.metamodeles import DECISION, Mf, NoeudMf
        n = 1500
        mf = Mf(nom="Chaîne")
        for i in range(1, n + 1):
            mf.noeuds["D%d" % i] = NoeudMf(id="D%d" % i, type=DECISION,
                                           nom="Décision %d" % i)
        for i in range(1, n):
            mf.arcs.append(("D%d" % (i + 1), "D%d" % i))
        dmn = serialiser_dmn(mf)
        self.assertEqual(verifier_dmn_serialise(dmn, mf), [])
        bpmn, _ = inverser(mf)
        mi = parser_bpmn(bpmn, est_texte=True)
        taches = [nid for nid in mi.noeuds if nid.startswith("t_")]
        self.assertEqual(taches[0], "t_D%d" % n)      # la plus amont d'abord
        self.assertEqual(taches[-1], "t_D1")

    def test_caracteres_interdits_par_xml(self):
        """Un renommage contenant un caractère de contrôle ne doit pas
        produire un document mal formé, ni en DMN ni en BPMN inverse."""
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p">
            <userTask id="t" name="Évaluer la demande"/>
            <textAnnotation id="a"><text>Réglementation applicable</text>
            </textAnnotation>
            <association id="as" sourceRef="a" targetRef="t"/>
          </process>
        </definitions>""" % self.NS
        arb = Arbitrages.depuis_json({
            "renommages": {"t": "Statuer\u0001 sur la demande"},
            "noms": {"a": "Norme\u0002 applicable"}})
        mf = transformer(parser_bpmn(xml, est_texte=True), arb)
        dmn = serialiser_dmn(mf)
        racine = ET.fromstring(dmn)
        self.assertIn("Statuer sur la demande",
                      [e.get("name") for e in racine.iter()])
        bpmn, _ = inverser(mf)
        ET.fromstring(bpmn)

    def test_inverse_identifiants_derives_uniques(self):
        """inputData « X » et « X_o » : les objets porteurs ne se
        télescopent pas, et l'aller-retour reste exact."""
        drd = """<?xml version="1.0"?>
        <definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
                     id="d" name="Collision" namespace="http://x">
          <decision id="d1" name="Statuer sur la demande">
            <informationRequirement id="i1">
              <requiredInput href="#X"/></informationRequirement>
            <informationRequirement id="i2">
              <requiredInput href="#X_o"/></informationRequirement>
          </decision>
          <inputData id="X" name="Dossier"/>
          <inputData id="X_o" name="Pièces jointes"/>
        </definitions>"""
        mf = parser_dmn(drd, est_texte=True)
        bpmn, arb = inverser(mf)
        ids = [e.get("id") for e in ET.fromstring(bpmn).iter() if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)), sorted(ids))
        mf2 = transformer(parser_bpmn(bpmn, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts = equivalents(mf, mf2)
        self.assertTrue(ok, ecarts)

    def test_drd_vide_serialise_sans_probleme(self):
        xml = """<?xml version="1.0"?>
        <definitions %s>
          <process id="p"><userTask id="t" name="Saisir la demande"/>
          </process>
        </definitions>""" % self.NS
        mf = transformer(parser_bpmn(xml, est_texte=True))
        self.assertEqual(len(mf.decisions), 0)
        self.assertEqual(verifier_dmn_serialise(serialiser_dmn(mf), mf), [])

    def test_mise_en_page_commentaire_final_et_collaboration(self):
        xml = """<?xml version="1.0"?>
        <definitions %s id="defs">
          <collaboration id="col">
            <participant id="p1" name="Demandeur" processRef="proc1"/>
            <participant id="p2" name="Guichet" processRef="proc2"/>
            <messageFlow id="m1" sourceRef="t1" targetRef="t2"/>
          </collaboration>
          <process id="proc1"><userTask id="t1" name="Déposer"/></process>
          <process id="proc2"><userTask id="t2" name="Évaluer la demande"/>
          </process>
        </definitions>
        <!-- exporté sans mise en page -->
        """ % self.NS
        avec = ajouter_di(xml)
        self.assertTrue(possede_di(avec))
        racine = ET.fromstring(avec)
        plans = [e for e in racine.iter() if e.tag.endswith("BPMNPlane")]
        self.assertEqual(plans[0].get("bpmnElement"), "col")
        formes = {e.get("bpmnElement"): e for e in racine.iter()
                  if e.tag.endswith("BPMNShape")}
        self.assertEqual(set(formes), {"p1", "p2", "t1", "t2"})

        def cadre(nid):
            b = [x for x in formes[nid].iter() if x.tag.endswith("Bounds")][0]
            return tuple(float(b.get(k)) for k in ("x", "y", "width", "height"))

        for part, tache in (("p1", "t1"), ("p2", "t2")):
            px, py, pw, ph = cadre(part)
            tx, ty, tw, th = cadre(tache)
            self.assertTrue(px <= tx and tx + tw <= px + pw)
            self.assertTrue(py <= ty and ty + th <= py + ph)
        x1, y1, w1, h1 = cadre("p1")
        self.assertLessEqual(y1 + h1, cadre("p2")[1])   # bandes disjointes
        self.assertIn('bpmnElement="m1"', avec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
