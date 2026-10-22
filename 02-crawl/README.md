# Crawl the fixed European cohort

This step runs the published TypeScript crawler and exports field evidence for Jev. It uses `01-prepare/data/sites.csv`, with `domain`, `rank`, `categories` as JSON, and `start_url`. Run preparation and compile the crawler first. Sweden is the supplied egress country. Coordinates and timezone describe the browser profile; they do not establish IP location.

Run these commands from the project folder:

```sh
python3 02-crawl/run.py --self-test
python3 02-crawl/run.py --pilot --egress-country Sweden
```

The pilot uses the first 10 domains in the saved cohort. It runs four site processes, caps each at 20 jobs and 600 seconds, and passes `--minJobTime 0`. Loaded-page readiness waits remain. Each of the four workers has a separate browser and extension cache. Workers reuse downloaded extensions between sites; browser profiles stay separate and the wrapper removes temporary profiles after each process exits. The approved original MiniLM-L6-v2 navigation model uses a shared CPU model cache. This is the crawler's navigation scorer, not a form or PI classifier. Preparation should warm the model cache once before four workers start.

Inspect `data/pilot-summary.json` before scaling. Its total storage forecast includes captures, normalized forms, the shared model and worker caches. It reports elapsed time, failures, forms, bytes, a 500-domain forecast and sampled per-site process-tree RSS. RSS is not the Mac's aggregate unified-memory use. Record Activity Monitor's memory use during the pilot as well. Forecasts depend on the pilot's actual coverage and failures. The full run requires a saved pilot below the total storage budget for the same cohort and job cap, plus confirmation that you reviewed its forecast:

```sh
python3 02-crawl/run.py --full --accept-pilot-forecast --egress-country Sweden
```

An atomic lock directory prevents overlapping runs and exports. Ctrl-C stops active process groups, saves interrupted site statuses and keeps partial captures. The wrapper monitors all crawl-step output against a 10 GiB budget. It reserves 64 MiB per active worker for writes already underway and terminates active processes when the stop threshold is reached. The monitor checks every 250 milliseconds between file scans. A single large browser write can exceed the reserve, so the ceiling is a monitored stop condition, not an atomic filesystem quota. If final writes cross it, the script reports `budget_exceeded_bytes`, exits with an error and retains raw evidence for inspection. Check the measured pilot storage forecast before running the cohort. A full run that exceeds the forecast needs a lower job cap or an agreed retention change first.

Storage scans use one metadata read per file and tolerate temporary files disappearing during browser-profile cleanup. At startup, the wrapper recovers newer per-attempt status records saved by workers before an interrupted controller could update `statuses.csv`. This preserves complete-site skipping after a controller failure. A focused fixture covers temporary-file deletion and status recovery without launching a browser.

`--workers`, `--jobs`, `--timeout`, `--budget-gib`, `--timezone`, `--latitude` and `--longitude` override defaults. `--node /absolute/path/to/node` supports the bundled runtime if Node is absent from PATH. Keep the Mac awake and use its direct European connection. No proxy, form filling or submission is added. Explicit HTTP 429 or 503 Retry-After responses stop that site's process; the wrapper does not immediately retry it.

The outputs are:

- `data/captures/<domain>/attempt-0001/` contains raw page HTML, form JSON and job metadata. Routine screenshots are disabled before capture. Raw HTML and form JSON can contain default values and tokens. Keep them local.
- `data/statuses.csv` records outcome, runtime, bytes, jobs, pages, forms, return code and sampled RSS for each attempted domain. A timeout is partial. A zero exit with no saved pages is unreached. Failed attempts remain in their own directories.
- `data/forms.jsonl` contains normalized records for annotation. Form IDs include the domain, job hash and form filename. Group and field IDs include their parent identity. Equal nonempty HTML names share one group, including radio controls. Unnamed controls have separate groups. No raw values or URLs enter this export. A fixed attribute whitelist preserves placeholder, accessibility descriptions, title, autocomplete, input mode and validation constraints. Select option text also survives without option values.
- `data/run-manifest.json` records limits, European profile and declared country. Each capture's `browser-profile.json` records browser and extension versions, capture date and cookie handling.
- `data/pilot-summary.json` or `data/full-summary.json` records measured runtime and output bytes. `data/export-summary.json` counts incomplete or malformed JSON writes that the export skipped. `data/crawler.patch` records the upstream changes.

Normalized controls contain name, label, type, visibility, disabled and read-only states, HTML-required presence, the original ARIA-required value, and separate required/optional text matches. An empty HTML `required` attribute is true. Missing requiredness signals stay unspecified. Contradictory signals remain separate. Stars count only when the form explicitly defines their meaning. Text matching currently recognizes English `required`, `mandatory`, `optional` and `not required`; an English browser profile does not guarantee English page content.

Normalized button text includes only visible, enabled buttons. This filter was corrected during full-run resumption. Re-export after the running crawl finishes so all captures use the corrected normalizer before annotation. Raw captures remain intact.

