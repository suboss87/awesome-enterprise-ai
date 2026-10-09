# Quality and deployment limits

I want these projects to be easy to inspect, run and improve. Passing tests is
one part of that. A team also needs to know which decisions the workflow can
support, what its evidence means and where its controls stop.

## What is verified

- Each workspace workflow has a runnable example, CLI, browser journey and tests.
- Business rules check amounts, dates, record identity, evidence and uncertainty.
- The shared runtime enforces execution deadlines and labels replay versus live AI.
- Each project documents permitted decisions and domain-specific acceptance work.
- The [verification record](VERIFICATION.md) includes unsuccessful model answers.

The [ten-workflow review](TEN-WORKFLOW-REVIEW.md) maps tested controls to the
source integrations and business acceptance each workflow still needs.

## Automated review, October 9, 2026

These are Jev's judgments of supplied code, tests and synthetic evidence at
revision `758cfe9bbecf369911fee0172b704214917b2516`, using rubric 1.0.0.
They are uncalibrated evidence scores, not measured accuracy, a comparison with
other products or production approval. Small score differences are not meaningful
proof of improvement. Business Insights and Proposal Evidence had smaller review
packets with partial runtime context.

| Workflow | Evidence score /100 | Next priority |
|---|---:|---|
| Customer resolution | 51.05 | Source integration |
| Incident investigation | 50.41 | Source integration |
| Vulnerability review | 50.66 | Source integration |
| Business insights | 51.53 | Source integration |
| Inventory planning | 51.90 | Source integration |
| Equipment monitoring | 50.04 | Source integration |
| Claims intake | 50.65 | Source integration |
| Proposal evidence | 54.20 | Source integration |
| Account review | 50.95 | Source integration |
| Onboarding | 49.31 | Source integration |

[Per-dimension results](../quality/assessment-summary.json) retain these outcomes.
All ten remain blocked from production designation. Earlier reviews also required
adopter validation; none established enterprise readiness. Data Repair Evidence
remains an experiment, with no demonstrated advantage for its optional AI step.

## What production still requires

Authorized source integrations must establish identity, scope, freshness and
completeness. Caller-supplied IDs and timestamps alone do not prove those facts.
The intended team must evaluate representative permitted cases, agree on error
tolerances and measure the actual business task, including review effort.

Platform and security owners must verify provider/data approval, access controls,
retention, load, recovery and a named operating owner. A business owner must accept
the workflow and escalation path. The [acceptance rubric](../quality/README.md),
[deployment guide](DEPLOYMENT.md) and each project's `GOVERNANCE.md` describe these
requirements. Documentation and green CI do not complete them.
