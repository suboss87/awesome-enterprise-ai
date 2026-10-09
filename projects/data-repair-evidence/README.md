# Data Repair Evidence

**Experimental · local evidence workflow · human acceptance required**

A validation failed. Someone repaired the data and the next job is green. Did it actually retest the same partition with the same checks?

This small workflow imports genuine GX suite results, binds them to an operator-declared data scope, follows declared dbt dependencies, and prepares a review packet. Its central decision is deterministic: a later passing validation is useful repair evidence only when its scope, full check coverage and test semantics match the initial failure. Corrected data may have a different fingerprint.

## An adoption task

A data reliability analyst receives a failed validation for `prod/orders/2026-09-30`. The data owner repairs the rows and supplies a later export. The analyst imports both runs and the authoritative suite, explicitly maps the native asset and artifact hashes to that logical partition, and attaches the declared dbt graph. The packet identifies the owner, the failed checks, every reachable declared exposure, and any evidence gaps. The owner reviews the packet in the team's existing ticket process. This tool neither performs the repair nor closes that ticket.

| Result | Meaning |
| --- | --- |
| `retest_evidence_ready` | Supplied later evidence passes the unchanged contract; human acceptance remains required. |
| `still_failing` | Comparable complete retest still has a failed check. |
| `unverified` | Scope, contract, coverage, timing, ownership or lineage prevents the repair claim. |

## Run the supplied example

From the repository root, Python 3.10+; no project runtime dependency or API key:

```sh
python3 projects/data-repair-evidence/tools/run.py --input projects/data-repair-evidence/examples/input.json
python3 -m unittest discover -s projects/data-repair-evidence/tests -v
```

The example is a historical snapshot with its own explicit `as_of` clock. Its expected result is `retest_evidence_ready`, `team:data-platform`, two declared consumers, and human review. It does **not** establish current source freshness. For new evidence, import fresh artifacts; the importer defaults to current UTC. Never use an old example clock to approve today's work.

## Import native artifacts

```sh
python3 projects/data-repair-evidence/tools/import_native.py \
  --run projects/data-repair-evidence/examples/native/failed-gx.json \
  --run projects/data-repair-evidence/examples/native/repaired-gx.json \
  --suite projects/data-repair-evidence/examples/native/suite.json \
  --mapping projects/data-repair-evidence/examples/mapping.json \
  --dbt projects/data-repair-evidence/examples/dbt-manifest.json \
  --lineage-complete --max-age-hours 72 --output /tmp/data-repair-packet.json
python3 projects/data-repair-evidence/tools/run.py --input /tmp/data-repair-packet.json
```

Old fixture runs will become `unverified` as they age. `--as-of` exists for explicitly historical evaluation. Supply runs in chronological order. Each mapping requires the raw artifact's SHA-256, exact native datasource/asset, environment, logical asset, dbt unique ID, partition/window and owner IDs. Duplicate bindings reject; competing owners require review. Mapping and suite are trusted operator inputs, **not authenticated source assertions**. The synthetic fixture's partition is an explicit analyst assertion, not inferred from the dataframe.

Supported importer: **GX 1.8.0 suite-result JSON**, its authoritative suite JSON, and the declared dependency subset of **dbt manifest v12**. Other exporter/schema versions and nonempty runtime suite parameters reject. This does not validate the full dbt schema or discover hidden dashboards. `--lineage-complete` is a human attestation; omit it when coverage is uncertain. Missing exposure owners stay visible and block readiness. No SQL is executed.

Limits: 2 MB per native file (at most three run files plus suite, mapping and manifest), 500 KB normalized packet, three runs, 100 checks/run, 500 lineage nodes, 1,000 edges, 20 runbook excerpts of 2,000 characters. Duplicate JSON keys/nonfinite numbers reject. Raw row samples, raw exception text and connection metadata are discarded during normalization. Semantic expectation arguments are retained for exact comparison and never sent to the model.

## Optional AI: sentence prioritization only

