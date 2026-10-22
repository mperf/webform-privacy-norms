# Code and file structure

Public aggregate outputs are in `results/`. Raw captures, prediction records, historical databases and private review packets referenced below are local evidence and are excluded from the repository.

This guide describes the inspected source as of 9 October 2026. The [technical report](technical-report.md) presents the final experiment; [execution evidence](script-execution-log.md) identifies saved logs and reports. Each numbered step has one entry script and one README. Saved snapshots such as `baseline-run.py` are provenance copies, not additional pipeline entry points.

## Folder map

The tree shows selected existing paths. Raw captures, environments, databases, caches and generated outputs are local data. Documentation excerpts are in each step's `data/documentation-logs/`.

```text
webform-privacy-norms/
  HANDOFF.md
  .venv/                              Python runtime
  .browsers/                          installed Playwright browsers
  upstream/                           pinned authors' artifact
    crawler/src/                      TypeScript crawler
    crawler/build/                    compiled JavaScript
    form-type-classification/         source purpose taxonomy
    pi-type-classification/            source PI taxonomy
  01-prepare/
    README.md
    run.py
    data/                             archives, read-only DBs, schema, sites, manifest
  02-crawl/
    README.md
    run.py
    data/
      crawler.patch                   saved upstream changes
      captures/                       domain/attempt/job raw evidence
      browser-cache/                  worker extension caches
      navigation-model-cache/         shared CPU navigation model
      statuses.csv                    selected attempt and outcome per domain
      forms.jsonl                     normalized base capture universe
      methodology-v3/                 enriched saved-capture export and checks
      documentation-logs/             selected execution evidence
  03-annotate/
    README.md
    run.py
    data/
      predictions.jsonl               original append-only annotations
      budget.jsonl                    shared original and selective request ledger
      methodology-v3/                 frozen selection, separate predictions, summaries
      documentation-logs/
  04-validate/
    README.md
    run.py
    data/
      review.csv                      original blinded pilot packet
      human-examination/              confirmed audit and separate metrics
      exclusion-diagnosis/            development diagnosis
      methodology-v3/                 checks, baseline preservation, fresh-heldout packet
      documentation-logs/
  05-analyze/
    README.md
    run.py
    data/
      results.db                      original derived results
      counts.json                     original coverage
      rates.csv                       original domain rates
      requiredness.csv                new-crawl control declarations
      figures/                        original plots
      methodology-v3/
        pilot/                        separate pilot analysis
        final/                        final 261-domain comparison and figures
      documentation-logs/
  deliverables/                       report, explanation, video and implementation docs
```

## Data flow and boundaries

Preparation freezes `sites.csv` and its manifest. Crawling reads that cohort, saves raw attempts, selects attempts in `statuses.csv` and exports `forms.jsonl`. Annotation converts descriptions into sanitized requests and appends prediction/review records. Validation creates blinded packets and evaluates supplied human labels. Analysis reads captures, statuses, historical annotations and prediction records, then writes its own result database and aggregate CSVs. Human review metrics do not automatically replace model predictions.

Capture keys join records within one dataset. A form ID hashes domain, job hash and filename; group IDs add the HTML name or unnamed-control index. Field IDs also add control index. Equal nonempty HTML names share a group. These identities do not match individual forms across years. Request cache keys are different: they represent sanitized evidence and annotation configuration, so the same capture ID cannot justify reuse after its descriptions change.

## 01-prepare/run.py

[Source](../01-prepare/run.py), [README](../01-prepare/README.md).

Defaults are 500 selected domains, seed 42, pinned upstream commit `a4f391d604e5cd557b881145b2a1cfd072e542d0` and a 10 GiB crawl reserve. `ROOT`, `DATA` and `UPSTREAM` resolve from the script path, so data lookup does not depend on the shell's directory.

| Functions | Responsibility |
| --- | --- |
| `connect`, `schemas`, `require`, `inspect` | Open historical SQLite references read-only, inspect actual schemas, enforce required columns and write schema evidence. |
| `eligible`, `category_names`, `select` | Join historical form/field labels with domain metadata, reject invalid inputs, recover category names and freeze a deterministic sample with checksums. Identical reruns reuse the cohort; differing output is rejected. |
| `setup`, `apply_crawler_patch` | Build the small Python environment, verify the upstream commit, apply the saved patch if needed, install browser/npm dependencies and compile. |
| `warm_navigation` | Optionally load and benchmark the original CPU navigation scorer with bounded download/time limits. |
| `download`, `decompress` | Bound archive and expanded sizes, preserve disk reserve, check SQLite integrity and hashes, and make expanded references read-only. `decompress` uses existing local archives and can verify/reuse matching output. |
| `self_test` | Exercise synthetic database selection and archive handling in temporary files. |

