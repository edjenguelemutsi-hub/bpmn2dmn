# -*- coding: utf-8 -*-
"""
Parseur BPMN 2.0 -> Mi (le modèle de processus réduit), première boîte du schéma de
construction.

Le parseur accepte les fichiers des principaux outils (Camunda Modeler,
bpmn.io, Signavio, Bizagi, ADONIS, Bonita) : tout espace de noms se
terminant par le nom local BPMN est reconnu, les processus d'une
collaboration sont fusionnés dans un même Mi, les sous-processus sont
dépliés (un sous-processus est remplacé par ses activités), les
couloirs donnent la fonction rho et les événements frontières la fonction
beta. Les défauts non bloquants (référence pendante, identifiant dupliqué)
sont collectés dans `mi.anomalies` sans interrompre la lecture.

`parser_bpmn` enchaîne les étapes de lecture ; `_parser_processus` lit un
processus élément par élément et se rappelle sur les sous-processus.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple

from .metamodeles import (ACTIVITES, DEFINITIONS_PORTEUSES, EVENEMENTS,
                          Mi, NoeudDonnees, NoeudFlux, PASSERELLES)

NOEUDS_DE_FLUX = ACTIVITES | PASSERELLES | EVENEMENTS
SOUS_PROCESSUS = ("subProcess", "transaction", "adHocSubProcess")
EVENEMENTS_RECEPTEURS = ("startEvent", "intermediateCatchEvent", "boundaryEvent")


def _local(tag: str) -> str:
    """Nom local d'une balise, sans namespace."""
    return tag.split("}")[-1] if "}" in tag else tag


def _texte_annotation(elem: ET.Element) -> str:
    """Texte d'une textAnnotation (élément <text> enfant, quel que soit le ns)."""
    for enfant in elem:
        if _local(enfant.tag) == "text":
            return "".join(enfant.itertext()).strip()
    return "".join(elem.itertext()).strip()


def _refs(elem: ET.Element, balise: str, attribut: str) -> List[str]:
    """Références d'une data*Association : élément enfant <balise> ou attribut."""
    out = []
    for enfant in elem:
        if _local(enfant.tag) == balise and enfant.text and enfant.text.strip():
            out.append(enfant.text.strip())
    if not out and elem.get(attribut):
        out.append(elem.get(attribut).strip())
    return out


class ErreurParseur(Exception):
    """Fichier illisible ou sans processus BPMN exploitable."""


def parser_bpmn(chemin_ou_texte: str, est_texte: bool = False) -> Mi:
    """Lit un fichier (ou une chaîne) BPMN 2.0 et construit Mi."""
    racine, source = _lire_racine(chemin_ou_texte, est_texte)
    processus = _processus_non_vides(racine)

    mi = Mi(source=source)
    noms = [p.get("name") for p in processus if p.get("name")]
    mi.nom = " + ".join(noms) if noms else (processus[0].get("id") or source)
    defs_donnees = _definitions_donnees(racine)

    conteneur_de: Dict[str, str] = {}          # nœud -> id du subProcess parent
    facades: List[str] = []                    # sous-processus dépliés
    for proc in processus:
        pid = proc.get("id") or ""
        _parser_processus(mi, proc, pid, defs_donnees, conteneur_de, facades)
    mi.conteneur = dict(conteneur_de)
    _relier_sous_processus(mi, facades)

    _lire_artefacts_hors_processus(mi, racine)
    _affecter_ressources(mi, racine, conteneur_de)       # couloirs -> rho
    _marquer_flux_messages(mi, racine)
    _adopter_donnees_directes(mi, defs_donnees)
    _controler_coherence(mi)
    return mi


def _lire_racine(chemin_ou_texte: str, est_texte: bool) -> Tuple[ET.Element, str]:
    """L'élément <definitions> du document et le nom de sa source."""
    try:
        if est_texte:
            racine = ET.parse(io.StringIO(chemin_ou_texte)).getroot()
            source = "<mémoire>"
        else:
            racine = ET.parse(chemin_ou_texte).getroot()
            source = str(chemin_ou_texte)
    except ET.ParseError as e:
        raise ErreurParseur("XML mal formé : %s" % e) from e
    if _local(racine.tag) != "definitions":
        raise ErreurParseur("La racine n'est pas <definitions> (BPMN 2.0 attendu), "
                            "mais <%s>." % _local(racine.tag))
    return racine, source


