# Prepare the historical cohort

This step inspects the released databases, installs the small runtime and selects 500 historically observed domains. It preserves the historical rank, category objects and starting URL. The source checkout is pinned at `a4f391d604e5cd557b881145b2a1cfd072e542d0`.

The local environment is already installed. Run its check from the `PET` directory:

```sh
webform-privacy-norms/.venv/bin/python webform-privacy-norms/01-prepare/run.py --self-test
```

On a new machine, run `python3 webform-privacy-norms/01-prepare/run.py setup` before that check.

Setup creates `webform-privacy-norms/.venv`, installs Beautiful Soup and zstandard, applies the saved crawler patch if needed, installs the crawler dependencies from the patched npm lockfile, installs Chromium in `.browsers` and compiles the crawler. It writes measured sizes, versions and elapsed time to `data/setup.json`. Use `setup --skip-compile` only while editing the crawler; compile before crawling. Python HTTP requests use the standard library. No classifier environment or training packages are installed. The original crawler's CPU sentence embedding model is a navigation dependency and downloads when the crawler first runs. Its shared cache is separate from the historical classifier weights excluded from this experiment.

The final setup verification and compilation took 7.381 seconds after dependency and browser downloads. It measured 15,801,498 bytes for Python, 341,704,115 bytes for npm dependencies, 598,884,442 bytes for Chromium, headless shell and FFmpeg, and 23,685,047 bytes for the shared navigation model cache. Together these use 980,075,102 bytes before package-manager caches. Free disk space afterward was 91,060,985,856 bytes. First installation took longer and included a failed browser mirror before a working fallback. No exact first-install total was captured. The original Chromium 121 could not launch on macOS 27. Playwright is now pinned at 1.64.0 with bundled Chromium 156.0.8078.4 for compatibility. Other npm dependencies retain their original versions. The real Chromium extraction fixture passed. The remaining npm audit reports 17 vulnerabilities.

## Provide or download the databases

