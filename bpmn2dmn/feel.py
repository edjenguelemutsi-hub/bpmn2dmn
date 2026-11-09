# -*- coding: utf-8 -*-
"""
Lecture des conditions écrites sur les flux de séquence et écriture de
tests unaires FEEL, pour l'ébauche des tables de décision (extension
« logique »).

Une condition de flux est écrite dans le langage que le modélisateur a
choisi : FEEL (`montant > 5000 and pays = "CM"`), JUEL de Camunda
(`${montant > 5000 && paysARisque}`), JavaScript ou Groovy
(`montant > 5000 || !paysARisque`). L'analyseur accepte le sous-ensemble
commun à ces langages : comparaisons d'une variable à un littéral
(nombre, chaîne, booléen), variables booléennes nues, négation,
conjonction, disjonction, parenthèses. Tout ce qui sort de ce
sous-ensemble (appel de fonction, arithmétique, comparaison de deux
variables) rend la condition « non lue » : la règle de la table garde
alors ses cellules à compléter et la condition d'origine en description,
rien n'est deviné.

Le résultat est une forme normale disjonctive : une liste de conjonctions
d'atomes ; chaque conjonction devient une règle de la table (une
disjonction donne donc plusieurs règles pour une même branche), et les
atomes portant sur une même variable sont réunis en un test unaire FEEL
(`> 5000`, `"CM"`, `true`, `[18..65)`, `not("A", "B")`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .qualification import normaliser

_MOTIF_JETON = re.compile(
    r"\s*(?:"
    r"(?P<nombre>-?\d+(?:[.,]\d+)?)"
    r"|(?P<chaine>\"[^\"]*\"|'[^']*')"
    r"|(?P<op>==|!=|<>|<=|>=|=|<|>|&&|\|\||!)"
    r"|(?P<paren>[()])"
    r"|(?P<ident>[A-Za-z_À-ſ][\w.À-ſ]*)"
    r")")

_ET = {"and", "&&", "et", "und"}
_OU = {"or", "||", "ou", "oder"}
_NON = {"not", "!", "non", "nicht", "no"}
_VRAI = {"true", "vrai", "wahr", "verdadero", "oui", "yes", "ja", "si", "sí"}
_FAUX = {"false", "faux", "falsch", "falso", "non", "no", "nein"}
_INVERSE = {"=": "!=", "!=": "=", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}


@dataclass(frozen=True)
class Atome:
    """variable <operateur> valeur ; `type_` vaut number, boolean ou string."""
    variable: str
    operateur: str          # = != < <= > >=
    valeur: str             # littéral tel qu'il sera écrit en FEEL
    type_: str

    def inverse(self) -> "Atome":
        if self.type_ == "boolean":        # not(x = true)  ->  x = false
            return Atome(self.variable, "=",
                         "false" if self.valeur == "true" else "true", "boolean")
        return Atome(self.variable, _INVERSE[self.operateur], self.valeur, self.type_)


Conjonction = Tuple[Atome, ...]
FND = List[Conjonction]      # forme normale disjonctive


class ConditionNonLue(ValueError):
    """La condition sort du sous-ensemble lu."""


def _jetons(texte: str) -> List[Tuple[str, str]]:
    t = re.sub(r"[$#]\{(.*?)\}", r" \1 ", texte, flags=re.S).strip()
    jetons: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(t):
        m = _MOTIF_JETON.match(t, pos)
        if not m or m.end() == pos:
            raise ConditionNonLue("caractère inattendu à la position %d" % pos)
        pos = m.end()
        for genre in ("nombre", "chaine", "op", "paren", "ident"):
            v = m.group(genre)
            if v is not None:
                jetons.append((genre, v))
                break
    return jetons


class _Analyseur:
    """Descente récursive : expr := terme (OU terme)* ; terme := facteur (ET
    facteur)* ; facteur := NON facteur | ( expr ) | comparaison | variable."""

    def __init__(self, jetons: List[Tuple[str, str]]):
        self.j = jetons
        self.i = 0

    def regarder(self) -> Optional[Tuple[str, str]]:
        return self.j[self.i] if self.i < len(self.j) else None

    def avancer(self) -> Tuple[str, str]:
        tok = self.j[self.i]
        self.i += 1
        return tok

    def est(self, ensemble) -> bool:
        tok = self.regarder()
        return tok is not None and tok[0] in ("op", "ident") and tok[1].lower() in ensemble

    def expr(self) -> FND:
        gauche = self.terme()
        while self.est(_OU):
            self.avancer()
            gauche = gauche + self.terme()
        return gauche

    def terme(self) -> FND:
        gauche = self.facteur()
        while self.est(_ET):
            self.avancer()
            droite = self.facteur()
            gauche = [a + b for a in gauche for b in droite]
        return gauche

    def facteur(self) -> FND:
        tok = self.regarder()
        if tok is None:
            raise ConditionNonLue("expression incomplète")
        if self.est(_NON):
            self.avancer()
            if self.regarder() == ("paren", "("):
                self.avancer()
                interieur = self.expr()
                self._fermer()
            else:
                interieur = self.facteur()
            return _nier(interieur)
        if tok == ("paren", "("):
            self.avancer()
            interieur = self.expr()
            self._fermer()
            return interieur
        return self.comparaison()

    def _fermer(self) -> None:
        if self.regarder() != ("paren", ")"):
            raise ConditionNonLue("parenthèse fermante attendue")
        self.avancer()

    def comparaison(self) -> FND:
        genre, v = self.avancer()
        if genre == "ident" and v.lower() in _VRAI | _FAUX | _ET | _OU | _NON:
            raise ConditionNonLue("littéral ou mot réservé isolé : %s" % v)
        suivant = self.regarder()
        if suivant is not None and suivant[0] == "op" and suivant[1] not in ("&&", "||", "!"):
            op = self.avancer()[1]
            op = {"==": "=", "<>": "!="}.get(op, op)
            if genre == "ident":
                variable, (gd, vd) = v, self._operande()
                if gd == "ident" and vd.lower() not in _VRAI | _FAUX:
                    raise ConditionNonLue("comparaison de deux variables : %s %s %s" % (v, op, vd))
                return [(_atome(variable, op, gd, vd),)]
            # littéral à gauche : 5000 < montant  ->  montant > 5000
            gd, vd = self._operande()
            if gd != "ident":
                raise ConditionNonLue("comparaison sans variable")
            renverse = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}.get(op, op)
            return [(_atome(vd, renverse, genre, v),)]
        if genre == "ident":
            return [(Atome(v, "=", "true", "boolean"),)]      # booléen nu
        raise ConditionNonLue("littéral isolé : %s" % v)

    def _operande(self) -> Tuple[str, str]:
        tok = self.regarder()
        if tok is None or tok[0] not in ("nombre", "chaine", "ident"):
            raise ConditionNonLue("opérande attendu")
        self.avancer()
        if tok[0] == "ident" and self.regarder() == ("paren", "("):
            raise ConditionNonLue("appel de fonction : %s(...)" % tok[1])
        return tok


def _atome(variable: str, op: str, genre: str, valeur: str) -> Atome:
    if genre == "nombre":
        return Atome(variable, op, valeur.replace(",", "."), "number")
    if genre == "chaine":
        return Atome(variable, op, '"%s"' % valeur[1:-1].replace('"', "'"), "string")
    bas = valeur.lower()
    if bas in _VRAI or bas in _FAUX:
        if op not in ("=", "!="):
            raise ConditionNonLue("comparaison ordonnée sur un booléen")
        return Atome(variable, op, "true" if bas in _VRAI else "false", "boolean")
    raise ConditionNonLue("opérande inattendu : %s" % valeur)


def _nier(fnd: FND) -> FND:
    """Négation d'une forme normale disjonctive (De Morgan, puis
    redistribution) ; les conjonctions obtenues restent petites sur les
    conditions de flux usuelles."""
    resultat: FND = [()]
    for conj in fnd:
        alternatives = [(a.inverse(),) for a in conj]
        resultat = [r + alt for r in resultat for alt in alternatives]
    return resultat


def analyser(texte: str) -> Optional[FND]:
    """La forme normale disjonctive d'une condition, ou None si la
    condition n'est pas lue (texte vide, sous-ensemble dépassé)."""
    if not texte or not texte.strip():
        return None
    try:
        jetons = _jetons(texte)
        if not jetons:
            return None
        analyseur = _Analyseur(jetons)
        fnd = analyseur.expr()
        if analyseur.regarder() is not None:
            raise ConditionNonLue("texte en trop après l'expression")
    except ConditionNonLue:
        return None
    # une conjonction contradictoire (x = 1 et x = 2) est conservée telle
    # quelle : l'expert la verra dans la table
    return fnd


