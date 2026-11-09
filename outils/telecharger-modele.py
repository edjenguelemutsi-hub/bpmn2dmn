# -*- coding: utf-8 -*-
"""
Télécharge les fichiers du modèle de langue léger de l'indice sémantique
(MiniLM-L12 multilingue, export ONNX quantifié de Xenova) dans
`bpmn2dmn/modeles/minilm-multilingue/` et écrit leurs empreintes SHA-256.

    pip install -r requirements-semantique.txt
    python -X utf8 outils/telecharger-modele.py

Environ 136 Mo. Les fichiers ne sont pas versionnés dans le dépôt ; les
empreintes attendues sont dans `bpmn2dmn/modeles/minilm-multilingue.sha256`
et le téléchargement est refusé si elles ne correspondent pas.
"""
import hashlib
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "bpmn2dmn", "modeles", "minilm-multilingue")
ATTENDUES = os.path.join(RACINE, "bpmn2dmn", "modeles", "minilm-multilingue.sha256")
DEPOT = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
FICHIERS = ["onnx/model_quantized.onnx", "tokenizer.json", "tokenizer_config.json",
            "special_tokens_map.json", "config.json"]


def sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def principal() -> int:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("pip install huggingface_hub  (nécessaire au téléchargement seulement)")
        return 1
    attendues = {}
    if os.path.isfile(ATTENDUES):
        for ligne in open(ATTENDUES, encoding="utf-8"):
            if ligne.strip():
                e, nom = ligne.split()
                attendues[nom] = e
    os.makedirs(DOSSIER, exist_ok=True)
    for f in FICHIERS:
        cible = os.path.join(DOSSIER, os.path.basename(f))
        if not os.path.exists(cible):
            chemin = hf_hub_download(DEPOT, f, revision="main")
            with open(chemin, "rb") as src, open(cible, "wb") as dst:
                dst.write(src.read())
            print("téléchargé :", os.path.basename(f), os.path.getsize(cible), "octets")
        e = sha256(cible)
        if os.path.basename(f) in attendues and attendues[os.path.basename(f)] != e:
            print("EMPREINTE INATTENDUE pour %s : %s" % (os.path.basename(f), e))
            return 1
        print("%s  %s" % (e, os.path.basename(f)))
    if not os.path.isfile(ATTENDUES):
        with open(ATTENDUES, "w", encoding="utf-8") as out:
            for f in FICHIERS:
                nom = os.path.basename(f)
                out.write("%s  %s\n" % (sha256(os.path.join(DOSSIER, nom)), nom))
        print("empreintes écrites :", ATTENDUES)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
