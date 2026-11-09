# -*- coding: utf-8 -*-
"""
L'indice sémantique de kappa : le caractère décisionnel d'un libellé jugé
par un modèle de langue léger, et non plus seulement par l'appartenance de
son verbe à la liste fermée Λ.

Principe. Un modèle de phrases multilingue (MiniLM-L12, douze couches,
384 dimensions, distillé pour la paraphrase, exécuté par ONNX Runtime sur
le processeur, quantifié en entiers de 8 bits) plonge le libellé dans un
espace où deux phrases de même sens sont proches, quelle que soit leur
langue. Un classifieur linéaire (régression logistique) appris sur des
exemples de libellés écrits à la main, décisionnels et non décisionnels,
dans plusieurs langues et plusieurs domaines, donne au libellé un score
entre 0 et 1 ; l'indice vaut vrai au-dessus d'un seuil fixé une fois pour
toutes. Les exemples d'apprentissage ne reprennent aucun libellé du
corpus de validation : le corpus reste un jeu de test.

Ce que l'indice garde des exigences du cadre : il est déterministe (même
modèle, mêmes poids, même seuil, même score à chaque exécution ; les
fichiers sont identifiés par leur empreinte SHA-256), il est tracé (le
score, le seuil et les exemples d'apprentissage les plus proches sont
écrits dans le motif de rétention de la décision), et il est optionnel
(extension « indice-semantique », désactivée par défaut : l'algorithme de
référence n'en dépend pas et ses sorties ne changent pas).

Dépendances, nécessaires seulement si l'extension est activée :
numpy, onnxruntime, tokenizers (`pip install -r requirements-semantique.txt`)
et les fichiers du modèle dans `modeles/minilm-multilingue/` (téléchargés
par `outils/telecharger-modele.py`, 136 Mo, non versionnés).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Dict, List, Optional, Sequence, Tuple

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER_MODELE = os.path.join(ICI, "modeles", "minilm-multilingue")
CHEMIN_CLASSIFIEUR = os.path.join(ICI, "modeles", "classifieur-semantique.json")
CHEMIN_EXEMPLES = os.path.join(ICI, "modeles", "exemples-indice-semantique.txt")
FICHIERS_MODELE = ("model_quantized.onnx", "tokenizer.json")
LONGUEUR_MAX = 64            # jetons : un libellé d'activité est court

_verrou = threading.Lock()
_instance: Optional["IndiceSemantique"] = None


class IndisponibleError(RuntimeError):
    """Le modèle ou le classifieur manquent : l'indice ne peut pas être calculé."""


def modele_present(dossier: str = DOSSIER_MODELE) -> bool:
    return all(os.path.isfile(os.path.join(dossier, f)) for f in FICHIERS_MODELE)


def classifieur_present(chemin: str = CHEMIN_CLASSIFIEUR) -> bool:
    return os.path.isfile(chemin)


def disponible() -> bool:
    """Vrai si l'indice peut être calculé sur cette machine."""
    if not (modele_present() and classifieur_present()):
        return False
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return True


def motif_indisponible() -> str:
    """Pourquoi l'indice n'est pas disponible, en une phrase."""
    manques = []
    if not modele_present():
        manques.append("fichiers du modèle absents de %s (python outils/telecharger-modele.py)"
                       % os.path.relpath(DOSSIER_MODELE))
    if not classifieur_present():
        manques.append("classifieur absent (%s)" % os.path.relpath(CHEMIN_CLASSIFIEUR))
    for paquet in ("numpy", "onnxruntime", "tokenizers"):
        try:
            __import__(paquet)
        except ImportError:
            manques.append("paquet Python « %s » non installé" % paquet)
    return "indice sémantique indisponible : " + " ; ".join(manques) \
        if manques else ""


def empreinte_fichier(chemin: str) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def lire_exemples(chemin: str = CHEMIN_EXEMPLES) -> List[Tuple[str, str]]:
    """Les exemples d'apprentissage : liste de (classe « D » ou « N », libellé)."""
    exemples: List[Tuple[str, str]] = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.rstrip("\n")
            if not ligne.strip() or ligne.startswith("#"):
                continue
            classe, _, texte = ligne.partition("\t")
            classe, texte = classe.strip().upper(), texte.strip()
            if classe in ("D", "N") and texte:
                exemples.append((classe, texte))
    return exemples


