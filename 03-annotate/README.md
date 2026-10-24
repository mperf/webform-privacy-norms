# Annotate the new forms

`run.py` sends compact evidence from `../02-crawl/data/forms.jsonl` to TypeSafe AI. It uses the pinned `jev-1.13.0` model. One Choice question classifies each form. Nineteen independent Noul questions classify each eligible field group. The script reads the exact historical labels from the pinned upstream Python literals without importing the original machine-learning packages.

Run these commands from `webform-privacy-norms`:

```sh
python3 03-annotate/run.py --self-test
python3 03-annotate/run.py --check-access
python3 03-annotate/run.py --limit 100
python3 03-annotate/run.py --forecast
python3 03-annotate/run.py
```

The limited command annotates at most 100 new identities, including forms and groups. Use it for a pilot after the historical databases and crawl inputs are ready. Check measured usage and forecast the remaining cost before the full command. The ten-site pilot measurements are recorded below.

The key loader first reads `TYPESAFE_API_KEY` from the runtime environment, then checks `.env` in this folder's parent and the PET project folder. It accepts single or double quoted values. `--check-access` makes only `GET /v1/models` and reports whether access succeeds. It never prints the key or the server body. This check does not establish account balance, purchase requirements, or a gateway surcharge. The direct official endpoint has the published model price described below.

## Evidence and decisions

Requests contain title, button text, names, labels, input types, requiredness attributes, safe descriptive attributes, and option text. The attribute whitelist is `placeholder`, `aria-label`, `aria-description`, `title`, `autocomplete`, `inputmode`, `pattern`, `min`, `max`, and `step`. The sanitizer removes URL and query text, named tokens, bearer credentials, UUIDs, and long opaque strings. It never includes attribute values outside this whitelist or option values. They contain no control values, URLs, capture identifiers, or raw HTML. The crawler must supply the documented sanitized export. Annotation drops hidden, invisible, disabled, and read-only controls, plus submit, reset, and button controls. A group with no eligible controls receives a review state without an API request. Radio controls retain their shared group identity.

The resumed full run also redacts schemeless, protocol-relative and relative URLs. Capture normalization excludes invisible and disabled buttons. If these corrections change the payload of an already completed identity, annotation preserves its earlier record and appends an explicit human-review record without another paid request. An exact matching cached payload can still be reused. These review records do not populate the cross-identity inference cache. The forecast reports them separately as `context_changed_review_identities`; they are excluded from remaining paid requests. Question definitions and thresholds remain unchanged.

The initial PI threshold is 0.5. A probability within 0.1 of that threshold marks the entire group for review. Several PI labels may be present. An empty label list is confident absence only when the status is `ok`. A failure or review state never counts as confirmed absence. Form predictions below confidence 0.6 or with an Unknown choice become `review` and use the Unknown label. These thresholds must be frozen after development validation and before held-out evaluation. `--threshold` changes the PI threshold and the cache key.

The nineteen historical PI classes include broader names than the paper's narrower presentation categories. This script preserves the source taxonomy for comparison. It does not create a class for every kind of personal information. For example, the source has no payment-card class. Taxonomy coverage and review states must remain visible in the final analysis.

## Outputs, cost, and resumption

`data/predictions.jsonl` has one record per form or group identity, with capture keys, labels, status, probabilities, uncertainty, threshold, prompt version, returned model, usage, and cost. Repeated contexts reuse successful or review predictions. The cache hashes the entire sanitized payload, all question definitions, model, prompt version, and thresholds. Different identities can reuse identical requests. Every identity still gets its own output record. Failed records can be retried on a later run. Under the annotation lock, resumption removes a malformed final line only when the interrupted append has no terminating newline. It adds a newline to a complete final JSON record that lacks one. Corruption in a newline-terminated record stops the run. A lost measured ledger append keeps the preceding full reservation. A partially written reservation cannot have preceded a transmitted request because the script flushes and syncs the reservation first. Read-only forecasts do not repair files and report malformed input as an error. Consumers should retain the latest record for each identity and prompt configuration.

`data/budget.jsonl` records each paid attempt before transmission. At the published $0.042 per million input tokens, each attempt reserves the worst-case 64,000-token input cost of $0.002688. Returned usage replaces that reservation with measured cost. Timeouts, failed attempts, and interrupted requests retain their full reservations. Retries consume the same ledger. The script stops if the next reservation would exceed $4.90, preserving ten cents below the $5 budget ceiling. `--budget` can lower that limit. A file lock prevents concurrent annotation runs from spending against stale ledger state. Keep the ledger when resuming or changing output paths. Never clear it to restart the spending allowance.

Calls run sequentially with a 60-second HTTP timeout and at most three attempts. Retryable HTTP errors and transport failures use short backoff. The script honors `Retry-After`. Authentication failure stops the batch. Rejected requests retain reservations because their billing outcome is unknown. The summary reports elapsed seconds, new records, cache hits, failures, measured input tokens, measured attempt count and cost, and unresolved attempt count and reserved cost. It writes the same data to `data/predictions.summary.json`. Counts and tokens come from the paid-attempt ledger, so cache hits and mock responses never increase billed totals. Individual cache hits have zero incremental cost, while copied usage describes the original inference.

