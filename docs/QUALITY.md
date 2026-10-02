# Project quality: October 2, 2026

I use this review to find the next thing worth fixing. The scores measure Jev’s judgment of the supplied evidence. They do not measure production accuracy or certify a deployment. All ten still need verified target-environment acceptance.

## What changed

The baseline assessed main51391fe. Follow-up assessed b9120fa after three reproduced defects were fixed, the proposal review ledger was added, and execution gained a wall-clock deadline with private failure receipts. The same questions, weights and level descriptions were used. Each project now also has domain-specific governance and acceptance criteria.

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

- Account evidence now rejects unnamed or ambiguous opportunity assignments and partial date tokens. Its correctness score moved from0.47 to2.00 out of4.
- Proposal review now stores decisions against exact source, requirement and draft content. Changed, expired or unapproved evidence blocks current export. Its reviewability score moved from2.00 to2.94 out of4.
- CLI and browser execution now terminate workers at a wall-clock deadline, preserve honest modes, and expose content-free execution receipts. The suite passes191tests and10CLIreplays.
- Each project names its business owner, permitted decisions, sensitive-data boundaries and domain-specific metrics. These documents describe acceptance work still required; they are not completed sign-offs.

## What still blocks production

Jev selected source integration as the next priority for all ten after this pass. That is a typed category, not a written technical diagnosis. The code and deployment review independently identify the remaining gaps: authorized source adapters, verifiable freshness and identity, representative domain evaluations, operational acceptance and measured business value.

Proposal Evidence remains experimental. A local OS-account ledger does not establish enterprise identity or prove an export is current. Vulnerability review still requires stronger package-ecosystem identity before real inventory adoption. No comparative superiority over other projects or enterprise deployment is claimed.

## Inspect the assessment

- [Frozen rubric and production gates](../quality/README.md), [machine-readable rubric](../quality/rubric.json) and [exact questions](../quality/questions.json).
- [Baseline summary](../quality/2026-10-02/baseline.json) and [raw distributions / code hashes](../quality/2026-10-02/baseline/).
- [Follow-up summary](../quality/2026-10-02/refinement.json), [raw distributions / code hashes](../quality/2026-10-02/refinement/) and [verification context and unresolved gaps](../quality/2026-10-02/refinement-context.json).
- [Rubric design request](../quality/2026-10-02/rubric-review-request.json) and [Jev’s typed design review](../quality/2026-10-02/rubric-review-response.json).

Resolved model: `jev-1.13.0`. Full requests and responses were retained privately with hashes; public artifacts contain the judgments and source manifests. Requests used only repository code and synthetic/public evidence. No unchanged request was resampled. No new live workflow inference was performed in this hardening pass; the historical September30livecases remain explicitly historical.
