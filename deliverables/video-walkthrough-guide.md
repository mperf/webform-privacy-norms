# Video walkthrough guide

Use the final 261-domain comparison throughout the recording. The [technical report](technical-report.md) is the factual reference. Present the completed method and results directly; the [execution evidence](script-execution-log.md) and [code structure](code-structure.md) hold implementation and processing provenance.

The twelve-minute sequence below is a recording suggestion. The supplied assignment requires a short screen recording uploaded to Canvas or provided by a link, for example YouTube. It gives no exact duration. For the thorough walkthrough, showing code changes and their results is required. Keep aggregate figures and tables on screen. Raw captures, field values, credentials, recipient URLs, private review answers and prediction records are unnecessary for the demonstration.

## Recording sequence

| Time | Narration | Show |
| --- | --- | --- |
| 0:00 to 1:00 | Introduce the paper's question: what information do web forms request, and how does that vary by website category and form purpose? Explain that common patterns provide an empirical baseline, while frequency alone does not establish necessity or acceptability. | Report [motivation](technical-report.md#motivation-and-research-questions) and the local paper's title. |
| 1:00 to 2:00 | Explain what we reproduced and reused. We ran the original TypeScript crawler with documented patches and adapted domain aggregation and paper-style graphs. Historical labels and categories came from the released databases. We did not retrain the authors' classifiers or reproduce privacy-policy analysis. | Report [artifact scope](technical-report.md#original-paper-and-artifact-reproduction). |
| 2:00 to 3:00 | State the fixed 500-domain sample from 10,143 eligible historical domains, seed 42. Sites are global domains accessed from Europe. The browser used English and Stockholm settings; Sweden egress was user-declared. Failed sites stayed in the cohort. | Report [cohort selection](technical-report.md#cohort-selection), optional checksum command below. |
| 3:00 to 4:00 | Explain four workers, twenty jobs per site and the 600-second timeout. A job is a navigation task, not necessarily a unique page. The original cap was 100 jobs. State 405 complete, 55 partial, six failed, 34 unreached and 7,953 saved forms. | Report [crawl table](technical-report.md#crawling-and-evidence-normalization), saved coverage command. |
| 4:00 to 5:00 | Jev labels purposes and PI using sanitized descriptions and the source taxonomies. Relevant saved context supplements selected records; other records retain their original annotations. Uncertain groups and Unknown purposes remain review. Final labels have no fresh human accuracy estimate. Cumulative measured plus reserved cost is $0.663963720. | Report [annotation](technical-report.md#annotation-and-handling-uncertainty). Keep new technique details brief. |
| 5:00 to 6:00 | State 261 comparison-eligible domains out of 405 complete. Historical and new rates use exactly these same domains. Fifty-eight complete zero-form sites count as observed zeros. Uncertainty excludes 144 complete sites. Each domain counts once per PI type, regardless of how many forms request it. | Report [analysis rules](technical-report.md#analysis-and-denominators). |
| 6:00 to 7:30 | Present historical versus new counts: email 255/261 versus 147/261, names 180/261 versus 81/261, phones 101/261 versus 33/261, addresses 45/261 versus 3/261. These are observed collection differences under different dates and protocols. | Report [result table](technical-report.md#results-on-the-matched-261-domains), Figures 1 and 2, matched-rates command. |
| 7:30 to 8:30 | Explain rare PI: birth date 5/261, age 1/261, tax ID 1/261, citizenship/immigration status 2/261. Five other types have observed-zero overall counts under eligibility rules. No new context cell passes every display filter. Gray cells are masked, not confirmed zeros. | Report Figures 3 and 4 in [matched comparison figures](technical-report.md#matched-comparison-figures). |
| 8:30 to 9:30 | Explain requiredness separately. Among 11,005 eligible visible controls across exports, including partial sites, HTML required appears on 3,044, ARIA/text required on 1,556, optional on 164 and unspecified on 6,833. There are two conflicts. Signals overlap; unspecified does not mean optional. We did not test enforcement. | Report [requiredness](technical-report.md#requiredness-extraction), requiredness command. |
| 9:30 to 10:30 | The small audit before selective reannotation had random exact agreement of 17/20 form purposes and 16/20 group label sets. Ten targeted uncertainty questions were separate. One reviewer confirmed all fifty answers. This does not validate the final hybrid protocol. Fresh twelve-form/sixteen-group human fields remain blank. | Report [limited audit](technical-report.md#limited-human-audit), aggregate metrics only. |
| 10:30 to 11:30 | Explain limits. Time, access location, browser, depth and annotation methods differ. Categories are historical. Coverage is incomplete and uncertainty affects selection. Diagnostic inspection found sibling-context contamination and conflicting explanations; Unknown remains review. No contemporary US control isolates a regional cause. | Report [annotation limitations](technical-report.md#annotation-limitations) and [conclusions](technical-report.md#limitations-and-conclusions). |
| 11:30 to 12:00 | Finish with a concrete discussion question: would equal-depth contemporary US and European crawls, combined with independent human labeling, best reduce these uncertainties? This is proposed future work. | Final result table or deliverables index. |

## Graph narration

Report Figures 1 and 2 are the new and historical contact plots on the same 261 domains. Figures 3 and 4 are the corresponding rare-PI heatmaps. Figures 5 and 6 describe historical selected-500 context only. The paper's Figure 4 and Figure 5 names refer to plot styles; the report's numbering is independent.

Start with the overall rates before discussing context bars. Overall all-purpose rates divide by 261. Category denominators count matched domains in each category. Purpose denominators count domains with an identifying-PI form of that purpose and can differ between datasets. Read the printed denominator. Hatching marks support below ten; n=0 is unavailable. Categories and purposes overlap, so percentages need not sum to 100.

Rare-PI context cells need at least ten domains and an unadjusted Bernoulli Welch p-value below 0.05, with further row/column retention based on a retained rate above the dataset's overall rate. Undefined tests remain masked. These tests describe contexts within each dataset, not historical-versus-new changes. No multiple-test correction was added. Four historical context cells survive on the matched set; none survive for the new data. Rare-class accuracy lacks human validation.

The [final six-page PDF](../results/figures/paper-style-figures.pdf) orders report Figures 1, 3, 2 and 4, then Figures 5 and 6. Keep the first four pages for the matched comparison. The final two use 500 domains and are optional context. Final PNGs are in the same versioned figures folder. Use the final PDF and PNGs for this recording.

## Read-only saved-output demonstrations

Run from `webform-privacy-norms` with the existing environment. These commands inspect saved results without running pipeline stages.

Show the recorded upstream source version:

```sh
python3 - <<'PY'
import json
from pathlib import Path
print(json.loads(Path('results/manifest.json').read_text())['upstream_commit'])
PY
```

Expected commit is `a4f391d604e5cd557b881145b2a1cfd072e542d0`. The cohort SHA-256 is `9a454091daead43902d188da386a2658b0681afc2194dd39ae2224d998bff4dc`. Avoid displaying the cohort CSV because it contains starting URLs.

Show final coverage:

```sh
python3 - <<'PY'
import json
from pathlib import Path
counts = json.loads(Path('results/summary.json').read_text())
for key in ('selected', 'attempted', 'reached', 'complete', 'partial',
            'form_bearing', 'compared', 'forms', 'fully_annotated_forms',
            'comparison_resolved_forms'):
    print(f'{key}: {counts[key]}')
PY
```

The form-bearing count includes partial exports. Fully annotated/comparison-resolved form counts of 3,316/7,478 are out of 7,953 forms, not domain denominators.

Show final historical/new contact rates:

```sh
python3 - <<'PY'
import csv
types = {'EmailAddress', 'PersonName', 'PhoneNumber', 'Address'}
with open('results/rates.csv', newline='') as source:
    for row in csv.DictReader(source):
        if (row['cohort'] == 'compared' and row['category'] == 'All'
                and row['form_type'] == 'All' and row['pi_type'] in types):
            rate = 100 * float(row['rate'])
            print(f"{row['dataset']:10} {row['pi_type']:12} "
                  f"{row['numerator']}/{row['denominator']} = {rate:.1f}%")
PY
```

Show requiredness for eligible visible user controls:

```sh
python3 - <<'PY'
import csv
with open('results/requiredness.csv', newline='') as source:
    for row in csv.DictReader(source):
        if row['technical'] == '0':
            rate = 100 * float(row['rate'])
            print(f"{row['signal']:30} {row['numerator']}/{row['denominator']} "
                  f"= {rate:.2f}%")
PY
```

The technical-control population is separate and does not enter these percentages.

## Required code-change demonstration

Include this demonstration in the recording, using about two minutes from the existing implementation and requiredness segments. Open the five entry scripts without executing them. The [code guide](code-structure.md) identifies their settings, branches and main functions. Show `run_site` for crawler limits, `normalize` for visible controls and requiredness, `tasks` and `parse_response` for sanitized requests and review gates, and `build_database` for domain eligibility. Keep context-enrichment details in the code guide unless needed to answer a question.

## Recording check

Check spoken values against final saved CSVs and report captions. State the denominator before a percentage: 261 matched domains, 500 historical context domains or 11,005 requiredness controls. Identify the audit as pre-reannotation, retain the single-reviewer scope and avoid claiming final accuracy. Watch the recording for unintended private content and readable graph labels.

## Command, change and result sequence

The thorough walkthrough must visibly connect a command with its result and show where code changed. Do not replace all terminal demonstrations with narrated slides.

1. Show the requiredness code view in `upstream/crawler/src/page-functions.ts`, lines 109 to 116, or report Figure 7. Explain why `hasAttribute('required')` correctly handles an empty boolean attribute and why HTML and ARIA signals are separate. Show the saved patch location.
2. Show `normalize` in `02-crawl/run.py`, which carries these declarations into normalized controls. State that requiredness is per control while PI annotation groups same-name controls.
3. Run the existing read-only requiredness command above and keep its output visible. Explain 3,044 HTML-required controls and 6,833 unspecified out of 11,005. The command inspects actual completed outputs; it does not regenerate them.
4. Show `build_database` in `05-analyze/run.py`. Explain complete-domain eligibility, observed-zero sites and why review cannot establish absence. Run the final coverage and contact-rate commands, then show Figures 1 and 2 on the same 261 domains.
5. Explain Jev model annotation and the limited audit. State which software/aggregate checks passed and which final human-validation claims remain unavailable.

This gives a command/result and code/change/result walkthrough while keeping the final comparison as the main narrative. Do not rerun the full pipeline merely to record it. A recorded video and its accessible Canvas upload/link remain deliverables to create; this guide is not the video itself.
