# -*- coding: utf-8 -*-
"""
Écriture d'un classeur Excel (.xlsx) avec la seule bibliothèque standard.

Un fichier .xlsx est une archive ZIP de documents XML (Office Open XML).
Nous n'en écrivons que ce dont le registre a besoin : plusieurs feuilles,
une ligne d'en-tête en gras sur fond coloré, la première ligne figée, un
filtre automatique, des largeurs de colonnes, et des cellules typées
(nombres entiers ou décimaux, textes). Le classeur produit s'ouvre dans
Excel, LibreOffice et Google Sheets, et se relit avec openpyxl.
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

Feuille = Tuple[str, Sequence[str], Iterable[Sequence[object]], Optional[Sequence[float]]]
#   (nom, en-têtes, lignes, largeurs de colonnes en caractères ou None)

_TYPES_CONTENU = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    '%s</Types>')

_RELS_RACINE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
    '</Relationships>')

# styles : 0 = normal, 1 = en-tête (gras, fond bleu clair), 2 = décimal
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="0.000"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF1C4587"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE8EEF7"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="3">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
    '<alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>')


def _colonne(index: int) -> str:
    """Numéro de colonne (à partir de 0) en lettres : A, B, ..., Z, AA..."""
    lettres = ""
    index += 1
    while index:
        index, reste = divmod(index - 1, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


def _cellule(ref: str, valeur, style: int = 0) -> str:
    if valeur is None or valeur == "":
        return ""
    if isinstance(valeur, bool):
        valeur = int(valeur)
    if isinstance(valeur, int):
        return '<c r="%s"%s><v>%d</v></c>' % (ref, ' s="%d"' % style if style else "", valeur)
    if isinstance(valeur, float):
        s = style or 2
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, s, repr(valeur))
    texte = escape(str(valeur))
    return ('<c r="%s" t="inlineStr"%s><is><t xml:space="preserve">%s</t></is></c>'
            % (ref, ' s="%d"' % style if style else "", texte))


def _feuille_xml(entetes: Sequence[str], lignes: Iterable[Sequence[object]],
                 largeurs: Optional[Sequence[float]]) -> str:
    parts: List[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
        '<sheetFormatPr defaultRowHeight="15"/>',
    ]
    if largeurs:
        parts.append("<cols>")
        for i, w in enumerate(largeurs):
            parts.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                         % (i + 1, i + 1, w))
        parts.append("</cols>")
    parts.append("<sheetData>")
    parts.append('<row r="1">' + "".join(
        _cellule("%s1" % _colonne(i), e, 1) for i, e in enumerate(entetes)) + "</row>")
    n = 1
    for ligne in lignes:
        n += 1
        parts.append('<row r="%d">' % n + "".join(
            _cellule("%s%d" % (_colonne(i), n), v) for i, v in enumerate(ligne)) + "</row>")
    parts.append("</sheetData>")
    if entetes:
        parts.append('<autoFilter ref="A1:%s%d"/>' % (_colonne(len(entetes) - 1), max(n, 1)))
    parts.append("</worksheet>")
    return "".join(parts)


def ecrire_classeur(chemin: str, feuilles: Sequence[Feuille],
                    titre: str = "", auteur: str = "") -> None:
    """Écrit le classeur ; chaque feuille = (nom, en-têtes, lignes, largeurs)."""
    if not feuilles:
        raise ValueError("un classeur doit avoir au moins une feuille")
    maintenant = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    overrides, feuilles_wb, rels_wb, contenus = [], [], [], []
    for i, (nom, entetes, lignes, largeurs) in enumerate(feuilles, start=1):
        overrides.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType='
                         '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
                         'worksheet+xml"/>' % i)
        feuilles_wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                           % (escape(nom[:31]), i, i))
        rels_wb.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                       'officeDocument/2006/relationships/worksheet" '
                       'Target="worksheets/sheet%d.xml"/>' % (i, i))
        contenus.append(("xl/worksheets/sheet%d.xml" % i,
                         _feuille_xml(entetes, lignes, largeurs)))
    n = len(feuilles)
    rels_wb.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   % (n + 1))
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView/></bookViews>'
        '<sheets>%s</sheets></workbook>' % "".join(feuilles_wb))
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships">%s</Relationships>' % "".join(rels_wb))
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
            'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>%s</dc:title><dc:creator>%s</dc:creator>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
            '</cp:coreProperties>' % (escape(titre), escape(auteur), maintenant, maintenant))
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
           'extended-properties"><Application>Transformateur BPMN-DMN</Application>'
           '</Properties>')
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPES_CONTENU % "".join(overrides))
        z.writestr("_rels/.rels", _RELS_RACINE)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/styles.xml", _STYLES)
        for nom, contenu in contenus:
            z.writestr(nom, contenu)
