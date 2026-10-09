# Project quality: October 2, 2026

I use this review to find the next thing worth fixing. The scores measure Jev’s judgment of the supplied evidence. They do not measure production accuracy or certify a deployment. All ten still need verified target-environment acceptance.

## What changed

The baseline assessed main `51391fe`. Follow-up assessed `b9120fa` after three reproduced defects were fixed, the proposal review ledger was added, and execution gained a wall-clock deadline with private failure receipts. The same questions, weights and level descriptions were used. Each project now also has domain-specific governance and acceptance criteria.

| Project | Before /100 | After /100 | Next priority from Jev |
|---|---:|---:|---|
| [customer-resolution](../projects/customer-resolution/) | 48.66 | 50.45 | source integration |
| [incident-operations](../projects/incident-operations/) | 49.24 | 50.29 | source integration |
| [exposure-review](../projects/exposure-review/) | 48.55 | 50.36 | source integration |
| [business-insights](../projects/business-insights/) | 48.77 | 50.48 | source integration |
| [inventory-decisions](../projects/inventory-decisions/) | 48.85 | 50.10 | source integration |
| [asset-operations](../projects/asset-operations/) | 49.27 | 50.33 | source integration |
| [claims-intake](../projects/claims-intake/) | 49.59 | 50.61 | source integration |
| [proposal-operations](../projects/proposal-operations/) | 49.04 | 52.88 | source integration |
| [account-intelligence](../projects/account-intelligence/) | 40.85 | 50.81 | source integration |
| [workforce-onboarding](../projects/workforce-onboarding/) | 48.35 | 49.49 | source integration |

These are evidence scores from an uncalibrated model judge. Small numerical differences should not be read as measured improvements. Shared code and a larger evidence bundle changed between assessments; this was not a controlled experiment isolating each fix.

## Changes supported by code and tests

- Account evidence now rejects unnamed or ambiguous opportunity assignments and partial date tokens. Its correctness score moved from 0.47 to 2.00 out of 4.
- Proposal review now stores decisions against exact source, requirement and draft content. Changed, expired or unapproved evidence blocks current export. Its reviewability score moved from 2.00 to 2.94 out of 4.
- CLI and browser execution now terminate workers at a wall-clock deadline, preserve honest modes, and expose content-free execution receipts. The suite passed 191 tests and ten CLI replays at assessment time.
- Each project names its business owner, permitted decisions, sensitive-data boundaries and domain-specific metrics. These documents describe acceptance work still required; they are not completed sign-offs.

## What still blocks production

Jev selected source integration as the next priority for all ten after this pass. That is a typed category, not a written technical diagnosis. The code and deployment review independently identify the remaining gaps: authorized source adapters, verifiable freshness and identity, representative domain evaluations, operational acceptance and measured business value.

Proposal Evidence remains experimental. A local OS-account ledger does not establish enterprise identity or prove an export is current. Vulnerability review still requires stronger package-ecosystem identity before real inventory adoption. No comparative superiority over other projects or enterprise deployment is claimed.

## Inspect the assessment

- [Frozen rubric and production gates](../quality/README.md), [machine-readable rubric](../quality/rubric.json) and [exact questions](../quality/questions.json).
- [Baseline summary](../quality/2026-10-02/baseline.json) and [raw distributions / code hashes](../quality/2026-10-02/baseline/).
- [Follow-up summary](../quality/2026-10-02/refinement.json), [raw distributions / code hashes](../quality/2026-10-02/refinement/) and [verification context and unresolved gaps](../quality/2026-10-02/refinement-context.json).
- [Rubric design request](../quality/2026-10-02/rubric-review-request.json) and [Jev’s typed design review](../quality/2026-10-02/rubric-review-response.json).

Resolved model: `jev-1.13.0`. Full requests and responses were retained privately with hashes; public artifacts contain the judgments and source manifests. Requests used only repository code and synthetic/public evidence. No unchanged request was resampled. No new live workflow inference was performed in this hardening pass; the historical September 30 live cases remain explicitly historical.

## Data Repair Evidence, October 3

The new experimental workflow received 49.97/100 on a scoped artifact assessment using the same rubric anchors. Jev selected `publish_experiment` and prioritized `source_integration`. This is not a matched before/after comparison or production approval. [Evidence, raw distributions and limitations](../quality/2026-10-03/data-repair.md).

## Focused retrofit review: October 9, 2026

After source-bound snapshot checks, customer/order binding and currency labels, and dated inventory receipts were added, Jev reviewed those three changed workflows at commit `4ea17a8326750186009f3bd951070769ad72336c` using the same frozen rubric. All three selected source integration as the first priority. Their scores remain evidence judgments, not measured accuracy or production approvals.

| Project | Score /100 | First priority |
|---|---:|---|
| [business-insights](../projects/business-insights/) | 50.39 | Source integration |
| [customer-resolution](../projects/customer-resolution/) | 50.23 | Source integration |
| [inventory-decisions](../projects/inventory-decisions/) | 49.98 | Source integration |

All three remain blocked from production designation. The new controls consume caller/adapter-provided source facts; they do not authenticate users, verify source systems, or replace business-owner acceptance. No live inference or adopter trial was performed for this revision. The eight unchanged workflows were not reassessed.

The [focused summary](../quality/2026-10-09/retrofit/summary.json), [Jev judgments](../quality/2026-10-09/retrofit/), source manifests and [verification context](../quality/2026-10-09/retrofit/context.json) are public. Full requests remain private; their hashes are retained in the manifests.

## Ten-workflow domain review: October 9

After independent audits and five workflow repairs, Jev assessed the original ten
at `758cfe9bbecf369911fee0172b704214917b2516` using unchanged rubric 1.0.0.
Each packet assigned its relevant business domain and disclosed incomplete
deployment evidence. These are model roles, not professional sign-offs.

| Project | Score /100 | First priority |
|---|---:|---|
| Customer resolution | 51.05 | Source integration |
| Incident investigation | 50.41 | Source integration |
| Vulnerability review | 50.66 | Source integration |
| Business insights | 51.53 | Source integration |
| Inventory planning | 51.90 | Source integration |
| Equipment monitoring | 50.04 | Source integration |
| Claims intake | 50.65 | Source integration |
| Proposal evidence | 54.20 | Source integration |
| Account review | 50.95 | Source integration |
| Onboarding | 49.31 | Source integration |

All ten remain blocked from production designation. The [assessment record](../quality/2026-10-09/ten-workflows/)
retains actual responses, manifests and two HTTP400 failures. The two rejected
requests were replaced with independently reviewed, smaller packets containing
the relevant code and unfavorable evidence. Eight successful calls were not
repeated. Focused packets provide partial runtime context, so these are not
controlled before/after comparisons or proof that every small score movement is
meaningful. No high-score target was supplied to the judge.

The [business review](TEN-WORKFLOW-REVIEW.md) lists enforceable controls and the
remaining adopter evidence. The [planner study](../projects/business-insights/evaluation/planner-2026-10-09/)
preserves its original false-ready answer and makes no improved live accuracy
claim after the deterministic correction.