`--forecast` reads the capture input, predictions, and ledger without calling the API. It counts unique sanitized requests still needed, measures mean input tokens from original pilot responses, and estimates remaining cost and sequential request time. It uses the observed ratio of total to measured attempts to account for unresolved calls. It also reports the worst-case reservation for three attempts per remaining unique request. With no measured pilot responses, the estimate is pending. The forecast covers the supplied captures only. A ten-site crawl cannot predict how many forms will appear on the remaining 490 sites, so the crawl pilot must provide that separate estimate before scaling. Real forecasts ignore mock records. Mock forecasts require `--mock` and remain marked as mock.

Completion means that every eligible form and group has a valid record or an explicit failure/review state. A resumed run should write no duplicate completed identities. Review coverage and failures still need reporting and manual validation.

## Fixture checks and current status

The self-test checks source taxonomy sizes, safe attributes and options, value/token/UUID/opaque-text removal, identity mapping, multiple PI labels, response probabilities, context-sensitive cache keys, persistent budget reservations, and interrupted append recovery. A mocked two-form fixture produced four records with two cache hits in 0.001 seconds. A second run produced no new records. These figures measure fixture execution only, not live API throughput. The read-only account access check passed before the paid pilot. Its measurements are below.

For a mock smoke run, use a separate output file so mock predictions cannot enter the live dataset:

```sh
python3 03-annotate/run.py --mock --input /tmp/forms-fixture.jsonl --output /tmp/mock-predictions.jsonl
```

Official sources checked on 2026-10-09 are the [HTTP quick start](https://docs.typesafe.ai/introduction/quickstart), [models and input-token price](https://docs.typesafe.ai/models), and [Jev 1.13 failure modes](https://docs.typesafe.ai/model-jaggedness/jev-1.13). The HTTP response uses `answers`, Choice `choice` and `probabilities`, numeric Noul `noul`, returned `model`, and `usage.input_tokens`. The model supports 64,000 input tokens per request. Small states and precise questions follow the documented guidance for literal reading and irrelevant context.


## Measured pilot, 2026-10-09

The ten-site captures contain 118 forms and 807 field groups, of which 138 groups have eligible visible user controls. All 925 identities have records. The 669 groups with no visible user controls have a review state and made no request. Deduplication reduced 256 eligible identities to 203 unique paid requests, with 53 cache hits. Every returned model is jev-1.13.0. There were no API failures, retries or unresolved budget reservations, and the read-only forecast finds zero remaining requests for the current pilot.

The initial 100-identity batch took 10.588 seconds and the remaining 825 identities took 44.207 seconds. Together they used 260,426 billed input tokens and cost $0.010937892 under the published $0.042 per million input tokens. Average input was 1,282.9 tokens per unique request, observed throughput was 3.70 unique requests per second, and mean request time was 0.269 seconds. The shared ledger retains $4.889062108 of its $4.90 working cap. It has not been cleared or restarted.

Linear extrapolation from ten attempted sites gives 10,150 unique requests, about $0.55 total API cost and 45.4 minutes of sequential request time for 500 sites. data/pilot-forecast.json records this estimate and its assumptions. Failure rates, partial coverage, context sizes and cross-domain reuse may differ for the remaining sites. The independent ledger still enforces the original $5 total spending ceiling. The forecast covers the same crawl depth; it is not a guarantee of annotation quality or complete coverage.

Form predictions include 37 ok and 81 review records. Eligible group predictions include 129 ok and 9 review records. The other 669 group review records represent excluded invisible, hidden, disabled, read-only or button controls. Review is not confirmed absence of PI. The blinded pilot sample needs human labels before prompts or thresholds are tuned, and held-out validation remains pending.

`data/request-preview.json` preserves the sanitized request preview for the initial 100 identities.


## Methodology follow-up, 2026-10-09

The default v2 annotation path and original `data/predictions.jsonl` remain unchanged. The frozen v3 path uses `data/methodology-v3/selection.json`, the saved enriched forms at `02-crawl/data/methodology-v3/forms.jsonl`, and the separate `data/methodology-v3/predictions.jsonl`. It records returned choices, returned confidence, effective labels and auxiliary uncertainty reasons separately. A manifest-scoped selection prevents a default run from reannotating the full 43,092-identity universe.

The paid follow-up completed 1,018 selected identities and 706 unique requests. It measured $0.658587720 cumulatively, with $0.005376 in the two original unresolved reservations and no new unresolved reservation. It retained the 0.5 PI threshold, 0.1 review margin, 0.6 purpose gate and exact endpoint review behavior. These results describe coverage and diagnostic model behavior, not validated accuracy.

## Full-cohort annotation, 2026-10-09

All 43,092 current identities have records: 7,953 forms and 35,139 groups. Forms have 3,462 ok and 4,491 review states. Groups have 9,096 ok and 26,043 review states; 25,212 groups have no eligible user controls and required no request. There are 160 changed-evidence review identities and one oversized context marked for manual review. Current identities have no API failures awaiting retry and the final forecast has zero remaining requests.

The full batch took 3,092.702 seconds. It left two HTTP 520 failures and an oversized request. The two failed requests succeeded in a 1.746-second resumed batch. Oversized requests now finish as explicit review without transmission; their fixture checks no spending and no repeat attempt. The original oversized failure remains in the append-only history.

The cumulative ledger has 11,120 measured attempts, 14,490,629 input tokens and $0.608606418 measured cost. Two earlier failed calls retain $0.005376 in reservations, for $0.613982418 measured plus reserved. These reservations remain because billing for those failed calls is unknown. The shared cap is unchanged. The latest summary describes the two-request resumed batch with cumulative ledger metrics; the prior full-batch summary remains in `02-crawl/data/resume-sequence.log`.

Human validation is pending. Review states remain unknown evidence and cannot establish absent PI.