def _processus_non_vides(racine: ET.Element) -> List[ET.Element]:
    """Les processus non vides (un pool « boîte noire » n'a pas de contenu)."""
    processus = []
    for elem in racine.iter():
        if _local(elem.tag) == "process":
            if any(_local(x.tag) in NOEUDS_DE_FLUX for x in elem.iter()):
                processus.append(elem)
    if not processus:
        raise ErreurParseur("Aucun processus BPMN non vide dans le fichier.")
    return processus


def _definitions_donnees(racine: ET.Element) -> Dict[str, Tuple[str, str]]:
    """Objets et magasins déclarés (les références y renvoient) :
    id -> (catégorie, nom)."""
    defs_donnees: Dict[str, Tuple[str, str]] = {}
    for elem in racine.iter():
        t = _local(elem.tag)
        if t in ("dataObject", "dataStore"):
            defs_donnees[elem.get("id") or ""] = (
                "objet" if t == "dataObject" else "magasin",
                elem.get("name") or "")
    return defs_donnees


def _lire_artefacts_hors_processus(mi: Mi, racine: ET.Element) -> None:
    """Annotations et associations hors processus : certains outils les
    placent au niveau de la collaboration."""
    for elem in racine.iter():
        t = _local(elem.tag)
        if t == "textAnnotation":
            nid = elem.get("id") or ""
            if nid and nid not in mi.donnees:
                mi.donnees[nid] = NoeudDonnees(id=nid, categorie="annotation",
                                               nom=_texte_annotation(elem))
        elif t == "association":
            s = (elem.get("sourceRef") or "").strip()
            c = (elem.get("targetRef") or "").strip()
            if s and c and (s, c) not in mi.flux_donnees:
                mi.flux_donnees.append((s, c))


def _affecter_ressources(mi: Mi, racine: ET.Element,
                         conteneur_de: Dict[str, str]) -> None:
    """Couloirs -> fonction rho. Héritage : un nœud remonté d'un
    sous-processus prend la ressource du premier sous-processus englobant
    qui en a une, à tout niveau."""
    rho: Dict[str, str] = {}
    for elem in racine.iter():
        if _local(elem.tag) != "lane":
            continue
        nom_lane = elem.get("name") or ""
        if not nom_lane:
            continue
        for enfant in elem:
            if _local(enfant.tag) == "flowNodeRef" and enfant.text:
                rho[enfant.text.strip()] = nom_lane
    for nid, ressource in rho.items():
        if nid in mi.noeuds:
            mi.noeuds[nid].ressource = ressource
    for nid, parent in conteneur_de.items():
        if nid not in mi.noeuds or mi.noeuds[nid].ressource is not None:
            continue
        while parent is not None and parent not in rho:
            parent = conteneur_de.get(parent)
        if parent is not None:
            mi.noeuds[nid].ressource = rho[parent]


def _marquer_flux_messages(mi: Mi, racine: ET.Element) -> None:
    """Flux de messages inter-pools : la charge utile vient de l'autre
    pool, l'événement récepteur devient porteur de données."""
    for elem in racine.iter():
        if _local(elem.tag) != "messageFlow":
            continue
        cible = (elem.get("targetRef") or "").strip()
        n = mi.noeuds.get(cible)
        if n is not None and n.nature == "evenement" and \
           n.type in EVENEMENTS_RECEPTEURS:
            n.porteur_donnees = True


def _adopter_donnees_directes(mi: Mi, defs_donnees: Dict[str, Tuple[str, str]]) -> None:
    """Un objet ou magasin visé directement par une association de
    données, sans dataObjectReference/dataStoreReference, devient lui-même
    un nœud de DN plutôt que d'être perdu."""
    for s, t in mi.flux_donnees:
        for x in (s, t):
            if x not in mi.noeuds and x not in mi.donnees and x in defs_donnees:
                categorie, nom = defs_donnees[x]
                mi.donnees[x] = NoeudDonnees(id=x, categorie=categorie, nom=nom)


def _controler_coherence(mi: Mi) -> None:
    """Contrôles non bloquants : les flux vers un identifiant inconnu sont
    signalés dans les anomalies puis écartés."""
    ids_connus = set(mi.noeuds) | set(mi.donnees)
    for s, t, _ in mi.flux_sequence:
        for x in (s, t):
            if x not in mi.noeuds:
                mi.anomalies.append("flux de séquence vers l'identifiant "
                                    "inconnu « %s »" % x)
    for s, t in mi.flux_donnees:
        for x in (s, t):
            if x not in ids_connus:
                mi.anomalies.append("flux de données vers l'identifiant "
                                    "inconnu « %s »" % x)
    mi.flux_sequence = [(s, t, l) for s, t, l in mi.flux_sequence
                        if s in mi.noeuds and t in mi.noeuds]
    mi.flux_donnees_ecartes = [(s, t) for s, t in mi.flux_donnees
                               if s not in ids_connus or t not in ids_connus]
    mi.flux_donnees = [(s, t) for s, t in mi.flux_donnees
                       if s in ids_connus and t in ids_connus]
    mi.beta = {e: a for e, a in mi.beta.items()
               if e in mi.noeuds and a in mi.noeuds}


