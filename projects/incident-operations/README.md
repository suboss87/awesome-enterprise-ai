# Incident Investigation Workbench

Incident responders lose time rebuilding timelines across alerts, deployments and logs. This workflow orders those observations and asks the model to surface competing explanations, contradictory observations and unanswered questions. It produces an investigation handoff, with every hypothesis still requiring human review.

## Run from the collection root

Explicit offline demonstration (no model call):

```bash
python3 -m enterprise_ai run incident-operations --input projects/incident-operations/examples/input.json --mode replay --responses projects/incident-operations/examples/responses.json
```

For actual inference, configure `OPENAI_API_KEY` in the server environment, then:

```bash
python3 -m enterprise_ai run incident-operations --input projects/incident-operations/examples/input.json --mode live
```

Live mode sends the supplied records to the configured fixed model provider through the collection runtime. Review data-handling requirements before using confidential records. No secrets belong in input examples. The output records live/replay mode; replay is never a model-quality measurement.

## Input contract

`incident_id`, timezone-aware `window_start`/`window_end`, and 1–200 `events`. Every event requires unique `id`, `at`, `kind` (alert, deployment, log, trace or operator_note), `service`, and `text`. Events outside the window fail. Timestamp ordering is deterministic; simultaneous events are ordered by ID, not presumed causal sequence.

Unknown fields, duplicate identifiers, invalid types and unsupported source quotations fail without producing a successful analysis. Refer to the runnable JSON example for the full shape. Inputs and model output have bounded lengths/counts. No model-generated URLs or commands are executed.

## Output and decisions

A sorted timeline, cited competing hypotheses, missing checks, coverage findings and a reviewer action. At most five hypotheses; each requires exact source quotations.

All results require human review. `findings` expose actionable conditions; `actions` are review recommendations only. The workflow does not write to enterprise systems.

## Evaluation

Chronological sorting and a source-count template are the baseline. A real evaluation should measure hypothesis support, contradiction recall, invented causes, and analyst correction effort against a single-prompt summary. The eight frozen cases cover ordering, simultaneous/timezone events, missing hypotheses, contradictory signals and hostile source text.

`evaluation/cases.json` freezes eight synthetic cases and expected metrics/finding labels before live evaluation. All recorded responses are authored fixtures. These verify calculation, citation and error-handling contracts, not actual model accuracy. No enterprise deployment validation or measured time savings is claimed.

```bash
python3 -m unittest discover -s projects/incident-operations/tests
```

The tests also reject fabricated quotations, foreign sources, duplicate IDs, missing model responses and invalid domain boundaries. Live evaluation must preserve failures and compare fixed cases with the stated baseline before release claims are upgraded.

## Limits

No live telemetry connectors, root-cause certification or remediation. Correlation with a deployment is not causation. Exact quotations prove string provenance, not that the explanation follows logically. Operator questions require review before use. Sources can contain confidential incident data.

Exact quotation checks cannot guarantee semantic entailment or defeat every prompt injection. Human reviewers must verify substantive interpretations. This is an original bounded reference workflow, not a copy of an upstream enterprise application. See the collection license and security guidance.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.
