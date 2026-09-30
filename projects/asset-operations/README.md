# Equipment Monitoring Workbench

Maintenance teams need to distinguish a persistent observation from a transient spike and see the relevant maintenance history. This workflow checks supplied sensor readings against explicit thresholds and links each asset to quoted work-order context for qualified review.

## Run from the collection root

Explicit offline demonstration (no model call):

```bash
python3 -m enterprise_ai run asset-operations --input projects/asset-operations/examples/input.json --mode replay --responses projects/asset-operations/examples/responses.json
```

For actual inference, configure `OPENAI_API_KEY` in the server environment, then:

```bash
python3 -m enterprise_ai run asset-operations --input projects/asset-operations/examples/input.json --mode live
```

Live mode sends the supplied records to the configured fixed model provider through the collection runtime. Review data-handling requirements before using confidential records. No secrets belong in input examples. The output records live/replay mode; replay is never a model-quality measurement.

## Input contract

Timezone-aware `as_of`; `assets` with unique `id`, `metric`, `unit`, numeric `upper_threshold`, integer `persistence`, `max_age_seconds`, `max_gap_seconds`; `readings` with unique `id`, existing `asset_id`, timestamp `at` and numeric `value`; `documents` with unique `id`, existing `asset_id`, `kind` (manual_excerpt, work_order, operator_note) and `text`. One configured metric per asset; normalize sensor units before submission.

Unknown fields, duplicate identifiers, invalid types and unsupported source quotations fail without producing a successful analysis. Refer to the runnable JSON example for the full shape. Inputs and model output have bounded lengths/counts. No model-generated URLs or commands are executed.

## Output and decisions

Readings are sorted by actual timestamps. Only values strictly above the threshold count. Consecutive high readings stop at a normal reading or an excessive sampling gap. Stale/no-data status takes precedence over a breach classification. Model summaries can cite only documents assigned to that asset.

All results require human review. `findings` expose actionable conditions; `actions` are review recommendations only. The workflow does not write to enterprise systems.

## Evaluation

Threshold and persistence rules are the baseline. Eight frozen cases cover persistent/transient observations, threshold equality, stale/missing readings, sampling gaps, absent maintenance history and unordered samples. Future evaluation measures document-grounded history accuracy and reviewer usefulness on independently labelled records.

`evaluation/cases.json` freezes eight synthetic cases and expected metrics/finding labels before live evaluation. All recorded responses are authored fixtures. These verify calculation, citation and error-handling contracts, not actual model accuracy. No enterprise deployment validation or measured time savings is claimed.

```bash
python3 -m unittest discover -s projects/asset-operations/tests
```

The tests also reject fabricated quotations, foreign sources, duplicate IDs, missing model responses and invalid domain boundaries. Live evaluation must preserve failures and compare fixed cases with the stated baseline before release claims are upgraded.

## Limits

No live monitoring connector, predictive maintenance model, physical diagnosis, equipment commands, repair instructions or safety certification. Thresholds and units are supplied by an authorized engineer. Being within threshold does not establish safe operation. Missing history is not proof that maintenance did not occur. This reference is unsuitable as a safety control.

Exact quotation checks cannot guarantee semantic entailment or defeat every prompt injection. Human reviewers must verify substantive interpretations. This is an original bounded reference workflow, not a copy of an upstream enterprise application. See the collection license and security guidance.
