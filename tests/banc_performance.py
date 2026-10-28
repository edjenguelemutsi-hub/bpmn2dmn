# -*- coding: utf-8 -*-
"""Banc de performance : chaîne de N décisions liées par objets partagés
(pire cas du pattern P4 : N-1 arcs décision->décision + atteignabilité)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bpmn2dmn.parseur import parser_bpmn
from bpmn2dmn.transformation import transformer
from bpmn2dmn.serialiseur import serialiser_dmn

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
M = ['<?xml version="1.0"?><definitions '
     'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
     '<process id="p" name="Chaine geante">']
for i in range(N):
    M.append('<dataObjectReference id="o%d" name="Resultat %d"/>' % (i, i))
    entree = ('<dataInputAssociation id="di%d"><sourceRef>o%d</sourceRef>'
              '</dataInputAssociation>' % (i, i - 1)) if i else ''
    M.append('<userTask id="t%d" name="Evaluer le lot %d">%s'
             '<dataOutputAssociation id="do%d"><targetRef>o%d</targetRef>'
             '</dataOutputAssociation></userTask>' % (i, i, entree, i, i))
    if i:
        M.append('<sequenceFlow id="f%d" sourceRef="t%d" targetRef="t%d"/>'
                 % (i, i - 1, i))
M.append('</process></definitions>')
xml = "".join(M)

debut = time.time()
mi = parser_bpmn(xml, est_texte=True)
t_parse = time.time() - debut
mf = transformer(mi)
t_transfo = time.time() - debut - t_parse
dmn = serialiser_dmn(mf)
t_total = time.time() - debut
print("N=%d : %d décisions, %d arcs — parseur %.2fs, T %.2fs, "
      "total (avec DMN+DI) %.2fs, acyclique=%s"
      % (N, len(mf.decisions), len(mf.arcs), t_parse, t_transfo,
         t_total, mf.acyclique()))