CLI branches are `setup`, `download`, `decompress`, `inspect`, `select` and `--self-test`. No subcommand displays help. `inspect` accepts `--domain-db`, `--annotation-db`, `--output`; `select` adds `--count` and `--seed`. Setup accepts `--skip-compile` and `--warm-navigation`. Download requires a URL; decompress accepts a local archive override. Both accept checksums and byte caps. Source defaults of 8 GiB compressed and 24 GiB expanded are configurable limits; the saved local decompression used 1/4 GiB caps.

Inputs are the pinned source, saved patch and historical database archives or expanded databases. Outputs include `.venv`, `.browsers`, the compiled crawler, `setup.json`, decompression reports, `schema.json`, `sites.csv` and `manifest.json`. The cohort and manifest are the input contract for the remaining steps.

## 02-crawl/run.py

[Source](../02-crawl/run.py), [README](../02-crawl/README.md).

`SETTINGS` defaults to four workers, twenty jobs per site, 600 seconds, 10 GiB, `en-US`, `Europe/Stockholm`, Stockholm coordinates and declared Sweden egress. CLI overrides cover workers, jobs, timeout, budget, node path, timezone, coordinates and country. Locale comes from `SETTINGS`.

| Functions/classes | Responsibility |
| --- | --- |
| `main`, `main_inner` | Parse branches, enforce full-run pilot/cohort/depth checks, own the crawl/export lock and coordinate workers and storage limits. Complete sites are skipped; other outcomes get new attempts. |
| `run_site`, `stop_process`, `resident_bytes` | Launch compiled upstream JavaScript for one site, record stdout/stderr per attempt, sample process-tree RSS, handle timeouts and terminate process groups. |
| `write_status`, `recover_statuses`, `counts`, `byte_count` | Persist attempt outcomes, recover worker records after interruption, count saved evidence and monitor output storage. |
| `identity`, `normalize`, `export` | Create stable capture identities and normalize fields from the status-selected attempt, preserving partial evidence and omitting raw control values and URLs from the base export. Visible enabled button text only. |
| `ContextDOM`, `dom_nodes`, `safe_node_text`, `context_secrets`, `sanitize_context`, `saved_context` | Inspect locally saved HTML, locate bounded descriptive form context and remove prohibited strings and secret candidates. |
| `default_context_selection`, `export_context` | Select blocking saved forms by default and write a separate enriched context export without browsing. |
| `self_test`, `storage_self_test`, `context_self_test` | Check browser extraction, storage/status behavior and offline saved-context privacy rules. |

`--pilot` selects the first ten sorted cohort domains; `--full --accept-pilot-forecast` selects the fixed cohort after saved forecast checks. `--export` rebuilds normalized evidence without browsing. `--context-export` writes the separate enriched export; `--context-selection` supplies explicit form IDs. `--context-self-test` is offline. `--self-test` includes a local browser fixture. Running without an explicit pilot/full or alternative branch is an error.

`run_site` invokes `upstream/crawler/build/crawler.js` with a separate attempt directory, starting URL, max-job count, zero deliberate minimum job delay, disabled screenshots and the browser profile. Worker caches remain separate, while `WEBFORM_MODEL_CACHE` selects a shared CPU navigation cache. Raw per-attempt stdout/stderr lives beside the attempt directories and can contain URLs, so it is not copied to presentation docs.

The upstream crawler.ts (`upstream/crawler/src/crawler.ts`, local evidence), page-functions.ts (`upstream/crawler/src/page-functions.ts`, local evidence), reward.ts (`upstream/crawler/src/reward.ts`, local evidence), types.ts (`upstream/crawler/src/types.ts`, local evidence) and utils.ts (`upstream/crawler/src/utils.ts`, local evidence) remain the crawling foundation. The [saved patch](../02-crawl/data/crawler.patch) records browser compatibility, profile, visibility, requiredness, screenshot and navigation-cache changes. Preparation applies the patch before install/compile. An external-protocol/mailto guard discussed in diagnosis remains unapplied.

