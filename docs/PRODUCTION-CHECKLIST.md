# Production acceptance

These are my side projects for recurring enterprise problems. I publish the code,
examples, evaluations and limits so another team can inspect them and decide
whether a workflow belongs in its own environment. I do not publish customer
records or claim deployments that have not been verified.

**Current decision: no workflow has verified enterprise production acceptance.**
The code is public and runnable. The protected batch path and container checks
cover execution and artifacts; they do not approve a business process.

## Repository delivery checks

- [x] Each workspace workflow has its own problem statement, implementation,
  examples, evaluation cases, tests and governance boundary.
- [x] Model interpretation is separated from deterministic amounts, dates,
  prerequisites and evidence checks.
- [x] Live and recorded modes are explicit; provider failures do not become demos.
- [x] Work runs with a deadline and produces sanitized failure metadata.
- [x] Private run directories reject reuse; completed results have hash-bound
  receipts and are excluded from ordinary stdout logs.
- [x] A pinned non-root container and automated isolated example checks are supplied.
- [ ] An adopter has approved source access, identities and provider/data handling.
- [ ] Independent representative business evaluation meets predeclared limits.
- [ ] Intended-environment load, failure recovery and rollback are accepted.
- [ ] Business, security/data and operational owners have signed the exact revision.

The checked items describe delivered code, not certification. Actual CI runs
must pass for the selected revision. Failing or unrun checks block that release.

## Every workflow has a different acceptance problem

All entries below are **pending adopter evidence and sign-off**. Use the linked
governance metrics; do not replace them with a model score or a test count.

| Workflow | Intended owner | What must be proved in the target environment |
|---|---|---|
| [Customer Resolution](../projects/customer-resolution/GOVERNANCE.md) | Support policy owner | Authorized customer/order/policy join; currency and remaining refund limits; correction rate and supervisor handling time; no automatic payment |
| [Incident Investigation](../projects/incident-operations/GOVERNANCE.md) | Incident commander | Authorized telemetry and incident window; no invented causes; quoted evidence and useful next checks on independent incident packets |
| [Vulnerability Review](../projects/exposure-review/GOVERNANCE.md) | Vulnerability owner | Authoritative inventory/advisory identity; ecosystem, exact version and backport limits; unknowns never count as clearance |
| [Business Insights](../projects/business-insights/GOVERNANCE.md) | Metric/data owner | Approved reporting snapshots and metric definitions; representative held-out questions; undefined measures withheld; exact results and baseline comparison |
| [Inventory Planning](../projects/inventory-decisions/GOVERNANCE.md) | Supply-chain planner | Authorized SKU/UOM and supplier dates; shortages before arrival; budget/quantity limits; planner corrections on real permitted scenarios |
| [Equipment Monitoring](../projects/asset-operations/GOVERNANCE.md) | Maintenance owner | Sensor/asset identity, fresh timestamps, verified threshold history; correct alarms and omissions; no autonomous safety action |
| [Claims Intake](../projects/claims-intake/GOVERNANCE.md) | Claims operations owner | Approved OCR and claim/policy/document binding; independent completeness and conflict labels; no coverage or settlement decision |
| [Proposal Evidence](../projects/proposal-operations/GOVERNANCE.md) | Bid/document owner | Organizational reviewer authority, current approved sources, revocation and export checks; representative entailment review; experimental hold remains |
| [Account Review](../projects/account-intelligence/GOVERNANCE.md) | Revenue-operations owner | Authorized CRM/meeting joins; scoped blocker and date-change labels; separate currency balances; no invented forecast or CRM write |
| [Onboarding](../projects/workforce-onboarding/GOVERNANCE.md) | HR/IT process owner | Authoritative complete role/task catalog, current completion records and dependency checks; false-ready rate including missing tasks |
| [Data Repair Evidence](../projects/data-repair-evidence/GOVERNANCE.md) | Data product owner | Authorized asset/run/lineage identity; complete unchanged retest semantics and meaningful population; no false-ready repair; optional AI must show benefit; experimental hold remains |

## Sign-off record

Copy this record into the organization's controlled system. Keep business cases,
personal identities, credentials, security evidence and approvals out of public
issues and commits. Do not prefill an approval with an assistant's name.

| Required field | Record before approval |
|---|---|
| Scope | Workflow, decision supported, prohibited actions and intended operators |
| Exact release | Git commit, image digest if used, model snapshot, prompt/schema/configuration hashes |
| Authorized inputs | Source systems, access scope, identity binding, completeness, freshness and source owner |
| Data/provider approval | Classification, allowed fields, region/retention, encryption, approved provider agreement and secret injection |
| Evaluation plan | Representative population, frozen holdout hash, baseline, independent labels, numerical acceptance limits and review protocol fixed before inference |
| Observed outcomes | All cases, failures, corrections, false-ready count, baseline comparison, latency/cost and uncertainty; evidence hashes |
| Operations | Job identity, capacity/load result, monitoring, failure handling, run retention, backup/restore and rollback rehearsal |
| Residual risks | Unsupported cases, open defects, mitigation, responsible owner and expiry/review date |
| Decisions | Named business, security/data and operations owners; approve/reject/hold; date; evidence reference |

Approval is valid only for that scope and revision under the organization's
normal authorization process. Reevaluate material changes to source semantics,
model/prompt, policies, identities or deployment. A signed record cannot replace
missing evidence, and a model-generated statement cannot supply human authority.
