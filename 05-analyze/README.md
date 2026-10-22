# Compare collection on matched domains

This step reads the fixed cohort, crawl statuses, new captures and Jev predictions. It opens the historical annotations database read-only and creates a separate `data/results.db` with original-compatible form and field classification tables. A field evidence table retains requiredness and control state. Incomplete PI annotation has a null `field_list`, rather than an empty negative list. Fully known PI lists are stored independently of purpose uncertainty. Comparison coverage separately recognizes confidently excluded forms. Jev probabilities remain separate records in the prediction JSONL; they are not MarkupLM scores.

Run from `webform-privacy-norms`:

```sh
.venv/bin/python 05-analyze/run.py --self-test
.venv/bin/python 05-analyze/run.py
```

Defaults use the preceding steps' `data` folders. Override input paths with `--sites`, `--statuses`, `--forms`, `--predictions` and `--historical`. Use `--output PATH` for another results folder. Rerunning replaces only analysis outputs and writes a measured run paragraph at the bottom of this README.

The script joins historical annotations on domain, job hash and form filename within each capture. It accepts forms for collection analysis only when at least one of the upstream notebook's eight identifying PI types occurs. It unions PI by domain and form purpose, so repeat pages do not count as additional domains. Category mapping follows the notebook's subcategories and selected parent-category substitutions. The cohort manifest supplies the full historical category-name map, including names outside the sample. Empty historical categories map to `Unknown`.

The paper reports 16 PI types. The annotation model retains all 19 source labels. `Fingerprints`, `Password` and `BusinessInfo` are omitted from the paper-rate CSV, not deleted from predictions or the database.

`rates.csv` includes historical rates on the selected cohort, historical rates on the compared subset and new rates on that same compared subset. Each row includes its numerator and denominator. For all-purpose rates the denominator is every domain in that cohort and category. For a specific purpose it is the domains with an identifying-PI form of that purpose. Form-purpose presence uses the identifying-form-bearing domains as its denominator. A domain can have several purposes and categories, so these percentages need not sum to 100.

The compared subset requires a complete crawl and usable PI annotation for every eligible visible user-control group. A form with identifying PI also needs usable purpose annotation. A form with no eligible controls, or with confidently no identifying PI, is excluded before purpose aggregation and does not need its purpose resolved. Unknown or review PI cannot establish absence. Raw annotation completeness is reported separately from comparison-resolved coverage; prediction and review records retain their original states. A complete site with no captured forms can contribute a zero observation. Failed, partial and unannotated sites remain missing evidence. `counts.json` reports these stages. `differences.csv` compares PI sets by domain and purpose. Its "not observed now" column does not prove removal of a field. Old annotation identities that no longer join current captures are counted separately. Matching IDs also require matching sanitized request cache keys, so changed capture evidence cannot reuse an old prediction by identity alone.

`requiredness.csv` reports HTML-declared required, ARIA/text-declared required, explicit optional signals, unspecified evidence and conflicts. These signals can overlap. Eligible visible user controls and technical hidden controls have separate denominators. Disabled, read-only and button controls remain in the evidence table but do not enter the visible-user denominator. These are new-crawl measurements; historical field requiredness is unavailable.

Completion means the exported counts reconcile, denominators are explicit and human-validation status is reported separately. Geography, time, annotation method and reduced crawl depth all affect the comparison. Differences cannot isolate a regional cause, establish unnecessary collection or prove legal noncompliance. The pilot comparison is provisional until human validation is complete. `--allow-mock` permits a synthetic integration check only when `--output` names a separate fixture directory; default analysis rejects mock predictions. The self-test also runs the combined synthetic pipeline through capture normalization, mocked annotation, cache reuse, blinded export and matched-rate checks. Fixture checks take less than a second; the analysis records actual elapsed seconds when data are available.


## Methodology follow-up, 2026-10-09

The follow-up analysis is separate from the original results and figures. It validates a manifest-scoped hybrid protocol: untouched records retain frozen v2 evidence and configuration, while selected replacements use v3 evidence and configuration. The final outputs are in `data/methodology-v3/final/`, including `followup-summary.json`, `baseline-followup-rates.csv`, `compared-domains.json`, `lineage.jsonl`, results database, requiredness export and versioned figures.

The revised comparison contains 261 domains, with historical rates recomputed on exactly those domains. The original 188-domain results remain the baseline. Revised complete-domain blockers are 358 forms, 327 eligible groups and 125 purpose blockers, compared with 773, 726 and 203. These are coverage units, not accuracy estimates. The analysis reports v2/v3 origin counts and preserves complete zero-form sites.

## Provisional full-cohort results, 2026-10-09

All 500 domains were attempted, 466 were reached, 405 completed and 407 had captured forms. There are 55 partial timeouts, six failures and 34 unreached domains. Of the complete domains, 188 have usable evidence for the matched comparison. The 217 other complete domains have unresolved eligible PI or identifying-form purpose evidence. The comparison includes 58 complete zero-form sites as observed zeros. There are 2,950 fully annotated forms and 7,063 comparison-resolved forms out of 7,953 captures.

The actual form-bearing count is 407. An earlier reporting lookup inserted 58 complete zero-form sites into that count; the correction preserves their eligibility as zeros while excluding them from form-bearing counts. The combined fixture verifies both behaviors. Fifteen earlier prediction identities no longer join current captures and are retained in the append-only history. All current identities have records. The results database passed SQLite quick_check.

