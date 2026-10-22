# Experiment deliverables

DD2496 Group 06, 9 October 2026. These documents describe the completed bounded European follow-up to *Understanding Privacy Norms through Web Forms*. The presentation documents lead directly with the final 261-domain historical/new comparison. Findings remain provisional because coverage differs from the historical crawl and fresh validation of the final annotation method is unavailable.

| Document | Use |
| --- | --- |
| [Experiment explanation](experiment-explanation.md) | Read first for the paper, experiment and final findings in plain language. |
| [Written PDF](technical-report.pdf) | Rendered submission report with final figures and the source-change visual. |
| [Technical report](technical-report.md) | Main submission report with methods, final numbers, figures and limitations. |
| [Video walkthrough guide](video-walkthrough-guide.md) | Record a presentation using final saved figures and read-only demonstrations. |
| [Script execution evidence](script-execution-log.md) | Inspect captured terminal excerpts and structured reports for all five scripts, with missing stdout identified. |
| [Code and file structure](code-structure.md) | Understand the folders, entry scripts, settings, branches, functions and data contracts. |

The [final six-page figure PDF](../results/figures/paper-style-figures.pdf) contains matched 261-domain plots and separate historical selected-500 context. The report embeds these final figures. Earlier output folders remain preserved for provenance; their processing history is documented separately from the submission narrative.

## Shared interpretation

We selected and attempted 500 domains, completed 405 and compare historical and new evidence on exactly the same 261 eligible domains. Requiredness describes controls across the new exports, including partial sites. The small pre-reannotation audit has one reviewer; it does not validate the final hybrid method. The fresh twelve-domain packet remains unlabeled.

Differences combine time, access location, browser versions, crawl depth, annotation methods and uncertainty exclusion. They do not isolate a regional effect, prove field removal or establish legal noncompliance. Gray heatmap cells are masked, not confirmed zeros.

## Submission context and remaining delivery items

The supplied rubric requires artifact exploration, a short screen recording and documentation as a PDF. Its A standard requires at least two exploration options and advanced work with substantial effort, clear reasoning and new insight. The report maps the completed work to those options, explains implementation decisions and privacy insights, and states verification limits.

The technical work supports an A-level case, but a grade depends on the examiner and the final demonstration. Before submission:

- Record the thorough walkthrough with a visible command/result and code-change/result sequence, then upload it to Canvas or supply an accessible video link.
- Include a repository snapshot containing this artifact. The configured repository is [mperf/webform-privacy-norms](https://github.com/mperf/webform-privacy-norms); the public package is prepared locally; publication remains pending.
- Add each member's individual contribution. This remains a required submission item.
- Read the written PDF and confirm the methods and limitations. Final-protocol human validation remains unavailable and must not be claimed.

The runnable code, saved outputs, report and guide are distinct from a completed submission. No extra paid analysis is necessary to write or record this package.

## Evidence

Final analysis and figures are in `05-analyze/data/methodology-v3/final/`. Selection, crawl evidence, original predictions, review packets and the shared ledger remain in their existing step folders. Each step's `data/documentation-logs/manifest.json` records source and excerpt checksums with extraction criteria. The new documentation uses saved local evidence; no crawl, inference, annotation changes or plot regeneration was performed.