def variables(fnd: FND) -> List[str]:
    """Les variables de la forme normale, dans l'ordre d'apparition."""
    vues: List[str] = []
    for conj in fnd:
        for a in conj:
            if a.variable not in vues:
                vues.append(a.variable)
    return vues


def test_unaire(atomes: List[Atome]) -> str:
    """Le test unaire FEEL d'une cellule, pour les atomes d'une même
    variable dans une même règle : « - » sans atome, un intervalle pour une
    paire de bornes, « not(...) » pour des exclusions, sinon la liste des
    tests séparés par des virgules (disjonction en FEEL)."""
    if not atomes:
        return "-"
    egalites = [a for a in atomes if a.operateur == "="]
    exclusions = [a for a in atomes if a.operateur == "!="]
    bornes = [a for a in atomes if a.operateur in ("<", "<=", ">", ">=")]
    parties: List[str] = []
    if egalites:
        parties.extend(a.valeur for a in egalites)
    if exclusions and not egalites:
        parties.append("not(%s)" % ", ".join(a.valeur for a in exclusions))
    inf = [a for a in bornes if a.operateur in (">", ">=")]
    sup = [a for a in bornes if a.operateur in ("<", "<=")]
    if len(inf) == 1 and len(sup) == 1:
        parties.append("%s%s..%s%s" % ("[" if inf[0].operateur == ">=" else "(",
                                       inf[0].valeur, sup[0].valeur,
                                       "]" if sup[0].operateur == "<=" else ")"))
    else:
        parties.extend("%s %s" % (a.operateur, a.valeur) for a in bornes)
    return ", ".join(parties) if parties else "-"


