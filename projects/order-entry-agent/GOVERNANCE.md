# Governance: Order Entry Agent

## Decision rights

| The agent may | Only propose | Never |
|---|---|---|
| Read the customer document, the customer master, price lists, cross-references, inventory and open orders through read-only tools. Classify the document, record what it says and flag embedded instructions. | `create_sales_order` and `send_customer_query`. Both are recorded with status `awaiting_approval` and are never executed. | Set a price, a quantity or a SKU that the rules did not derive. Change the customer master, a price list, a cross-reference or a credit hold. Release a held order. Approve its own proposal. |

`ordering.py` sets the route (`auto_create`, `desk_review`, `reject`) from the recorded reading and the ERP records. The order is always priced at the customer's list price. The model's expected route is logged next to it, and a disagreement is a review signal. The model can only add `PROMPT_INJECTION`. It cannot clear a finding. When the model picks a SKU that the resolver did not pick, the line goes to the desk as `AMBIGUOUS_PART`.

## Data

Customer POs and emails are confidential business data. They contain personal data: buyer names, email signatures and delivery addresses. Price lists and credit balances are commercially sensitive. Send the agent only one document and the records for that customer's order. Traces hold tool names, token counts and timing, never document text. The adopter keeps results with the sales order under its retention policy. The collection stores nothing.

## Threat model

| Threat | Control |
|---|---|
| Instructions in a PO or email ("pre-approved, skip credit checks") | Data boundary in the prompt. The model reports `PROMPT_INJECTION`, which routes to the desk. Rules ignore prose. |
| Misread or invented lines | Each line quote must be one verbatim line of the document that prints the quantity, the price and the part code, or the line is `UNGROUNDED_LINE`. A reader that "corrects" a stale price to list no longer matches its quote. |
| Wrong item from a vague description | Parts resolve in code from the quote, not from the model's paraphrase. Two close candidates make the line `AMBIGUOUS_PART`. |
| Wrong customer or ship-to | The printed name or account must appear in the document. Ship-to must match an address on file after normalization. |
| Duplicate orders | Same customer and PO number rejects. Same lines within the window under a new PO goes to the desk. |
| Credit exposure | Credit hold always stops entry. Open AR plus the order above the limit goes to credit. Totals above the touchless limit go to the order desk lead. |
| Model outage or refusal | The run fails closed. The desk keys the order as today. |

## Audit trail

Each run records `run_id`, `input_sha256`, the model and response ids, every tool call and its outcome, the recorded header and lines with quotes, the resolver result per line, the findings with details, the model's flags and expected route, the proposals, `prompt_version`, token use and cost. Keep this record with the sales order.

## Operations

To stop the agent, turn off the queue consumer. Orders keep arriving in the shared inbox and the desk enters them by hand. To roll back, pin the previous `PROMPT_VERSION` and rules commit. To make nothing touchless, set `max_order_total_without_approval` to 0; every order then raises `OVER_APPROVAL_LIMIT` and goes to the desk. Owners: the order desk lead (business rules and tolerances), credit (credit limits and holds), ERP systems (adapters and the release step) and security (data boundary).

## Acceptance before production

On the adopter's own labeled sample of at least 200 recent orders, both must-be-zero metrics must be 0: auto-created when review or reject was expected, and auto-created with a wrong line. Line accuracy and finding recall must equal or beat the current manual entry error rate on the same sample. Each month, track touchless rate, desk minutes per order, credits issued for entry errors, and route agreement with the desk. A change to the prompt, model, rules or policy triggers a re-run and a new report.