class Plongeur:
    """Le modèle de phrases : texte -> vecteur unitaire de 384 réels."""

    def __init__(self, dossier: str = DOSSIER_MODELE, fils: int = 2):
        if not modele_present(dossier):
            raise IndisponibleError(motif_indisponible())
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.dossier = dossier
        self.tokenizer = Tokenizer.from_file(os.path.join(dossier, "tokenizer.json"))
        self.tokenizer.enable_truncation(LONGUEUR_MAX)
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            os.path.join(dossier, "model_quantized.onnx"), options,
            providers=["CPUExecutionProvider"])
        self.entrees = [e.name for e in self.session.get_inputs()]
        self._cache: Dict[str, "np.ndarray"] = {}

    def empreintes(self) -> Dict[str, str]:
        return {f: empreinte_fichier(os.path.join(self.dossier, f))
                for f in FICHIERS_MODELE}

    def plonger(self, textes: Sequence[str]):
        """Vecteurs unitaires (moyenne des états cachés masquée, puis
        normalisation L2), dans l'ordre des textes ; mémoïsé par texte."""
        np = self.np
        a_calculer = [t for t in dict.fromkeys(textes) if t not in self._cache]
        for debut in range(0, len(a_calculer), 64):
            lot = a_calculer[debut:debut + 64]
            encodages = self.tokenizer.encode_batch(lot)
            L = max(len(e.ids) for e in encodages)
            ids = np.zeros((len(lot), L), dtype=np.int64)
            masque = np.zeros((len(lot), L), dtype=np.int64)
            for i, e in enumerate(encodages):
                ids[i, :len(e.ids)] = e.ids
                masque[i, :len(e.ids)] = 1
            nourriture = {"input_ids": ids, "attention_mask": masque}
            if "token_type_ids" in self.entrees:
                nourriture["token_type_ids"] = np.zeros_like(ids)
            sortie = self.session.run(None, nourriture)[0]
            m = masque[:, :, None].astype(np.float32)
            v = (sortie * m).sum(1) / np.maximum(m.sum(1), 1e-9)
            v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            for t, vec in zip(lot, v):
                self._cache[t] = vec.astype(np.float32)
        return np.stack([self._cache[t] for t in textes]) if textes \
            else np.zeros((0, 384), dtype=np.float32)


class IndiceSemantique:
    """Le classifieur appliqué au plongement : score, verdict, explication."""

    def __init__(self, chemin_classifieur: str = CHEMIN_CLASSIFIEUR,
                 plongeur: Optional[Plongeur] = None):
        if not classifieur_present(chemin_classifieur):
            raise IndisponibleError(motif_indisponible())
        with open(chemin_classifieur, encoding="utf-8") as f:
            self.parametres = json.load(f)
        self.plongeur = plongeur or Plongeur()
        np = self.plongeur.np
        self.w = np.asarray(self.parametres["poids"], dtype=np.float32)
        self.b = float(self.parametres["biais"])
        self.seuil = float(self.parametres["seuil"])
        self.exemples = [(x["classe"], x["texte"]) for x in self.parametres["exemples"]]
        self._vecteurs_exemples = None

    def scores(self, libelles: Sequence[str]) -> List[float]:
        np = self.plongeur.np
        if not libelles:
            return []
        V = self.plongeur.plonger([l.strip() or "-" for l in libelles])
        z = V @ self.w + self.b
        p = 1.0 / (1.0 + np.exp(-z))
        return [float(round(x, 4)) for x in p]

    def score(self, libelle: str) -> float:
        return self.scores([libelle])[0]

    def evaluer(self, libelle: str) -> bool:
        return self.score(libelle) >= self.seuil

    def voisins(self, libelle: str, k: int = 3) -> List[Dict]:
        """Les k exemples d'apprentissage les plus proches du libellé
        (similarité cosinus), pour l'explication."""
        np = self.plongeur.np
        if self._vecteurs_exemples is None:
            self._vecteurs_exemples = self.plongeur.plonger([t for _, t in self.exemples])
        v = self.plongeur.plonger([libelle.strip() or "-"])[0]
        sims = self._vecteurs_exemples @ v
        ordre = np.argsort(-sims)[:k]
        return [{"texte": self.exemples[i][1], "classe": self.exemples[i][0],
                 "similarite": float(round(sims[i], 3))} for i in ordre]

    def expliquer(self, libelle: str) -> Dict:
        s = self.score(libelle)
        return {"libelle": libelle, "score": s, "seuil": self.seuil,
                "verdict": s >= self.seuil, "voisins": self.voisins(libelle)}

    def motif(self, libelle: str) -> str:
        """Le motif écrit dans le rapport : score, seuil, exemple le plus proche."""
        e = self.expliquer(libelle)
        proche = e["voisins"][0] if e["voisins"] else None
        texte = "indice sémantique : score %.2f (seuil %.2f)" % (e["score"], e["seuil"])
        if proche:
            texte += ", proche de « %s » (%s, similarité %.2f)" % (
                proche["texte"], "décision" if proche["classe"] == "D" else "non décision",
                proche["similarite"])
        return texte


