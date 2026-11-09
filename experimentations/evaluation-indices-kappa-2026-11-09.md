# Variantes du prédicat kappa sur le corpus de référence

Candidats DA : 109 ; décisions de la référence : 59 ; modèles : 20.
Classifieur sémantique : seuil 0.50, 392 exemples d'apprentissage, validation croisée précision 0.910 / rappel 0.880.

| Variante | corpus (P / R) | jeux-test-camunda (P / R) | Total (P / R) | retenues | à tort | manquées |
|---|---|---|---|---|---|---|
| position | 100.0 / 59.4 | 100.0 / 63.0 | 100.0 / 61.0 | 36 | 0 | 23 |
| lexique | 100.0 / 96.9 | 100.0 / 100.0 | 100.0 / 98.3 | 58 | 0 | 1 |
| semantique | 63.6 / 87.5 | 87.5 / 77.8 | 72.1 / 83.1 | 68 | 19 | 10 |
| reference (position ou lexique) | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 59 | 0 | 0 |
| position ou semantique | 66.0 / 96.9 | 90.0 / 100.0 | 75.3 / 98.3 | 77 | 19 | 1 |
| position, lexique ou semantique | 66.7 / 100.0 | 90.0 / 100.0 | 75.6 / 100.0 | 78 | 19 | 0 |

## Erreurs de l'indice sémantique seul

| Modèle | Libellé | Référence | Score |
|---|---|---|---|
| admission-hopital.bpmn | Saisir les constantes vitales | non | 0.639 |
| bourse-etudes.bpmn | Saisir les relevés de notes | non | 0.509 |
| bourse-etudes.bpmn | Vérifier les pièces du dossier de bourse | décision | 0.422 |
| copd.bpmn | Treat exacerbations | non | 0.799 |
| copd.bpmn | Prescribe therapy | non | 0.592 |
| copd.bpmn | Examine and interview patient | non | 0.581 |
| credit-bancaire.bpmn | Constituer le dossier de garanties | non | 0.645 |
| credit-bancaire.bpmn | Statuer sur l'octroi du crédit | décision | 0.431 |
| dedouanement.bpmn | Examiner les documents joints | décision | 0.133 |
| dedouanement.bpmn | Statuer sur la mainlevée | décision | 0.307 |
| dedouanement.bpmn | Imprimer le bon à enlever | non | 0.539 |
| fimex.bpmn | Saisir l'observation de complément | non | 0.822 |
| fimex.bpmn | Saisir le motif de rejet | non | 0.703 |
| fimex.bpmn | Saisir l'observation de réexamen | non | 0.863 |
| marche-public.bpmn | Transmettre les offres à la sous-commission | non | 0.518 |
| permis-construire.bpmn | Enregistrer la demande de permis | non | 0.569 |
| permis-construire.bpmn | Saisir les caractéristiques du projet | non | 0.693 |
| permis-construire.bpmn | Consulter les services techniques | non | 0.526 |
| recrutement.bpmn | Convoquer les candidats aux entretiens | non | 0.599 |
| sinistre-assurance.bpmn | Mandater l'expert automobile | non | 0.581 |
| 01-credit-bancaire.bpmn | Statuer sur l'octroi du crédit | décision | 0.431 |
| 02-sinistre-assurance.bpmn | Statuer sur l'indemnisation | décision | 0.462 |
| 03-admission-hopital.bpmn | Mesurer les constantes vitales | non | 0.577 |
| 06-dedouanement.bpmn | Vérifier les documents joints | décision | 0.128 |
| 07-bourse-etudes.bpmn | Vérifier les pièces du dossier | décision | 0.413 |
| 07-bourse-etudes.bpmn | Statuer sur l'attribution de la bourse | décision | 0.443 |
| 08-permis-construire.bpmn | Établir l'arrêté municipal | non | 0.568 |
| 09-visa-sejour.bpmn | Statuer sur la délivrance du visa | décision | 0.400 |
| 09-visa-sejour.bpmn | Apposer la vignette au passeport | non | 0.513 |

