# Equipment Monitoring Workbench: governance and acceptance

## Ownership and decision boundary

The maintenance-engineering owner sets sensor thresholds and persistence rules; a qualified maintenance engineer reviews observations. Output combines configured threshold states with sourced maintenance context. It must not diagnose faults, predict failure, issue shutdown advice or control equipment.

Telemetry and work orders can reveal operating conditions and personnel details. Export authorized asset records with stable IDs, timestamps and documented unit normalization. The asset owner must approve thresholds, sampling gaps and maximum age. Notes do not replace the approved maintenance manual or safety process.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Threshold-state agreement with an independent oracle for equality, persistence and mixed timezone readings.
- Recall of missing/stale data and sampling gaps; false persistent-breach rate.
- Asset-bound maintenance-summary precision and unsupported-history rate when documents are absent.
- Reviewer usefulness and preparation time versus the existing threshold dashboard and work-order lookup.

## Controls and remaining proof

Implemented: chronological sensor evaluation, configured freshness/gap checks, per-asset citations and missing-history disclosure. Unverified: sensor calibration, live adapter reliability, safety outcomes and equipment-specific thresholds. Deployment needs monitored telemetry ingestion and unit validation, with the existing maintenance/safety authority retained. Run in observation-only mode; this software does not replace a safety instrumented system or an equipment protection control.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
