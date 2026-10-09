# Verification record

This is a record of tested behavior, not certification or a promise of fit for every enterprise. All supplied examples are fictional. No customer deployment, savings or superiority to another product is claimed.

## Offline verification

Run from the repository root:

```sh
python3 scripts/verify_workflows.py
```

**153 tests pass locally**: 25 shared runtime, input-boundary and server tests, plus 128 project tests. Ten CLI example replays also pass.

The verifier runs the shared runtime/security tests, each workflow's business-rule tests, and every catalog workflow's CLI example replay. Tests exercise invalid inputs, missing evidence, conflicting records, exact arithmetic and human-review boundaries. Recorded-response tests do not measure live model quality.

The GitHub `enterprise-workflows` job runs this command on pushes, pull requests, manual runs and the existing daily schedule. The two earlier projects keep their own verification jobs.

## Browser verification

All ten workflows were exercised in Chromium: select a project, load its example, run a replay, inspect the result and export JSON. Malformed JSON and edited replay inputs were rejected. Desktop 1440×1000 and mobile 390×844 were inspected; no page script errors or mobile horizontal overflow were observed. The README screenshot is from the actual workspace.

The final browser pass also verified nested duplicate-key rejection and one actual live customer-resolution run, including live execution metadata and a provider response ID. The other nine browser journeys used replay; their live workflow behavior was exercised separately through Python.

## Actual inference: 2026-09-30

A frozen 58-case synthetic set was run through the configured model. Requests and raw responses were retained privately. **50/58 automatic checks passed on the first run.** Two independent reviewers then inspected all 58 cases against their inputs, including outputs that passed automatic checks.

| Initial finding | Correction |
|---|---|
| Four vulnerability runs quoted metadata or invented citation IDs | Prompt now explicitly restricts quotations to the advisory text and exact advisory IDs |
| One incident run quoted a timestamp rather than source text | Prompt distinguishes contextual metadata from quotable event text |
| Three claims runs rejected correct amounts followed by sentence punctuation | Numeric-token validation fixed; tests retain full-number boundaries |
| Two sales answers treated ordinary procurement progress as an obstruction | Prompt requires explicit evidence of a blocker and omits neutral status |
| Incident answers treated alternative explanations as contradictions | Prompt requires evidence incompatible with the particular hypothesis |
| Analytics displayed zero for an empty period | An empty result now has a null total and an explicit missing-data finding |

A corrective live run of all 15 incident, vulnerability and account cases passed **15/15 automatic checks**. This is regression evidence on known cases, not a new held-out benchmark. An intermediate sandbox-network failure was retained separately; it is not counted as model evaluation.

Independent semantic review accepted the inspected corrections in the 15-case live regression. The original nine claims cases also meet their frozen outcomes after replaying the saved inference through the corrected validator (eight saved responses and one case requiring no call; no new claims inference). Shared regressions cover the fixes.

Automatic checks and semantic review are distinct. Small synthetic sets do not establish production accuracy. No representative enterprise integration, latency/load study or controlled comparison with a non-AI baseline has been completed. Business owners must test their own workflows before adoption.

## Fresh independent cases: 2026-09-30

After the initial fixes were complete, two independent authors created twenty new synthetic cases using only the input contracts and examples. Neither inspected earlier evaluation cases or model outputs. Expected outcomes were frozen before inference. **20/20 automatic checks passed without changing prompts, code or expected outcomes.** Each author then reviewed the other author's actual outputs for semantic correctness. All twenty met their specific semantic criteria, with no blocking defect found. Nonblocking observations remain: one claims information request could describe the identity conflict more precisely, and two incident outputs could separate overlapping hypotheses and supporting/counterevidence labels more clearly.

[The complete case set](../evaluation/live-cases.json) and [actual result snapshots](../evaluation/2026-09-30/) are public. These are two cases per project, not a representative enterprise accuracy estimate. The initial failures and consumed corrective regressions above remain part of the record.

```sh
python3 scripts/evaluate_workflows.py --cases evaluation/live-cases.json \
  --output /tmp/enterprise-ai-fresh-run --workers 2
```

This command reproduces the 2026-09-30 evaluation contract. Its frozen Business Insights inputs predate the required `source_snapshot` contract and therefore are historical evidence, not replayable against the current workflow without a separately versioned migration. Keep the original inputs and result snapshots unchanged; prepare and freeze a new case set with adapter-declared snapshot metadata before any new inference.

