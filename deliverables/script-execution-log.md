# Script execution evidence

Public aggregate outputs are in `results/`. Raw captures, prediction records, historical databases and private review packets referenced below are local evidence and are excluded from the repository.

Evidence snapshot: 9 October 2026. This document records the available evidence for the five entry scripts. The presentation documents use the final 261-domain results directly. Earlier processing appears here only to explain execution provenance. No script was rerun to manufacture historical output.

Captured terminal output and structured reports are different evidence types. Command examples below describe interfaces supported by the inspected source, from `webform-privacy-norms`; they are not claimed as verbatim original shell invocations. Where the original command line or stdout is missing, it is unavailable. Durations belong to their named runs, not total project time. Dates stored in source reports retain their recorded timezone.

## 01-prepare

Source: [run.py](../01-prepare/run.py). Supported phases are `setup`, `decompress`, `inspect` and `select`; `download` is also supported but the existing archives were obtained through the browser. Options include `setup --warm-navigation`, database path overrides, `select --count 500 --seed 42`, and `decompress <database> --max-compressed-gib 1 --max-expanded-gib 4`. Original stdout and complete original shell invocations are unavailable.

The saved setup report (`01-prepare/data/setup.json`, local evidence) records successful compilation, Node v22.23.3 on arm64 and 7.381 seconds. This is a warm verification, not the initial install duration. The schema report (`01-prepare/data/schema.json`, local evidence) records inspected table columns, keys, indexes and row counts. The selection manifest (`01-prepare/data/manifest.json`, local evidence) supports 500 unique selected domains from 10,143 eligible domains, with seed 42 and cohort SHA-256 `9a454091daead43902d188da386a2658b0681afc2194dd39ae2224d998bff4dc`. It contains no selection duration. The preparation README reports 2.88 seconds, but the original terminal output for that duration is unavailable.

| Database | Compressed bytes | Expanded bytes | Expansion/check seconds | SQLite check |
| --- | ---: | ---: | ---: | --- |
| domain.db | 29,471,397 | 130,707,456 | 0.337 | ok |
| webform-data.db | 108,756,586 | 690,651,136 | 1.250 | ok |

The local decompression reports support these measurements and saved checksums. No publisher checksum was supplied. Initial installation timing and browser-mirror errors lack captured stdout. The navigation-model report (`01-prepare/data/navigation-model.json`, local evidence) provides saved model-cache measurements; these are not crawl throughput. See the structured excerpts and source checksums (`01-prepare/data/documentation-logs/manifest.json`, local evidence).

## 02-crawl

Source: [run.py](../02-crawl/run.py). Supported full-cohort command shape is `.venv/bin/python 02-crawl/run.py --full --accept-pilot-forecast --egress-country Sweden`, with defaults of four workers, twenty jobs, a 600-second timeout and a 10 GiB output cap. `--pilot`, `--export`, `--context-export` and fixture branches are separate. This supported command shape is not a recovered shell transcript.

full-run.log (`02-crawl/data/full-run.log`, local evidence) is actual captured terminal output. Its final aggregate excerpt (`02-crawl/data/documentation-logs/full-run-terminal.txt`, local evidence) contains 500 attempted domains, 405 complete, 55 partial timeouts, six failed and 34 unreached. It records 7,344 pages, 8,134 started jobs, 7,953 exported forms, 23,933.245 seconds and 2,728,191,749 output bytes. The elapsed time belongs to the resumed full-run controller, not every prior attempt. `failures: 95` includes all noncomplete outcomes, not only the six failed statuses. No storage stop or budget excess occurred. The structured full summary (`02-crawl/data/full-summary.json`, local evidence) agrees with the excerpt.

resume-sequence.log (`02-crawl/data/resume-sequence.log`, local evidence), line 3, contains the captured export result Exported 7953 forms (`02-crawl/data/documentation-logs/export-terminal.txt`, local evidence). The saved export summary reports zero skipped incomplete or invalid records. Original standalone pilot stdout is unavailable; pilot-summary.json (`02-crawl/data/pilot-summary.json`, local evidence) records its measurements separately.

The initial continuation attempt stopped while looking for the not-yet-written full summary. The later continuation stopped after unresolved annotation requests, then records completed recovery. These warnings are supported by `resume-sequence-attempt-0001.log`, `resume-sequence.log` and resume-sequence.json (`02-crawl/data/resume-sequence.json`, local evidence). Their tracebacks are omitted from publishable excerpts because local paths are unnecessary. This is execution provenance, not another experiment.

The saved-context export used existing captures and did not crawl. Its context summary (`02-crawl/data/methodology-v3/context-export-summary.json`, local evidence) and verification reports are structured evidence, not captured stdout. Per-domain status files, raw browser logs and captures remain local. Extraction manifest (`02-crawl/data/documentation-logs/manifest.json`, local evidence).

## 03-annotate

Source: [run.py](../03-annotate/run.py). Default execution annotates current forms and can make paid requests. `--forecast` reads existing evidence without inference. The final selective protocol requires `--input`, `--output` and `--selection-manifest` pointing to the separate methodology-v3 files. `--limit` bounds new records rather than unique paid requests; `--budget` constrains the same shared ledger. Complete original shell invocations are unavailable.

The captured full-batch summary (`03-annotate/data/documentation-logs/annotation-terminal.txt`, local evidence) comes verbatim from line 6 of the continuation log. It records 3,092.702 seconds and three batch failures before recovery. The final original predictions.summary.json (`03-annotate/data/predictions.summary.json`, local evidence) is a structured summary of a later two-record, zero-failure batch lasting 1.746 seconds. Its cumulative ledger values are 11,120 measured attempts, 14,490,629 input tokens, $0.608606418 measured cost and $0.005376 reserved for two uncertain-billing attempts. Neither summary is total annotation runtime. Older identity records remain in the append-only history.

