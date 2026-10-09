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

1. Supply your question, the business date, a normalized snapshot, and its declared source metadata.
2. The workflow checks completeness and date coverage before interpreting the question.
3. AI maps the question to a supported measure, grouping and filters, or asks for clarification.
4. Python validates the plan and calculates with decimal arithmetic only inside the covered period.
5. Review the plan, formula, matched record IDs, source snapshot and answer together; export JSON.

AI interprets language. It does not execute SQL, calculate totals, change records or invent missing measures.

The planner's `plan.status` describes whether it could form a supported plan. The outer `answer_status` describes the workflow outcome: `calculated` means a value was produced, while `withheld` means a review finding prevented an answer. A ready plan can still be withheld when currencies or filters need attention, or when no rows match. Both outcomes remain subject to human review.

## Input contract

See [the complete example](examples/input.json).

| Field | Meaning |
|---|---|
| `question` | The requested analysis; ambiguous or unsupported requests require clarification |
| `as_of` | ISO business date for relative time expressions |
| `source_snapshot.source_system`, `snapshot_id` | Adapter-declared source and immutable extract identity |
| `source_snapshot.exported_at`, `data_as_of` | Extract time with timezone and last date represented |
| `source_snapshot.schema_version`, `metric_definition_version` | Versions used to interpret fields and business measures |
| `source_snapshot.metric_definition_status` | Must be `approved`; unknown or unapproved business definitions withhold totals |
| `source_snapshot.row_grain` | What one record represents; the adapter must prevent duplicate business events |
| `source_snapshot.coverage_start`, `coverage_end` | Inclusive dates for which the adapter asserts the extract is complete |
| `source_snapshot.completeness` | Must be `complete`; `partial` or `unknown` returns a withheld result before an AI call |
| `source_snapshot.freshness` | Must be `current`; the trusted adapter applies the organization’s freshness window |
| `records[].id` | Unique source record identifier |
| `date`, `region`, `product`, `currency` | Date and grouping/filter dimensions; three-letter uppercase currency |
| `revenue`, `refund`, `cost` | Nonnegative decimal strings, up to two fractional digits |
| `units` | Nonnegative integer; recorded units, not units net of returns |

Supported measures: gross revenue, net revenue (revenue minus refunds), cost, gross profit (revenue minus refunds and cost), and units. Group by region, product, calendar month, or no dimension. Date filters are inclusive. An omitted boundary means the corresponding complete snapshot boundary. A requested period outside coverage is withheld, never silently truncated. The snapshot must have unique rows at a consistent grain; adapters must prevent double counting.

## Review and adoption

- Compare answers with an independently calculated report before trusting a new data mapping.
- Bind this metadata inside a trusted export adapter. It is declared provenance, not cryptographic proof: the local workflow cannot authenticate a source, enforce warehouse row permissions, or prove that an adapter's completeness claim is true.
- The adapter must set `freshness: current` only after applying the adopter’s approved freshness window, and set `metric_definition_status: approved` only for an owner-approved version. This workflow fails closed on stale, unknown or unapproved states; it cannot verify the adapter's assertions.
- Mixed currencies cannot be summed as money without an explicit currency choice. There is no FX conversion.
- No matching rows produces `total: null` and a `no_data` finding, not a claim of zero business activity.
- When a finding blocks the answer, `answer_status` is `withheld`; inspect the finding before using the plan or metrics.
- Unknown dimensions, margin, forecasting and growth are outside the contract. The model can still misinterpret a supported question; inspect its returned plan.
- No warehouse connector, row-level authorization or hosted multiuser service is supplied. Use an authorized export for the first trial.

## Verification

```sh
python3 -m unittest discover -s projects/business-insights/tests -v
```

Tests cover exact calculations, filtering, unsupported requests, snapshot completeness and coverage, currency boundaries and invalid plans. [Evaluation cases](evaluation/cases.json) and [collection verification](../../docs/VERIFICATION.md) distinguish recorded tests from live inference and semantic review.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).
