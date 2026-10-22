# Validate new annotations

## Methodology follow-up validation

The original review files remain unchanged. The v3 follow-up keeps the fresh blinded packet at `data/methodology-v3/fresh-heldout/` separate from development and paid outputs. It contains 12 form questions and 16 group questions across 12 reserved domains, with blank human-label fields and no Jev answers. No accuracy metric is claimed from the paid follow-up because fresh human labels are not available.

The independent pilot check and paid comparison are in `data/methodology-v3/`. They preserve returned purpose choice, returned confidence, effective review label and auxiliary evidence reason separately. An auxiliary reason conflict occurred for two returned Unknown choices; Unknown still deterministically remains review. Sibling context sometimes introduced unrelated PI labels, and the unchanged review gate retained those cases. These are diagnostic observations, not human reference labels.

This step exports a blinded review CSV for up to 100 forms and 300 eligible visible field groups. It uses the new capture file, never historical predictions as ground truth. A seeded domain split assigns approximately one quarter of domains to development. Domains with identical sanitized Jev form or group requests stay in the same split. The check includes the model, question definitions and all request context. Large duplicate components can change the split size.

Run these commands from `webform-privacy-norms` with the preparation environment:

```sh
.venv/bin/python 04-validate/run.py --self-test
.venv/bin/python 04-validate/run.py export
```

The export reads `02-crawl/data/forms.jsonl` and writes `04-validate/data/review.csv` and `manifest.json`. It refuses to overwrite an existing review file. Use `--output PATH` for another export. The rows contain the capture context and evidence, with no model predictions. Reviewers should work independently in copies of the CSV, then resolve disagreements into one final CSV. Keep the IDs, split and duplicate signatures unchanged.

Fill `human_labels` with a JSON array of exact source taxonomy labels. Forms need one purpose label or `["Unknown"]`. Groups can have several PI labels. Use `[]` when the group requests none of the 19 PI labels. Blank means not yet labeled. Fill `human_requiredness` on group rows with a JSON object whose keys are control `field_id` values and whose values are `required`, `optional`, `unspecified` or `conflict`. Record the reviewer and any ambiguity. An unqualified star does not establish requiredness. The source taxonomies are in the pinned upstream classification scripts. `Fingerprints`, `Password` and `BusinessInfo` remain model labels but are outside the paper's narrower 16-label analysis.

Use only the development rows to tune definitions or the PI threshold. Freeze the settings before inspecting held-out labels. Save `data/freeze.json` with `prompt_version`, `threshold` and a timezone-aware `frozen_at` timestamp. These must match the prediction records used for evaluation. The timestamp is a declaration by the group, not proof of when a reviewer first saw the evaluation data.

```sh
.venv/bin/python 04-validate/run.py evaluate
```

Evaluation reads the review CSV, freeze file and `03-annotate/data/predictions.jsonl`. It writes `data/metrics.json`, with class support, precision, recall, macro-F1 over supported classes, exact label-set agreement, prediction coverage and Unknown/review coverage. Unsupported classes have null scores. Requiredness checks compare supplied human decisions with the saved extraction evidence. Separate reviewer agreement needs the independent CSVs; the final resolved CSV cannot establish it.

Completion requires supplied human labels and the frozen settings. Until then, validation is pending. A 300-group sample cannot establish accuracy for every rare class. The fixture checks run in less than a second; real export and evaluation print their elapsed seconds. No human annotation time has been measured.


## Pilot export, 2026-10-09

The blinded export took 0.11 seconds and contains 100 forms and 111 eligible field groups from nine form-bearing pilot domains. This is below the approximate 300-group target because the pilot has only 138 eligible groups in total and the sampled forms contain 111. Development domains are 360totalsecurity.com and abc.com. Seven other form-bearing domains are held out for evaluation. No exact sanitized request duplicates cross the split. Human-label columns remain blank, and no freeze declaration or evaluation metrics have been created.

Keep data/review.csv intact while reviewers work. Use development rows for any tuning. Preserve this pilot review if a separate later cohort export is needed. Model predictions remain absent from the initial human-label CSV.

## Pilot capture compatibility

Only 54 pilot review rows match current sanitized capture signatures. Another 152 have changed evidence and five refer to missing current forms. Current-run evaluation would reject these rows. Preserve this original pilot CSV as evidence; prepare a separate fresh review export for current-run validation and inspect its split against the existing held-out pilot domains before tuning. Human labels, disagreement resolution and a settings freeze remain pending.


## Human examination procedure

Keep review packets and filled answers local. Each form question asks for its main purpose; each eligible group question asks for the complete set of requested PI labels and the requiredness of its controls. Judge only saved evidence. Do not infer missing controls or test submission behavior.

Use exact taxonomy labels in `human_labels`, keep uncertain cases explicit, and record reviewer notes. Check evidence signatures and duplicate-domain components before evaluating a packet against current predictions. The completed small audit used twenty random form and twenty random group questions, with ten targeted uncertainty questions analyzed separately.

Export future packets into a separate directory, preserve the original review and freeze settings before inspecting held-out answers. Validate IDs, codes, signatures and source checksums before importing labels. Do not treat diagnostic suggestions as independently authored reference labels. Human review time is not inferred from machine runtime.

## Completed limited human audit, 2026-10-09

Mattia confirmed all 50 answers in `data/human-examination/answers.txt` as theirs. The imported labeled CSV and separate random and targeted metrics are saved beside the packet. The random sample has form-purpose agreement of 17/20 and field-group exact agreement of 16/20. Two group disagreements are model abstentions; two are confident extra or inappropriate PI labels. Requiredness matches on 27/27 controls across both samples, with seven required and 20 unspecified. Optional and conflict categories have no support.

`data/human-examination/audit-results.md` gives the findings, denominators and provenance. This is one reviewer's limited audit, not the full original validation target or independent multi-reviewer validation. SETTINGS = KEEP_CURRENT was retained and 22.05 was normalized to today's 22:05 Stockholm time, with that date/zone interpretation recorded in the audit freeze file. No tuning, prediction replacement or paid requests occurred. Unsupported classes and full validation remain pending.
