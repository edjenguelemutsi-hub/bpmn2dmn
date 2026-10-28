# -*- coding: utf-8 -*-
"""
app.py — l'application web interactive du transformateur BPMN <-> DMN.

Serveur bibliothèque standard (http.server) : rien à installer.
L'interface (ui/index.html) embarque les moteurs de rendu bpmn-js et
dmn-js (ceux de Camunda Modeler), copiés en local : l'application
fonctionne hors ligne.

    python cli.py servir            # http://localhost:8765
    python app.py                   # équivalent (--port N, --reseau,
                                    #             --sans-navigateur)

API :
  POST /api/transformer   {bpmn, arbitrages?, nom?, extensions?}
                                               -> {ok, dmn, rapport}
                          (rapport.experimentation : ligne ajoutée au registre ;
                           extensions : liste de noms, voir GET /api/extensions)
  GET  /api/extensions                         -> {ok, extensions: [{nom, phrase}]}
  POST /api/inverser      {dmn}                -> {ok, bpmn, arbitrages,
                                                   aller_retour, ecarts}
  POST /api/exemple       {}                   -> {ok, bpmn}   (FIMEX)
  GET  /api/registre                           -> {ok, actif, dossier, nombre,
                                                   dernieres, synthese}
  GET  /registre/registre.csv | registre.xlsx | campagnes.csv  (téléchargement)
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bpmn2dmn.extensions import EXTENSIONS, normaliser_extensions, variante
from bpmn2dmn.parseur import parser_bpmn, ErreurParseur
from bpmn2dmn.transformation import expliquer_drd_vide, transformer
from bpmn2dmn.serialiseur import serialiser_dmn
from bpmn2dmn.inverse import parser_dmn, inverser, ErreurDMN
from bpmn2dmn.qualification import Arbitrages, VIDE
from bpmn2dmn.miseenpage import ajouter_di, possede_di
from bpmn2dmn.registre import Registre, desactive
from bpmn2dmn.validation import equivalents, verifier_invariants

# en exécutable autonome (PyInstaller), les ressources sont dépliées
# dans le dossier temporaire sys._MEIPASS
ICI = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ICI, "ui")
CHEMIN_FIMEX = os.path.join(ICI, "corpus", "fimex.bpmn")

TYPES_MIME = {".html": "text/html; charset=utf-8",
              ".js": "application/javascript; charset=utf-8",
              ".css": "text/css; charset=utf-8",
              ".svg": "image/svg+xml", ".png": "image/png",
              ".json": "application/json; charset=utf-8",
              ".csv": "text/csv; charset=utf-8",
              ".xlsx": "application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet"}

# le registre des expérimentations partagé par toutes les requêtes ;
# None = suspendu (--sans-registre ou BPMN2DMN_SANS_REGISTRE=1)
REGISTRE = None if desactive() else Registre()
FICHIERS_REGISTRE = ("registre.csv", "registre.xlsx", "campagnes.csv")


from cli import rapport_json


def _rapport(mf):
    return rapport_json(mf)


TAILLE_MAX = 20 * 1024 * 1024        # au-delà, le corps est refusé


class Requetes(BaseHTTPRequestHandler):
    server_version = "bpmn2dmn/1.0"
    timeout = 30            # un client qui n'envoie pas son corps est lâché

    # utilitaires
    def _json(self, code: int, donnees: dict) -> None:
        corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _fichier(self, chemin: str, telecharger: bool = False) -> None:
        if not os.path.isfile(chemin):
            self.send_error(404)
            return
        ext = os.path.splitext(chemin)[1].lower()
        with open(chemin, "rb") as f:
            corps = f.read()
        self.send_response(200)
        self.send_header("Content-Type",
                         TYPES_MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(corps)))
        if telecharger:
            self.send_header("Content-Disposition", 'attachment; filename="%s"'
                             % os.path.basename(chemin))
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, fmt, *args):          # journal discret
        pass

    # GET : fichiers de l'interface
    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin in ("/", "/index.html"):
            self._fichier(os.path.join(UI, "index.html"))
        elif chemin == "/api/sante":
            # la page l'interroge au chargement pour signaler un serveur
            # arrêté ; sert aussi de diagnostic sur une machine inconnue
            self._json(200, {"ok": True,
                             "python": sys.version.split()[0],
                             "plateforme": sys.platform})
        elif chemin.startswith("/lib/"):
            self._fichier(os.path.join(UI, "lib",
                                       os.path.basename(chemin)))
        elif chemin == "/api/registre":
            self._api_registre()
        elif chemin == "/api/extensions":
            self._json(200, {"ok": True, "extensions": [
                {"nom": n, "phrase": p} for n, p in EXTENSIONS.items()]})
        elif chemin.startswith("/registre/"):
            nom = os.path.basename(chemin)
            if REGISTRE is None or nom not in FICHIERS_REGISTRE:
                self.send_error(404)
                return
            self._fichier(os.path.join(REGISTRE.dossier, nom), telecharger=True)
        else:
            self.send_error(404)

    def _api_registre(self):
        """État du registre pour la page : compte, dernières lignes, synthèse."""
        if REGISTRE is None:
            self._json(200, {"ok": True, "actif": False, "nombre": 0,
                             "dernieres": [], "synthese": {}})
            return
        colonnes = ("experience", "horodatage", "code_modele", "fichier",
                    "contexte", "arbitrages", "decisions", "donnees_entree",
                    "sources_connaissance", "bkm", "ef_exigences",
                    "points_expert", "precision", "rappel", "acyclique",
                    "duree_totale_ms")
        try:
            lignes = REGISTRE.lignes()
            dernieres = [{c: l.get(c, "") for c in colonnes} for l in lignes[-15:]]
            dernieres.reverse()
            self._json(200, {"ok": True, "actif": True, "dossier": REGISTRE.dossier,
                             "nombre": len(lignes), "dernieres": dernieres,
                             "synthese": REGISTRE.synthese()})
        except Exception as e:
            self._json(200, {"ok": True, "actif": True, "dossier": REGISTRE.dossier,
                             "nombre": 0, "dernieres": [], "synthese": {},
                             "erreur": str(e)})

    # POST : l'API
    def do_POST(self):
        try:
            taille = int(self.headers.get("Content-Length") or 0)
            if taille < 0 or taille > TAILLE_MAX:
                self._json(413, {"ok": False,
                                 "erreur": "taille de requête refusée"})
                return
            corps = self.rfile.read(taille).decode("utf-8") if taille else "{}"
            donnees = json.loads(corps or "{}")
            if not isinstance(donnees, dict):
                raise ValueError("un objet JSON est attendu")
        except Exception as e:
            self._json(400, {"ok": False, "erreur": "requête illisible : %s" % e})
            return

        try:
            if self.path == "/api/transformer":
                self._api_transformer(donnees)
            elif self.path == "/api/inverser":
                self._api_inverser(donnees)
            elif self.path == "/api/exemple":
                self._api_exemple()
            elif self.path == "/api/miseenpage":
                self._api_miseenpage(donnees)
            else:
                self.send_error(404)
        except Exception as e:            # jamais de connexion coupée :
            import traceback              # toute erreur devient un JSON
            traceback.print_exc()
            try:
                self._json(500, {"ok": False,
                                 "erreur": "erreur interne : %s" % e})
            except Exception:
                pass

    @staticmethod
    def _champ_texte(donnees, cle):
        """Champ texte obligatoire — refuse proprement tout autre type."""
        valeur = donnees.get(cle)
        if not isinstance(valeur, str) or not valeur.strip():
            return None
        return valeur

    def _api_miseenpage(self, donnees):
        """Ajoute une mise en page BPMNDI aux modèles qui n'en ont pas."""
        texte = self._champ_texte(donnees, "bpmn")
        if texte is None:
            self._json(400, {"ok": False, "erreur": "aucun BPMN fourni"})
            return
        try:
            self._json(200, {"ok": True, "bpmn": ajouter_di(texte),
                             "ajoutee": not possede_di(texte)})
        except Exception as e:
            self._json(422, {"ok": False, "erreur": str(e)})

    def _api_transformer(self, donnees):
        texte = self._champ_texte(donnees, "bpmn")
        if texte is None:
            self._json(400, {"ok": False,
                             "erreur": "aucun BPMN fourni (champ « bpmn », "
                                       "chaîne XML attendue)"})
            return
        t0 = time.perf_counter()
        try:
            mi = parser_bpmn(texte, est_texte=True)
        except ErreurParseur as e:
            self._json(422, {"ok": False, "erreur": str(e)})
            return
        t1 = time.perf_counter()
        try:
            ext = normaliser_extensions(donnees.get("extensions") or [])
        except (ValueError, TypeError) as e:
            self._json(422, {"ok": False, "erreur": "extensions : %s" % e})
            return
        arb = VIDE
        if donnees.get("arbitrages"):
            try:
                if not isinstance(donnees["arbitrages"], dict):
                    raise TypeError("un objet JSON est attendu")
                arb = Arbitrages.depuis_json(donnees["arbitrages"])
            except Exception as e:
                self._json(422, {"ok": False,
                                 "erreur": "arbitrages illisibles : %s" % e})
                return
        mf = transformer(mi, arb, ext)
        t2 = time.perf_counter()
        dmn = serialiser_dmn(mf)
        t3 = time.perf_counter()
        rapport = _rapport(mf)
        rapport["anomalies_source"] = mi.anomalies
        rapport["diagnostic_vide"] = expliquer_drd_vide(mi, mf)
        rapport["experimentation"] = self._consigner(
            mi, mf, texte, arb, dmn, rapport, donnees.get("nom"),
            {"analyse": (t1 - t0) * 1000, "transformation": (t2 - t1) * 1000,
             "serialisation": (t3 - t2) * 1000, "totale": (t3 - t0) * 1000})
        self._json(200, {"ok": True, "dmn": dmn, "rapport": rapport})

    @staticmethod
    def _consigner(mi, mf, texte, arb, dmn, rapport, nom, durees):
        """Ajoute l'extraction au registre ; jamais bloquant."""
        if REGISTRE is None:
            return None
        try:
            ligne = REGISTRE.enregistrer(
                mi, mf, "application web", texte_bpmn=texte, arbitrages=arb,
                dmn=dmn, rapport=rapport, durees=durees,
                nom=nom if isinstance(nom, str) and nom.strip() else None,
                variante=variante(mf.extensions))
        except Exception as e:
            print("Registre : enregistrement impossible (%s)" % e, file=sys.stderr)
            return {"erreur": str(e)}
        return {"experience": ligne["experience"], "code_modele": ligne["code_modele"],
                "horodatage": ligne["horodatage"], "dossier": REGISTRE.dossier}

    def _api_inverser(self, donnees):
        texte = self._champ_texte(donnees, "dmn")
        if texte is None:
            self._json(400, {"ok": False,
                             "erreur": "aucun DMN fourni (champ « dmn », "
                                       "chaîne XML attendue)"})
            return
        try:
            mf = parser_dmn(texte, est_texte=True)
        except ErreurDMN as e:
            self._json(422, {"ok": False, "erreur": str(e)})
            return
        bpmn, arbitrages = inverser(mf)
        # preuve d'aller-retour immédiate
        try:
            mf2 = transformer(parser_bpmn(bpmn, est_texte=True),
                              Arbitrages.depuis_json(arbitrages))
            ok_ar, ecarts = equivalents(mf, mf2)
        except Exception as e:                      # pragma: no cover
            ok_ar, ecarts = False, [str(e)]

        # rapport détaillé, au même niveau que le sens direct
        from bpmn2dmn.metamodeles import DECISION
        ir, kr = set(mf.IR), set(mf.KR)
        noms = {n.id: n.nom for n in mf.noeuds.values()}
        rapport = {
            "resume": {"decisions": len(mf.decisions),
                       "inputs": len(mf.inputs),
                       "sources": len(mf.sources),
                       "bkm": len(mf.bkms),
                       "IR": len(mf.IR), "KR": len(mf.KR),
                       "AR": len(mf.AR)},
            "decisions": [{"nom": n.nom,
                           "tache": n.nom,
                           "passerelle": "Verdict : " + n.nom,
                           "fin_arret": "Instruction arrêtée"}
                          for n in mf.decisions],
            "inputs": [{"nom": n.nom,
                        "lecteurs": [noms[v] for u, v in mf.arcs
                                     if u == n.id]}
                       for n in mf.inputs],
            "resultats": [{"source": noms[u], "cible": noms[v],
                           "objet": "Résultat : " + noms[u]}
                          for u, v in mf.arcs
                          if mf.noeuds[u].type == DECISION
                          and mf.noeuds[v].type == DECISION],
            "annotations": [{"nom": n.nom,
                             "genre": "Source de connaissance (KS)"
                             if n.type == "KnowledgeSource"
                             else "Modèle de connaissance métier (BKM)",
                             "cibles": [noms[v] for u, v in mf.arcs
                                        if u == n.id]}
                            for n in (mf.sources + mf.bkms)],
            "arbitrages_generes": {
                "annotations": len(arbitrages.get("annotations") or {}),
                "renommages": len(arbitrages.get("renommages") or {}),
                "noms": len(arbitrages.get("noms") or {})},
            "aller_retour": ok_ar, "ecarts": ecarts,
        }
        self._json(200, {"ok": True, "bpmn": bpmn, "arbitrages": arbitrages,
                         "aller_retour": ok_ar, "ecarts": ecarts,
                         "rapport": rapport,
                         "resume": rapport["resume"]})

    def _api_exemple(self):
        chemins = [CHEMIN_FIMEX,
                   os.path.join(ICI, "..", "sources-figures",
                                "rendu-bpmn-js", "fimex.bpmn")]
        for c in chemins:
            if os.path.isfile(c):
                with open(c, encoding="utf-8") as f:
                    self._json(200, {"ok": True, "bpmn": f.read()})
                return
        self._json(404, {"ok": False, "erreur": "exemple FIMEX introuvable"})


