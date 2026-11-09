# Échantillon : décisions retenues grâce à l'indice sémantique sur les modèles allemands

Tirage au sort (graine 20261109) de 60 décisions retenues par la variante
« definition-etendue + indice-semantique » et **non retenues** par la variante
« definition-etendue » seule, sur les diagrammes des participants des cours
allemands de bpmn-for-research (`banc-ouvert/sources/bfr/DE/*/resultats/`).
Chaque ligne : libellé de l'activité, question de la passerelle qui la suit
(vide si la passerelle n'est pas nommée), jugement de l'auteur (D = l'activité
est bien une étape de décision ; N = non). Le jugement est celui d'un seul
annotateur, qui lit l'allemand ; il donne un ordre de grandeur, pas une
mesure.

| Libellé | Passerelle | Jugement |
|---|---|---|
| Regressoption prüfen | | D |
| Widerspruch prüfen | | D |
| Geldeingang oder Widerspruch prüfen | | D |
| Versicherung abschließen | | N (souscrire l'assurance : exécution) |
| Prüfung Versicherung notwendig | Ergebnis Prüfung Versicherung notwendig | D |
| Mengenprüfung | Ergebnis Mengenprüfung | D |
| Scoring Level 1 durchführen | Ergebnis vorliegend? | D (calcul du score, étape décisionnelle du corrigé) |
| Versicherung abschließen | | N |
| Regress prüfen | | D |
| Widerspruch prüfen | gerechtfertigt | D |
| Regressprüfung | Regress möglich? | D |
| Zahlungseingang prüfen | Zahlung fristgerecht eingegangen? | D |
| Einspruch prüfen | gerechtfertigt? | D |
| Versicherung über Logistikleiter abschließen | | N |
| Fall prüfen | | D |
| Widerspruch prüfen | Zahlungsverweigerung | D |
| Regress prüfen | | D |
| Widerspruch prüfen | | D |
| Prüfung ob Versicherung erforderlich | | D |
| Versicherung abschließen | | N |
| Regressanspruch prüfen | Regressanspruch gerechtfertigt | D |
| Widerspruch prüfen | Widerspruch gerechtfertigt? | D |
| Fall prüfen | Regressanspruch besteht? | D |
| Widerspruch prüfen | Zahlungsverweigerung gerechtfertigt | D |
| Anfrage verarbeiten | Ergebnis? | N (traiter la demande : trop général) |
| Prüfung Anspruch | berechtigt? | D |
| Widerspruch prüfen | berechtigt? | D |
| Fall prüfen (ich) | Regress möglich? | D |
| Widerspruch prüfen (ich) | Widerspruch gerechtfertigt? | D |
| Fall prüfen | | D |
| Widerspruch prüfen | | D |
| Fall überprüfen | Regress möglich? | D |
| Zweites Scoring durchführen | | D |
| Level 1 Score berechnen | | D |
| Level 2 Score berechnen | | D |
| Widerspruch prüfen | Widerspruch gerechtfertigt? | D |
| Sachlage prüfen | Widerspruch eingelegt? | D |
| Versicherung prüfen | Versicherung nötig? | D |
| Regress prüfen | Regressanspruch? | D |
| Wiederspruch prüfen | Wiederspruch gerechtfertigt | D |
| Versicherung abschliessen | | N |
| Versicherung abschließen | | N |
| Zahlungs-aufforderung prüfen | Widerspruch? | D |
| Regress-meldung prüfen | Regress? | D |
| Widerspruch prüfen | Widerspruch korrekt? | D |
| Scoringanfrage stellen | Ergebnis sofort? | N (envoyer la demande de score) |
| Regressmöglichkeit prüfen | Regress möglich? | D |
| Widerspruch prüfen | Widerspruch gerechtfertigt? | D |
| Regressprüfung | JA (Regress) | D |
| Widerspruch prüfen | | D |
| Anfrage Warenversand | | N (demande d'expédition) |
| Warenversand Standard | | N (expédition standard) |
| Lieferant auswählen | | D |
| Fall prüfen | Möglichkeit besteht? | D |
| Widerspruch prüfen | Gerechtfertigt? | D |
| Scoring Level 1 durchführen | | D |
| Sachverhalt prüfen | Regress? | D |
| Widerspruch prüfen | | D |
| Scoring Level 1 durchführen | Scoring verzögert sich | D |
| Feststellen ob Scoring Level 1 vorhanden | Level 1 vorhanden? | D |

Bilan : 50 décisions sur 60 (83 %), 10 non-décisions, toutes de deux
familles : « Versicherung abschließen » (souscrire une assurance, qui suit la
décision « assurance nécessaire ? » et précède une passerelle de jonction) et
les libellés nominaux de demande ou d'expédition (« Anfrage », « Warenversand »).
Le lexique Λ, qui ne contient aucun verbe allemand, ne retient aucune de ces
60 activités ; la position seule ne suffit pas non plus pour une tâche
générique (il faut deux indices). L'indice sémantique apporte donc sur cette
collection ce que la liste fermée ne peut pas donner, au prix d'environ une
erreur sur six, que l'expert voit avec le score et l'exemple d'apprentissage
le plus proche dans le motif de rétention.
