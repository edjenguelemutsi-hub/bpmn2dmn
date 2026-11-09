# -*- coding: utf-8 -*-
"""
Contrôle de bout en bout de l'interface web, sans navigateur visible :
le serveur est lancé sur un port libre, puis Edge en mode sans fenêtre
charge la page dans ses modes de démonstration automatique et le titre
de la page dit si chaque parcours a réussi.

    python -X utf8 tests/controle_interface.py

Parcours : auto=1 (exemple FIMEX extrait), auto=3 (retour à l'accueil),
auto=4 (inversion du DRD produit), auto=5 (co-évolution : une décision
renommée dans le DRD est reportée sur le BPMN, cohérence vérifiée).
Outil de contrôle du développeur ; il n'est pas lancé par unittest.
"""
import os
import re
import socket
import subprocess
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = [p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
        if os.path.isfile(p)]


def port_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def attendre(port: int, delai: float = 20.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def principal() -> int:
    if not EDGE:
        print("Edge introuvable : contrôle non exécuté")
        return 0
    port = port_libre()
    serveur = subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(RACINE, "cli.py"),
                                "servir", "-p", str(port), "--sans-navigateur", "--sans-registre"],
                               cwd=RACINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not attendre(port):
            print("serveur non démarré")
            return 1
        resultat = 0
        for mode, attendu in (("1", "DEMO-OK"), ("3", "ACCUEIL-OK"), ("4", "INVERSION-OK"),
                              ("5", "COEVOLUTION-OK")):
            url = "http://127.0.0.1:%d/?auto=%s" % (port, mode)
            sortie = subprocess.run(
                [EDGE[0], "--headless=new", "--disable-gpu", "--no-first-run",
                 "--virtual-time-budget=25000", "--dump-dom", url],
                capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
            m = re.search(r"<title>([^<]*)</title>", sortie)
            titre = m.group(1) if m else "(sans titre)"
            ok = titre.startswith(attendu)
            resultat |= 0 if ok else 1
            print("auto=%s : %s  %s" % (mode, "OK " if ok else "ECHEC", titre))
        return resultat
    finally:
        serveur.terminate()
        try:
            serveur.wait(5)
        except subprocess.TimeoutExpired:
            serveur.kill()


if __name__ == "__main__":
    sys.exit(principal())