def _parser_processus(mi: Mi, proc: ET.Element, pid: str,
                      defs_donnees: Dict[str, Tuple[str, str]],
                      conteneur_de: Dict[str, str],
                      facades: List[str]) -> None:
    """Parcourt un <process> ou un <subProcess> (dépliage récursif)."""
    for elem in proc:
        t = _local(elem.tag)
        nid = elem.get("id") or ""

        # les id BPMN sont des xsd:ID uniques ; certains fichiers issus de
        # fusions multi-outils les dupliquent entre pools : on conserve la
        # première occurrence et on le signale plutôt que d'écraser en silence
        if nid and nid in mi.noeuds and t in NOEUDS_DE_FLUX:
            mi.anomalies.append(
                "identifiant « %s » dupliqué entre processus : seule la "
                "première occurrence est conservée" % nid)
            continue

        if t in SOUS_PROCESSUS:
            _parser_sous_processus(mi, elem, nid, pid, defs_donnees,
                                   conteneur_de, facades)
        elif t in ACTIVITES:
            mi.noeuds[nid] = NoeudFlux(id=nid, type=t,
                                       nom=elem.get("name") or "",
                                       nature="activite", processus=pid)
            _extraire_associations_donnees(mi, elem, nid)
        elif t in PASSERELLES:
            mi.noeuds[nid] = NoeudFlux(id=nid, type=t,
                                       nom=elem.get("name") or "",
                                       nature="passerelle", processus=pid)
        elif t in EVENEMENTS:
            _parser_evenement(mi, elem, nid, t, pid)
        elif t == "sequenceFlow":
            s = (elem.get("sourceRef") or "").strip()
            c = (elem.get("targetRef") or "").strip()
            mi.flux_sequence.append((s, c, elem.get("name") or ""))
            for enfant in elem:
                if _local(enfant.tag) == "conditionExpression":
                    texte = "".join(enfant.itertext()).strip()
                    if texte:
                        mi.conditions[(s, c)] = texte
        elif t in ("dataObjectReference", "dataStoreReference"):
            _parser_reference_donnees(mi, elem, nid, t, defs_donnees)
        elif t == "dataStore":
            # magasin déclaré au niveau definitions mais référencé ici
            if nid not in mi.donnees:
                mi.donnees[nid] = NoeudDonnees(id=nid, categorie="magasin",
                                               nom=elem.get("name") or "")
        elif t == "textAnnotation":
            mi.donnees[nid] = NoeudDonnees(id=nid, categorie="annotation",
                                           nom=_texte_annotation(elem))
        elif t == "association":
            s = (elem.get("sourceRef") or "").strip()
            c = (elem.get("targetRef") or "").strip()
            if s and c:
                mi.flux_donnees.append((s, c))
        elif t == "ioSpecification":
            # données d'entrée et de sortie du processus : relevées pour
            # l'extension « donnees-processus », ignorées par la transformation
            # de référence
            for enfant in elem:
                if _local(enfant.tag) in ("dataInput", "dataOutput") and enfant.get("id"):
                    mi.donnees_processus[enfant.get("id")] = enfant.get("name") or ""
        # laneSet, artefacts divers : traités ailleurs ou ignorés


def _parser_sous_processus(mi: Mi, elem: ET.Element, nid: str, pid: str,
                           defs_donnees: Dict[str, Tuple[str, str]],
                           conteneur_de: Dict[str, str],
                           facades: List[str]) -> None:
    """Un sous-processus détaillé est déplié : les nœuds internes sont
    remontés au niveau du processus ; le sous-processus garde un nœud
    « façade » de type subProcess, hors du graphe de séquence (voir
    _relier_sous_processus), qui n'est pas une activité mais reste résolu
    pour les couloirs et les frontières. Un sous-processus replié (aucun
    détail) est une activité candidate."""
    enfants_flux = [x for x in elem if _local(x.tag) in NOEUDS_DE_FLUX]
    if enfants_flux:
        mi.noeuds[nid] = NoeudFlux(
            id=nid, type="subProcess", nom=elem.get("name") or "",
            nature="passerelle",       # neutre : ni activité, ni décision
            processus=pid)
        facades.append(nid)
        _parser_processus(mi, elem, pid, defs_donnees, conteneur_de, facades)
        for x in elem:
            xid = x.get("id") or ""
            if xid and _local(x.tag) in NOEUDS_DE_FLUX:
                conteneur_de[xid] = nid
    else:
        mi.noeuds[nid] = NoeudFlux(
            id=nid, type="subProcess", nom=elem.get("name") or "",
            nature="activite", processus=pid)
    _extraire_associations_donnees(mi, elem, nid)


