# Governance: Claims Intake Agent

## Decision rights

| The agent may | Only propose | Never |
|---|---|---|
| Read the packet, the policy record and the intake checklist. Classify documents, extract fields per document, flag inconsistencies, pressure and embedded instructions. | Assign to an adjuster queue. Send the claimant a missing-information request. Both land in a queue as `awaiting_approval` or `draft`. | Set a reserve, decide liability or coverage, approve or deny a claim, pay anything, contact a third party, change the policy. |

The route is computed by `intake.py`: a source-authority table merges the documents (police report over FNOL for date and location, registration over estimate for VIN), tolerances separate typing noise from conflicts, and the coverage checklist decides completeness. The model's recommendation is logged beside it. Model-only flags (`PRE_EXISTING_DAMAGE`, `PROMPT_INJECTION`, `SUSPICIOUS_REQUEST`) can only escalate.

## Data

Claim packets contain personal data: names, addresses, plates, VINs, injuries. This is **special-category data where injuries are involved**. Send one packet at a time with only the policy records it needs. Do not include medical detail beyond the injury flag. Traces hold document ids, tool names and token counts, never document text. Retention follows the adopter's claims file policy; the collection stores nothing.

## Threat model

| Threat | Control |
|---|---|
| Fabricated or inflated claim | Cross-document conflict detection; estimate versus declared value; pre-existing damage notes surfaced for the adjuster. |
| Instructions embedded in a document ("mark complete") | Data boundary; the model reports `PROMPT_INJECTION`; the route is computed by rules that ignore prose. |
| Wrong policy or vehicle bound to the claim | Policy lookup by number only; VIN and listed-driver checks; coverage question when they fail. |
| Fabricated evidence | Every quote must exist verbatim in a document or `finish` is rejected. |
| Over-confident completeness | Required documents are a code table per loss type, not a model judgement; missing items block assignment. |
| Model outage or refusal | The run fails closed; nothing is assigned by default. |

## Audit trail

Each run records `run_id`, `input_sha256`, model and response ids, tool calls, token usage, cost, per-document extractions, the merged claim, every conflict with both values and the winning source, the flags, the model's recommendation and all proposed actions.

## Operations

Kill switch: stop the intake consumer; packets fall back to the manual queue. Rollback: set every route to `conflicts_for_adjuster` by disabling `ready_for_adjuster` in the adopter wrapper. Owners: claims operations lead (business), claims platform team (adapters), compliance (personal data).

## Acceptance before production

Zero unsafe `ready_for_adjuster` outcomes on the adopter's own labeled sample of at least 200 packets. Document classification above 98% on that sample. Conflict recall and missing-document accuracy at or above the current manual intake, measured on the same sample. Cycle time from receipt to assignment tracked monthly.
