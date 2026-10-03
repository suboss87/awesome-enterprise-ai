# Proposal Evidence Workbench: governance and acceptance

## Ownership and decision boundary

The bid/proposal owner is accountable for submitted answers; a product subject-matter owner reviews each capability claim. Output is a requirement matrix with drafts, gaps and conflicts. It must not certify compliance, submit bids or approve its own answers.

Packets contain confidential product capabilities and buyer requirements. Obtain approved, versioned material from document owners and refresh it before review/export. Manual source approval labels are caller-supplied. GitHub-bound drafts instead pin an operator manifest file and refresh exact repository/path/blob sources internally before approval/export. Approval authority remains the local policy owner; organizational document-owner identity is not verified. Current UTC checks alone cannot discover an upstream revocation missing from a manual export.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Unsupported-claim rate and evidence entailment precision judged against requirement-specific labels.
- Recall of contradictions, expired/revoked evidence and missing requirement coverage.
- Approval invalidation agreement after edits to requirements, drafts or any source, including uncited sources.
- Reviewer corrections and preparation time against approved-answer lookup; stale approved exports are counted separately.

## Controls and remaining proof

Implemented: exact citations, dated approval gates, local SQLite review ledger with content binding/revision checks, and an optional read-only GitHub adapter with pinned operator policy, immutable provenance, internal refresh and a total execution deadline. Public synthetic GitHub connectivity was verified; private enterprise authorization, organization roles, representative bid evaluation and deployment operations remain unverified. The ledger identifies the local OS account, not an enterprise approval role. Keep the experimental status until source freshness and authorized review are established in the target environment; approved local output still needs the normal bid approval process.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
