# -*- coding: utf-8 -*-
"""
Générateur de modèles BPMN et de leur oracle, pour la validation de masse.

À partir d'une graine, `generer` produit un processus BPMN 2.0 aléatoire
mais plausible (domaines métier, libellés, structures variées) et, en même
temps, le DRD attendu : l'oracle est calculé par construction, le
générateur sachant quelles activités il a rendues décisionnelles et
quelles données il leur a attachées, ce qui évite toute circularité avec
T. Chaque modèle exerce P1 à P6 et comporte des distracteurs. La même
graine redonne toujours le même modèle, une défaillance est donc rejouable.

`generer` enchaîne les étapes ; `_Generation` porte le tirage aléatoire,
le document en construction et l'oracle. L'ordre des tirages est celui du
modèle : le déplacer changerait les modèles produits par chaque graine.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

# banques lexicales par domaine (processus d'administration et de métier)
DOMAINES = {
    "commerce-exterieur": {
        "objets": ["Demande d'agrément", "Dossier d'importation",
                   "Déclaration en douane", "Certificat d'origine",
                   "Facture pro forma", "Licence d'exportation"],
        "magasins": ["Registre des opérateurs", "Base des agréments",
                     "Fichier des importateurs"],
        "sujets": ["le dossier", "la déclaration", "l'agrément",
                   "la licence", "le certificat"],
        "autorites": ["Réglementation du commerce extérieur",
                      "Directive de la douane", "Procédure du guichet unique"],
        "regles": ["Calcul du taux de taxation applicable",
                   "Répartition équitable des dossiers entre agents",
                   "Barème des redevances par catégorie"],
    },
    "banque": {
        "objets": ["Demande de crédit", "Relevé de compte", "Plan d'affaires",
                   "Garantie proposée", "Bulletin de salaire"],
        "magasins": ["Centrale des risques", "Historique client"],
        "sujets": ["la solvabilité", "le crédit", "la garantie", "le taux"],
        "autorites": ["Réglementation prudentielle COBAC",
                      "Politique interne de crédit",
                      "Norme de conformité bancaire"],
        "regles": ["Calcul du score de solvabilité",
                   "Formule de plafonnement du taux d'endettement"],
    },
    "assurance": {
        "objets": ["Déclaration de sinistre", "Rapport d'expertise",
                   "Contrat d'assurance", "Constat amiable"],
        "magasins": ["Base des contrats", "Historique des sinistres"],
        "sujets": ["le sinistre", "l'indemnisation", "la garantie"],
        "autorites": ["Code CIMA des assurances",
                      "Directive d'indemnisation des sinistres"],
        "regles": ["Barème d'indemnisation par type de dommage",
                   "Calcul de la vétusté applicable"],
    },
    "sante": {
        "objets": ["Dossier du patient", "Résultats d'analyses",
                   "Rapport d'anamnèse", "Ordonnance en cours"],
        "magasins": ["Dossier médical partagé", "Registre des lits"],
        "sujets": ["l'hospitalisation", "le diagnostic", "le traitement"],
        "autorites": ["Recommandation de bonnes pratiques cliniques",
                      "Procédure d'admission aux urgences"],
        "regles": ["Score de gravité calculé selon les constantes",
                   "Algorithme de tri des urgences"],
    },
    "ressources-humaines": {
        "objets": ["Dossier de candidature", "Fiche d'évaluation",
                   "Demande de congé", "Relevé des présences"],
        "magasins": ["Base du personnel", "Référentiel des postes"],
        "sujets": ["la candidature", "la promotion", "le congé"],
        "autorites": ["Convention collective applicable",
                      "Règlement intérieur de l'entreprise"],
        "regles": ["Grille de notation des entretiens",
                   "Calcul de l'ancienneté pondérée"],
    },
    "marches-publics": {
        "objets": ["Offre technique", "Offre financière",
                   "Cahier des charges", "Caution de soumission"],
        "magasins": ["Registre des prestataires", "Base des marchés"],
        "sujets": ["l'offre", "l'attribution", "la conformité de l'offre"],
        "autorites": ["Code des marchés publics",
                      "Circulaire de passation des marchés"],
        "regles": ["Pondération technique et financière des offres",
                   "Formule de notation des soumissions"],
    },
}

VERBES_DECISION_GEN = ["Évaluer", "Vérifier", "Statuer sur", "Décider de",
                       "Examiner", "Apprécier", "Coter", "Affecter",
                       "Arbitrer", "Juger"]
VERBES_NEUTRES = ["Saisir", "Consulter", "Imprimer", "Archiver", "Numériser",
                  "Transmettre", "Enregistrer", "Préparer", "Compléter",
                  "Mettre à jour", "Notifier", "Publier"]
# NB : « Classer » est exclu des verbes neutres (« classer » ∈ Λ).
ANNOT_DECORATIVES = ["Apposer le logo et le cachet officiel",
                     "QR code de vérification en pied de page",
                     "Mise en forme selon la charte graphique",
                     "Note : conserver une copie papier"]
ANNOT_AMBIGUES = ["Tenir compte du contexte particulier du demandeur",
                  "Voir le dossier de l'année précédente",
                  "L'avis du chef de service est souhaité"]
LANES_HUMAINES = ["Agent instructeur", "Chef de service", "Superviseur",
                  "Analyste", "Gestionnaire", "Expert métier"]
LANES_SYSTEMES = ["Système d'information", "Plateforme en ligne",
                  "Moteur de règles", "Serveur d'intégration"]
# nom de l'événement de départ porteur : l'oracle de P3 attend une donnée
# d'entrée de ce nom exact
NOM_DEPART_MESSAGE = "Demande reçue"


class ModeleAttendu:
    """L'oracle : ce que T doit produire sur le modèle généré."""

    def __init__(self):
        self.decisions: List[str] = []            # noms attendus dans DA*
        self.candidats_non_corrobores: List[str] = []
        self.inputs: List[str] = []               # noms des données d'entrée
        self.sources: List[str] = []              # noms des KS attendues
        self.bkms: List[str] = []                 # noms des BKM (avec préfixe)
        self.ir: List[Tuple[str, str]] = []       # (nom source, nom décision)
        self.kr: List[Tuple[str, str]] = []
        self.ar: List[Tuple[str, str]] = []
        self.ecartes: int = 0

    def as_dict(self) -> Dict:
        return {"decisions": sorted(self.decisions),
                "candidats_non_corrobores": sorted(self.candidats_non_corrobores),
                "inputs": sorted(self.inputs),
                "sources": sorted(self.sources),
                "bkms": sorted(self.bkms),
                "nb_ir": len(self.ir), "nb_kr": len(self.kr),
                "nb_ar": len(self.ar), "ecartes": self.ecartes}


