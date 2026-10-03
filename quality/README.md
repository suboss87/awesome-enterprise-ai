# How I judge the projects

A useful demo is a start. I want each project to survive a harder question: could the team responsible for this business process adopt it, understand its failures and operate it safely?

The [rubric](rubric.json) scores eight dimensions from 0 to 4. The descriptions are evidence anchors, not adjectives. For example, a runnable export-based trial is different from an authorized source integration tested with its intended operators. A passing synthetic example cannot stand in for a representative user evaluation.

| Dimension | Weight | What earns a stronger score |
|---|---:|---|
| Business value | 15% | Measured improvement in the user's task, including review effort |
| Correctness | 20% | Independent domain cases, difficult failures and agreed error tolerances |
| Adoption | 10% | An operator can use authorized source data and recover from mistakes |
| Reliability | 15% | Tested deadlines, failure recovery and actual service objectives |
| Security | 15% | Verified access and data controls in the intended environment |
| Reviewability | 10% | Decisions remain tied to current evidence and an accountable reviewer |
| Distinct value | 10% | A useful, tested difference; comparative claims require an executed baseline |
| Authenticity | 5% | Accurate claims, inspectable evidence and preserved source notices |

The weighted result is `sum(weight × score / 4) × 100`. Read the individual dimensions and probability distributions too. A single number hides too much.

## What Jev does

Jev reviewed the proposed rubric, then scored the actual code, tests, saved synthetic outputs, deployment limits and independently reproduced defects. It returns typed judgments. It does not write a technical rationale or certify a deployment. The dimensions and mandatory gates were accepted as usable in that design review; this is not a validation of the judge against domain experts.

The questions are frozen in [questions.json](questions.json). [Current results](../docs/QUALITY.md) retain the earlier assessment and show the changed evidence. I don't rerun unchanged evidence to obtain a better score.

## Production requires separate acceptance

A high average cannot compensate for a failed production gate. Each project needs:

1. Independent representative correctness evaluation against predeclared limits, with no unresolved critical defect.
2. Verified source authorization, identity and data controls, including approval of the actual model-provider arrangement.
3. Deployment-specific load, fault and recovery checks, monitoring, rollback and a named operator.
4. A business owner who accepts the workflow, escalation process and measured results.
5. Supported provenance and maturity claims, including required notices for reused code.

Missing evidence blocks production designation. The internal target is at least 3 in every dimension plus all gates; it is an improvement target, not an industry standard. Each project's `GOVERNANCE.md` explains its particular decisions, sensitive data and acceptance risks. Keep target-environment sign-offs and sensitive cases in the adopter's controlled system, not a public GitHub issue.

## Reproduce a new assessment

Use `scripts/score_projects.py prepare` with a context file containing actual verification evidence, shared gaps, and a `projects` map covering the selected project slugs. By default all current projects are selected; repeat `--project` on `prepare` to assess only materially changed projects. The context must match that selection exactly. Summaries use the frozen batch membership, so later catalog additions do not invalidate an earlier batch. Completed legacy batches without `context.json` must contain the original ten projects; missing projects cannot silently disappear from a summary. It requires a clean checkout, then snapshots code and tests into a new directory. The manifest binds the entire request before inference, including saved evaluation outputs. Completed older assessments retain their original call-time request hash; they cannot be submitted as new prepared assessments. Review those requests before sending them to an external judge. Requests contain source code and saved synthetic outputs; do not put confidential cases into this public workflow.

```sh
python3 scripts/score_projects.py prepare /private/path/assessment \
  --context /private/path/verified-context.json
# Set TYPESAFE_API_KEY securely in the environment; do not commit it.
python3 scripts/score_projects.py assess /private/path/assessment \
  --project customer-resolution
python3 scripts/score_projects.py summarize /private/path/assessment
```

Call `assess` once for each project. Started calls are not retried automatically, including ambiguous failures. The report validates frozen questions, project identity, source/context bindings, answer distributions and request/response hashes. Keep resolved model versions and raw distributions: later evidence, model versions or wording can change the result. No model score is a measured error rate.

The method follows TypeSafe's [Score](https://docs.typesafe.ai/primitives/score) and [composite scoring](https://docs.typesafe.ai/patterns/composite-scoring) APIs. The weights and production gates are this repository's explicit policy.