Final selective reannotation has structured pilot (`03-annotate/data/methodology-v3/pilot-summary.json`, local evidence) and remaining-batch (`03-annotate/data/methodology-v3/predictions.summary.json`, local evidence) summaries. Original stdout for these runs is unavailable.

| Batch | New identity records | Cache-hit records | Measured requests added | Seconds | Measured cost added |
| --- | ---: | ---: | ---: | ---: | ---: |
| Selective pilot | 47 | 1 | 46 | 13.692 | $0.003062472 |
| Remaining selection | 971 | 311 | 659 | 185.751 | $0.046918830 |
| Both | 1,018 | 312 | 705 | Not a total project duration | $0.049981302 |

Request deltas and costs above are calculated from the cumulative summary values, not recovered terminal counters. The selection has 706 distinct request keys; one oversized record remained unpaid review. Final origins are 42,074 carried-forward and 1,018 reassessed records, totaling 43,092 current identities. Among reassessed records, 521 are accepted and 497 remain review. The two final batches added no failures or reservations. The later batch's `budget_cap_usd: 0.8` is its tighter ledger cap, not a reset of the original $4.90 working allowance.

Cumulative measured cost is $0.658587720 plus unchanged reservations of $0.005376, totaling $0.663963720. Remaining allowance below $4.90 is $4.236036280. No paid work remains authorized by this documentation task. Extracted structured summaries and checksums (`03-annotate/data/documentation-logs/manifest.json`, local evidence).

## 04-validate

Source: [run.py](../04-validate/run.py). `export --output <separate-folder>` creates blinded questions; `evaluate --review <csv> --freeze <json> --output <folder>` evaluates supplied labels. `--forms` and `--predictions` select the evidence. The default branch is export and may overwrite review outputs, so it was not run here. Original stdout, original complete command lines and original evaluation durations are unavailable.

The random metrics (`04-validate/data/human-examination/random-results/metrics.json`, local evidence) support twenty labeled forms and twenty labeled groups, with exact agreement of 17/20 and 16/20. The targeted metrics (`04-validate/data/human-examination/targeted-results/metrics.json`, local evidence) separately support five form and five group questions, with agreement of 5/5 and 1/5. These targeted uncertainty cases are not random accuracy estimates. Requiredness checks cover twenty random and seven targeted controls with zero disagreements.

The answer check (`04-validate/data/human-examination/answer-check.json`, local evidence) records fifty current-signature matches, all answers confirmed, and preservation of the original packet. The audit report (`04-validate/data/human-examination/audit-results.md`, local evidence) retains the single-reviewer. Question-level answers were not extracted into documentation logs.

The fresh packet manifest (`04-validate/data/methodology-v3/fresh-heldout/manifest.json`, local evidence) has twelve forms, sixteen groups and twelve reserved domains; human-label fields remain blank. Prepaid verification and pilot diagnostic judgment are structured diagnostic reports, not independent human labels or stdout. The existing audit does not validate the final protocol. Aggregate-only excerpts and checksums (`04-validate/data/documentation-logs/manifest.json`, local evidence).

## 05-analyze

Source: [run.py](../05-analyze/run.py). Default analysis writes the original output folder. The final hybrid branch requires explicit `--forms`, `--predictions`, `--followup-manifest` and separate `--output` arguments; baseline options select the preserved original evidence. `--plots --output <analysis-folder>` plots saved results. Original standalone final-analysis and plotting stdout are unavailable.

The captured completion event (`05-analyze/data/documentation-logs/continuation-terminal.txt`, local evidence) is a continuation-wrapper event containing the original analysis result, not standalone stdout from run.py. Earlier results remain preserved in the default output directory. The final structured [counts](../results/summary.json) record 6.294 seconds, 500 selected/attempted domains, 405 complete, 261 comparison domains, 7,953 forms, 3,316 fully annotated forms, 7,478 comparison-resolved forms and zero unjoined identities. Form coverage counts include all exported outcomes; they are not domain denominators.

The [follow-up summary](../results/summary.json) records lineage and the distinct sensitivity set. Historical/new rates in `rates.csv` use exactly 261 domains. `baseline-followup-rates.csv` uses the identical 187 retained original domains for both protocols, with equal overall contact counts of 74 email, 44 name, nineteen phone and one address. It is not the historical/new comparison. Seventy-four domains newly qualify and `helpnetsecurity.com` is excluded. This provenance stays separate from the audience narrative.

The final figure manifest (`05-analyze/data/methodology-v3/final/figures/manifest.json`, local evidence) records 6.638 seconds, 261 matched domains and 500 selected-context domains. It supports six PNG/PDF pairs and the combined PDF. No new analysis or plots were generated for this documentation task. Extracted structured evidence and checksums (`05-analyze/data/documentation-logs/manifest.json`, local evidence).

## Extraction record

Each step's `data/documentation-logs/manifest.json` identifies source paths, source SHA-256, extraction criteria, evidence type, output path and output SHA-256. Terminal excerpts retain exact selected text. Structured excerpts use explicit field whitelists and reserialize JSON; they are not transcripts. Review answers, raw form values, payloads, credentials, recipient addresses and capture URLs are omitted. Missing stdout remains unavailable. New documentation checks verify links, source function names, aggregate claims and preserved inputs; they do not establish annotation accuracy.
