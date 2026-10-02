# Claims Intake Workbench: governance and acceptance

## Ownership and decision boundary

The claims-operations owner defines document requirements; an authorized adjuster reviews completeness and disagreements. Output is an evidence checklist and requests for missing information. It must not decide coverage, deny claims, accuse fraud or approve payment.

Pages may contain identity, financial, medical or incident information. Limit collection to the claim, enforce existing case permissions and use approved extraction/OCR before submission. Requirements must come from the policy/claims authority; a submitted document or email is not proof of policy authority or another document's existence.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Document-type precision/recall, including unreadable material and emails describing absent documents.
- Field extraction accuracy with exact claimant, event date, currency and numeric evidence.
- False-complete rate for wrong-claimant packets, partial documents and missing required fields.
- Adjuster correction rate and preparation time, stratified by document quality and packet type.

## Controls and remaining proof

Implemented: page-to-document binding, literal field checks, conflicting identity/event findings and one-document completeness rules. Unverified: OCR quality, authoritative policy lookup, representative claims and adjuster outcomes. Deployment needs case-scoped ingestion, restricted evidence access and approved retention. An amount discrepancy remains an adjuster review item; a complete checklist is not a payable or covered claim. Evaluate omissions as well as hallucinations before operational use.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
