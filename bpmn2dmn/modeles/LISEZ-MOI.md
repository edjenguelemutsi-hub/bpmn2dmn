# Modèles de l'indice sémantique

| Fichier | Rôle |
|---|---|
| `exemples-indice-semantique.txt` | les 392 libellés d'apprentissage écrits à la main (150 décisions « D », 242 non-décisions « N » ; français, anglais, allemand, espagnol), aucun repris du corpus de validation |
| `classifieur-semantique.json` | la régression logistique apprise (384 poids, biais, seuil 0,5), avec les empreintes des fichiers du modèle, la mesure en validation croisée et la liste des exemples ; produit par `python -X utf8 outils/entrainer-indice-semantique.py` |
| `minilm-multilingue.sha256` | les empreintes SHA-256 attendues des fichiers du modèle de langue |
| `minilm-multilingue/` | les fichiers du modèle (non versionnés, 136 Mo) : `model_quantized.onnx`, `tokenizer.json` et leurs réglages, téléchargés par `python -X utf8 outils/telecharger-modele.py` depuis le dépôt Hugging Face `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (export ONNX du modèle `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, licence Apache 2.0) |

Validation croisée (cinq plis) du classifieur : précision 0,910, rappel
0,880, exactitude 0,921 ; les 31 erreurs hors pli sont listées dans le
fichier JSON (`validation_croisee.erreurs`).
