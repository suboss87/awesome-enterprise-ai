# Verification record

This is a record of tested behavior, not certification or a promise of fit for every enterprise. All supplied examples are fictional. No customer deployment, savings or superiority to another product is claimed.

## Offline verification

Run from the repository root:

```sh
python3 scripts/verify_workflows.py
```

**153 tests pass locally**: 25 shared runtime, input-boundary and server tests, plus 128 project tests. Ten CLI example replays also pass.

The verifier runs the shared runtime/security tests, each workflow's business-rule tests, and all ten CLI example replays. Tests exercise invalid inputs, missing evidence, conflicting records, exact arithmetic and human-review boundaries. Recorded-response tests do not measure live model quality.

The GitHub `enterprise-workflows` job runs this command on pushes, pull requests, manual runs and the existing daily schedule. The two earlier projects keep their own verification jobs.

## Browser verification

All ten workflows were exercised in Chromium: select a project, load its example, run a replay, inspect the result and export JSON. Malformed JSON and edited replay inputs were rejected. Desktop 1440×1000 and mobile 390×844 were inspected; no page script errors or mobile horizontal overflow were observed. The README screenshot is from the actual workspace.

The final browser pass also verified nested duplicate-key rejection and one actual live customer-resolution run, including live execution metadata and a provider response ID. The other nine browser journeys used replay; their live workflow behavior was exercised separately through Python.

## Actual inference — 2026-09-30

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

## Reproduce or extend evaluation

Each project includes declared cases under `evaluation/`. Some recorded cases deliberately inject invalid model responses to test rejection; those are not live model benchmarks.

`scripts/evaluate_workflows.py` accepts a separate JSON object with a `cases` list. Each case needs `project`, `id`, `input`, and an `expected` object containing any of `metrics`, `required_findings`, `forbidden_findings`, `any_findings`, or dotted `paths`. Freeze expected outcomes before inference. Save output outside the public repository and inspect the actual responses separately.

Do not change an expected result to make an observed failure pass. Preserve prior runs, document the cause and distinguish a corrective regression from fresh validation.
