# Vulnerability Remediation Planner

A scanner finding does not establish whether an installed component is affected or which team should investigate it. This workflow joins supplied finding IDs to inventory and explicit advisory version lists, then interprets advisory context for an owner review queue.

## Run from the collection root

Explicit offline demonstration (no model call):

```bash
python3 -m enterprise_ai run exposure-review --input projects/exposure-review/examples/input.json --mode replay --responses projects/exposure-review/examples/responses.json
```

For actual inference, configure `OPENAI_API_KEY` in the server environment, then:

```bash
python3 -m enterprise_ai run exposure-review --input projects/exposure-review/examples/input.json --mode live
```

Live mode sends the supplied records to the configured fixed model provider through the collection runtime. Review data-handling requirements before using confidential records. No secrets belong in input examples. The output records live/replay mode; replay is never a model-quality measurement.

## Input contract

`inventory_complete` boolean; `inventory` entries with unique `id`, `package`, `version`, `service`, `owner`; `advisories` with unique `id`, `package`, explicit `affected_versions`, `fixed_versions`, and `text`; `findings` with unique `id`, `inventory_id`, `advisory_id`. Package identity and version matching are exact. Advisory version arrays cannot overlap.

Unknown fields, duplicate identifiers, invalid types and unsupported source quotations fail without producing a successful analysis. Refer to the runnable JSON example for the full shape. Inputs and model output have bounded lengths/counts. No model-generated URLs or commands are executed.

## Output and decisions

Per-finding match state and owner; quoted advisory impact, preconditions and review questions. Empty inventory is flagged even when the caller claims completeness. A listed fixed version is an input assertion, not exploitability clearance.

All results require human review. `findings` expose actionable conditions; `actions` are review recommendations only. The workflow does not write to enterprise systems.

## Evaluation

Exact package/version matching plus severity sorting is the baseline. Eight cases exercise affected/fixed/unlisted versions, absent/partial inventory, package mismatch, unresolved inventory references and adversarial text. Future evaluation needs pinned authentic advisory snapshots, vendor backports and reviewer-labelled applicability. Measure false-safe classifications and owner/fix correctness.

`evaluation/cases.json` freezes eight synthetic cases and expected metrics/finding labels before live evaluation. All recorded responses are authored fixtures. These verify calculation, citation and error-handling contracts, not actual model accuracy. No enterprise deployment validation or measured time savings is claimed.

```bash
python3 -m unittest discover -s projects/exposure-review/tests
```

The tests also reject fabricated quotations, foreign sources, duplicate IDs, missing model responses and invalid domain boundaries. Live evaluation must preserve failures and compare fixed cases with the stated baseline before release claims are upgraded.

## Limits

No scanning, exploitation, runtime reachability analysis, version-range resolution, vendor feed or package upgrades. Callers must normalize package identities and supply authoritative version lists; the model cannot amend them. The tool is not a vulnerability suppression or deployment gate. Advisory prose remains untrusted.

Exact quotation checks cannot guarantee semantic entailment or defeat every prompt injection. Human reviewers must verify substantive interpretations. This is an original bounded reference workflow, not a copy of an upstream enterprise application. See the collection license and security guidance.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.
