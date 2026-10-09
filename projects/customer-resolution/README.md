# Customer Resolution Desk

A support representative turns a customer's request and current order record into a cancellation, return, or escalation plan. The plan includes the remaining refundable balance, policy limit, blocking reasons, and a handoff that distinguishes proposed actions from completed ones.

## Try it

Run from the repository root; Python standard library only:

```sh
python3 -m enterprise_ai run customer-resolution --input projects/customer-resolution/examples/input.json --mode replay --responses projects/customer-resolution/examples/responses.json
python3 -m unittest discover -s projects/customer-resolution/tests -v
```

Replay uses an explicitly hand-authored model response. For actual inference, set `OPENAI_API_KEY` in your environment and replace the replay arguments with `--mode live`. The shared provider records model/response metadata. No refund or order API is called in either mode.

## Business flow

1. Supply the current order, applicable return policy, customer message, and verified tool state.
2. AI classifies the request and cites the customer's words.
3. Rules check cancellation state, delivery date, return window, prior refunds, and monetary limits.
4. Staff receive a reviewable action proposal. Blocked or uncertain tool state prevents an actionable proposal; uncertainty explicitly requires verification before retry.

The example requests a return ten days after delivery. It proposes review of the return, with a maximum of 5,000 minor units and no action performed. Change `tool_state` to `uncertain` to see the blocked handoff.

## Input contract

All fields shown in `examples/input.json` are required except `order.delivered_on`, which is required only for delivered orders. Unknown fields are rejected.

- `as_of`: explicit ISO date, not the machine clock.
- `policy.return_window_days`: integer 0–365; `max_refund_cents`: integer minor units 0–1,000,000,000; `currency` must equal the order currency. A cap in another currency is rejected before inference.
- `order`: unique case-bound `id`, matching `customer_ref`, uppercase ISO-style `currency`, status (pending, shipped, delivered, or cancelled), and nonnegative `total_cents` / `refunded_cents`; refunded cannot exceed total. Future delivery is invalid.
- `message`: case-bound `id`, the same `customer_ref`, and `text` (10,000 characters maximum). A mismatch is rejected before the model call.
- `tool_state`: ready, blocked, or uncertain, supplied by the operator or adapter. Ready means tool state is known, not authorization to execute.

All money must already be normalized to the order's declared currency and minor unit. The reference checks that the message and order carry the same customer reference, then includes currency with every amount. This identifier equality does not authenticate a person or prove the adapter's join is correct. The caller must derive both fields from an authenticated, case-scoped source. No exchange conversion, tax computation, partial-line allocation, return eligibility exceptions, or payment reconciliation is inferred.

## AI and rules

AI handles intent and explicitly requested amounts. Rules control allowed states and maximum amounts. Zero requested amount means unspecified; it is not a refund instruction. Quote matching proves source presence, not correct intent or amount interpretation. Staff must check both.

`actions` contains proposals only. `handoff.completed_actions` is always empty. Neither a model response nor a successful CLI run means a refund occurred.

## Evaluation

`evaluation/cases.json` freezes ten synthetic intended outcomes covering expired returns, duplicate refund exposure, already-refunded orders, uncertain tool outcomes, illegal cancellation, future dates and fabricated citations. Tests check deterministic decisions using replay; they do not measure live model quality.

For a live study, label held-out customer messages independently, compare against keyword intent plus the same policy rules, and measure intent accuracy, wrong action proposals, amount extraction, and escalation correctness. Include messages referencing another order and prompt injection. No customer dataset or production validation is claimed.

## Deployment boundary

Use behind existing authentication and case-level authorization. Minimize personal information before sending inputs to a model. Output is sensitive support data; apply your normal retention policy. There are no outbound messages, refunds, dynamic tools, URL fetches, or credentials in inputs.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.

See the [operational trial and integration acceptance plan](../../docs/ADOPTION-ROADMAP.md) for source-system responsibilities and what must be verified before enterprise adoption.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).