```sh
python3 projects/data-repair-evidence/tools/run.py --input projects/data-repair-evidence/examples/input.json --mode replay --responses projects/data-repair-evidence/examples/responses.json
# Optional paid provider request; OPENAI_API_KEY must already be configured:
python3 projects/data-repair-evidence/tools/run.py --input projects/data-repair-evidence/examples/input.json --mode live
```

Template mode makes **zero model calls**. Replay exercises **one simulated structured call**, not inference. Live mode uses the repository's existing provider for one structured call inside the shared 120-second worker boundary. No live call or measured benefit is claimed here. AI selects/reorders at most six existing evidence sentences; it cannot author a new fact, owner, action or decision. The full baseline stays in the output even if the selected view omits something. Approved runbook excerpts are untrusted context, not commands. Operators must review even approved excerpts and identifiers for disclosure before live use.

This is deliberately a modest optional experiment, not an agent or multi-agent system. It may add no value. Keep the template if prioritization does not help a real reviewer. See [evaluation plan](evaluation/README.md) for the comparison required before claiming enhancement.

## Structure

- `workflow.py`: native normalization, graph validation, retest rules and handoff.
- `tools/import_native.py`: bounded artifact reader and explicit mapping.
- `tools/run.py`: local template, replay or live mode.
- `examples/native/`: actual GX-generated synthetic fail/pass results and hash provenance.
- `examples/dbt-manifest.json`: **independently authored minimal fixture**, not a dbt-generated artifact or live connector proof.
- `tests/`: frozen-case regressions and native import round trip.
- `evaluation/`: release gates and unmeasured adoption/AI questions.

See [governance and deployment gaps](GOVERNANCE.md). This is an export-based reference experiment, not production approval. It does not replace GX, dbt, a catalog or an incident platform. Whether this portable comparison is preferable to existing tools remains an adopter decision.


## Collection workspace

This experiment is also available in `python3 -m enterprise_ai serve`. The supplied browser example replays one authored sentence-selection response. For a zero-call template, use the standalone command above. Shared CLI replay:

```sh
python3 -m enterprise_ai run data-repair-evidence --input projects/data-repair-evidence/examples/input.json --mode replay --responses projects/data-repair-evidence/examples/responses.json
```

Live and replay CLI/browser paths use the collection's bounded worker and execution receipts. The local template path makes no network call. Native fixture generation uses a separate development environment; those packages are not runtime dependencies of this project.


## Verified trial, October 3, 2026

The native import round trip and frozen adversarial tests pass. A real browser replay initially exposed different hashes for JSON numbers such as `0.0` and `0`; the corrected canonicalization treats equivalent integral numbers alike while preserving booleans and genuinely different integers. The same browser journey then completed with a successful result, HTTP 200 and no console errors.

One live model call selected the same four evidence sentences as the template. Its output retained the expected owner, both declared consumers, the deterministic status and human-review requirement. This checks provider integration; it demonstrates no AI improvement. That run predates the numeric-hash correction and is retained as historical evidence. The model-facing statements did not change, so no repeat inference was performed merely to obtain a different ordering.

### Assessed coverage and current failures

A successful GX result alone is insufficient: every supplied check must report a positive `element_count`. Population semantics are explicitly supported for `expect_column_values_to_be_null` and `expect_column_values_to_not_be_null` (all rows), and `expect_column_values_to_be_between`, `expect_column_values_to_be_in_set`, and `expect_column_values_to_not_be_in_set` (nonmissing rows). All require explicit `unexpected_count`; range/membership also require explicit `missing_count`. At least one row must have been assessed, and unexpected counts cannot exceed that assessed population. Unknown expectation types remain unverified; missing counts are never inferred as zero. Empty, unknown or all-missing assessed populations produce `unverified`, even when GX reports a pass. This conservative gate does not certify that every business row was checked; operators still own partition coverage and source completeness. Expectations without these population aggregates are not sufficient for readiness in this version.

Outputs distinguish `initial_failed_checks` from `current_failed_checks` (the latest supplied run). Each contains the relevant check IDs and aggregate counts; current failures also appear in the full baseline handoff. The legacy `failed_checks` field remains an alias for initial failures for compatibility. A retest can resolve one check while exposing another; the new failure must remain visible and the status stays `still_failing` when the run is otherwise comparable.
