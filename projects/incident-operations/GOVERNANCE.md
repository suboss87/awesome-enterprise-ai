# Incident Investigation Workbench: governance and acceptance

## Ownership and decision boundary

The incident-management owner defines the evidence window; the incident commander or on-call engineer reviews explanations. Output is a timeline with competing hypotheses and missing checks. It must not declare a confirmed root cause, execute commands, remediate services or close an incident.

Logs and traces can expose credentials, user identifiers and infrastructure details. Redact secrets upstream, preserve source IDs and timezone offsets, and record telemetry export completeness. A supplied event window does not prove that all relevant signals were collected.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Timeline ordering agreement with normalized source timestamps, including simultaneous events.
- Supporting-evidence precision and false-contradiction rate, labeled independently by incident reviewers.
- Rate of unsupported causal assertions and instructions to change a running service.
- Useful missing-check recall and investigation preparation time against a timeline-only baseline.

## Controls and remaining proof

Implemented: bounded incident windows, timezone-aware sorting, exact citations and no command execution. Unverified: source ingestion completeness, performance on real incidents and operational benefit. Deployment needs scoped read-only telemetry access, secret redaction and incident-owner review. Preserve the normal incident command and change-approval process; this output is supporting material, not authority to intervene.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
