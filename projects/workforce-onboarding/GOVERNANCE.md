# Onboarding Readiness Desk: governance and acceptance

## Ownership and decision boundary

The onboarding operations owner coordinates readiness; HR and the relevant IT/security task owner review policy applicability and completion. Output identifies required tasks, unfinished prerequisites and inconsistent completion. It must not provision access, mark work complete or authorize a starter's access rights.

Starter role, location and task records are personal employment data. Use minimal authorized exports and current policy excerpts from HR/security owners. Task status needs confirmation from the system responsible for completing that task. The workflow checks supplied records; it cannot verify that access or equipment actually exists.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Policy applicability agreement by role/location, including ambiguous and conflicting excerpts.
- False-ready rate for required tasks, unfinished prerequisites and inconsistent completion records.
- Dependency-closure agreement for optional prerequisites, cycles and missing task IDs.
- Owner correction rate and time to prepare a readiness review versus the existing onboarding checklist.

## Controls and remaining proof

Implemented: immutable required flags, dependency closure, cycle rejection, uncertainty blocking and cited policy matches. Unverified: authoritative policy versions, actual provisioning status, HR integrations and organizational outcomes. Deployment needs role-restricted HR/task exports with a documented status cutoff. A ready result describes the supplied snapshot, not access authorization. Keep provisioning and task completion within existing owner-approved systems and recheck changed dependencies before the start date.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
