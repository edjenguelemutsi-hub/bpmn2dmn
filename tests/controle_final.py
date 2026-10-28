# -*- coding: utf-8 -*-
"""
Contrôle final de robustesse : entrées hostiles, dégénérées ou extrêmes.

Règle du contrôle : sur toute entrée, l'algorithme doit soit produire un
résultat qui respecte les 8 invariants formels et se sérialise/relit
proprement, soit refuser par une erreur propre (ErreurParseur/ErreurDMN)
— jamais d'exception imprévue, jamais de sortie invalide.

    python tests/controle_final.py
"""
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from bpmn2dmn.parseur import parser_bpmn, ErreurParseur
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import parser_dmn, inverser, ErreurDMN
from bpmn2dmn.qualification import Arbitrages
from bpmn2dmn.validation import (equivalents, verifier_dmn_serialise,
                                 verifier_invariants)

NS = 'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'
resultats = []


def controle(nom, fonction):
    try:
        verdict = fonction()
        resultats.append((nom, True, verdict or "conforme"))
    except (ErreurParseur, ErreurDMN) as e:
        resultats.append((nom, True, "refus propre : %s" % str(e)[:60]))
    except Exception as e:
        resultats.append((nom, False, "%s : %s"
                         % (type(e).__name__, str(e)[:90])))


def chaine_complete(xml, arbitrages=None):
    """BPMN -> Mi -> Mf (invariants) -> DMN relu -> inverse -> aller-retour."""
    mi = parser_bpmn(xml, est_texte=True)
    mf = transformer(mi, Arbitrages.depuis_json(arbitrages)
                     if arbitrages else Arbitrages())
    inv = verifier_invariants(mf)
    assert not inv, "invariants violés : %s" % inv
    dmn = serialiser_dmn(mf)
    pb = verifier_dmn_serialise(dmn, mf)
    assert not pb, "sérialisation : %s" % pb
    if mf.decisions:
        bpmn2, arb = inverser(mf)
        mf2 = transformer(parser_bpmn(bpmn2, est_texte=True),
                          Arbitrages.depuis_json(arb))
        ok, ecarts = equivalents(mf, mf2)
        assert ok, "aller-retour : %s" % ecarts
    return "chaîne complète OK (%d décisions)" % len(mf.decisions)


# 1. entrées illisibles ou vides : refus propre exigé
controle("XML tronqué", lambda: chaine_complete("<definitions><oops>"))
controle("fichier vide", lambda: chaine_complete(""))
controle("pas du XML", lambda: chaine_complete("bonjour le monde"))
controle("racine inattendue", lambda: chaine_complete(
    "<html><body>rien</body></html>"))
controle("definitions sans processus", lambda: chaine_complete(
    '<definitions %s/>' % NS))
controle("processus totalement vide", lambda: chaine_complete(
    '<definitions %s><process id="p"/></definitions>' % NS))
controle("DMN : XML tronqué",
         lambda: parser_dmn("<definitions><oops>", est_texte=True))
controle("DMN : aucune décision", lambda: parser_dmn(
    '<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" '
    'id="d" name="n"><inputData id="i" name="I"/></definitions>',
    est_texte=True))

# 2. modèles dégénérés mais lisibles : chaîne complète exigée
controle("boucle de séquence (cycle BPMN)", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="a" name="Évaluer la demande"/>'
    '<userTask id="b" name="Vérifier le dossier"/>'
    '<sequenceFlow id="f1" sourceRef="a" targetRef="b"/>'
    '<sequenceFlow id="f2" sourceRef="b" targetRef="a"/>'
    '</process></definitions>' % NS))
controle("flux vers soi-même", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="a" name="Évaluer la demande"/>'
    '<sequenceFlow id="f1" sourceRef="a" targetRef="a"/>'
    '</process></definitions>' % NS))
controle("références toutes pendantes", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="a" name="Statuer sur le cas"/>'
    '<sequenceFlow id="f1" sourceRef="x1" targetRef="x2"/>'
    '<association id="s1" sourceRef="x3" targetRef="x4"/>'
    '<textAnnotation id="an1"><text>Barème de calcul</text></textAnnotation>'
    '</process></definitions>' % NS))
controle("décision qui lit ET écrit le même objet", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<dataObjectReference id="o1" name="Dossier"/>'
    '<userTask id="a" name="Évaluer le dossier">'
    '<dataInputAssociation id="d1"><sourceRef>o1</sourceRef>'
    '</dataInputAssociation>'
    '<dataOutputAssociation id="d2"><targetRef>o1</targetRef>'
    '</dataOutputAssociation></userTask>'
    '</process></definitions>' % NS))
