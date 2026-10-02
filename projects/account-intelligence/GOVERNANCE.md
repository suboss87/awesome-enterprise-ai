# Account Review Workbench: governance and acceptance

## Ownership and decision boundary

The revenue-operations owner owns CRM definitions; the account owner reviews each meeting observation. Output reconciles recorded opportunities, quoted blockers, next steps and proposed close dates. It must not update CRM, send outreach, invent win probabilities or replace official forecasts.

CRM and meeting notes contain commercial and personal information. Export only the authorized account and preserve literal opportunity IDs in notes. Refresh CRM values before considering edits. All amounts must share a currency/minor-unit convention; the contract does not convert currencies or verify source-system permissions.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Opportunity-association precision, including unnamed notes, multiple IDs and misleading ID prefixes.
- Blocker precision/recall, separating routine procurement progress from actual obstruction.
- Exact date-change extraction, including partial date tokens and unquoted dates.
- Pipeline-total agreement and account-owner correction time versus manual CRM/meeting reconciliation.

## Controls and remaining proof

Implemented: account consistency checks, strict explicit opportunity association, complete quoted date tokens, deterministic pipeline totals and no CRM writes. Unverified: connector permissions, meeting completeness, representative language coverage and real sales outcomes. Deployment needs authorized CRM/note exports and a reviewer queue tied to existing account ownership. Reject ambiguous associations rather than guessing. Exact ID and quotation checks still do not establish semantic relevance; the account owner must confirm each proposed change.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
