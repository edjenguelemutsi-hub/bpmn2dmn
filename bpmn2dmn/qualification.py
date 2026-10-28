# -*- coding: utf-8 -*-
"""
Fonctions de qualification kappa (corroboration), omega (ressources) et
gamma (annotations), telles que le cadre formel les définit, et arbitrages de l'expert.

Les règles ouvertes (P5, P6) et les candidats non corroborés ne sont pas
tranchés par le programme seul (objectif OS4) : il propose, motive et
trace, l'expert du domaine arbitre. Les arbitrages sont lus dans un
fichier JSON et réappliqués de façon déterministe :

    {
      "candidats":   {"<id activité>": true | false},
      "ressources":  {"<nom ressource>": "KS" | "non"},
      "annotations": {"<id annotation>": "I" | "KS" | "BKM" | "non"},
      "renommages":  {"<id activité>": "Nom de la décision"}
    }

Le lexique de décision Λ reprend celui de mon premier prototype et
l'étend (français et anglais) ; c'est un paramètre, un lexique métier peut
lui être substitué sans toucher à l'algorithme.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict

from .metamodeles import Mi, NoeudFlux

# Λ : lexique des verbes de décision (indice lexical de kappa)
LAMBDA_VERBES = (
    # français (premier prototype) + extensions courantes
    "evaluer", "verifier", "decider", "statuer", "affecter", "coter",
    "apprecier", "examiner", "arbitrer", "juger", "selectionner", "choisir",
    "classer", "qualifier", "approuver", "autoriser", "accorder",
    "refuser", "rejeter", "estimer", "diagnostiquer", "prioriser",
    "determiner", "trancher", "controler",
    # anglais (idem) ; « valider »/« validate » sont volontairement exclus :
    # valider pour signature, valider un formulaire... ne décident rien
    # (contre-exemple FIMEX T8, référence experte)
    "evaluate", "verify", "decide", "assess", "make", "plan", "determine",
    "check", "approve", "authorize", "authorise", "select", "choose",
    "classify", "grade", "review", "judge", "rank", "screen",
    "prioritize", "prioritise", "accept", "reject", "grant", "diagnose",
    "estimate", "assign", "allocate",
)

# omega : indices qu'une ressource est un système (il exécute, ne gouverne
# pas). « service » n'y figure pas : un « Service juridique » ou un « Chef de
# service » est une unité humaine.
IND_SYSTEME = ("systeme", "system", "plateforme", "platform", "moteur",
               "engine", "serveur", "server", "automate", "robot", "batch",
               "application", "logiciel", "software", "bot")

# indices qu'une ressource gouverne une décision (extension
# « roles-gouvernants ») : instances collégiales, autorités, fonctions de
# direction, de contrôle et de signature
IND_GOUVERNANCE = ("comite", "commission", "conseil", "jury", "directeur",
                   "directrice", "direction", "chef", "responsable",
                   "autorite", "ministre", "ministere", "signataire",
                   "superviseur", "controleur", "inspecteur", "president",
                   "secretaire general", "gouverneur", "decideur",
                   "board", "committee", "commission", "council", "director",
                   "head", "manager", "supervisor", "authority", "officer",
                   "chief", "inspector", "controller", "approver", "signatory")

# gamma : indices lexicaux des trois catégories d'annotation
IND_AUTORITE = ("reglementation", "regulation", "reglement", "guideline",
                "recommandation", "directive", "norme", "standard",
                "procedure", "loi", "law", "decret", "arrete", "criteres",
                "convention", "protocole",
                "criteria", "consider", "hospitalize if", "policy",
                "politique", "charte", "code ", "circulaire", "referentiel")
IND_REGLE = ("aleatoire", "equitable", "calcul", "algorithme", "formule",
             "ponderation", "repartition", "bareme", "scoring", "score",
             "random", "round robin", "formula", "computation", "if ", "si ",
             "seuil", "threshold", "taux", "rate", "grille")
IND_NON_DECISIONNEL = ("qr code", "cachet", "mise en forme", "meme medecin",
                       "same doctor", "signataire porte", "police de caracteres", "logo",
                       "format", "couleur", "color", "font", "layout",
                       "remarque technique", "todo", "a faire", "note :")


def normaliser(s: str) -> str:
    """Minuscules, sans accents ni ponctuation parasite (comparaisons)."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def premier_mot(s: str) -> str:
    mots = normaliser(s).replace("'", " ").split()
    return mots[0] if mots else ""


def contient_indice(texte_normalise: str, indice: str) -> bool:
    """Vrai si l'indice figure dans le texte en commençant sur une frontière
    de mot et, sauf s'il se termine lui-même par une espace, en finissant
    sur une autre. Sans cette précaution, « plan » se lirait dans
    « transplanter » et « format » dans « information »."""
    motif = r"(?<![a-z0-9])" + re.escape(indice)
    if not indice.endswith(" "):
        motif += r"(?![a-z0-9])"
    return re.search(motif, texte_normalise) is not None


