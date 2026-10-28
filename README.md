# bpmn2dmn

Extraction of DMN decision requirements diagrams (DRD) from BPMN process models,
by a formal graph transformation with hybrid filtering of decision candidates.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.NNNNNNN.svg)](https://doi.org/10.5281/zenodo.NNNNNNN)
[![Licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

This tool accompanies the article:

> R. Djeumen, F. Edjenguele. *Data-driven extraction of DMN decision models from BPMN
> processes: A formal graph transformation approach with hybrid candidate filtering.*
> 2026 (under review; this reference will be updated on publication).

## How to cite

If this tool helps your work, please cite the article above and the software:

> F. Edjenguele, R. Djeumen. *bpmn2dmn* (version 1.0.0). Zenodo, 2026.
> https://doi.org/10.5281/zenodo.NNNNNNN

A BibTeX entry is available through the "Cite this repository" button of GitHub (file
`CITATION.cff`). We would be glad to hear about the work in which the tool was useful:
open an issue on this repository.

## What it does

- reads a BPMN 2.0 file and builds the reduced process graph $M_i$ (activities,
  gateways, events, flows, lanes, data objects, data stores, annotations);
- applies the six patterns $P_1$ to $P_6$ of the transformation $T$ and the hybrid
  corroboration predicate (spatial clue: the task is immediately followed by an
  exclusive or inclusive gateway; lexical clue: a decision verb in its label);
- writes a DMN 1.3 file with DMNDI layout, checks eight invariants on the result
  (acyclicity, well-formed requirements, no duplicate arc, ...) and records every
  question left to the human expert;
- offers the inverse transformation (DRD to BPMN skeleton), a generator of test
  models with their oracle, a CSV register of all runs, and seven optional
  extensions of the algorithm, disabled by default (`EXTENSIONS-ALGORITHME.md`).

## Requirements

Python 3.10 or later (developed and tested with Python 3.13) and two libraries:

```
pip install -r requirements.txt
```

Everything runs offline. The web interface embeds the bpmn-js and dmn-js viewers.

## Use

From the root of the repository:

```
python cli.py transformer corpus/fimex.bpmn -o fimex.dmn -a corpus/fimex.arbitrages.json
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
to leave the register as published.

On Windows, `Lancer-application.bat` starts the web interface with a double click.
The code, its comments, the messages of the tool and the secondary notes (`LISEZ-MOI.md`
files) are written in French.

## Layout of the repository

| Folder or file | Content |
|---|---|
| `bpmn2dmn/` | the library: parser, metamodels, transformation, validation, serialiser, inverse transformation, generator, extensions, register |
| `cli.py`, `app.py`, `ui/` | command line, local web server and interface |
| `corpus/` | the ten detailed models of the corpus (FIMEX, COPD and eight others) with their expert references (`.gold`), the FIMEX verdict file and the FIMEX reference DRD |
| `jeux-test-camunda/` | the ten simpler test models of the corpus, with their expert references; they open in Camunda Modeler |
| `catalogue-patterns/` | one small model per pattern and per guard, with the expected result |
| `tests/` | unit and robustness tests (`python -m unittest discover -s tests`, 112 tests) |
| `build-xsd/` | the OMG XML schemas of BPMN 2.0 and DMN 1.3, used by the schema checks |
| `outils/` | side tools: baselines, parallel campaigns, XSD validation, captures |
| `experimentations/` | the register of extractions (`registre.csv`, `campagnes.csv`), its column dictionary and the outputs of each run |
| `EXTENSIONS-ALGORITHME.md` | description of the seven optional extensions |

## Reproducing the figures of the article

- `python cli.py valider "corpus/*.bpmn" "jeux-test-camunda/*.bpmn"` prints, for each of the
  twenty models, the detected decisions against the expert reference, then the precision and
  recall (59 decisions, 32 in `corpus/` and 27 in `jeux-test-camunda/`);
- `experimentations/registre.csv` is the register cited in the article; one line is
  enough to replay an extraction identically (`experimentations/LISEZ-MOI.md`);
- `python cli.py campagne N` repeats the large-scale check of the implementation.

## Licence

- Everything in this repository (code, models, references, register) is released under
  the MIT licence, see `LICENSE`.
- Embedded viewers bpmn-js and dmn-js: bpmn.io licence, see `ui/lib/LICENSE-bpmn.io.txt`.
  The "Powered by bpmn.io" mark must be kept.
- OMG schemas in `build-xsd/`: Copyright Object Management Group, redistributed unchanged.

## Authors

- Francis Edjenguele, University of Douala and Single Window for Foreign Trade
  Operations (GUCE), Douala, Cameroon
- Rodrigue Djeumen, University of Douala, Cameroon

The FIMEX model is published with the agreement of GUCE.