def _parser_evenement(mi: Mi, elem: ET.Element, nid: str, t: str, pid: str) -> None:
    """Un événement, porteur s'il a une définition de message ou de
    signal ; une frontière renseigne beta et son caractère interrupteur."""
    definitions = [_local(x.tag) for x in elem if _local(x.tag).endswith("EventDefinition")]
    porteur = any(d in DEFINITIONS_PORTEUSES for d in definitions)
    if definitions:
        mi.definitions_evenements[nid] = definitions
    n = NoeudFlux(id=nid, type=t, nom=elem.get("name") or "",
                  nature="evenement", porteur_donnees=porteur,
                  processus=pid)
    if t == "boundaryEvent":
        hote = (elem.get("attachedToRef") or "").strip()
        if hote:
            mi.beta[nid] = hote
        n.interrompt = (elem.get("cancelActivity") or "true") \
            .lower() != "false"
    mi.noeuds[nid] = n
    _extraire_associations_donnees(mi, elem, nid)


def _parser_reference_donnees(mi: Mi, elem: ET.Element, nid: str, t: str,
                              defs_donnees: Dict[str, Tuple[str, str]]) -> None:
    """Référence d'objet ou de magasin ; sans nom propre, elle prend celui
    de la déclaration visée."""
    categorie = "objet" if t == "dataObjectReference" else "magasin"
    nom = elem.get("name") or ""
    if not nom:
        ref = (elem.get("dataObjectRef") if categorie == "objet"
               else elem.get("dataStoreRef")) or ""
        nom = defs_donnees.get(ref.strip(), ("", ""))[1]
    mi.donnees[nid] = NoeudDonnees(id=nid, categorie=categorie, nom=nom)


def _relier_sous_processus(mi: Mi, facades: List[str]) -> None:
    """Un sous-processus déplié est remplacé par ses activités : les flux
    de séquence qui entraient dans la façade sont redirigés vers chaque
    nœud interne d'entrée (ses événements de départ, à défaut ses nœuds
    sans prédécesseur), ceux qui en sortaient partent de chaque nœud
    interne de sortie (événements de fin, à défaut nœuds sans successeur).
    Les sous-processus imbriqués sont traités de l'intérieur vers
    l'extérieur ; la façade ne porte ensuite plus aucun flux."""
    def profondeur(f: str) -> int:
        n, p = 0, mi.conteneur.get(f)
        while p is not None:
            n, p = n + 1, mi.conteneur.get(p)
        return n

    for f in sorted(facades, key=profondeur, reverse=True):
        internes = [n for n in mi.contenu(f) if n not in facades]
        if not internes:
            continue
        avec_pred: Set[str] = {t for _, t, _ in mi.flux_sequence}
        avec_succ: Set[str] = {s for s, _, _ in mi.flux_sequence}
        ordinaires = [n for n in internes
                      if mi.noeuds[n].type != "boundaryEvent"]
        entrees = [n for n in internes if mi.noeuds[n].type == "startEvent"
                   and n not in avec_pred] \
            or [n for n in ordinaires if n not in avec_pred] or internes
        sorties = [n for n in internes if mi.noeuds[n].type == "endEvent"
                   and n not in avec_succ] \
            or [n for n in ordinaires if n not in avec_succ] or internes
        relies = []
        for s, t, l in mi.flux_sequence:
            for s2 in (sorties if s == f else [s]):
                for t2 in (entrees if t == f else [t]):
                    relies.append((s2, t2, l))
        mi.flux_sequence = relies


def _extraire_associations_donnees(mi: Mi, elem: ET.Element, nid: str) -> None:
    """dataInputAssociation / dataOutputAssociation d'une activité ou d'un
    événement -> arcs de E_d (lecture : donnée -> nœud ; écriture : nœud -> donnée)."""
    for x in elem:
        t = _local(x.tag)
        if t == "dataInputAssociation":
            for src in _refs(x, "sourceRef", "sourceRef"):
                mi.flux_donnees.append((src, nid))
        elif t == "dataOutputAssociation":
            for cible in _refs(x, "targetRef", "targetRef"):
                mi.flux_donnees.append((nid, cible))
