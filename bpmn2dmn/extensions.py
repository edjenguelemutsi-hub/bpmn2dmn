# -*- coding: utf-8 -*-
"""
Les extensions de l'algorithme de transformation.

Chacune répond à une limite établie par le catalogue de patterns. Toutes
sont désactivées par défaut : l'algorithme de référence produit alors
exactement les mêmes résultats qu'avant leur introduction. Elles
s'activent une à une (`transformer(mi, arbitrages, extensions={...})`,
option `--extensions` de la ligne de commande, cases à cocher de
l'application) et la variante retenue est consignée dans le registre des
expérimentations. Le détail de chaque règle est dans
`EXTENSIONS-ALGORITHME.md`.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import FrozenSet, Iterable, Union

EXTENSIONS: "OrderedDict[str, str]" = OrderedDict([
    ("definition-etendue",
     "Une tâche générique, de service, d'envoi, de réception, manuelle, de "
     "script ou un appel d'activité corroborés par kappa deviennent des "
     "candidats : retenus avec les deux indices, soumis à l'expert avec un seul."),
    ("conditions-passerelle",
     "Les variables lues dans les conditions des flux sortants des passerelles "
     "qui suivent une décision sont proposées comme données d'entrée (P7), "
     "créées après arbitrage."),
    ("evenements-conditionnels",
     "Un événement à définition conditionnelle (condition sur des données) est "
     "porteur : il alimente la décision comme un message (P3)."),
    ("donnees-processus",
     "Les données d'entrée et de sortie déclarées au niveau du processus "
     "(ioSpecification) sont traitées comme des objets de données (P2)."),
    ("roles-gouvernants",
     "Un couloir dont le nom porte un indice de gouvernance (comité, "
     "directeur, signataire...) est proposé comme source de connaissance, "
     "l'expert confirmant (P5)."),
    ("noms-suggeres",
     "Pour une décision retenue par la seule position, un nom est suggéré "
     "d'après la question de la passerelle qui la suit (delta)."),
    ("logique",
     "Chaque décision suivie d'une passerelle reçoit dans le DMN une table de "
     "décision squelette : entrées = ses exigences, sorties = les branches de "
     "la passerelle (vers le déploiement dans Camunda)."),
])

TOUTES = frozenset(EXTENSIONS)


def normaliser_extensions(valeur: Union[None, str, Iterable[str]]) -> FrozenSet[str]:
    """Un ensemble d'extensions valides à partir d'une chaîne (« a,b »,
    « toutes ») ou d'une liste ; un nom inconnu lève ValueError."""
    if valeur is None:
        return frozenset()
    if isinstance(valeur, str):
        noms = [x.strip() for x in valeur.replace(";", ",").replace("+", ",").split(",")]
    else:
        noms = [str(x).strip() for x in valeur]
    noms = [n for n in noms if n]
    if any(n in ("toutes", "all") for n in noms):
        return TOUTES
    inconnues = [n for n in noms if n not in EXTENSIONS]
    if inconnues:
        raise ValueError("extension(s) inconnue(s) : %s ; extensions disponibles : %s"
                         % (", ".join(inconnues), ", ".join(EXTENSIONS)))
    return frozenset(noms)


def variante(extensions: Iterable[str]) -> str:
    """Le libellé consigné dans le registre : « reference » ou la liste."""
    actives = sorted(set(extensions))
    return "extensions:" + "+".join(actives) if actives else "reference"


def texte_liste() -> str:
    L = ["Extensions de l'algorithme (désactivées par défaut) :"]
    for nom, phrase in EXTENSIONS.items():
        L.append("  %-26s %s" % (nom, phrase))
    L.append("  %-26s %s" % ("toutes", "active toutes les extensions"))
    return "\n".join(L)