def _ip_locale() -> str:
    """Adresse IP de la machine sur le réseau local (au mieux)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))          # aucune donnée n'est émise
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Serveur(ThreadingHTTPServer):
    """Serveur qui refuse de partager son port : sous Windows, la
    réutilisation d'adresse laisserait deux instances écouter le même
    port, la seconde ne recevant jamais rien. Sous macOS et Linux, au
    contraire, la réutilisation est nécessaire : sans elle, relancer
    l'application dans la minute qui suit son arrêt échoue (« port déjà
    utilisé ») alors que le port n'est plus qu'en attente de fermeture ;
    deux instances actives restent impossibles sur ces systèmes."""
    allow_reuse_address = os.name != "nt"
    request_queue_size = 128

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET,
                                   socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def servir(port: int = 8765, ouvrir: bool = True,
           reseau: bool = False, registre_dossier: str = None,
           sans_registre: bool = False) -> int:
    """Démarre l'application. Par défaut, accès local uniquement
    (127.0.0.1 : rien ne sort de l'ordinateur, aucun accès Internet).
    Avec reseau=True, elle est aussi accessible aux autres ordinateurs
    du réseau local via http://<IP de cette machine>:<port>."""
    global REGISTRE
    if sans_registre:
        REGISTRE = None
    elif registre_dossier:
        REGISTRE = Registre(registre_dossier)
    hote = "0.0.0.0" if reseau else "127.0.0.1"
    try:
        serveur = Serveur((hote, port), Requetes)
    except OSError as e:
        print("Impossible d'écouter sur le port %d : %s" % (port, e))
        print("Le port est sans doute déjà utilisé (autre instance de "
              "l'application ?) ; relancez avec --port <autre numéro>.")
        if getattr(sys, "frozen", False):
            # lancé par double-clic : laisser lire le message avant que
            # la fenêtre ne se ferme
            input("Appuyez sur Entrée pour fermer.")
        return 1
    # adresse numérique plutôt que « localhost » : sur macOS, ce nom désigne
    # d'abord l'adresse IPv6 ::1, sur laquelle le serveur n'écoute pas
    url = "http://127.0.0.1:%d" % port
    print("Application démarrée : %s   (ou http://localhost:%d ; "
          "Ctrl+C pour arrêter)" % (url, port))
    print("Fonctionne entièrement hors ligne : aucune connexion Internet "
          "n'est utilisée.")
    if REGISTRE is not None:
        print("Registre des expérimentations : %s (une ligne par extraction, "
              "CSV + Excel)" % REGISTRE.dossier)
    else:
        print("Registre des expérimentations suspendu.")
    if reseau:
        print("Accès depuis les autres ordinateurs du réseau : "
              "http://%s:%d" % (_ip_locale(), port))
        print("(le pare-feu Windows peut demander une autorisation au "
              "premier lancement)")
    if ouvrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    return 0


def principal(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        description="Extraction de modèle DMN à partir de modèle BPMN "
                    "(application web locale)")
    p.add_argument("-p", "--port", type=int, default=8765)
    p.add_argument("--reseau", action="store_true",
                   help="rendre l'application accessible aux autres "
                        "ordinateurs du réseau local")
    p.add_argument("--sans-navigateur", action="store_true",
                   help="ne pas ouvrir le navigateur au démarrage")
    p.add_argument("--sans-registre", action="store_true",
                   help="ne pas consigner les extractions dans le registre "
                        "des expérimentations")
    p.add_argument("--registre", metavar="DOSSIER",
                   help="dossier du registre des expérimentations")
    args = p.parse_args(argv)
    return servir(args.port, ouvrir=not args.sans_navigateur,
                  reseau=args.reseau, registre_dossier=args.registre,
                  sans_registre=args.sans_registre)


if __name__ == "__main__":
    sys.exit(principal())
