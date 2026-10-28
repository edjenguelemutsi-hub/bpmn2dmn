# -*- coding: utf-8 -*-
"""
bpmn2dmn : transformateur BPMN <-> DMN au niveau des exigences de décision (DRD).

Implémente le cadre formel établi dans mes travaux sur la transition
BPMN-DMN (Edjenguele Mutsi Francis Hervé, Université de Douala, M2
Recherche Génie Logiciel) : les métamodèles réduits Mi et Mf, la
transformation T (patterns P1..P6, algorithme de référence raffiné), la
transformation inverse T_inv et la sérialisation
DMN 1.3 + DMNDI et BPMN 2.0 + BPMNDI.

Chaîne de construction : BPMN.xml -> parseur -> Mi -> transformation -> Mf
-> serialiseur -> DRD.xml -> visualiseur.
"""

__version__ = "1.1.0"
