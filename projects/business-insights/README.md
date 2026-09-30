# Business Insights Workbench

**Turn a business question into a calculation someone can inspect.**

Operations teams often spend more time agreeing what a number means than producing it. This workflow turns a plain-language question into a restricted analysis plan, then calculates the result from a supplied sales snapshot. Every group links back to its source records.

## Try it

From the repository root, with Python 3.11 or later:

```sh
python3 -m enterprise_ai run business-insights \
  --input projects/business-insights/examples/input.json \
  --mode replay --responses projects/business-insights/examples/responses.json
```

The example asks for September net revenue by region. Three source rows produce two matching records, **USD 1,900.00** net revenue, split into North **1,100.00** and South **800.00**. Replay uses a recorded interpretation; it makes no AI call.

For your own question, edit a copy of the input and use `--mode live` with `OPENAI_API_KEY` configured on the server. Or run `python3 -m enterprise_ai serve` and select this workflow in the browser.

## How it works

1. Supply your question, the business date, and a normalized snapshot.
2. AI maps the question to a supported measure, grouping and filters, or asks for clarification.
3. Python validates the plan and calculates with decimal arithmetic.
4. Review the plan, formula, matched record IDs and answer together; export JSON.

AI interprets language. It does not execute SQL, calculate totals, change records or invent missing measures.

## Input contract

See [the complete example](examples/input.json).

| Field | Meaning |
|---|---|
| `question` | The requested analysis; ambiguous or unsupported requests require clarification |
| `as_of` | ISO business date for relative time expressions |
| `records[].id` | Unique source record identifier |
| `date`, `region`, `product`, `currency` | Date and grouping/filter dimensions; three-letter uppercase currency |
| `revenue`, `refund`, `cost` | Nonnegative decimal strings, up to two fractional digits |
| `units` | Nonnegative integer; recorded units, not units net of returns |

Supported measures: gross revenue, net revenue (revenue minus refunds), cost, gross profit (revenue minus refunds and cost), and units. Group by region, product, calendar month, or no dimension. Date filters are inclusive. The snapshot must have unique rows at a consistent grain; adapters must prevent double counting.

## Review and adoption

- Compare answers with an independently calculated report before trusting a new data mapping.
- Mixed currencies cannot be summed as money without an explicit currency choice. There is no FX conversion.
- No matching rows produces `total: null` and a `no_data` finding, not a claim of zero business activity.
- Unknown dimensions, margin, forecasting and growth are outside the contract. The model can still misinterpret a supported question; inspect its returned plan.
- No warehouse connector, row-level authorization or hosted multiuser service is supplied. Use an authorized export for the first trial.

## Verification

```sh
python3 -m unittest discover -s projects/business-insights/tests -v
```

Tests cover exact calculations, filtering, unsupported requests, currency boundaries and invalid plans. [Evaluation cases](evaluation/cases.json) and [collection verification](../../docs/VERIFICATION.md) distinguish recorded tests from live inference and semantic review.
