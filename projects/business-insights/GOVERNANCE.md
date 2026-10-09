# Business Insights Workbench: governance and acceptance

## Ownership and decision boundary

The finance or analytics metric owner approves definitions; a qualified analyst reviews the generated plan and source rows. Output is a bounded aggregation over supplied records. It must not execute generated SQL, publish financial statements, forecast results or silently substitute supported measures for unsupported questions.

Records may contain commercial performance data. Restrict exports using existing row permissions and remove unnecessary identifiers. The owning ledger or warehouse defines currency, gross versus net revenue and reporting cutoff. `as_of` guides relative-date interpretation; it does not attest warehouse freshness or completeness. `source_snapshot` carries adapter-declared identity, schema, metric-definition status/version, grain, date coverage, completeness and freshness. It is not cryptographic or authorization proof. A trusted adapter must derive these values from the actual query/export, apply the organization’s freshness and metric-approval rules, and enforce row permissions before calling this workflow.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Agreement of supported measures, filters, date windows and groups with independently authored query plans.
- Exact totals and record lineage against a deterministic financial oracle.
- Clarification recall for unsupported measures, ambiguous definitions and mixed currencies.
- False zero answers on empty selections, plus analyst correction time against saved queries.

## Controls and remaining proof

Implemented: allowlisted plans, decimal arithmetic, source-record lineage, mixed-currency gates, null totals for empty selections, and fail-closed holds for stale/unknown freshness, unapproved/unknown metric definitions, partial/unknown snapshots or periods outside declared coverage. Unverified: authenticity of source metadata, warehouse permission enforcement, actual freshness policy, business-specific metric semantics and representative question accuracy. Deployment needs a governed export adapter and approved metric glossary. Reconcile outputs against existing reports before analyst acceptance; no production database connection or permission boundary ships here.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