Inputs are `sites.csv`, compiled upstream crawler, installed browser and model/extension caches. Outputs are raw attempt captures/logs, `statuses.csv`, browser profiles, run summaries and normalized JSONL. Base normalized controls preserve whitelisted descriptive attributes and separate requiredness signals; annotation sanitizes the descriptions again before any transfer. The saved-context branch writes `data/methodology-v3/forms.jsonl` and its context reports, preserving the base export and controls.

## 03-annotate/run.py

[Source](../03-annotate/run.py), [README](../03-annotate/README.md).

The model is pinned to `jev-1.13.0`. Default prompt version is `europe-500-v2`. `configure_v3` explicitly selects the frozen revised coding definitions. Constants set the PI threshold to 0.5, review margin to 0.1, purpose gate to 0.6, three attempts, 60-second request timeout, 64,000 maximum input-token reservation and $4.90 working cap. The endpoint and pricing used in saved accounting are explicit source constants.

| Functions/classes | Responsibility |
| --- | --- |
| `source_labels`, `taxonomies` | Parse source label literals through Python AST without importing the authors' ML environments. Verify ten purposes and nineteen PI classes. |
| `load_key`, `clean_text`, `sanitized_controls`, `eligible_group`, `tasks` | Load credentials locally, sanitize descriptive evidence, filter technical/non-user controls and build form/group questions. |
| `canonical`, `cache_key` | Serialize consistently and hash request evidence plus model, definitions, prompt version and confidence settings. |
| `configure_v3`, `freeze_followup`, `validate_selection`, `selected_task` | Freeze and validate explicit replacement identities, hashes and configuration; reject baseline-output replacement and out-of-manifest selection. |
| `Budget`, `request`, `call_with_budget`, `budget_metrics` | Check account access, reserve each attempt in the shared ledger, make bounded requests and retain unresolved billing reservations. |
| `probability`, `parse_response` | Validate returned model/labels/probabilities and assign accepted, review or failure states. Unknown remains review despite auxiliary explanations. |
| `read_jsonl`, `repair_jsonl_tail`, `append`, `annotate` | Resume append-only records under the ledger lock, repair only an interrupted final JSONL tail, reuse compatible cache entries and save per-batch summaries. |
| `forecast`, `mock_response`, `self_test` | Estimate outstanding requests from current saved inputs or exercise synthetic responses in separate fixture outputs. |

Default execution can spend money. `--check-access` checks the account without inference; `--forecast` estimates current input without inference; `--freeze-followup` creates a selection without inference. `--mock` requires separate prediction output and does not produce experiment labels. Main options are `--input`, `--output`, `--limit`, `--threshold`, `--budget` and `--selection-manifest`.

Selected reannotation uses a separate output file and a validated manifest. Every real branch retains the same `03-annotate/data/budget.jsonl` and lock. Compatible duplicates reuse answers. New evidence for a previously completed identity becomes review unless it is part of the separately authorized selection workflow. Requests over the 24,000-byte compact-context limit remain unpaid review. `--limit` counts new identity records, which can include cache hits and unpaid review records.

Inputs are normalized JSONL, upstream taxonomies, optional frozen selection and existing prediction/cache history. Outputs are append-only predictions, per-batch summaries, forecasts and ledger events. Analysis receives status/probabilities/labels and request hashes, rather than treating all record presence as accepted annotation.

## 04-validate/run.py

[Source](../04-validate/run.py), [README](../04-validate/README.md).

Defaults are seed 42, up to 100 forms and 300 eligible groups, with a 25% development-domain target. These defaults describe the generic export, not the completed 20/20 random audit or fresh 12/16 packet.

| Functions | Responsibility |
| --- | --- |
| `annotation_module`, `signatures` | Load the annotation definitions and hash sanitized form/group contexts for duplicate separation. |
| `export` | Union domain components sharing exact request signatures, allocate development/evaluation components and export blinded questions with blank human fields. |
| `evaluate` | Require a dated configuration freeze, prevent duplicate leakage and mock predictions, verify labels/signatures/configuration and calculate per-class metrics, exact-set agreement, coverage and requiredness checks. |
| `read_jsonl`, `self_test` | Read saved records and test duplicate splitting, freeze constraints and metric behavior with synthetic evidence. |

CLI choices are `export` and `evaluate`, with export as the default. Options select `--forms`, `--predictions`, `--review`, `--freeze` and `--output`. `--self-test` is separate. Export writes `review.csv` and `manifest.json`; evaluate writes `metrics.json`. Exports can overwrite a packet at the selected destination, so preserve existing review outputs and use separate directories.