def instance() -> IndiceSemantique:
    """L'indice partagé du processus (chargement paresseux, une seule fois)."""
    global _instance
    with _verrou:
        if _instance is None:
            _instance = IndiceSemantique()
        return _instance


def indice_semantique(libelle: str) -> bool:
    """κ_s(a) : vrai si le libellé est jugé décisionnel. Lève
    IndisponibleError si le modèle n'est pas installé."""
    if not libelle or not libelle.strip():
        return False
    return instance().evaluer(libelle)


# ----------------------------------------------------------------------
# apprentissage du classifieur (outils/entrainer-indice-semantique.py)
# ----------------------------------------------------------------------
def entrainer(exemples: List[Tuple[str, str]], plongeur: Optional[Plongeur] = None,
              C: float = 1.0, plis: int = 5, graine: int = 0) -> Dict:
    """Apprend la régression logistique sur les plongements des exemples et
    retourne les paramètres à écrire dans le fichier du classifieur, avec
    la mesure en validation croisée (précision, rappel, exactitude) et le
    seuil retenu (celui qui maximise le F1 moyen des plis, arrondi à
    0,05 ; 0,5 à égalité)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    plongeur = plongeur or Plongeur()
    textes = [t for _, t in exemples]
    y = np.array([1 if c == "D" else 0 for c, _ in exemples])
    X = plongeur.plonger(textes)

    def ajuster(Xa, ya):
        clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced",
                                 random_state=graine)
        clf.fit(Xa, ya)
        return clf

    # validation croisée : scores hors pli, puis choix du seuil
    kf = StratifiedKFold(n_splits=plis, shuffle=True, random_state=graine)
    hors_pli = np.zeros(len(y))
    for app, test in kf.split(X, y):
        clf = ajuster(X[app], y[app])
        hors_pli[test] = clf.predict_proba(X[test])[:, 1]
    meilleur = (0.5, -1.0)
    for seuil in [round(0.3 + 0.05 * k, 2) for k in range(9)]:
        pred = hors_pli >= seuil
        vp = int((pred & (y == 1)).sum())
        fp = int((pred & (y == 0)).sum())
        fn = int((~pred & (y == 1)).sum())
        f1 = 2 * vp / (2 * vp + fp + fn) if vp else 0.0
        if f1 > meilleur[1] + 1e-9 or (abs(f1 - meilleur[1]) <= 1e-9 and seuil == 0.5):
            meilleur = (seuil, f1)
    seuil = meilleur[0]
    pred = hors_pli >= seuil
    vp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    vn = int((~pred & (y == 0)).sum())
    mesure_cv = {"plis": plis, "seuil": seuil,
                 "precision": round(vp / (vp + fp), 3) if vp + fp else 0.0,
                 "rappel": round(vp / (vp + fn), 3) if vp + fn else 0.0,
                 "exactitude": round((vp + vn) / len(y), 3),
                 "vp": vp, "fp": fp, "fn": fn, "vn": vn,
                 "erreurs": [{"texte": textes[i], "classe": "D" if y[i] else "N",
                              "score": round(float(hors_pli[i]), 3)}
                             for i in range(len(y)) if pred[i] != (y[i] == 1)]}

    clf = ajuster(X, y)
    return {
        "description": "Indice sémantique de kappa : régression logistique sur les "
                       "plongements MiniLM multilingues (384 dimensions) des libellés "
                       "d'activité ; score >= seuil => libellé décisionnel.",
        "modele": {"depot": "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
                   "fichiers": plongeur.empreintes(), "dimension": int(X.shape[1]),
                   "longueur_max_jetons": LONGUEUR_MAX,
                   "agregation": "moyenne masquée puis normalisation L2"},
        "apprentissage": {"exemples": len(y), "decisions": int(y.sum()),
                          "non_decisions": int(len(y) - y.sum()),
                          "C": C, "ponderation": "balanced", "graine": graine,
                          "empreinte_exemples": hashlib.sha256(
                              "\n".join("%s\t%s" % e for e in exemples).encode("utf-8")
                          ).hexdigest()},
        "validation_croisee": mesure_cv,
        "seuil": seuil,
        "biais": float(clf.intercept_[0]),
        "poids": [float(round(x, 7)) for x in clf.coef_[0]],
        "exemples": [{"classe": c, "texte": t} for c, t in exemples],
    }