These selected examples use the same 188-domain denominator on both sides, with the original identifying-PI eligibility rule:

| PI type | Historical numerator / denominator | New numerator / denominator |
| --- | ---: | ---: |
| EmailAddress | 182 / 188, 96.8% | 75 / 188, 39.9% |
| PersonName | 131 / 188, 69.7% | 44 / 188, 23.4% |
| PhoneNumber | 76 / 188, 40.4% | 19 / 188, 10.1% |
| Address | 38 / 188, 20.2% | 1 / 188, 0.5% |

These are observed collection differences under different dates, location, browser versions, crawl depth and annotation methods. The new crawl used 20 jobs per site versus the original 100-job cap. The comparison subset also excludes uncertainty, so it may differ systematically from excluded sites. These rates do not establish field removal or a regional effect. A limited human audit is now complete, with 17/20 random form-purpose and 16/20 random field-group agreement. Full validation and rare-class support remain incomplete. See `../04-validate/data/human-examination/audit-results.md` for scope and provenance.

Requiredness has its own denominator of 11,005 eligible visible user controls across all saved attempts selected for export, including partial sites. HTML required occurs on 3,044 controls, 27.7%; ARIA or text required occurs on 1,556, 14.1%; explicit optional evidence occurs on 164, 1.5%; 6,833 are unspecified, 62.1%. Two have conflicts. Signal columns can overlap. Technical controls are separate in `requiredness.csv`, and historical requiredness is unavailable.


## Paper-style figures

The original paper's Figure 4 is the contact-information bar chart, and Figure 5 is the nine-panel rare-PI heatmap. These are recreated from the saved results database and matched historical annotations by the existing entry script. Figure 6 requires privacy-policy analysis, which is outside this experiment. The pipeline and classifier diagrams are methodological illustrations, not data graphs for this follow-up.

Run from `webform-privacy-norms` after analysis:

```sh
.venv/bin/python 05-analyze/run.py --plots
```

Preparation now includes pinned matplotlib 3.11.2 and scipy 1.18.1 for plotting and the notebook's statistical calculation. They are already installed locally. For another installed environment that lacks them, use `.venv/bin/python -m pip install matplotlib==3.11.2 scipy==1.18.1`. This command makes no crawl or annotation requests. The original analysis outputs and all predictions remain unchanged.

Outputs are in `data/figures/`. `paper-style-figures.pdf` contains six pages. Each page also has its own PNG and PDF:

| Files | Dataset |
| --- | --- |
| figure-4-new-compared, figure-5-new-compared | European follow-up on the 188 comparison-eligible domains |
| figure-4-historical-compared, figure-5-historical-compared | Historical annotations on exactly those same 188 domains |
| figure-4-historical-selected, figure-5-historical-selected | Historical annotations on all 500 selected domains, for cohort context |

Compare the first two datasets directly. The 500-domain historical view describes a larger denominator and is not the matched comparison. Titles identify the dataset and cohort size. Category and purpose axes follow the paper's chosen categories and order. Colors use the paper's contact-type palette. Dashed lines show overall cohort rates. Figure 4 labels each context's denominator; hatched bars flag support below ten and n=0 means unavailable, not a measured percentage.

Figure 5 uses the upstream notebook's nine PI types, Bernoulli Welch calculation, context support of at least ten, unadjusted p<0.05, and row/column selection requiring a retained rate above the overall rate. Cells show collecting domains / context domains and percentages. The overall cell remains visible. Gray cells are masked. Zero-variance comparisons have undefined tests and remain masked. A zero overall rate has an undefined relative color, so its overall cell is neutral. Red, yellow and green encode 0x, 1x and 2x the dataset's overall rate, with values above 2x saturated.

These are paper-style adaptations using the project's explicit denominators. All-category rates include every domain in the defined cohort, including complete observed-zero sites. Purpose rates condition on domains with identifying-PI forms of that purpose. Duplicated forms are unioned at domain/purpose level. Context-versus-other-context tests can involve overlapping domains because one domain can have several purposes. They are descriptive reproductions, not paired historical-versus-European significance tests or claims of regional effects. No multiple-testing correction was added to the paper's procedure.

No new European context cell passes all Figure 5 filters in the matched subset. The overall observations are date of birth on 2/188 domains and citizenship/immigration status on 1/188; the other seven rare types have observed-zero counts under these eligibility rules. This does not establish population-wide absence. Historical matched heatmaps retain two context cells; the historical 500-domain heatmaps retain fourteen. Sparse figures are expected at this sample size and are not filled with unsupported rates.

`figure-5-cells.csv` preserves every tested context's numerator, denominator, rate, complement counts, p-value and display flag, including masked cells. `manifest.json` records measured generation time, package version and support counts. The final generation took 5.981 seconds. All six combined PDF pages were rendered and visually inspected; no text extends outside the page. Completion means all six PNGs and PDFs exist, the combined PDF has six pages, and plotted cohort/counts reconcile with `counts.json` and `rates.csv`. Each applicable context count is checked by the plotting command. Human audit limits and changed crawl depth remain relevant to every plot.

<!-- measured-results -->

Latest run compared 188 domains. Counts are in `data/counts.json`. The analysis took 3.917 seconds. Human validation remains separate.
