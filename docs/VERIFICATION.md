# Verification record

This is a record of tested behavior, not certification or a promise of fit for every enterprise. All supplied examples are fictional. No customer deployment, savings or superiority to another product is claimed.

## Offline verification

Run from the repository root:

```sh
python3 scripts/verify_workflows.py
```

**312 tests across 12 suites and eleven CLI example replays pass** at the October 9 revision. Historical inference results below describe the code and contracts used for those studies.

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

## Runtime and governance checks

Tests cover account/date binding, worker deadlines, post-failure server capacity,
private failure receipts and malformed inputs. Proposal review checks exact
content, changed sources, expiry, draft integrity, competing revisions and
controlled export. The ledger identifies a local OS account, not an enterprise
approval role. A large proposal with 100 requirements and a result over 800 KB
exercises the worker, CLI and staging path; source inputs retain a 500 KB bound.

The assessment utility separately checks frozen rubric questions, project
membership, source hashes, request bindings and verification context. These are
integrity checks on a review tool, not workflow correctness measurements.

## Data Repair Evidence

The collection includes eleven workspace workflows: nine references and two
experiments, Proposal Evidence and Data Repair Evidence. Neither experiment has
verified target-environment acceptance.

Data Repair Evidence includes 34 regression tests and genuine GX 1.8.0 fail/pass
exports on fictional data, with recorded artifact provenance. Its dbt-shaped
lineage graph is an authored fixture. Checks cover scope identity, unchanged
expectation semantics, incomplete or stale retests, missing ownership and privacy
boundaries. Genuine empty-batch GX results demonstrate that a passing job can
still lack meaningful coverage. Shifted failures remain visible in the output.

One frozen live model trial preserved the expected facts but selected the same
four sentences as the zero-call template. It does not demonstrate AI benefit.
No authenticated enterprise source integration or business acceptance is claimed.

## Business controls and planner trial: October 9

Regression checks enforce policy denomination, claim-policy binding,
mixed-currency pipeline separation, shortages before inventory receipt and
source extraction chronology. The five affected browser replay journeys passed
at desktop and mobile widths. These are synthetic workflow checks, not production
trials.

The [twelve-case planner study](../projects/business-insights/evaluation/planner-2026-10-09/)
measured 10/12 strict plan agreements and 11/12 correct answer states for the live
model, including one unsafe calculation among six expected holds. Rules had
11/12 answer states and no unsafe calculations. A subsequent deterministic
clarification fix is regression-tested; no improved live score is claimed.
The public case copy omits evaluator author metadata and clarifies labeling
provenance. It preserves every original input and label and records its distinct
hash. Per-case results, token usage and
the failed answer remain available.

The [ten-workflow review](TEN-WORKFLOW-REVIEW.md) separates tested business controls
from remaining adopter acceptance. Historical September inference inputs predate
the new customer policy currency, claim policy ID, account currency and inventory
contracts as well as analytics snapshot metadata. Keep that historical study
unchanged; use current project fixtures or separately versioned inputs for a new
study. [Quality and limits](QUALITY.md) describes the current review outcomes.
