# -*- coding: utf-8 -*-
"""Test client de l'API de l'application : inversion des 10 DRD des jeux
d'essai via HTTP (comme le ferait l'interface), + robustesse aux entrées
mal typées. Usage : python tests/test_api_inversion.py [port]"""
import glob
import io
import json
import os
import sys
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() \
    else 8765
URL = "http://localhost:%d/api/inverser" % PORT


def appel(corps: dict):
    req = urllib.request.Request(
        URL, data=json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def principal() -> int:
    echecs = 0
    for chemin in sorted(glob.glob(os.path.join(RACINE, "essais",
                                                "drd-jeux", "*.dmn"))):
        dmn = io.open(chemin, encoding="utf-8").read()
        statut, rep = appel({"dmn": dmn})
        ok = rep.get("ok") and rep.get("aller_retour")
        print("%-32s HTTP %d  ok=%s  aller_retour=%s"
              % (os.path.basename(chemin), statut, rep.get("ok"),
                 rep.get("aller_retour")))
        if not ok:
            echecs += 1

    # robustesse : entrées mal typées -> erreur JSON propre, sans plantage
    for corps, attendu in ((({"dmn": {"x": 1}}), 400),
                           (({"dmn": ""}), 400),
                           (({}), 400),
                           (({"dmn": "<pas du xml"}), 422)):
        statut, rep = appel(corps)
        bien = statut == attendu and rep.get("ok") is False
        print("entrée invalide %-22s -> HTTP %d (%s)"
              % (str(corps)[:22], statut, "propre" if bien else "inattendu"))
        if not bien:
            echecs += 1

    print("Résultat :", "tout conforme" if not echecs
          else "%d échec(s)" % echecs)
    return 1 if echecs else 0


# script client (nécessite le serveur lancé) : exécution en direct
# seulement, la découverte unittest ne doit pas le déclencher à l'import
if __name__ == "__main__":
    sys.exit(principal())