@dataclass
class Arbitrages:
    """Verdicts de l'expert, réappliqués de façon déterministe."""
    candidats: Dict[str, bool] = field(default_factory=dict)
    ressources: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    renommages: Dict[str, str] = field(default_factory=dict)
    noms: Dict[str, str] = field(default_factory=dict)
    #   annotation id -> nom exact du nœud KS/BKM/I à produire (posé par la
    #   transformation inverse pour restituer les libellés à l'identique)

    @classmethod
    def depuis_json(cls, chemin_ou_dict) -> "Arbitrages":
        if isinstance(chemin_ou_dict, dict):
            d = chemin_ou_dict
        elif isinstance(chemin_ou_dict, str):
            with open(chemin_ou_dict, encoding="utf-8") as f:
                d = json.load(f)
        else:
            raise TypeError("arbitrages : dictionnaire ou chemin de fichier "
                            "attendu, pas %s" % type(chemin_ou_dict).__name__)
        if not isinstance(d, dict):
            raise TypeError("arbitrages : un objet JSON est attendu")
        return cls(candidats={k: _booleen(v) for k, v in
                              _section(d, "candidats").items()},
                   ressources=_textes(_section(d, "ressources")),
                   annotations=_textes(_section(d, "annotations")),
                   renommages=_textes(_section(d, "renommages")),
                   noms=_textes(_section(d, "noms")))


def _section(d: dict, cle: str) -> dict:
    valeur = d.get(cle) or {}
    if not isinstance(valeur, dict):
        raise TypeError("arbitrages : « %s » doit être un objet" % cle)
    return valeur


def _booleen(v) -> bool:
    """Verdict vrai/faux ; les chaînes « true »/« false » sont tolérées,
    tout autre texte est refusé plutôt que deviné."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    raise TypeError("arbitrages : verdict de candidat invalide : %r" % (v,))


def _textes(section: dict) -> Dict[str, str]:
    for k, v in section.items():
        if not isinstance(v, str):
            raise TypeError("arbitrages : valeur non textuelle pour « %s »"
                            % k)
    return dict(section)


VIDE = Arbitrages()


# kappa : prédicat de corroboration
def indice_position(mi: Mi, aid: str) -> bool:
    """∃ g ∈ G : (a,g) ∈ E_s et g exclusive (ou inclusive : même sémantique
    de verdict appliqué — choix du prototype, conservé)."""
    for t in mi.successeurs(aid):
        n = mi.noeuds.get(t)
        if n is not None and n.type in ("exclusiveGateway", "inclusiveGateway"):
            return True
    return False


def indice_lexical(activite: NoeudFlux) -> bool:
    """verbe(a) ∈ Λ : le libellé commence par un verbe de décision, ou en
    contient un (tolérance du prototype, conservée pour le rappel)."""
    n = normaliser(activite.nom)
    if not n:
        return False
    if premier_mot(activite.nom) in LAMBDA_VERBES:
        return True
    return any(contient_indice(n, v) for v in LAMBDA_VERBES)


def kappa(mi: Mi, aid: str) -> Dict[str, bool]:
    """Retourne les deux indices — le prédicat vaut leur disjonction."""
    a = mi.noeuds[aid]
    return {"position": indice_position(mi, aid),
            "lexical": indice_lexical(a)}


# omega : qualification d'une ressource, {KS, ⊥} ou indéterminé
def omega(ressource: str, arbitrages: Arbitrages = VIDE) -> str:
    """Retourne "KS", "non" (⊥ : simple exécutant) ou "indetermine"."""
    verdict = arbitrages.ressources.get(ressource)
    if verdict in ("KS", "non"):
        return verdict
    n = normaliser(ressource)
    if any(contient_indice(n, k) for k in IND_SYSTEME):
        return "non"
    return "indetermine"


def indice_gouvernance(ressource: str) -> bool:
    """Vrai si le nom de la ressource porte un indice de gouvernance
    (extension « roles-gouvernants »), par mots entiers."""
    n = normaliser(ressource)
    return any(contient_indice(n, k) for k in IND_GOUVERNANCE)


# gamma : qualification d'une annotation, {I, KS, BKM, ⊥} ou indéterminé
def gamma(annotation_id: str, texte: str,
          arbitrages: Arbitrages = VIDE) -> str:
    """Retourne "I", "KS", "BKM", "non" (⊥ : décorative) ou "indetermine"."""
    verdict = arbitrages.annotations.get(annotation_id)
    if verdict in ("I", "KS", "BKM", "non"):
        return verdict
    n = normaliser(texte)
    if not n:
        return "non"
    if any(contient_indice(n, k) for k in IND_NON_DECISIONNEL):
        return "non"
    if any(contient_indice(n, k) for k in IND_REGLE):
        return "BKM"
    if any(contient_indice(n, k) for k in IND_AUTORITE):
        return "KS"
    return "indetermine"