This command makes actual model calls and incurs provider usage. Use a new output directory; the evaluator refuses to overwrite an existing run. Synthetic snapshots can be inspected without a provider key.

## Reproduce or extend evaluation

Each project includes declared cases under `evaluation/`. Some recorded cases deliberately inject invalid model responses to test rejection; those are not live model benchmarks.

`scripts/evaluate_workflows.py` accepts a separate JSON object with a `cases` list. Each case needs `project`, `id`, `input`, and an `expected` object containing any of `metrics`, `required_findings`, `forbidden_findings`, `any_findings`, or dotted `paths`. Freeze expected outcomes before inference. Save output outside the public repository and inspect the actual responses separately.

Do not change an expected result to make an observed failure pass. Preserve prior runs, document the cause and distinguish a corrective regression from fresh validation.

## Initial Jev artifact assessment: historical holds

Jev (`jev-1.13.0`) reviewed all ten implementations, tests, deployment limits and the retained initial/corrective evaluation evidence. All ten received `fix_before_reference`, with `adopter_validation_required` for enterprise readiness. Usefulness scores ranged from 1.99 to 2.04 on the declared 0–4 rubric. These are typed artifact judgments, not runtime benchmark scores or written technical diagnoses.

These original judgments remain in the record. They were not overwritten or resampled with unchanged evidence. The follow-up below reports the materially new evidence and current dispositions. No comparative superiority or bank production readiness is claimed. All three GitHub CI jobs passed on candidate `20195350caa66f61aa6596e3c9807fbb276b24d7` ([run](https://github.com/suboss87/awesome-enterprise-ai/actions/runs/36684488756)). The follow-up assessment below used the fresh cases and operational trial plan; the original judgments are retained.

## Follow-up artifact assessment and publication scope

The same original questions and rubric were applied to materially new evidence: twenty independent fresh live cases, cross-author semantic reviews, public reproducible snapshots, an operational trial plan, and passing exact-head CI on `e4396b0006027f5e8ea13c40b7db2fd0f33399fa` ([run](https://github.com/suboss87/awesome-enterprise-ai/actions/runs/36690768229)). Runtime code and model prompts were unchanged during the fresh evaluation.

**Nine projects received `ready_reference`. Proposal Evidence received `fix_before_reference`.** A separate diagnostic classified its remaining hold as `operational_deployment`; no written technical diagnosis was returned. Operational capabilities were not implemented by writing the adoption plan, and that hold remains unresolved.

All ten received `adopter_validation_required` for enterprise readiness. Usefulness scores ranged from 1.89 to 1.99 on the original 0–4 rubric. These scores describe bounded utility, not enterprise excellence or evidence of superiority. [Per-project results](../evaluation/2026-09-30/artifact-review.json) retain the actual dispositions.

This publication makes nine reviewed references and one clearly labeled experimental implementation available. It does **not** claim all ten passed release approval. The experimental project remains available for code inspection, synthetic testing and further development. Its promotion requires operational evidence and a resolved review hold; a green CI run alone is insufficient.

## Runtime and governance refinement: 2026-10-02

The local suite passes 191 tests across 11 suites and ten CLI example replays. New checks cover ambiguous account binding, complete quoted date tokens, execution mode validation, actual slow-progress child termination, post-failure server capacity, private receipt creation, malformed-input receipts, and the proposal review lifecycle. Independent review found no remaining blocker inside the documented single-OS-account scope. A sandbox initially prevented localhost binding; the same server tests were then run with binding enabled and passed.

The shared worker now has a wall-clock deadline. Proposal decisions are stored against exact input and answer contents; tests cover changed sources/requirements, expiry, draft integrity, invalid approvals and competing review revisions. This does not implement source-system authentication or organizational identity. Frozen earlier actual-inference account outputs were revalidated against the stricter rules without new model calls.

[Jev quality review](QUALITY.md) preserves both assessments against an unchanged rubric. All ten still require production acceptance evidence. The new `GOVERNANCE.md` files specify domain-specific metrics and ownership; they do not claim those trials or sign-offs have happened.

The scorer itself received a separate integrity review after inference. It now rejects modified rubric questions, reordered score levels, substituted projects or source files, and verification context that differs from its frozen snapshot. A compact-JSON round-trip test catches serialization drift. Eleven scorer tests pass; re-validating all saved follow-up assessments produced byte-identical summary scores with no new inference. These six additional tests were added after the 191-test assessment snapshot.

GitHub review then identified two additional domain boundaries and two scorer provenance gaps. Space-separated timestamps are now rejected as standalone account dates. An actual proposal with 100 requirements and a result larger than 800 KB completes the worker/CLI/staging path; review imports share the 10 MB serialized result bound while source inputs stay at 500 KB. Scoring preparation now requires a clean checkout and binds the entire request before inference, including saved evaluation data. Fourteen scorer tests pass. The published Jev follow-up remains tied to b9120fa; these later fixes are covered by regression tests, not retroactively attributed to that model assessment.

Final integrated local verification passes **203 tests across 11 suites and ten CLI replays**, including the large-proposal and complete assessment-binding regressions. GitHub CI verifies the publication commit separately.


## October 3: current collection verification

The collection now includes eleven workflows: nine reference implementations and two experiments, Proposal Evidence and Data Repair Evidence. Integrated local verification passes **270 tests and eleven CLI replays** after the proposal source recovery fixes. Historical counts and assessments above describe their original revisions.

Data Repair Evidence adds 34 tests, genuine GX 1.8.0 fail/pass exports with recorded provenance, and an explicitly authored dbt manifest fixture. Independent checks cover scope identity, unchanged check semantics, incomplete retests, stale evidence, missing ownership and privacy boundaries. A real Chromium replay exposed numeric JSON normalization drift; the corrected journey returned HTTP 200 with no console errors.

One frozen live model trial preserved the expected facts but selected the same four sentences as the zero-call template. It does not demonstrate AI benefit. Jev selected `publish_experiment`, with 49.97/100 readiness evidence and source integration as the next priority. See [the scoped assessment](../quality/2026-10-03/data-repair.md). No authenticated source integration, enterprise business acceptance or production readiness is claimed.

Late release review reproduced passing empty GX batches and omitted newly failing checks. Corrections require meaningful assessed coverage under explicitly supported expectation semantics and expose both initial and current failures with aggregate counts. Actual empty GX output, missing/inconsistent coverage, unknown expectation semantics and shifted-failure regressions are retained. Independent probes and a fresh browser replay passed. Jev selected `publish_experimental_fix` for this correction; the original numerical assessment remains unchanged.

## Current source and timing contracts: October 9

After the Business Insights snapshot contract, Customer Resolution binding/currency checks, and Inventory Planning receipt-date horizon were added, the integrated verifier passes **286 tests across 12 suites and eleven CLI replays**. The three updated browser journeys passed at desktop, tablet and mobile widths with no page errors. Tests and replays use synthetic examples; this is not live inference, an adopter trial or production acceptance. The three-project Jev assessment is recorded separately in [the focused quality review](QUALITY.md#focused-retrofit-review-october-9-2026).

## Ten-workflow audit and planner trial: October 9

The next independent audit repaired policy denomination, claim-policy binding, mixed-currency pipeline totals, shortages before inventory receipt and source extraction chronology. Integrated verification passes **312 tests across 12 suites and eleven CLI replays**. Browser replays of all five changed workflows returned HTTP 200 without console errors; wide account tables were visually checked and made readable at desktop and mobile widths. The eleventh experimental Data Repair workflow remains in those integrated checks but is outside this ten-project assessment.

The [independently labeled twelve-case planner trial](../projects/business-insights/evaluation/planner-2026-10-09/) measured 10/12 strict plan agreements and 11/12 correct answer states for the live model, including one unsafe calculation among six expected holds. Rules had 11/12 answer states and no unsafe calculations. A subsequent deterministic clarification fix is regression-tested; no improved live score is claimed. Original labels, failed output, provider usage and hash-matched original source are retained.

[The ten-workflow review](TEN-WORKFLOW-REVIEW.md) separates tested business controls from remaining adopter acceptance. Historical September inference inputs predate the new customer policy currency, claim policy ID, account currency and inventory contracts as well as analytics snapshot metadata. Keep that historical study unchanged; use current project fixtures or separately versioned inputs for a new study.
