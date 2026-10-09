# Inventory Planning Workbench

Planners need a transparent replenishment scenario that exposes storage, cash and supplier uncertainty. This workflow computes a mean-demand proposal, shows constraints separately and interprets notes without permitting the model to invent a forecast or change numeric assumptions.

## Run from the collection root

Explicit offline demonstration (no model call):

```bash
python3 -m enterprise_ai run inventory-decisions --input projects/inventory-decisions/examples/input.json --mode replay --responses projects/inventory-decisions/examples/responses.json
```

For actual inference, configure `OPENAI_API_KEY` in the server environment, then:

```bash
python3 -m enterprise_ai run inventory-decisions --input projects/inventory-decisions/examples/input.json --mode live
```

Live mode sends the supplied records to the configured fixed model provider through the collection runtime. Review data-handling requirements before using confidential records. No secrets belong in input examples. The output records live/replay mode; replay is never a model-quality measurement.

## Input contract

`as_of` ISO day, uppercase three-letter `currency`, integer `budget_cents`, `items`, and `notes`. Each item requires unique `sku`, explicit `unit_of_measure`, nonnegative integer `on_hand`, `reserved`, `on_order`, `lead_days`, `review_days`, `safety_units`, `capacity_units`, `unit_cost_cents`, and contiguous daily `history` ending yesterday with explicit zero-demand days. Positive open-order quantity requires `on_order_available_on`; zero quantity requires null. History entries require `date`, `units`. Notes have unique `id`, existing `sku`, and `text`. All items share one currency.

Unknown fields, duplicate identifiers, invalid types and unsupported source quotations fail without producing a successful analysis. Refer to the runnable JSON example for the full shape. Inputs and model output have bounded lengths/counts. No model-generated URLs or commands are executed.

## Output and decisions

Target = ceil(mean daily units × (lead_days + review_days)) + safety_units. Position = on_hand − reserved + open-order units expected by the end of the lead plus review horizon. Later receipts are excluded from that position and surfaced as a review finding; they still count against storage capacity. Requested = max(0,target − position). Capacity ceiling = max(0,capacity_units − on_hand − on_order). Proposed = min(requested,capacity ceiling). Integer-cent costs are exact. Budget overrun is a finding; no hidden allocation priority. Notes remain separate review annotations.

All results require human review. `findings` expose actionable conditions; `actions` are review recommendations only. The workflow does not write to enterprise systems.

## Evaluation

Mean-demand reorder rules are the baseline, deliberately retained. Eight frozen cases exercise budget/capacity constraints, zero demand, pending receipts, reserved stock, absent notes and hostile notes. Future model evaluation must measure constraint/uncertainty classification and planner correction time, not claim forecasting gains from an LLM.

`evaluation/cases.json` freezes eight synthetic cases and expected metrics/finding labels before live evaluation. All recorded responses are authored fixtures. These verify calculation, citation and error-handling contracts, not actual model accuracy. No enterprise deployment validation or measured time savings is claimed.

```bash
python3 -m unittest discover -s projects/inventory-decisions/tests
```

The tests also reject fabricated quotations, foreign sources, duplicate IDs, missing model responses and invalid domain boundaries. Live evaluation must preserve failures and compare fixed cases with the stated baseline before release claims are upgraded.

## Limits

No seasonality forecast, supplier integration, purchases or optimization guarantee. Capacity is conservative: all pending units are counted, without modeled consumption before arrival. The caller supplies receipt dates; the workflow does not verify them with a supplier or ERP. No service-level or stockout probability is estimated. Budget findings require a planner to prioritize items.

Exact quotation checks cannot guarantee semantic entailment or defeat every prompt injection. Human reviewers must verify substantive interpretations. This is an original bounded reference workflow, not a copy of an upstream enterprise application. See the collection license and security guidance.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).
