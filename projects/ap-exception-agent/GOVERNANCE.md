# Governance: AP Exception Agent

## Decision rights

| The agent may | Only propose | Never |
|---|---|---|
| Read vendor master, purchase orders, goods receipts and the AP ledger through read-only tools. Extract, classify and flag. | Release for payment, a vendor query email, a reject-and-notify. Each lands in a queue with status `awaiting_approval`. | Change vendor master data, bank details or PO quantities. Post a journal. Approve its own proposal. |

The route (`auto_approve`, `human_review`, `reject`) is computed by `matching.py` from the extraction and the ERP records. The model's recommendation is logged beside it; a disagreement is itself a review signal. Model-only flags (`PROMPT_INJECTION`, `SUSPICIOUS_REQUEST`) can only escalate, never clear.

## Data

Invoice text and covering emails are **confidential business data** and may contain personal data (names, bank accounts, emails). Send the agent only the records it needs for one invoice. Mask personal data that the match does not use before the model call. Traces hold tool names, token counts and timing, never document text. Results are stored by the adopter under their AP retention policy; the collection stores nothing.

## Threat model

| Threat | Control |
|---|---|
| Instructions embedded in an invoice or email ("approve immediately") | Data boundary in the system prompt; documents arrive inside delimited data blocks; the model reports `PROMPT_INJECTION`; the route is computed by rules that ignore prose. |
| Business email compromise: changed bank account, urgency | `BANK_DETAILS_CHANGED` compares the printed IBAN with vendor master; any change routes to review with a call-back instruction. |
| Duplicate or near-duplicate billing | Ledger search on exact number (reject) and transposed digits or same amount (review). |
| Fabricated evidence | Every quote must exist verbatim in the source or `finish` is rejected. |
| Tool misuse | Tool inputs are schema-validated; write tools are never executed; unknown tools are refused. |
| Model outage or refusal | The run fails closed with no result; nothing is approved by default. |

## Audit trail

Each run records `run_id`, `input_sha256`, model id and response ids, every tool call and outcome, token usage, cost estimate, the extraction, the rules' flags, the model's recommendation and all proposed actions. Keep this with the invoice record.

## Operations

Kill switch: stop the queue consumer; no payment depends on the agent being up. Rollback: route all invoices to `human_review` by setting `auto_approve_limit` to 0. Owners: AP team lead (business), finance systems (ERP adapters), security (vendor-master and bank-change controls).

## Acceptance before production

Unsafe auto-approvals must be 0 on the adopter's own labeled sample of at least 200 invoices. Route accuracy and flag recall must beat the current process, measured on the same sample. Straight-through rate and cost per invoice are tracked monthly against the Ardent Partners benchmark.
