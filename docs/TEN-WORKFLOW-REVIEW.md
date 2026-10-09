# Ten workflows, reviewed against their business decisions

The original ten projects remain the focus. This pass independently inspected
their code and replay tests, repaired reproduced business-boundary gaps, and
tested the five changed browser journeys. All supplied records are fictional.
Passing these checks supports a reference implementation, not production
acceptance by a bank or another enterprise.

| Workflow | Verified controls in this pass and existing tests | Evidence still needed from an adopter |
|---|---|---|
| Customer resolution | Matching message/order customer references, matching policy/order currency, remaining refund balance, blocked uncertain execution | Authenticated support/order/payment binding; current policy authority and reconciliation |
| Incident investigation | Ordered incident window, exact source quotations, hypotheses distinguished from confirmed causes | Telemetry coverage and provenance; independently reviewed incident explanations |
| Vulnerability review | Ecosystem, package and exact version binding; unknown inventory is not clearance | Authoritative SBOM/advisory ingestion, ecosystem-specific version and backport interpretation |
| Business insights | Snapshot chronology, coverage and readiness; exact arithmetic; clarification of undefined profitability | Approved reporting source and metric ownership; representative analyst holdout and comparative value |
| Inventory planning | Dated receipts, shortages before arrival, exact cost/capacity limits and input bounds | ERP SKU/UOM/cutoff binding; verified supplier dates and representative planner decisions |
| Equipment monitoring | Timestamp freshness, consecutive threshold observations and asset-scoped document quotes | Authenticated sensor/work-order feeds; independent alarm/history-summary evaluation |
| Claims intake | Page/document identity, claim-policy conflict exclusion, required-field completeness | Approved OCR and claim/policy binding; independent packet extraction/completeness labels |
| Proposal evidence | Exact-content decisions, source/policy revalidation, controlled export and revocation | Organizational reviewer identity and source authority; representative response entailment review |
| Account review | Opportunity-scoped meeting quotes, literal date changes, separate pipeline currency balances | Authorized CRM/meeting joins; independent blocker/date-change labels and freshness |
| Onboarding | Dependency graph, preserved required flags, inconsistent completion and uncertain policy holds | Authorized complete role checklist and HR/IT completion records; false-ready evaluation |

An onboarding result assesses only supplied tasks. It cannot discover a task
omitted from the checklist. A currency code checks denomination, not whether a
source converted or rounded an amount correctly. Source IDs and freshness flags
remain caller assertions unless a trusted integration proves them. These are
material deployment boundaries.

## What changed

Five workflows gained enforceable controls rather than more maturity claims:
refund-policy denomination, claim-policy identity, pipeline currency separation,
inventory shortages before receipt, and analytics extraction chronology. ASCII
currency checks reject misleading non-ASCII codes. Wide output tables now retain
readable columns and scroll within the result pane.

The [Business Insights planner study](../projects/business-insights/evaluation/planner-2026-10-09/)
preserves a real failed model response. A deterministic clarification rule fixes
that observed ambiguity, including a negated gross-profit mention. The public
results retain the original case outcomes; they do not demonstrate a general
AI advantage.

## Production acceptance

The [frozen quality rubric](../quality/rubric.json) requires independent business
correctness evidence, approved target identity/data/provider controls, operational
load and recovery evidence, accountable owners and truthful provenance. Jev
scores the supplied evidence against these anchors. It does not provide a domain
expert sign-off or certify a deployment. None of the ten has verified target
enterprise acceptance.

A first production trial needs an authorized sandbox, representative permitted
records and an accountable business owner. Platform and security owners must
validate the intended access, retention, provider and operating boundaries.
Each [governance file](../projects/) defines its domain's permitted decisions and
acceptance metrics. Planned work is never counted as completed evidence.
