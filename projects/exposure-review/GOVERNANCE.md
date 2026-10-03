# Vulnerability Remediation Planner: governance and acceptance

## Ownership and decision boundary

The vulnerability-management owner sets triage policy; the affected service owner and security analyst review each finding. Output distinguishes exact version matches from missing inventory and summarizes advisory text. It must not clear exploitability, authorize patching, suppress scanner findings or generate exploitation instructions.

Inventory contains sensitive service and ownership information. Use authorized scanner and software-inventory exports with collection times. An advisory publisher owns applicability facts; prose and version arrays need reconciliation before use. Exact package strings do not establish ecosystem identity, vendor backports or version-range semantics.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Agreement of deterministic package/version states with a curated inventory-advisory oracle.
- False fixed-version classifications across ecosystem collisions, vendor builds and incomplete inventory.
- Advisory impact/precondition precision and unsupported exploitability assertions.
- Analyst triage time and correction rate versus exact matching plus manual advisory reading.

## Controls and remaining proof

Implemented: exact matching, explicit unknown states, inventory-coverage warning and source quotations. Unverified: authoritative package namespaces, SBOM ingestion, version-range evaluation and real security-team outcomes. Deployment needs a validated package-identity adapter, fresh scanner links and owner routing. Keep scanner alerts active until the existing security process resolves them; a fixed-version match is not a security clearance.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).

## Package identity boundary

Require an explicit ecosystem and normalized name on every inventory and advisory row. Review ecosystem mismatches as unresolved identity, including same-name fixed-version collisions. Caller metadata remains authoritative; private registry origin, platform qualifiers, SBOM parsing and version ranges are not resolved. New `evaluation/ecosystem-cases.json` is a separately identified contract migration; the original frozen evidence is retained unchanged.
