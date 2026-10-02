# Inventory Planning Workbench: governance and acceptance

## Ownership and decision boundary

The supply-planning owner sets lead times and service assumptions; a planner reviews replenishment scenarios. Output is a mean-demand calculation with capacity, budget and supplier-note findings. It must not create purchase orders, allocate budget automatically or present its mean-demand baseline as a seasonal forecast.

Stock, reservations, prices and supplier notes are commercially sensitive. Use authorized, synchronized inventory exports. Daily history must include zero-demand days and end yesterday. Confirm on-order quantities and lead times upstream; the contract does not model receipt dates or supply reliability.

## Acceptance evidence

Before evaluating, the owner must record the target population, labeled holdout, baseline, numerical limits for each metric below and failure handling. These limits require adopter approval; unset limits mean deployment acceptance is unverified. Freeze them before viewing results.

- Exact target quantities, costs and capacity limits against an independent arithmetic oracle.
- Missed budget, capacity and mean lead-time stockout warnings across boundary cases.
- Supplier-note constraint/uncertainty precision and recall, including misleading instructions.
- Planner overrides, preparation time and scenario usefulness versus the existing replenishment spreadsheet.

## Controls and remaining proof

Implemented: contiguous demand-history checks, rational mean-demand arithmetic, integer costs and cited note reviews. Unverified: forecast quality, purchasing outcomes, ERP integration and synchronization between exports. Deployment needs SKU/unit normalization, an agreed snapshot cutoff and planner review in the procurement process. Validate high-variance and intermittent-demand exclusions before using the baseline; no automatic order execution is supported.

Start with [project cases](evaluation/cases.json) and [tests](tests/test_workflow.py). Synthetic replay tests verify rules, not production accuracy. Apply the [shared acceptance rubric](../../quality/README.md), read [current assessments](../../docs/QUALITY.md), and follow [deployment boundaries](../../docs/DEPLOYMENT.md).
