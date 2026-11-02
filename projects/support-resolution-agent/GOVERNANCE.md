# Governance: Support Resolution Agent

## Decision rights

| The agent may | Only propose | Never |
|---|---|---|
| Read the ticket customer, that customer's orders and the policy sections visible to the requester's tenant and role. Classify intent, identify the order, draft the reply. | A refund, cancellation, return, replacement or escalation, and the customer reply. Each lands in a queue as `awaiting_approval` or `draft`. | Execute a refund or cancellation. Read another customer's or tenant's order. Quote a hidden section. Grant an exception the policy parameters do not allow. |

`policy.py` computes the route (`resolve`, `escalate`, `refuse`) and the amount from the order state, the policy version in force on the order date and the role limit. The model's proposal is logged beside it; a disagreement is a review finding. Model-only flags (`PROMPT_INJECTION`, `SUSPICIOUS_REQUEST`) can only escalate.

## Data

Tickets and orders are **confidential customer data** with personal data in free text. Send one tenant's records for one ticket. Internal policy sections are **restricted**; visibility is filtered in code before retrieval. Traces hold tool names, token counts and timing, never ticket text.

## Threat model

| Threat | Control |
|---|---|
| Instructions inside the ticket | Data boundary; rules own the route; the flag escalates; a reply promising a refused action is withheld. |
| Cross-customer or cross-tenant order access | `lookup_order` refuses and discloses nothing; the refusal is a finding. |
| Policy leak to a lower role or another tenant | Hidden sections never reach the model; a quote from one is a `PERMISSION_LEAK` and the reply is withheld. |
| Fabricated quotes | Evidence must exist verbatim or `finish` is rejected; citations are re-verified in code. |
| Over-limit refunds | Role limits applied in code; above limit escalates to finance. |
| Model outage or refusal | Fails closed; nothing is proposed. |

## Audit trail

`run_id`, `input_sha256`, model and response ids, every tool call and outcome, tokens and cost, intent, the rules' decision and reasons, verified citations, the model's proposal, reply status and all proposed actions.

## Operations

Kill switch: stop the queue consumer; tickets fall back to the human queue. Rollback: set both refund limits to 0 so every money action escalates. Owners: support operations lead (business), CRM platform team (adapters), security (tenant and role boundaries).

## Acceptance before production

Permission leaks and unauthorised actions must be 0 on the adopter's labeled sample of at least 200 tickets across tenants and roles. Route accuracy and grounded-reply rate must beat the keyword baseline on the same sample. Escalation precision is reviewed monthly.