def generer(seed: int) -> Tuple[str, ModeleAttendu]:
    """Retourne (bpmn_xml, oracle attendu) pour la graine donnée."""
    generation = _Generation(seed)
    generation.ouvrir_processus()                      # événement de départ
    for k in range(generation.nb_decisions):
        generation.ajouter_distracteurs()              # tâches neutres avant la décision
        generation.ajouter_decision(k)                 # P1, P2, P4 et P6 exercés
    generation.fermer_processus()                      # fin, puis oracle de P3
    return generation.assembler_document(), generation.attendu


class _Generation:
    """Un modèle en cours de génération : tirage, document et oracle."""

    def __init__(self, seed: int):
        self.seed = seed
        self.alea = random.Random(seed)
        alea = self.alea
        self.domaine = alea.choice(sorted(DOMAINES))
        self.banque = DOMAINES[self.domaine]
        self.attendu = ModeleAttendu()

        self.nb_decisions = alea.randint(1, 5)
        self.nb_distracteurs = alea.randint(1, 6)
        self.avec_depart_message = alea.random() < 0.5
        self.avec_magasin = alea.random() < 0.5

        self.lanes: List[str] = alea.sample(LANES_HUMAINES, alea.randint(1, 2))
        if alea.random() < 0.6:
            self.lanes.append(alea.choice(LANES_SYSTEMES))
        self.lane_humaines = [l for l in self.lanes if l in LANES_HUMAINES]
        self.lane_systemes = [l for l in self.lanes if l in LANES_SYSTEMES]

        self.M: List[str] = []                 # corps du process
        self.flux: List[Tuple[str, str, str]] = []
        self.lane_de: Dict[str, str] = {}
        self.n_ids = 0
        self.precedent = ""                    # dernier nœud de la chaîne, posé par ouvrir_processus

        # données disponibles
        self.objets_dispo = list(self.banque["objets"])
        alea.shuffle(self.objets_dispo)
        self.donnees_creees: Dict[str, str] = {}      # nom -> id
        self.resultats_amont: List[Tuple[str, str]] = []   # (nom objet résultat, nom décision)

    # ------------------------------------------------------------------
    # services
    # ------------------------------------------------------------------
    def nid(self, prefixe: str) -> str:
        """Identifiant suivant, numéroté dans l'ordre de création."""
        self.n_ids += 1
        return "%s%d" % (prefixe, self.n_ids)

    def objet_donnees(self, nom: str) -> str:
        """L'objet de données de ce nom, déclaré à la première demande."""
        if nom not in self.donnees_creees:
            oid = self.nid("do")
            self.donnees_creees[nom] = oid
            self.M.append('    <bpmn:dataObjectReference id="%s" name=%s '
                          'dataObjectRef="%s_o"/>' % (oid, quoteattr(nom), oid))
            self.M.append('    <bpmn:dataObject id="%s_o"/>' % oid)
        return self.donnees_creees[nom]

    def magasin_donnees(self, nom: str) -> str:
        """Le magasin de données de ce nom, déclaré à la première demande."""
        if nom not in self.donnees_creees:
            oid = self.nid("ds")
            self.donnees_creees[nom] = oid
            self.M.append('    <bpmn:dataStoreReference id="%s" name=%s/>'
                          % (oid, quoteattr(nom)))
        return self.donnees_creees[nom]

    def tache(self, nom: str, type_: str = "userTask",
              lane: Optional[str] = None, contenu: str = "") -> str:
        """Déclare une tâche (couloir tiré au sort si non précisé)."""
        tid = self.nid("t")
        if contenu:
            self.M.append('    <bpmn:%s id="%s" name=%s>%s</bpmn:%s>'
                          % (type_, tid, quoteattr(nom), contenu, type_))
        else:
            self.M.append('    <bpmn:%s id="%s" name=%s/>'
                          % (type_, tid, quoteattr(nom)))
        self.lane_de[tid] = lane or self.alea.choice(self.lanes)
        return tid

    def enchainer(self, t: str) -> None:
        """Relie le nœud au bout de la chaîne et en fait le nouveau bout."""
        self.flux.append((self.nid("f"), self.precedent, t))
        self.precedent = t

    # ------------------------------------------------------------------
    # étapes
    # ------------------------------------------------------------------
    def ouvrir_processus(self) -> None:
        """L'événement de départ, porteur d'un message une fois sur deux."""
        if self.avec_depart_message:
            self.M.append('    <bpmn:startEvent id="debut" name=%s>'
                          '<bpmn:messageEventDefinition id="debut_med"/>'
                          '</bpmn:startEvent>' % quoteattr(NOM_DEPART_MESSAGE))
        else:
            self.M.append('    <bpmn:startEvent id="debut" name="Début"/>')
        self.precedent = "debut"

    def ajouter_distracteurs(self) -> None:
        """Tâches sans valeur décisionnelle : utilisateur au verbe neutre
        (candidat non corroboré), service ou envoi."""
        alea, banque = self.alea, self.banque
        for _ in range(alea.randint(0, max(1, self.nb_distracteurs // self.nb_decisions))):
            genre = alea.random()
            if genre < 0.6:
                nom_dist = "%s %s" % (alea.choice(VERBES_NEUTRES),
                                      alea.choice(banque["sujets"]))
                dt = self.tache(nom_dist, "userTask", alea.choice(self.lane_humaines))
                self.attendu.candidats_non_corrobores.append(nom_dist)
            elif genre < 0.8:
                dt = self.tache("Générer la notification automatique",
                                "serviceTask",
                                alea.choice(self.lane_systemes or self.lane_humaines))
            else:
                dt = self.tache("Transmettre le dossier", "sendTask",
                                alea.choice(self.lane_humaines))
            self.enchainer(dt)

    def ajouter_decision(self, k: int) -> None:
        """La décision k : corroborée par la position, le lexique ou les
        deux ; ses lectures (P2, P4), son résultat, son annotation (P6) et
        sa passerelle (P1) ; l'oracle est complété au fil de l'eau."""
        alea, banque, attendu = self.alea, self.banque, self.attendu
        corrobore_par = alea.choice(["position", "lexique", "les-deux"])
        type_tache = "businessRuleTask" if alea.random() < 0.3 else "userTask"
        sujet = alea.choice(banque["sujets"])
        if corrobore_par in ("lexique", "les-deux"):
            nom_dec = "%s %s" % (alea.choice(VERBES_DECISION_GEN), sujet)
        else:
            nom_dec = "Traitement de %s (comité)" % sujet    # aucun verbe de Λ
        if nom_dec in attendu.decisions:                     # unicité des noms
            nom_dec += " — étape %d" % (k + 1)
        lane_dec = alea.choice(self.lane_humaines)

        contenu, entrees_dec, arcs_dec_amont = self._lectures_de_la_decision()
        nom_res = self._resultat_de_la_decision(nom_dec, contenu)
        tdec = self.tache(nom_dec, type_tache, lane_dec, "".join(contenu))
        self.enchainer(tdec)

        # l'oracle enregistre la décision et ses exigences
        attendu.decisions.append(nom_dec)
        for nom_o in entrees_dec:
            if nom_o not in attendu.inputs:
                attendu.inputs.append(nom_o)
            attendu.ir.append((nom_o, nom_dec))
        for nom_amont in arcs_dec_amont:
            attendu.ir.append((nom_amont, nom_dec))
        if nom_res:
            self.resultats_amont.append((nom_res, nom_dec))

        if alea.random() < 0.55:
            self._annoter(tdec, nom_dec)                     # P6
        if corrobore_par in ("position", "les-deux"):
            self._ajouter_passerelle()                       # P1

    def _lectures_de_la_decision(self) -> Tuple[List[str], List[str], List[str]]:
        """P2 : objets (et parfois un magasin) lus ; P4 : lecture du
        résultat d'une décision amont. Le XSD BPMN 2.0 exige un targetRef
        sur chaque dataInputAssociation : une propriété interne de la tâche
        sert de cible, placée en tête du contenu."""
        alea, banque = self.alea, self.banque
        contenu: List[str] = []
        entrees_dec: List[str] = []
        pid_prop = self.nid("prop")

        def lire(oid):
            contenu.append('<bpmn:dataInputAssociation id="%s">'
                           '<bpmn:sourceRef>%s</bpmn:sourceRef>'
                           '<bpmn:targetRef>%s</bpmn:targetRef>'
                           '</bpmn:dataInputAssociation>'
                           % (self.nid("dia"), oid, pid_prop))

        for _ in range(alea.randint(1, 2)):
            if not self.objets_dispo:
                break
            nom_o = self.objets_dispo.pop()
            lire(self.objet_donnees(nom_o))
            entrees_dec.append(nom_o)
        if self.avec_magasin and alea.random() < 0.5:
            nom_m = alea.choice(banque["magasins"])
            lire(self.magasin_donnees(nom_m))
            entrees_dec.append(nom_m)
        arcs_dec_amont: List[str] = []
        if self.resultats_amont and alea.random() < 0.7:
            nom_res, nom_dec_amont = alea.choice(self.resultats_amont)
            lire(self.objet_donnees(nom_res))
            arcs_dec_amont.append(nom_dec_amont)
        if contenu:
            contenu.insert(0, '<bpmn:property id="%s" '
                              'name="__targetRef_placeholder"/>' % pid_prop)
        return contenu, entrees_dec, arcs_dec_amont

    def _resultat_de_la_decision(self, nom_dec: str, contenu: List[str]) -> Optional[str]:
        """Sortie : résultat de cette décision (parfois), lisible en aval."""
        if self.alea.random() >= 0.75:
            return None
        nom_res = "Résultat : %s" % nom_dec.lower()
        rid = self.objet_donnees(nom_res)
        contenu.append('<bpmn:dataOutputAssociation id="%s">'
                       '<bpmn:targetRef>%s</bpmn:targetRef>'
                       '</bpmn:dataOutputAssociation>' % (self.nid("doa"), rid))
        return nom_res

    def _annoter(self, tdec: str, nom_dec: str) -> None:
        """P6 : une annotation d'autorité (KS), de règle (BKM), décorative
        (écartée) ou ambiguë (point à confirmer)."""
        alea, banque, attendu = self.alea, self.banque, self.attendu
        genre = alea.random()
        anid = self.nid("an")
        if genre < 0.35:
            texte = alea.choice(banque["autorites"])
            if texte not in attendu.sources:
                attendu.sources.append(texte)
            attendu.ar.append((texte, nom_dec))
        elif genre < 0.6:
            texte = alea.choice(banque["regles"])
            nom_b = "Règle : " + texte
            if nom_b not in attendu.bkms:
                attendu.bkms.append(nom_b)
            attendu.kr.append((nom_b, nom_dec))
        elif genre < 0.8:
            texte = alea.choice(ANNOT_DECORATIVES)
            attendu.ecartes += 1
        else:
            texte = alea.choice(ANNOT_AMBIGUES)   # -> point à confirmer
        self.M.append('    <bpmn:textAnnotation id="%s"><bpmn:text>%s'
                      '</bpmn:text></bpmn:textAnnotation>'
                      % (anid, escape(texte)))
        self.M.append('    <bpmn:association id="%s" sourceRef="%s" '
                      'targetRef="%s"/>' % (self.nid("as"), anid, tdec))

    def _ajouter_passerelle(self) -> None:
        """P1 : corroboration par la position (passerelle exclusive suivie
        d'une fin de refus)."""
        gid = self.nid("g")
        self.M.append('    <bpmn:exclusiveGateway id="%s" name=%s/>'
                      % (gid, quoteattr("Verdict ?")))
        self.enchainer(gid)
        fid_fin = self.nid("fin")
        self.M.append('    <bpmn:endEvent id="%s" name="Refusé"/>' % fid_fin)
        self.flux.append((self.nid("f"), gid, fid_fin))

    def fermer_processus(self) -> None:
        """Fin du processus, puis oracle de P3 : la donnée d'entrée n'existe
        que si le successeur immédiat du départ porteur est une décision
        retenue, ce que l'oracle vérifie sur les flux réels. P5 : les
        ressources des décisions sont humaines, donc indéterminées (points
        à confirmer, aucune KS automatique) : rien à ajouter à l'oracle."""
        fin = self.nid("fin")
        self.M.append('    <bpmn:endEvent id="%s" name="Terminé"/>' % fin)
        self.flux.append((self.nid("f"), self.precedent, fin))
        if self.avec_depart_message:
            succ_debut = [t for _, s, t in self.flux if s == "debut"]
            for tid in succ_debut:
                nomt = _nom_de(self.M, tid)
                if nomt in self.attendu.decisions:
                    self.attendu.inputs.append(NOM_DEPART_MESSAGE)
                    self.attendu.ir.append((NOM_DEPART_MESSAGE, nomt))

    def _lanes_xml(self) -> List[str]:
        """Le laneSet : les nœuds non affectés (événements, passerelles)
        vont dans la première lane."""
        lanes_xml = ['    <bpmn:laneSet id="ls1">']
        membres: Dict[str, List[str]] = {l: [] for l in self.lanes}
        for tid, l in self.lane_de.items():
            membres.setdefault(l, []).append(tid)
        affectes = set(self.lane_de)
        for ligne in self.M:
            for prefixe in ('bpmn:startEvent id="', 'bpmn:endEvent id="',
                            'bpmn:exclusiveGateway id="'):
                if prefixe in ligne:
                    xid = ligne.split(prefixe)[1].split('"')[0]
                    if xid not in affectes:
                        membres[self.lanes[0]].append(xid)
                        affectes.add(xid)
        for idx, l in enumerate(self.lanes):
            lanes_xml.append('      <bpmn:lane id="lane_%d" name=%s>'
                             % (idx + 1, quoteattr(l)))
            for m in membres.get(l, []):
                lanes_xml.append('        <bpmn:flowNodeRef>%s</bpmn:flowNodeRef>' % m)
            lanes_xml.append('      </bpmn:lane>')
        lanes_xml.append('    </bpmn:laneSet>')
        return lanes_xml

    def assembler_document(self) -> str:
        """Le document BPMN. Conformité XSD : les artefacts (annotations,
        associations) suivent tous les éléments de flux dans <process>."""
        flux_xml = ['    <bpmn:sequenceFlow id="%s" sourceRef="%s" targetRef="%s"/>'
                    % (fid, s, t) for fid, s, t in self.flux]
        nom_proc = "Processus %s n°%d" % (self.domaine, self.seed)
        doc = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<bpmn:definitions '
               'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
               'id="Defs_%d" targetNamespace="http://bpmn2dmn/genere">' % self.seed,
               '  <bpmn:process id="proc_%d" name=%s isExecutable="false">'
               % (self.seed, quoteattr(nom_proc))]
        artefacts = [l for l in self.M if "<bpmn:textAnnotation" in l
                     or "<bpmn:association " in l]
        doc.extend(self._lanes_xml())
        doc.extend(l for l in self.M if l not in artefacts)
        doc.extend(flux_xml)
        doc.extend(artefacts)
        doc.append('  </bpmn:process>')
        doc.append('</bpmn:definitions>')
        return "\n".join(doc) + "\n"


def _nom_de(lignes: List[str], tid: str) -> str:
    """Retrouve le nom déclaré pour l'identifiant donné dans le corps généré."""
    cherche = 'id="%s"' % tid
    for ligne in lignes:
        if cherche in ligne and "name=" in ligne:
            partie = ligne.split("name=", 1)[1]
            guillemet = partie[0]
            return partie[1:].split(guillemet)[0]
    return ""