Get access through the [authors' artifact page](https://athinagroup.eng.uci.edu/projects/auditing-and-policy-analysis/webform-artifacts/). Only `domain.db.zst` and `webform-data.db.zst` are needed. Both approved archives are already downloaded in `data/`. Preserve them and use local decompression below. Do not fetch the raw crawl, screenshots or model archives.

The local archives expanded sequentially on 2026-10-09 with a 1 GiB compressed cap, a 4 GiB expanded cap and the 10 GiB crawl reserve:

```sh
webform-privacy-norms/.venv/bin/python webform-privacy-norms/01-prepare/run.py decompress domain.db --max-compressed-gib 1 --max-expanded-gib 4
webform-privacy-norms/.venv/bin/python webform-privacy-norms/01-prepare/run.py decompress webform-data.db --max-compressed-gib 1 --max-expanded-gib 4
```

`decompress` reads the existing `data/<name>.zst`. Use `--archive /path/archive.zst` for another local source, or `--sha256` to check a supplied digest. It checks the compressed size before expansion, reserves free space for the full expanded cap plus the crawl reserve, and checks remaining space while writing. It removes its own temporary output after failure, preserves the archive, runs SQLite `quick_check`, records both checksums in `data/<name>.decompress.json`, then makes the database read-only. An identical rerun verifies the database and archive against the report and reuses them. It refuses an existing database without a matching report or an interrupted temporary file. No network requests or dependency installation occur.

| File | Compressed bytes | Expanded bytes | Expansion and verification seconds |
| --- | ---: | ---: | ---: |
| domain.db | 29,471,397 | 130,707,456 | 0.337 |
| webform-data.db | 108,756,586 | 690,651,136 | 1.250 |

Both SQLite checks passed. Archives and expanded references together use 959,586,575 bytes. Expanded SHA-256 checksums are `33e3b699dc40138f2c17a64997d9738346f3c4b162f637ef7d91d3d9a3bd4a66` for `domain.db` and `7455a20f01f9576533dd452c74cc4fb0d3634644bc92b6934e88832fdb9d6124` for `webform-data.db`. No publisher checksum was supplied; the reports distinguish comparison with a supplied local digest from publisher verification.

If the expanded databases already exist, use their paths in the inspect and select commands below. Otherwise obtain the HTTPS download links and check their advertised sizes. For each archive, run this command with the appropriate name:

```sh
webform-privacy-norms/.venv/bin/python webform-privacy-norms/01-prepare/run.py download domain.db --url "$DOMAIN_DB_URL" --max-compressed-gib 8 --max-expanded-gib 24
webform-privacy-norms/.venv/bin/python webform-privacy-norms/01-prepare/run.py download webform-data.db --url "$WEBFORM_DB_URL" --max-compressed-gib 8 --max-expanded-gib 24
```

These caps are configurable limits, not measured database sizes. The downloader checks the advertised compressed size when available, bounds both streams, reserves 10 GiB for the new crawl and requires enough free space for both configured caps. It decompresses one database at a time, performs SQLite `quick_check`, saves both checksums and actual byte counts, and makes each expanded database read-only. Add `--sha256` if the publisher provides an archive checksum. Without it, the saved checksum identifies the downloaded bytes but does not verify them against the publisher. The downloader refuses existing archives or databases and removes incomplete temporary files after a failure. A retry restarts that archive. It does not retain signed URLs in its reports.

## Inspect and freeze selection

```sh
python3 webform-privacy-norms/01-prepare/run.py inspect
python3 webform-privacy-norms/01-prepare/run.py select
```

For databases elsewhere, supply the same paths to both commands:

```sh
python3 webform-privacy-norms/01-prepare/run.py inspect --domain-db /path/domain.db --annotation-db /path/webform-data.db
python3 webform-privacy-norms/01-prepare/run.py select --domain-db /path/domain.db --annotation-db /path/webform-data.db
```

The script inspects table columns before querying. The pinned source defines `tranco_list.ranking`, `domain_info.content_categories`, `http_info.url`, and historical form/field joins on `domain`, `job_hash` and `form_filename`. The released schemas were verified and match these columns. `inspect` saves `data/schema.json` with column types, primary-key positions, indexes and table row counts. It opens both references read-only. If another release differs, selection stops with the missing columns instead of guessing.

An eligible domain has at least one joined historical form/field annotation with a recognized form type and a nonempty JSON list containing only the 19 source PI labels, plus a rank, valid historical category objects and an HTTP starting URL. Empty category lists retain the historical Unknown category. Selection does not require identifying PI; the analysis step applies that filter when calculating rates. The script sorts eligible domains, samples with Python seed 42, then sorts the selected output. It stops if fewer than 500 qualify.

The outputs are `data/sites.csv` and `data/manifest.json`. CSV columns are `domain`, `rank`, `categories` and `start_url`. Categories remain a JSON array in each CSV cell. The manifest records database paths, checksums and bytes, the pinned source commit, selection SQL and rule, seed, eligible count, rejected records and CSV checksum. It also records the full historical category ID/name mapping, including categories outside the selected cohort, so analysis can recover parent category names. The scripts open historical databases in read-only mode. Rerunning with identical inputs reuses the cohort; differing inputs or outputs cause an error. Keep failed crawl sites in this cohort.

Completion means a unique 500-row CSV, a matching manifest, actual database schema verification and a successful crawler compile. The updated preparation self-test took 0.387 seconds. It verified deterministic selection from realistic historical table fixtures, malformed and unknown-label exclusion, composite-key joins, insufficient-cohort failure, unchanged input checksums and read-only database protection. It also verifies the local decompression cap, failure cleanup, archive preservation, checksum mismatch rejection, read-only mode and identical rerun. Real selection chose 500 unique domains from 10,143 eligible domains in 2.88 seconds. An identical rerun reused the same CSV and manifest. Every selected domain meets the inspected historical join, category and starting-URL rules.


## Restore the pinned checkout on another machine

Keep the tracked `02-crawl/data/crawler.patch` with these scripts. If `upstream` is absent, run:

```sh
git clone --depth 1 --no-checkout https://github.com/UCI-Networking-Group/webform.git webform-privacy-norms/upstream
git -C webform-privacy-norms/upstream fetch --depth 1 origin a4f391d604e5cd557b881145b2a1cfd072e542d0
git -C webform-privacy-norms/upstream checkout --detach a4f391d604e5cd557b881145b2a1cfd072e542d0
git -C webform-privacy-norms/upstream apply --check ../02-crawl/data/crawler.patch
git -C webform-privacy-norms/upstream apply ../02-crawl/data/crawler.patch
python3 webform-privacy-norms/01-prepare/run.py setup --warm-navigation
```

Setup checks the pinned commit and recognizes an already applied patch. It refuses a patch conflict rather than overwriting changes. It applies the package compatibility changes before installing dependencies. Node 20 or newer is required by Playwright 1.64.0. The verified local runtime is Node 22.23.3 on arm64.

`setup --warm-navigation` optionally downloads and benchmarks the original CPU navigation scorer with one process. It uses the same `Xenova/all-MiniLM-L6-v2` feature-extraction pipeline and seed phrases as the crawler. Transformers.js defaults to quantized ONNX weights. The warm check refuses a non-quantized ONNX download, limits all HTTP response bytes to 40 MiB, sets a 60-second request timeout and stops the process after 180 seconds. All site workers later use the same `02-crawl/data/navigation-model-cache` directory.

The approved initial check on this Apple M4 downloaded 23,688,411 response bytes and saved 23,685,047 cache bytes. The quantized model itself is 22,972,370 bytes. Startup, including its initial model download and seed embeddings, took 5.181 seconds. Five short link texts averaged 3.462 milliseconds each. The later cached run started in 0.592 seconds and averaged 3.510 milliseconds per link text. These are navigation scoring measurements, not crawl throughput. `data/navigation-model.json` records CPU, architecture, node version, file checksums and measurements. It records the requested mutable `main` revision and the observed remote commit `751bff37182d3f1213fa05d7196b954e230abad9`. File checksums identify the exact cached weights. A later warm check keeps the initial measurement while recording its current timing.


## Plotting dependencies

## Methodology follow-up

The original cohort and historical databases remain unchanged. The follow-up uses the frozen 500-domain cohort and the saved 7,953-form export; it does not select more domains or recrawl. A fresh blinded packet is preserved at `04-validate/data/methodology-v3/fresh-heldout/` with 12 forms, 16 groups and 12 reserved domains. Its human fields were blank before the follow-up and no model answers were included.

The frozen v3 configuration and selection are in `03-annotate/data/methodology-v3/selection.json`. It records the original source taxonomies, 0.5 PI threshold, 0.1 review margin and 0.6 purpose gate. Context and operational taxonomy clarifications were tested together. The upstream artifact does not publish detailed overlap rules, so the v3 distinctions are provisional study coding choices. The technical report's methodology follow-up section is the factual reference.

Paper-style graphs now use matplotlib 3.11.2 and scipy 1.18.1, pinned in this step's setup script. They were added to the existing environment after the crawl and human audit. The earlier setup sizes describe the pre-plotting installation. No model, browser or annotation dependency changed. The graph command is `.venv/bin/python 05-analyze/run.py --plots` from `webform-privacy-norms`.
