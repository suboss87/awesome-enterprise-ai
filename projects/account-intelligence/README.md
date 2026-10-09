# Account Review Workbench

Prepare an account review from CRM opportunities and meeting notes. The workbench keeps monetary values in the CRM record, surfaces quoted blockers and next steps, compares explicitly recorded meeting dates with CRM close dates, and flags stale engagement and overdue opportunities.

## Try it

From the repository root:

```sh
python3 -m enterprise_ai run account-intelligence --input projects/account-intelligence/examples/input.json --mode replay --responses projects/account-intelligence/examples/responses.json
python3 -m unittest discover -s projects/account-intelligence/tests -v
```

Replay uses hand-authored fixtures. For actual inference, set `OPENAI_API_KEY`, use `--mode live`, and omit `--responses`. No CRM writes or messages are sent. No dependencies beyond the shared Python standard-library runtime.

## Business flow

1. Export one authorized account's opportunities and meeting records.
2. AI identifies relevant blockers, next steps and explicitly dated close-date proposals in the notes.
3. Rules retain official CRM values, calculate open pipeline totals, compare proposed dates, and check overdue records and engagement freshness.
4. The account owner reviews the evidence and chooses any CRM changes in the existing CRM.

The example reports a meeting proposal for November 1 against an October 15 CRM date. The original CRM date remains unchanged. Neither date is treated as a reliable revenue forecast.

## Input contract

- `as_of`: ISO review date.
- `account`: `id` and `name`.
- `opportunities`: up to 100 records with unique `id`, matching `account_id`, `title`, integer `amount_cents`, three-letter uppercase ASCII `currency`, `stage`, ISO `close_date`, and `next_step` (empty when missing).
- Stages: prospect, qualified, proposal, won, lost. Won/lost amounts are excluded from open pipeline. Values must already use the declared currency's minor-unit convention; no conversion is performed. `pipeline_by_currency` records separate balances. With multiple active currencies, `open_pipeline_cents` and its `currency` are null and a review finding prevents treating the balances as a combined total.
- `meetings`: up to 100 records with unique `id`, matching `account_id`, ISO `date` no later than `as_of`, and `text` up to 10,000 characters.

Unknown fields and cross-account records are rejected. Each observation must quote exactly one known opportunity ID matching its target. A quote without an ID is accepted only when the full meeting names exactly that target opportunity ID. Missing or multiple associations fail validation; even a single supplied opportunity is not assumed to be the subject of unnamed notes. Include explicit opportunity IDs in source exports rather than assigning them by inference.

Date proposals must appear as a complete ISO date token in a quoted meeting passage. A date prefix inside a longer identifier, malformed date or timestamp (including a space/tab before the time) is rejected; ordinary punctuation is allowed. Natural-language dates need normalization or manual review. The account identity check is a consistency control, not authentication.

## Output and boundaries

The result includes recorded account/opportunity facts, quoted observations, a review queue, pipeline totals and `forecast_probability: null`. A model cannot invent an opportunity ID, provide an unquoted date, change CRM values, or insert its own numeric forecast through the output schema.

AI interprets meeting statements; exact citations still do not prove relevance or entailment. Explicit ID checks reduce mistaken associations but cannot determine whether a quoted statement semantically applies to the named opportunity. Reviewers must still check that association. A blocker is an observed statement, not a verified business fact.

## Evaluation

Ten frozen synthetic scenarios cover date discrepancies, overdue deals, missing next steps, closed-deal accounting, stale/no meeting history, account contamination, invented IDs/dates and invalid money types. Tests replay intended observations and check business rules; no live accuracy claim is made.

Compare held-out meeting-to-opportunity labels against keyword matching plus deterministic CRM field checks. Measure correct opportunity association, blocker/next-step precision, date conflicts, unsupported claims and preparation time. Real CRM data and production connectors have not been tested.

## Adoption

Export only records visible to the reviewer; enforce authentication and row permissions before this module. Avoid unnecessary personal information in notes. Apply retention controls to outputs and model requests. There is no outreach, scraping, automatic opportunity update, personal profiling or bulk forecast generation.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).
