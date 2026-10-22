# Understanding our web-form experiment

Public aggregate outputs are in `results/`. Raw captures, prediction records, historical databases and private review packets referenced below are local evidence and are excluded from the repository.

We revisited websites from *Understanding Privacy Norms through Web Forms* with a bounded crawl from a European connection. We reused the authors' historical annotations, ran their crawler with documented changes and labeled newly captured forms with Jev. The final comparison uses 261 identical domains on both sides. It observes fewer requests for four common contact-information types in the new captures. Time, location, crawl coverage and annotation methods differ, so we cannot isolate a regional cause.

The [technical report](technical-report.md) is the factual reference, and the [video guide](video-walkthrough-guide.md) provides a recording sequence.

## What the original paper asks

Hao Cui, Rahmadi Trimananda and Athina Markopoulou studied explicit requests for personal information through web forms. Their paper appeared in *Proceedings on Privacy Enhancing Technologies*, 2025, issue 1, pages 5–22. The [local paper](https://doi.org/10.56553/popets-2025-0002) explains the motivation and original methods.

A web form might ask for an email address to subscribe to a newsletter, a name to register an account or an address to arrange a delivery. The purpose changes how we interpret the information request. The authors call common patterns in a particular website category and form purpose *privacy norms*. For example, a newsletter subscription and a financial account registration provide different contexts.

The paper measures what forms ask for. Those observations can inform a discussion of appropriateness, but frequency alone does not establish that a request is necessary, acceptable or lawful. Our follow-up reports observed collection patterns and does not make legal judgments.

The authors crawled 11,500 sites in the United States during December 2023–January 2024. They captured 938,324 raw forms and retained 292,655 filtered forms. Their annotation pipeline used large-language-model-assisted labeling to train smaller classifiers for form purpose and personal-information types. They then analyzed those labels by website category and form purpose. The paper also compared forms with privacy-policy disclosures. Our follow-up omits privacy-policy analysis. These are the paper's measurements, not the size of our new dataset. See the paper's collection, annotation and analysis sections and the published artifact appendix (`upstream/ARTIFACT-EVALUATION.md`, local evidence).

## What we wanted to learn

We wanted to see what a bounded follow-up could reproduce using the released artifact, and what information requests we would observe when revisiting historically studied domains from Europe. We also added a measurement of whether new controls declare themselves required or optional.

The sample contains global domains accessed from Europe. It is not a sample of European websites. The browser used English, a Stockholm timezone and Stockholm coordinates. The connection's Swedish egress country was user-declared rather than independently measured. The original and new measurements also occurred at different dates. A direct regional-effect experiment would need stronger controls than this comparison provides. Scope and browser evidence (`HANDOFF.md`, local evidence), [crawl methods](../02-crawl/README.md).

The assignment requires artifact exploration, a short video and a written PDF. For an A, it asks for at least two exploration options, thorough explanations and a walkthrough, plus substantial effort, clear reasoning and new insight at a level suitable for sharing with the authors. Our work covers a new dataset, code modifications, changed crawl parameters, adapted figures and a new requiredness question. These overlap, so the strength of the contribution comes from the measurement and its reasoning rather than simply counting options.

## Our main contributions compared with the original paper

We reused the authors' crawler, navigation model, historical annotations, website categories and label taxonomies. Our main contributions were:

| Contribution | What we changed or added |
| --- | --- |
| European-access revisit | Collected 7,953 new forms from a fixed sample of 500 historical domains with a Stockholm browser profile and user-declared Swedish egress. Compared historical and new observations on the same 261 eligible domains. This provides a later European-access measurement, without isolating a regional effect. |
| Declared requiredness | Added extraction of HTML, ARIA and text signals for required or optional controls, preserving unspecified and conflicting cases. This asks whether forms declare information mandatory, a question not measured in the historical annotations. |
| Direct annotation with Jev | Annotated new form purposes and PI groups using sanitized descriptions, explicit confidence-based review states, caching and a shared spending ledger. This replaces classifier training for our new captures; it does not establish a more accurate annotation method. |
| Bounded, auditable execution | Adapted the crawler to the current browser and added visibility checks, four-worker orchestration, twenty-job limits, timeouts and resumable attempts. Saved manifests and record lineage connect captures to final results. |
| Adapted analysis and figures | Applied the paper's domain-level aggregation and contact/rare-PI graph styles to the new matched dataset, with explicit denominators and uncertainty exclusions. Requiredness results provide a separate control-level view. |

These contributions extend the released artifact. Historical classifier training and privacy-policy analysis remain outside our scope. The [technical report](technical-report.md#design-decisions-and-reasoning) explains the reasoning behind the changes, and the [code guide](code-structure.md) identifies their implementation.

## How the experiment works

We selected 500 domains from 10,143 eligible historical domains using seed 42. The cohort stayed fixed, including failed sites. Four browser workers explored up to twenty navigation jobs per site with a 600-second timeout. The browser used English, Stockholm timezone and coordinates, with user-declared Swedish egress. The crawl completed 405 domains, had 55 partial timeouts, six failures and 34 unreached sites, and exported 7,953 forms. A job is a navigation task and does not necessarily represent a unique page.

We kept the original TypeScript crawler and its navigation model, historical categories and taxonomies. Our additions were bounded orchestration, compatibility with the current browser, visibility checks, declared requiredness, sanitized direct Jev annotation and matched domain-level analysis. We did not train the authors' historical classifiers, reconstruct their original crawl or reproduce privacy-policy analysis. [Artifact scope](technical-report.md#original-paper-and-artifact-reproduction).

Jev labels form purposes and the personal-information types requested by groups of controls. Controls with the same nonempty HTML name share a group, such as radio buttons. Requests exclude captured values, URLs, tokens and raw HTML. Selected records use relevant saved headings and explanations, while untouched records retain their original annotations. Confidence gates send uncertain evidence to review. A review state cannot establish absence of information requests. The final labels mix carried-forward and selectively reassessed records, and the overlap clarifications are provisional study coding choices. [Annotation method](technical-report.md#annotation-and-handling-uncertainty).

Of 405 complete domains, 261 have sufficiently resolved evidence for comparison and 144 remain excluded through uncertainty. The included set contains 58 complete sites with no captured forms, treated as observed zeros. Incomplete sites stay outside the comparison. We union qualifying PI labels across forms on a domain, so one email form and twenty email forms each count as one domain requesting email. A zero means no qualifying request was observed within the crawl and eligibility rules. It does not mean the website never asks for that information.

## What we found

Both columns use exactly the same 261 domains.

| PI type | Historical | New crawl |
| --- | ---: | ---: |
| Email address | 255/261, 97.7% | 147/261, 56.3% |
| Person name | 180/261, 69.0% | 81/261, 31.0% |
| Phone number | 101/261, 38.7% | 33/261, 12.6% |
| Address | 45/261, 17.2% | 3/261, 1.1% |

The [saved rates](../results/rates.csv) support these observations. For example, the new email rate is 147 divided by 261, multiplied by 100, giving 56.3%. Dividing by 500 would mix included evidence with incomplete or uncertain evidence. Dividing by 7,953 would measure forms, a different unit. A purpose-specific rate instead uses domains with an identifying-PI form of that purpose. Categories and purposes overlap, so percentages need not sum to 100.

### Reading the graphs

![New contact-information observations](../results/figures/figure-4-new-compared.png)

New observations on 261 domains. Overall rates use 261; category and purpose rates use their printed conditional denominators. Dashed lines show overall rates, and hatching flags support below ten.

![Historical contact-information observations](../results/figures/figure-4-historical-compared.png)

Historical annotations on exactly the same 261 domains. Compare this graph with the new graph above. Dates, depth, browser and annotation methods still differ.

![New rare-information observations](../results/figures/figure-5-new-compared.png)

The rare-PI chart observes birth date on 5/261 domains, age on 1/261, tax ID on 1/261 and citizenship/immigration status on 2/261. The other five types have observed-zero overall counts under the rules. No new context cell passes all paper-style display filters. Gray cells are masked, not confirmed zeros. The historical chart on the same set retains four context cells. The unadjusted tests describe contexts within a dataset, not historical-versus-new differences. Rare-class accuracy has not been human-validated. [Figure definitions and captions](technical-report.md#paper-style-figures-and-interpretation).

Historical selected-500 figures are separate cohort context. They must not be treated as the direct baseline for the 261-domain comparison.

## What requiredness tells us

Requiredness describes explicit declarations in the new exported controls, including partial sites. Among 11,005 eligible visible user controls, 3,044 have HTML-required evidence, 1,556 have ARIA/text-required evidence, 164 have explicit optional evidence, 6,833 are unspecified and two have conflicts. Signals overlap. Unspecified does not mean optional. We did not test browser or server enforcement, and historical requiredness is unavailable. [Requiredness results](../results/requiredness.csv).

## How much we validated

A small audit before selective reannotation checked twenty random form purposes and twenty random field-group label sets, with exact agreement of 17/20 and 16/20. Ten targeted uncertainty questions were separate. One reviewer confirmed all fifty answers. This is human-confirmed evidence with confirmation by one reviewer, not an independent multiple-reviewer validation study. Requiredness agreed on 27 checked declarations, comprising seven required and twenty unspecified controls. No optional or conflict examples were audited. Audit evidence (`04-validate/data/human-examination/audit-results.md`, local evidence).

That audit does not validate the final hybrid method. A fresh packet has twelve form and sixteen group questions from twelve reserved domains, with blank human fields. Added context can also mislead the model: Diagnostic inspection found sibling-label contamination, and 65 Unknown-purpose records had contradictory auxiliary explanations that remained review. More resolved evidence does not demonstrate greater accuracy.

Cumulative API spending is $0.658587720 measured plus $0.005376 reserved, totaling $0.663963720 under the shared $4.90 working cap and $5 ceiling. The [execution-evidence document](script-execution-log.md) records request accounting and available logs without adding it to the presentation narrative.

## What we can defend in a discussion

We can demonstrate a bounded adaptation of the original crawler, reuse of historical labels, explicit uncertainty rules, declared requiredness and final rates with stated denominators. The experiment cannot isolate a European effect, establish website-wide absence, prove field removal or determine legal noncompliance. Time, access location, browser versions, crawl depth and annotation methods changed together. Rare requests are not automatically unnecessary.

For a presentation, explain why context matters, state the 500 selected, 405 complete and 261 comparison-eligible domains, and show the final matched results directly. Follow with requiredness and validation limits. Use the [technical report](technical-report.md) for factual checks, and the [code structure](code-structure.md) for implementation questions.

## Why this is a substantive artifact contribution

The new requiredness question distinguishes asking for information from declaring it mandatory. Most saved controls are unspecified, so interpreting missing required attributes as optional would erase uncertainty. The matched-domain method also shows why a revisit's rates depend on crawl coverage and annotation eligibility. Added context can help interpretation but can introduce sibling-label contamination. These are concrete privacy-measurement insights that we can discuss with the authors.

The [technical report](technical-report.md#design-decisions-and-reasoning) now explains the choices, [correctness checks](technical-report.md#correctness-checks), [changes in code](technical-report.md#changes-to-inspect-in-code) and [future work](technical-report.md#future-work). Jev supplied model labels. Software tests and aggregate reconciliation support implementation correctness, while the limited human audit does not validate the final hybrid labels. A stronger validation study remains future work.
