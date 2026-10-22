# European web-form artifact exploration

A bounded follow-up to [Understanding Privacy Norms through Web Forms](https://doi.org/10.56553/popets-2025-0002), DD2496 Group 06.

We reused the released crawler and historical annotations, captured new forms with a Stockholm browser profile and user-declared Swedish network egress, and annotated new evidence with Jev. Of 500 fixed historical domains, 405 completed and 261 qualify for the final matched comparison. We also measured declared requiredness.

## Start here

- [Experiment explanation](deliverables/experiment-explanation.md)
- [Technical report](deliverables/technical-report.md) and [written PDF](deliverables/technical-report.pdf)
- [Code and file structure](deliverables/code-structure.md)
- [Video walkthrough](deliverables/video-walkthrough-guide.md)
- [Execution evidence](deliverables/script-execution-log.md)
- [Aggregate results and figures](results/README.md)

## Main results

Both columns use exactly the same 261 domains.

| Information type | Historical | New captures |
| --- | ---: | ---: |
| Email address | 255/261 | 147/261 |
| Person name | 180/261 | 81/261 |
| Phone number | 101/261 | 33/261 |
| Address | 45/261 | 3/261 |

Among 11,005 eligible visible controls across exports, 3,044 have HTML-required evidence and 6,833 have no explicit required/optional declaration. Signals can overlap. Unspecified does not mean optional; server enforcement was not tested.

Dates, access location, browser versions, depth and annotation methods differ. The results do not isolate a regional effect or establish field removal. The earlier small audit does not validate the final annotation protocol; fresh human labels remain unavailable.

## Layout

| Folder | Responsibility |
| --- | --- |
| `01-prepare/` | Install dependencies, inspect historical databases and freeze the cohort. |
| `02-crawl/` | Run bounded crawls and normalize saved controls; includes the upstream patch. |
| `03-annotate/` | Sanitize descriptions, annotate with Jev and enforce the budget. |
| `04-validate/` | Export blinded questions and evaluate supplied labels. |
| `05-analyze/` | Derive matched rates and figures. |
| `results/` | Selected aggregate outputs and checksums. |
| `deliverables/` | Report and explanation, source guide and video plan. |

Each numbered step has one entry script and one README. The public package excludes raw captures, historical databases, predictions, request/ledger payloads, private labels, installed environments and internal continuation history. Detailed documentation identifies omitted files as local evidence. Full regeneration needs these separately retained inputs; the aggregate results can be inspected directly.

## Installation

Use Python 3 and Node.js 20 or newer. The recorded runtime used Python 3.14 and Node 22.23.3 on Apple silicon. From the repository root:

```sh
git clone --depth 1 --no-checkout https://github.com/UCI-Networking-Group/webform.git upstream
git -C upstream fetch --depth 1 origin a4f391d604e5cd557b881145b2a1cfd072e542d0
git -C upstream checkout --detach a4f391d604e5cd557b881145b2a1cfd072e542d0
python3 01-prepare/run.py setup --warm-navigation
```

Setup applies `02-crawl/data/crawler.patch`, installs pinned dependencies and Chromium, then compiles the crawler. The preparation README documents disk requirements and separately obtaining the historical databases. The software license is not a dataset redistribution license.

Copy `.env.example` to `.env` and fill `TYPESAFE_API_KEY` only if annotation is needed. Never commit it. Crawling contacts live websites, annotation can spend money, and the original experiment's budget is not authorization for another run. Read each step README before executing it.

## Inspect saved results

Only Python's standard library is needed:

```sh
python3 - <<'PY'
import json
from pathlib import Path
print(json.loads(Path('results/summary.json').read_text()))
PY
```

The public video guide also uses saved aggregate files, so recording a demonstration does not require another crawl or inference run.

## Uploading and reuse

This repository contains the selected public files. Commit the code, documentation, saved patch and aggregate outputs admitted by `.gitignore`. Keep credentials, raw captures, private review records and installed dependencies local.

Publication remains pending. Before submission, add the repository/video links and individual contributions. Select a license for the group's original additions before inviting reuse. The [third-party notices](THIRD_PARTY_NOTICES.md) retain the upstream copyright and permission notice.