Rerunning skips complete domains and retries other outcomes with a new attempt directory. The export uses only the status-selected latest attempt for each domain. It retains evidence from that attempt when its outcome is partial. Older raw attempts remain available for local inspection. Analysis must use site status to keep partial coverage separate. Rebuild the export without browsing with `python3 02-crawl/run.py --export`.

Completion means each attempted domain has a status and every saved form has a normalized identity. Full-cohort completion also requires complete statuses for all selected domains. The self-test checks individual visibility, empty boolean attributes, conflicting ARIA evidence, radio grouping, stable identities, raw-value exclusion and screenshot-disabled metadata through a local Playwright page. It performs no live site crawl or model inference.

The local fixture passed after dependency setup. `data/fixture-report.json` records its runtime and checks. The real 10-site pilot ran on 2026-10-09 after historical schema verification and fixed cohort selection. Its measurements are below.

The artifact's Chromium 121 failed to launch on macOS 27 even outside the agent sandbox. A modern installed Chromium browser loaded the same local fixture outside the sandbox. The crawler now pins Playwright 1.64.0 and its bundled Chromium 156.0.8078.4. Browser launches also need permission to run outside the agent sandbox in this session. The updated persistent context uses the bundled `chromium` channel, as required for headless extensions in the [official Playwright instructions](https://playwright.dev/docs/chrome-extensions). Both original Manifest v3 extension workers loaded in the actual context. Cookie extension 1.1.1 stays pinned; the upstream EFF download provided Privacy Badger 2026.9.15. Version changes affect comparability and stay in the crawl manifest.


## Measured pilot, 2026-10-09

## Methodology follow-up from saved captures

The v3 context export is offline and does not run the crawler. `--context-self-test` checks redaction and DOM association; `--context-export` writes `data/methodology-v3/forms.jsonl`. It preserves all 7,953 baseline form records and their identities, controls, eligibility and requiredness. It selected the 773 baseline blocking forms, added bounded headings or explanatory text to 426, and retained 58,673 context characters. Each item is capped at 240 characters and the context at 1,200 characters. Hidden ancestors, controls, options, values, URLs, emails and tokens are removed. The export records local capture provenance outside the outbound request.

The saved extractor cannot recover external CSS visibility and a captured form can still bundle components. These limits remain in the follow-up analysis. No new crawl, cohort or browser workload belongs to v3.

The ten-site run took 847.135 seconds, about 14.1 minutes, with four workers and the agreed 20-job cap. Six domains completed, two timed out with partial captures, one failed after its browser context closed, and one was unreached. The run started 163 jobs, saved 142 pages and exported 118 forms without malformed records. Every attempted domain has a status and a browser profile. All profiles report Chromium 156.0.8078.4, cookie extension 1.1.1, Privacy Badger 2026.9.15, en-US and Europe/Stockholm. Sweden remains the user-declared egress country.

Total crawl-step output was 154,383,168 bytes, about 147 MiB including caches and normalized records. The forecast for 500 domains is 2,757,706,436 bytes, about 2.57 GiB, below the 10 GiB ceiling. There was no storage stop or budget overshoot. The mean site-process duration gives 8.4 hours with four workers continuously busy. Extrapolating the measured pilot wall time gives 11.8 hours. Observed throughput was 42.5 attempted sites per hour and average parallel site-process occupancy was 2.86. These estimates include observed failures and do not promise complete evidence from all 500 sites. The pilot uses the first ten sorted domains of the random cohort, so its coverage and volume may not represent the remaining sites.

Peak sampled RSS for one site process tree was 2,507,259,904 bytes, about 2.34 GiB. Separate system-wide memory_pressure checks showed 31-50 percent free during the run. Timed samples are in data/memory-samples.jsonl. This measures the whole Mac and is not crawler-only RAM or Activity Monitor's memory-use measure. The observations support retaining four workers for the same settings.

Review data/pilot-summary.json, statuses.csv and export-summary.json before a full run. Keep failed and partial domains in the cohort. Their captures can be annotated, but they remain outside the completed matched comparison. The full run subsequently finished; measurements follow.


## Full-cohort measurements, 2026-10-09

All 500 domains have outcomes: 405 complete, 55 partial timeouts, six failed and 34 unreached. The resumed full crawl took 23,933.245 seconds, about 6.65 hours. It saved 7,344 pages and exported 7,953 forms from 407 domains, with no malformed export records. There are 466 reached domains. Failed and partial outcomes remain in the cohort and outside the complete comparison denominator.

Crawl-step storage at completion was 2,728,195,374 bytes, about 2.54 GiB, below 10 GiB with no storage stop. Peak sampled RSS for one site process tree was 4,215,259,136 bytes, about 3.93 GiB. The original pilot and interrupted attempts remain preserved. No crawl is active. `full-summary.json`, `statuses.csv`, `export-summary.json` and `resume-sequence.json` contain the measured records.

The diagnosed external-protocol click issue remains deferred. The completed crawl was left unchanged during diagnosis. Any future crawler fix should guard scheduling and execution before another run.