Human labels are inputs, never generated ground truth. Evaluation does not change predictions, gates or analysis inclusion. The human-examination folder holds the completed audit's imported labels and separate random/targeted metrics. Methodology-v3 holds diagnostic checks and a fresh held-out packet with blank human fields. Saved bespoke packet/provenance files are evidence artifacts; this script's default export does not recreate all of them.

## 05-analyze/run.py

[Source](../05-analyze/run.py), [README](../05-analyze/README.md).

`SETTINGS['identifying_pi']` contains eight types used for upstream-style form eligibility. `PAPER_TYPES` retains sixteen rate-export types. Figure constants select categories, purposes and nine rare types. Historical references are read-only; derived results have their own database.

| Functions | Responsibility |
| --- | --- |
| `taxonomy`, `categories`, `historical` | Read source taxonomies, map reused historical categories and join historical form/field annotations with composite keys. |
| `load_annotation`, `build_database` | Use shared group eligibility, validate capture identities and request keys, reject live mock predictions and create form/field classification, field evidence and annotation-state tables. |
| `request_keys`, `hybrid_predictions` | Verify each carried-forward/replacement annotation against frozen evidence and configuration; require identical base controls and capture universe. |
| `aggregate`, `rate_rows`, `requiredness` | Union domain PI, calculate conditional rates and classify separate requiredness declarations. |
| `database_records`, `coverage_summary`, `write_followup_comparison` | Read preserved original results, summarize blockers, write the retained-domain sensitivity comparison and record final domain set and identity lineage. |
| `analyze`, `write_csv` | Check cohort/status/capture consistency, choose complete resolved domains and write result databases, rates, differences, requiredness and counts. |
| `plot_figures` | Read saved analysis, apply paper-style support/display rules, verify count agreement and create PNGs, PDFs, cell CSV and a plotting manifest. |
| `pipeline_self_test`, `hybrid_self_test`, `self_test` | Exercise synthetic aggregation and validated hybrid joins, including incomplete and complete zero-form sites. |

No flag runs analysis with original default inputs/output. `--plots` reads the selected analysis folder and writes figures there. `--self-test` uses fixtures. Input overrides include `--sites`, `--statuses`, `--forms`, `--predictions`, `--historical` and `--output`. `--followup-manifest` enables hybrid validation; `--baseline-annotation`, `--baseline-forms`, `--baseline-predictions` and `--baseline-results` identify the preserved original evidence. `--allow-mock` is for separate fixture output only. Hybrid analysis rejects the original default output destination.

`build_database` retains known group PI independently of purpose uncertainty. Unresolved PI has NULL `field_list`; Unknown purpose does not erase known PI. Fully annotated forms require accepted purpose and all eligible groups. Comparison-resolved forms require accepted groups and accepted purpose only if identifying PI occurs. A complete domain with no captured forms can therefore support observed zero, while partial domains remain excluded. The SQL result keys mirror the historical composite joins.

Final outputs live in `05-analyze/data/methodology-v3/final/`: `results.db`, `counts.json`, `rates.csv`, `differences.csv`, `requiredness.csv`, `compared-domains.json`, `followup-summary.json`, `lineage.jsonl`, `baseline-followup-rates.csv` and `figures/`. The main historical/new comparison uses 261 domains. The separate retained-original sensitivity table uses 187 domains for both protocols. Pilot and original output directories remain separate.

## Inspecting or regenerating final outputs

For demonstrations, read existing JSON/CSV/PNG/PDF files. The [video guide](video-walkthrough-guide.md) supplies read-only commands. The following command shapes document the final branch from `webform-privacy-norms`; they were not executed for this documentation task and overwrite derived outputs in the chosen final folder.

```sh
.venv/bin/python 05-analyze/run.py \
  --forms 02-crawl/data/methodology-v3/forms.jsonl \
  --predictions 03-annotate/data/methodology-v3/predictions.jsonl \
  --followup-manifest 03-annotate/data/methodology-v3/selection.json \
  --output 05-analyze/data/methodology-v3/final

.venv/bin/python 05-analyze/run.py --plots \
  --output 05-analyze/data/methodology-v3/final
```

Historical references, the fixed cohort, raw attempts, original predictions, private reviews and shared budget ledger remain preserved. Changes to a frozen source or input invalidate the selective manifest; documentation changes do not change those inputs. Source checksums for the inspected entry scripts are recorded in documentation verification (`deliverables/documentation-verification.json`, local evidence).
