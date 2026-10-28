# Jeux d'essai Camunda Modeler

Dix processus BPMN 2.0 à mise en page soignée, prêts à
ouvrir dans **Camunda Modeler** (Fichier → Ouvrir) ou à
déposer dans l'application du transformateur
(`python cli.py servir`). Chaque fichier a sa référence
experte `.gold` (décisions attendues) :
`python cli.py valider "jeux-test-camunda/*.bpmn"`.

Régénération : `python outils/generer_jeux_camunda.py`.

| Fichier | Processus | Décisions |
|---|---|---|
| `01-credit-bancaire.bpmn` | Instruction d'une demande de crédit | 3 |
| `02-sinistre-assurance.bpmn` | Traitement d'une déclaration de sinistre | 3 |
| `03-admission-hopital.bpmn` | Admission d'un patient aux urgences | 2 |
| `04-recrutement.bpmn` | Instruction d'une candidature | 2 |
| `05-marche-public.bpmn` | Évaluation des offres d'un appel d'offres | 4 |
| `06-dedouanement.bpmn` | Mainlevée d'une déclaration en douane | 2 |
| `07-bourse-etudes.bpmn` | Attribution d'une bourse d'études | 3 |
| `08-permis-construire.bpmn` | Instruction d'un permis de construire | 3 |
| `09-visa-sejour.bpmn` | Délivrance d'un visa de séjour | 2 |
| `10-subvention-agricole.bpmn` | Attribution d'une subvention agricole | 3 |
