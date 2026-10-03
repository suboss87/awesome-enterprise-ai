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

Template mode makes **zero model calls**. Replay exercises **one simulated structured call**, not inference. Live mode uses the repository's existing provider for one structured call. No live call or measured benefit is claimed here. AI selects/reorders at most six existing evidence sentences; it cannot author a new fact, owner, action or decision. The full baseline stays in the output even if the selected view omits something. Approved runbook excerpts are untrusted context, not commands. Operators must review even approved excerpts and identifiers for disclosure before live use.

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