def type_feel(atomes: List[Atome]) -> str:
    types = {a.type_ for a in atomes}
    if types == {"number"}:
        return "number"
    if types == {"boolean"}:
        return "boolean"
    return "string"


def identifiant_feel(nom: str) -> str:
    """Un nom de variable FEEL lisible tiré d'un libellé : « Dossier
    constitué ? » -> dossierConstitue ; un identifiant reste tel quel."""
    if re.match(r"^[A-Za-z_][\w.]*$", nom or ""):
        return nom
    mots = re.findall(r"[a-z0-9]+", normaliser(nom))
    if not mots:
        return "valeur"
    return mots[0] + "".join(m[:1].upper() + m[1:] for m in mots[1:])


def libelle_booleen(libelle: str) -> Optional[bool]:
    """« oui », « yes », « ja » -> True ; « non », « no », « nein » -> False ;
    sinon None (le libellé n'est pas une réponse à une question fermée)."""
    n = normaliser(libelle).strip(" .!")
    if n in _VRAI:
        return True
    if n in _FAUX:
        return False
    return None


def condition_feel(conj: Conjonction) -> str:
    """Réécrit une conjonction en expression FEEL complète (pour reporter
    une règle de table de décision dans la condition d'un flux)."""
    parties = []
    for a in conj:
        if a.type_ == "boolean" and a.operateur == "=":
            parties.append(a.variable if a.valeur == "true" else "not(%s)" % a.variable)
        else:
            parties.append("%s %s %s" % (a.variable, a.operateur, a.valeur))
    return " and ".join(parties)


def regle_vers_condition(cellules: Dict[str, str], types: Dict[str, str]) -> str:
    """Les cellules d'une règle (variable -> test unaire) réécrites en une
    condition FEEL de flux ; une cellule « - » n'impose rien."""
    parties: List[str] = []
    for variable, test in cellules.items():
        test = (test or "").strip()
        if not test or test == "-":
            continue
        t = types.get(variable, "string")
        morceaux = [m.strip() for m in _decouper_tests(test)]
        sous: List[str] = []
        for m in morceaux:
            if re.match(r"^[\[(].*\.\..*[\])]$", m):
                bas, haut = m[1:-1].split("..", 1)
                sous.append("%s %s %s and %s %s %s" % (
                    variable, ">=" if m[0] == "[" else ">", bas.strip(),
                    variable, "<=" if m[-1] == "]" else "<", haut.strip()))
            elif m.startswith("not(") and m.endswith(")"):
                valeurs = [x.strip() for x in m[4:-1].split(",")]
                sous.append(" and ".join("%s != %s" % (variable, v) for v in valeurs))
            elif re.match(r"^(<=|>=|<|>|!=|=)\s*", m):
                op = re.match(r"^(<=|>=|<|>|!=|=)", m).group(1)
                sous.append("%s %s %s" % (variable, op, m[len(op):].strip()))
            elif t == "boolean" and m in ("true", "false"):
                sous.append(variable if m == "true" else "not(%s)" % variable)
            else:
                sous.append("%s = %s" % (variable, m))
        parties.append("(%s)" % " or ".join(sous) if len(sous) > 1 else sous[0])
    return " and ".join(parties)


def _decouper_tests(test: str) -> List[str]:
    """Sépare « "A", "B" » ou « < 5, > 10 » sur les virgules hors
    parenthèses et hors chaînes."""
    morceaux, courant, prof, chaine = [], "", 0, None
    for c in test:
        if chaine:
            courant += c
            if c == chaine:
                chaine = None
            continue
        if c in "\"'":
            chaine = c
            courant += c
        elif c in "([":
            prof += 1
            courant += c
        elif c in ")]":
            prof -= 1
            courant += c
        elif c == "," and prof == 0:
            morceaux.append(courant)
            courant = ""
        else:
            courant += c
    if courant.strip():
        morceaux.append(courant)
    return morceaux
