# Customer Resolution Desk: governance and acceptance

## Ownership and decision boundary

The customer-service policy owner owns eligibility rules; a support supervisor reviews each proposal against the current order. Output is a cancellation, return or escalation proposal. This workflow must not cancel orders, issue refunds, promise payment or retry an uncertain transaction.

Messages can contain customer identifiers and purchase details. Export only the authorized case, redact unrelated personal information, and obtain order status, prior refunds and policy limits from their owning systems immediately before action. The supplied `tool_state` is a caller assertion, not an independent transaction check.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Intent precision/recall on separate cancellation, return, refund and unsupported-request labels.
- Rate of proposals missing a required blocker for expired windows, prior refunds, caps or uncertain tool state.
- Requested-amount extraction error rate, including unspecified amounts and misleading embedded instructions.
- Supervisor correction rate and handling time versus the existing policy checklist.

## Controls and remaining proof

Implemented: integer refund limits, explicit order currency in the proposal, matching message/order customer references, delivery/window checks, quoted intent and explicit non-execution. The reference equality check is not authentication and cannot prove that a trusted adapter performed the right customer-to-order join. Unverified: source authorization, current order reconciliation, real support outcomes and transaction recovery. A deployment needs read-only order access scoped to the case and supervised handoff to the existing transaction system; any write path requires a separate approval and idempotency design.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
