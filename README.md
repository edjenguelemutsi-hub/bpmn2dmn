# bpmn2dmn

Extraction of DMN decision requirements diagrams (DRD) from BPMN process models,
by a formal graph transformation with hybrid filtering of decision candidates.
Version 1.2 adds decision tables written in FEEL, stable identifiers and
traceability between the two models (DMN-to-BPMN synchronisation, impact
analysis), an optional semantic clue computed by a light multilingual language
model, and an open benchmark on more than three thousand third-party models.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23736474.svg)](https://doi.org/10.5281/zenodo.23736474)
[![Licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

This tool accompanies the article:

> R. Djeumen, F. Edjenguele. *Data-driven extraction of DMN decision models from BPMN
> processes: A formal graph transformation approach with hybrid candidate filtering.*
> 2026 (under review; this reference will be updated on publication).

## How to cite

If this tool helps your work, please cite the article above and the software:

> F. Edjenguele, R. Djeumen. *bpmn2dmn* (version 1.2.0). Zenodo, 2026.
> https://doi.org/10.5281/zenodo.23736473 (concept DOI, resolves to the latest version;
> version 1.0.0, the one used for the article: https://doi.org/10.5281/zenodo.23736474)

A BibTeX entry is available through the "Cite this repository" button of GitHub (file
`CITATION.cff`). We would be glad to hear about the work in which the tool was useful:
open an issue on this repository.

## What it does

- reads a BPMN 2.0 file and builds the reduced process graph $M_i$ (activities,
  gateways, events, flows, lanes, data objects, data stores, annotations, flow
  conditions, default flows);
- applies the six patterns $P_1$ to $P_6$ of the transformation $T$ and the hybrid
  corroboration predicate $\kappa$ (spatial clue: the task is immediately followed by an
  exclusive or inclusive gateway; lexical clue: a decision verb in its label);
- writes a DMN 1.3 file with DMNDI layout, **stable identifiers** derived from the BPMN
  elements (`Decision_T3`, `InputData_do_dossier`) and a **trace element** on every node
  and requirement (source element, pattern, clues), checks eight invariants on the
  result (acyclicity, well-formed requirements, no duplicate arc, ...) and records every
  question left to the human expert; a `.trace.json` file accompanies the DMN;
- with the `logique` extension, writes for each decision followed by a gateway a
  **decision table** whose rules are read from the conditions written on the outgoing
  sequence flows (FEEL, JUEL, JavaScript subsets) and written as FEEL unary tests, with
  typed input columns, the default flow as last rule (hit policy FIRST) and, for a
  yes/no gateway without conditions, a boolean input named after the question; tables
  whose every rule is written are executable by a DMN engine;
- **synchronises** a DRD modified in Camunda Modeler back to the BPMN file
  (`synchroniser`: renamed, added or removed decisions, input data, requirements,
  knowledge sources, table rules written as flow conditions), then replays the
  transformation and checks that it gives the modified DRD back; **analyses the impact**
  of a modified process on a previously produced DRD (`impact`: vanished or renamed
  nodes, invalidated requirements);
- with the `indice-semantique` extension, adds a third clue to $\kappa$: a light
  multilingual sentence model (MiniLM-L12, ONNX, 118 MB, run on the CPU) and a logistic
  classifier trained on hand-written labels judge whether a label is decisional in any
  language; the clue never retains a decision alone, it proposes it to the expert with
  its score and the nearest training example;
- offers the inverse transformation (DRD to BPMN skeleton), a generator of test
  models with their oracle, a CSV register of all runs, eight optional
  extensions of the algorithm, disabled by default (`EXTENSIONS-ALGORITHME.md`), and an
  open benchmark on 3,761 third-party models (`BANC-OUVERT.md`).

## Requirements

Python 3.10 or later (developed and tested with Python 3.13) and two libraries:

```
pip install -r requirements.txt
```

Everything runs offline. The web interface embeds the bpmn-js and dmn-js viewers.

The semantic clue is optional. It needs three more libraries and the model files
(about 136 MB, downloaded once, not versioned here):

```
pip install -r requirements-semantique.txt
python outils/telecharger-modele.py
```

Without them, the extension is listed as unavailable and everything else works.

## Use

From the root of the repository:

```
python cli.py transformer corpus/fimex.bpmn -o fimex.dmn -a corpus/fimex.arbitrages.json
python cli.py transformer corpus/fimex.bpmn -o fimex.dmn --extensions logique   # decision tables
python cli.py synchroniser corpus/fimex.bpmn fimex-modifie.dmn -a corpus/fimex.arbitrages.json -o fimex-mis-a-jour.bpmn
python cli.py impact fimex.dmn fimex-modifie.bpmn -a corpus/fimex.arbitrages.json
python cli.py inverser fimex.dmn -o fimex-squelette.bpmn
python cli.py valider "corpus/*.bpmn" "jeux-test-camunda/*.bpmn"   # the 20 models against their expert references
python cli.py generer 100 -d generes       # 100 generated models with their oracle
python cli.py campagne 1000                # mass campaign: invariants, oracle, round trip
python cli.py servir                       # web interface at http://localhost:8765
python cli.py registre --dernieres 10      # summary of the experiment register
python cli.py extensions                   # list of the optional extensions
```

Every `transformer`, `valider` or `campagne` run appends a line to `experimentations/registre.csv`
and writes its outputs next to it. Add `--sans-registre` (or set `BPMN2DMN_SANS_REGISTRE=1`)
to leave the register as published. A register written by version 1.0 is migrated in
place when the new columns of version 1.2 are added (no line is lost).

On Windows, `Lancer-application.bat` starts the web interface with a double click. The
interface has three tabs: extraction (BPMN to DRD, with the expert's verdicts and the
decision tables), inverse path (DRD to BPMN skeleton) and co-evolution (a modified DRD
synchronised back to the process, or the impact of a modified process on the DRD).
The code, its comments, the messages of the tool and the secondary notes (`LISEZ-MOI.md`
files) are written in French.

## Layout of the repository

| Folder or file | Content |
|---|---|
| `bpmn2dmn/` | the library: parser, metamodels, transformation, validation, serialiser, inverse transformation, generator, extensions, register, `feel.py` (flow conditions and FEEL tests), `coevolution.py` (traceability, synchronisation, impact), `semantique.py` (semantic clue) |
| `bpmn2dmn/modeles/` | the training labels and the trained classifier of the semantic clue; the language model files are downloaded here (`minilm-multilingue/`, checksums in `minilm-multilingue.sha256`) |
| `cli.py`, `app.py`, `ui/` | command line, local web server and interface |
| `corpus/` | the ten detailed models of the corpus (FIMEX, COPD and eight others) with their expert references (`.gold`), the FIMEX verdict file and the FIMEX reference DRD |
| `jeux-test-camunda/` | the ten simpler test models of the corpus, with their expert references; they open in Camunda Modeler |
| `catalogue-patterns/` | one small model per pattern and per guard, with the expected result; `resultats-extensions/` gives the effect of the extensions, decision tables included |
| `tests/` | unit and robustness tests (`python -m unittest discover -s tests`, 141 tests); `controle_interface.py` drives the web interface headlessly |
| `build-xsd/` | the OMG XML schemas of BPMN 2.0 and DMN 1.3, used by the schema checks |
| `outils/` | side tools: baselines, parallel campaigns, XSD validation, captures, training and evaluation of the semantic clue (`entrainer-indice-semantique.py`, `evaluer-indices.py`), benchmark (`telecharger-banc.py`, `banc-ouvert.py`) |
| `experimentations/` | the register of extractions (`registre.csv`, `campagnes.csv`), its column dictionary, the outputs of each run and the evaluation of the $\kappa$ variants on the corpus |
| `banc-ouvert/` | the synthesis of the open benchmark (`synthese.md`, `resultats.csv`, the German sample); the 3,761 downloaded models are not versioned |
| `EXTENSIONS-ALGORITHME.md` | description of the eight optional extensions |
| `TRACABILITE-COEVOLUTION.md` | stable identifiers, trace, synchronisation and impact analysis |
| `BANC-OUVERT.md` | the open benchmark: collections, protocol, results |

## Reproducing the figures of the article

- `python cli.py valider "corpus/*.bpmn" "jeux-test-camunda/*.bpmn"` prints, for each of the
  twenty models, the detected decisions against the expert reference, then the precision and
  recall (59 decisions, 32 in `corpus/` and 27 in `jeux-test-camunda/`);
- `experimentations/registre.csv` is the register cited in the article; one line is
  enough to replay an extraction identically (`experimentations/LISEZ-MOI.md`);
- `python cli.py campagne N` repeats the large-scale check of the implementation;
- `python outils/evaluer-indices.py` compares the variants of $\kappa$ (spatial, lexical,
  semantic and their combinations) on the corpus; `python outils/banc-ouvert.py` replays
  the open benchmark after `python outils/telecharger-banc.py`.

## What changed in version 1.2

The reference algorithm and its outputs on the corpus are unchanged (same nodes, same
names, same requirements, same questions to the expert; verified by `tests/test_v4.py`
against the published outputs of version 1.0). What is new answers the observations of
the thesis supervisors: the decision tables are no longer skeletons but are written in
FEEL from the flow conditions; the identifiers of the DRD are stable and every element
carries its trace, which makes the DMN-to-BPMN synchronisation and the impact analysis
possible; the closed verb list of $\kappa$ can be complemented by a semantic clue that
reads any language; and the tool has been run on 3,761 models written by others.

## Licence

- Everything in this repository (code, models, references, register) is released under
  the MIT licence, see `LICENSE`.
- Embedded viewers bpmn-js and dmn-js: bpmn.io licence, see `ui/lib/LICENSE-bpmn.io.txt`.
  The "Powered by bpmn.io" mark must be kept.
- OMG schemas in `build-xsd/`: Copyright Object Management Group, redistributed unchanged.
- The language model of the semantic clue (paraphrase-multilingual-MiniLM-L12-v2, ONNX
  export by Xenova) is distributed by its authors under the Apache 2.0 licence; it is
  downloaded by the user and not redistributed here.
- The models of the open benchmark (camunda/bpmn-for-research: academic use only, link
  to the repository to be kept; bpmn-miwg-test-suite: OMG) are downloaded by the user and
  not redistributed here.

## Authors

- Francis Edjenguele, University of Douala and Single Window for Foreign Trade
  Operations (GUCE), Douala, Cameroon
- Rodrigue Djeumen, University of Douala, Cameroon

The FIMEX model is published with the agreement of GUCE.