## Tous les candidats

| Modèle | Libellé | Référence | position | lexique | sémantique (score) |
|---|---|---|---|---|---|
| admission-hopital.bpmn | Enregistrer le patient à l'accueil | non | non | non | non (0.233) |
| admission-hopital.bpmn | Saisir les constantes vitales | non | non | non | oui (0.639) |
| admission-hopital.bpmn | Installer le patient en salle d'attente | non | non | non | non (0.414) |
| admission-hopital.bpmn | Évaluer l'état du patient à l'arrivée | oui | non | oui | oui (0.778) |
| admission-hopital.bpmn | Examiner les antécédents médicaux | oui | non | oui | oui (0.691) |
| admission-hopital.bpmn | Décider de l'orientation du patient | oui | oui | oui | oui (0.786) |
| bourse-etudes.bpmn | Enregistrer les demandes de bourse | non | non | non | non (0.369) |
| bourse-etudes.bpmn | Saisir les relevés de notes | non | non | non | oui (0.509) |
| bourse-etudes.bpmn | Vérifier les pièces du dossier de bourse | oui | oui | oui | non (0.422) |
| bourse-etudes.bpmn | Évaluer le mérite académique du candidat | oui | non | oui | oui (0.933) |
| bourse-etudes.bpmn | Décider de l'attribution de la bourse | oui | oui | oui | oui (0.704) |
| bourse-etudes.bpmn | Publier la liste des bénéficiaires | non | non | non | non (0.353) |
| copd.bpmn | Evaluate request | oui | oui | oui | oui (0.681) |
| copd.bpmn | Evaluate hospitalization | oui | oui | oui | oui (0.810) |
| copd.bpmn | Treat exacerbations | non | non | non | oui (0.799) |
| copd.bpmn | Prescribe therapy | non | non | non | oui (0.592) |
| copd.bpmn | Plan an examination | oui | non | oui | oui (0.732) |
| copd.bpmn | Refresh calendar | non | non | non | non (0.144) |
| copd.bpmn | Examine and interview patient | non | non | non | oui (0.581) |
| copd.bpmn | Make working diagnosis | oui | non | oui | oui (0.671) |
| copd.bpmn | Conduct diagnostic workup | non | non | non | non (0.338) |
| credit-bancaire.bpmn | Saisir les informations du client | non | non | non | non (0.312) |
| credit-bancaire.bpmn | Constituer le dossier de garanties | non | non | non | oui (0.645) |
| credit-bancaire.bpmn | Vérifier la complétude du dossier de crédit | oui | oui | oui | oui (0.701) |
| credit-bancaire.bpmn | Évaluer la solvabilité du demandeur | oui | non | oui | oui (0.877) |
| credit-bancaire.bpmn | Statuer sur l'octroi du crédit | oui | oui | oui | non (0.431) |
| credit-bancaire.bpmn | Archiver le dossier de crédit | non | non | non | non (0.230) |
| dedouanement.bpmn | Enregistrer la déclaration au guichet | non | non | non | non (0.156) |
| dedouanement.bpmn | Saisir le manifeste de cargaison | non | non | non | non (0.146) |
| dedouanement.bpmn | Vérifier la déclaration en détail | oui | oui | oui | oui (0.779) |
| dedouanement.bpmn | Examiner les documents joints | oui | non | oui | non (0.133) |
| dedouanement.bpmn | Statuer sur la mainlevée | oui | oui | oui | non (0.307) |
| dedouanement.bpmn | Imprimer le bon à enlever | non | non | non | oui (0.539) |
| fimex.bpmn | Affecter le dossier à un agent | oui | non | oui | oui (0.621) |
| fimex.bpmn | Consulter le dossier coté | non | non | non | non (0.385) |
| fimex.bpmn | Vérifier la conformité documentaire | oui | oui | oui | oui (0.521) |
| fimex.bpmn | Saisir l'observation de complément | non | non | non | oui (0.822) |
| fimex.bpmn | Saisir le motif de rejet | non | non | non | oui (0.703) |
| fimex.bpmn | Valider pour signature | non | non | non | non (0.441) |
| fimex.bpmn | Saisir l'observation de réexamen | non | non | non | oui (0.863) |
| fimex.bpmn | Consulter la demande et la décision | oui | oui | non | oui (0.887) |
| fimex.bpmn | Signer électroniquement l'attestation | non | non | non | non (0.131) |
| marche-public.bpmn | Enregistrer les plis reçus | non | non | non | non (0.054) |
| marche-public.bpmn | Ouvrir les plis en séance | non | non | non | non (0.145) |
| marche-public.bpmn | Transmettre les offres à la sous-commission | non | non | non | oui (0.518) |
| marche-public.bpmn | Vérifier la conformité administrative des offres | oui | oui | oui | oui (0.823) |
| marche-public.bpmn | Coter les offres techniques | oui | non | oui | oui (0.529) |
| marche-public.bpmn | Statuer sur l'attribution du marché | oui | oui | oui | oui (0.604) |
| marche-public.bpmn | Apprécier la recevabilité des recours | oui | non | oui | oui (0.798) |
| marche-public.bpmn | Archiver le dossier du marché | non | non | non | non (0.304) |
| permis-construire.bpmn | Enregistrer la demande de permis | non | non | non | oui (0.569) |
| permis-construire.bpmn | Saisir les caractéristiques du projet | non | non | non | oui (0.693) |
| permis-construire.bpmn | Vérifier la complétude de la demande de permis | oui | oui | oui | oui (0.936) |
| permis-construire.bpmn | Consulter les services techniques | non | non | non | oui (0.526) |
| permis-construire.bpmn | Examiner la conformité au plan d'urbanisme | oui | non | oui | oui (0.764) |
| permis-construire.bpmn | Statuer sur la délivrance du permis | oui | oui | oui | oui (0.575) |
| permis-construire.bpmn | Archiver le dossier du permis | non | non | non | non (0.285) |
| recrutement.bpmn | Publier l'offre d'emploi | non | non | non | non (0.195) |
| recrutement.bpmn | Enregistrer les candidatures reçues | non | non | non | non (0.241) |
| recrutement.bpmn | Vérifier l'éligibilité de la candidature | oui | oui | oui | oui (0.815) |
| recrutement.bpmn | Convoquer les candidats aux entretiens | non | non | non | oui (0.599) |
| recrutement.bpmn | Coter l'entretien du candidat | oui | non | oui | oui (0.509) |
| recrutement.bpmn | Choisir le candidat à recruter | oui | oui | oui | oui (0.527) |
| sinistre-assurance.bpmn | Enregistrer la déclaration de sinistre | non | non | non | non (0.324) |
| sinistre-assurance.bpmn | Vérifier les garanties du contrat | oui | non | oui | oui (0.618) |
| sinistre-assurance.bpmn | Mandater l'expert automobile | non | non | non | oui (0.581) |
| sinistre-assurance.bpmn | Apprécier la responsabilité de l'assuré | oui | oui | oui | oui (0.876) |
| sinistre-assurance.bpmn | Décider de l'indemnisation du sinistre | oui | oui | oui | oui (0.652) |
| sinistre-assurance.bpmn | Clôturer le dossier sinistre | non | non | non | non (0.430) |
| 01-credit-bancaire.bpmn | Saisir les informations du client | non | non | non | non (0.312) |
| 01-credit-bancaire.bpmn | Vérifier la complétude du dossier | oui | oui | oui | oui (0.756) |
| 01-credit-bancaire.bpmn | Évaluer la solvabilité du demandeur | oui | non | oui | oui (0.877) |
| 01-credit-bancaire.bpmn | Statuer sur l'octroi du crédit | oui | oui | oui | non (0.431) |
| 02-sinistre-assurance.bpmn | Enregistrer la déclaration | non | non | non | non (0.225) |
| 02-sinistre-assurance.bpmn | Vérifier la validité de la garantie | oui | oui | oui | oui (0.938) |
| 02-sinistre-assurance.bpmn | Évaluer le montant des dommages | oui | non | oui | oui (0.850) |
| 02-sinistre-assurance.bpmn | Statuer sur l'indemnisation | oui | oui | oui | non (0.462) |
| 03-admission-hopital.bpmn | Mesurer les constantes vitales | non | non | non | oui (0.577) |
| 03-admission-hopital.bpmn | Coter la gravité du patient | oui | non | oui | oui (0.627) |
| 03-admission-hopital.bpmn | Examiner le patient | oui | oui | oui | oui (0.514) |
| 03-admission-hopital.bpmn | Installer le patient au lit | non | non | non | non (0.301) |
| 03-admission-hopital.bpmn | Rédiger le compte rendu d'admission | non | non | non | non (0.223) |
| 04-recrutement.bpmn | Enregistrer la candidature | non | non | non | non (0.262) |
| 04-recrutement.bpmn | Vérifier l'éligibilité de la candidature | oui | oui | oui | oui (0.815) |
| 04-recrutement.bpmn | Apprécier l'entretien du candidat | oui | oui | oui | oui (0.630) |
| 05-marche-public.bpmn | Ouvrir les plis en séance | non | non | non | non (0.145) |
| 05-marche-public.bpmn | Vérifier la conformité administrative | oui | oui | oui | oui (0.826) |
| 05-marche-public.bpmn | Évaluer l'offre technique | oui | non | oui | oui (0.863) |
| 05-marche-public.bpmn | Évaluer l'offre financière | oui | non | oui | oui (0.887) |
| 05-marche-public.bpmn | Statuer sur l'attribution du marché | oui | oui | oui | oui (0.604) |
| 06-dedouanement.bpmn | Vérifier les documents joints | oui | oui | oui | non (0.128) |
| 06-dedouanement.bpmn | Apprécier la valeur en douane | oui | non | oui | oui (0.784) |
| 07-bourse-etudes.bpmn | Enregistrer le dossier | non | non | non | non (0.203) |
| 07-bourse-etudes.bpmn | Vérifier les pièces du dossier | oui | oui | oui | non (0.413) |
| 07-bourse-etudes.bpmn | Coter le mérite académique | oui | non | oui | oui (0.832) |
| 07-bourse-etudes.bpmn | Statuer sur l'attribution de la bourse | oui | oui | oui | non (0.443) |
| 08-permis-construire.bpmn | Enregistrer la demande | non | non | non | non (0.239) |
| 08-permis-construire.bpmn | Vérifier la complétude des pièces | oui | oui | oui | oui (0.673) |
| 08-permis-construire.bpmn | Examiner la conformité au plan d'urbanisme | oui | non | oui | oui (0.764) |
| 08-permis-construire.bpmn | Statuer sur la délivrance du permis | oui | oui | oui | oui (0.575) |
| 08-permis-construire.bpmn | Établir l'arrêté municipal | non | non | non | oui (0.568) |
| 09-visa-sejour.bpmn | Numériser les pièces du dossier | non | non | non | non (0.252) |
| 09-visa-sejour.bpmn | Vérifier l'authenticité des documents | oui | non | oui | oui (0.509) |
| 09-visa-sejour.bpmn | Statuer sur la délivrance du visa | oui | oui | oui | non (0.400) |
| 09-visa-sejour.bpmn | Apposer la vignette au passeport | non | non | non | oui (0.513) |
| 10-subvention-agricole.bpmn | Vérifier l'éligibilité de l'exploitation | oui | oui | oui | oui (0.923) |
| 10-subvention-agricole.bpmn | Programmer la visite de terrain | non | non | non | non (0.449) |
| 10-subvention-agricole.bpmn | Apprécier le projet agricole | oui | non | oui | oui (0.505) |
| 10-subvention-agricole.bpmn | Statuer sur le montant de la subvention | oui | oui | oui | oui (0.681) |