controle("deux décisions qui s'échangent mutuellement des objets",
         lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<dataObjectReference id="o1" name="Avis A"/>'
    '<dataObjectReference id="o2" name="Avis B"/>'
    '<userTask id="a" name="Évaluer le volet technique">'
    '<dataInputAssociation id="d1"><sourceRef>o2</sourceRef>'
    '</dataInputAssociation>'
    '<dataOutputAssociation id="d2"><targetRef>o1</targetRef>'
    '</dataOutputAssociation></userTask>'
    '<userTask id="b" name="Évaluer le volet financier">'
    '<dataInputAssociation id="d3"><sourceRef>o1</sourceRef>'
    '</dataInputAssociation>'
    '<dataOutputAssociation id="d4"><targetRef>o2</targetRef>'
    '</dataOutputAssociation></userTask>'
    '<sequenceFlow id="f1" sourceRef="a" targetRef="b"/>'
    '<sequenceFlow id="f2" sourceRef="b" targetRef="a"/>'
    '</process></definitions>' % NS))

# 3. contenus extrêmes : chaîne complète exigée
controle("caractères XML spéciaux dans tous les libellés",
         lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<dataObjectReference id="o1" name="Pièces &lt;A&gt; &amp; «B» \'C\'"/>'
    '<userTask id="a" name="Évaluer &lt;tout&gt; &amp; &quot;statuer&quot;">'
    '<dataInputAssociation id="d1"><sourceRef>o1</sourceRef>'
    '</dataInputAssociation></userTask>'
    '<textAnnotation id="an1"><text>Barème &lt;&amp;&gt; spécial</text>'
    '</textAnnotation>'
    '<association id="s1" sourceRef="an1" targetRef="a"/>'
    '</process></definitions>' % NS))
controle("libellé de 500 caractères", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="a" name="Évaluer %s"/>'
    '</process></definitions>' % (NS, "trés long libellé " * 28)))
controle("identifiants unicode", lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="tâche_décision_1" name="Évaluer le cas"/>'
    '<exclusiveGateway id="passerelle_n°1"/>'
    '<sequenceFlow id="f1" sourceRef="tâche_décision_1" '
    'targetRef="passerelle_n°1"/>'
    '</process></definitions>' % NS))
controle("arbitrages incohérents (clés inconnues, verdicts invalides)",
         lambda: chaine_complete(
    '<definitions %s><process id="p">'
    '<userTask id="a" name="Évaluer la demande"/>'
    '</process></definitions>' % NS,
    arbitrages={"candidats": {"inexistant": True},
                "ressources": {"Personne": "VERDICT_INCONNU"},
                "annotations": {"rien": "??"},
                "renommages": {"fantome": "X"}}))

# 4. DRD hostiles pour l'inverse
DMN_NS = 'xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"'


def drd_cyclique():
    mf = parser_dmn(
        '<definitions %s id="d" name="Cycle">'
        '<decision id="d1" name="A"><informationRequirement id="i1">'
        '<requiredDecision href="#d2"/></informationRequirement></decision>'
        '<decision id="d2" name="B"><informationRequirement id="i2">'
        '<requiredDecision href="#d1"/></informationRequirement></decision>'
        '</definitions>' % DMN_NS, est_texte=True)
    bpmn, _ = inverser(mf)
    return "inverse produit sans plantage (%d flux)" % bpmn.count("sequenceFlow")


def drd_reference_pendante():
    mf = parser_dmn(
        '<definitions %s id="d" name="Pendante">'
        '<decision id="d1" name="A"><informationRequirement id="i1">'
        '<requiredInput href="#fantome"/></informationRequirement>'
        '</decision></definitions>' % DMN_NS, est_texte=True)
    return "lu : %d décisions, %d arcs (pendantes ignorées)" % (
        len(mf.decisions), len(mf.arcs))


def drd_de_reference():
    chemin = os.path.join(RACINE, "corpus", "fimex-drd-reference.dmn")
    mf = parser_dmn(io.open(chemin, encoding="utf-8").read(), est_texte=True)
    bpmn, arbitrages = inverser(mf)
    mf2 = transformer(parser_bpmn(bpmn, est_texte=True),
                      Arbitrages.depuis_json(arbitrages))
    ok, ecarts = equivalents(mf, mf2)
    return "vérifié" if ok else "échec " + str(ecarts)[:60]


controle("DRD avec cycle (décision qui se requiert elle-même)", drd_cyclique)
controle("DRD avec référence pendante", drd_reference_pendante)
controle("DRD de référence FIMEX (corpus/fimex-drd-reference.dmn) :"
         " aller-retour", drd_de_reference)

# bilan
print("Contrôle final de robustesse : %d épreuves" % len(resultats))
print()
echecs = 0
for nom, ok, detail in resultats:
    print(" %-5s %-52s %s" % ("OK" if ok else "ECHEC", nom, detail))
    if not ok:
        echecs += 1
print()
print("Contrôle final : %s" % ("%d épreuves conformes" % len(resultats)
                               if not echecs else "%d échec(s)" % echecs))
sys.exit(1 if echecs else 0)
