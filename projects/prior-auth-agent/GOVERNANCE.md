# Governance: Prior Authorization Agent

## Decision rights

| The agent may | Only propose | Never |
|---|---|---|
| Read the request, documents and coverage policy. Record verbatim, dated evidence per criterion. Call the deterministic evaluation and clock tools. Draft a provider request. | `propose_decision` (approve, route to a nurse, route to the medical director) and `request_additional_information`. Both are recorded as `awaiting_approval` and never executed. | Make or draft an adverse determination: no tool offers one, and a draft with adverse-decision language is withheld. Change the policy or request. Count a criterion met without a verbatim, dated quote. Approve its own proposal. |

`criteria.py` sets the route from the evidence, request, plan and policy. The model's recommendation is logged beside it. The model can add only `PROMPT_INJECTION`. An approval the rules do not support raises `UNGROUNDED_CLAIM` and goes to a nurse.

## Why approve-only

Public concern about payer AI centres on denials, and regulation follows. For Medicare Advantage, a physician or other appropriate professional must review an adverse medical-necessity decision ([42 CFR 422.566(d)](https://www.law.cornell.edu/cfr/text/42/422.566)). California [SB 1120](https://sd13.senate.ca.gov/news/press-release/december-9-2024/landmark-law-prohibits-health-insurance-companies-using-ai-to) (2024, the Physicians Make Decisions Act, effective 2025-01-01) requires a licensed physician or qualified professional to make medical-necessity denials and bars an algorithm from making them alone; other states have similar bills. Approve-only keeps the agent on the safe side by construction. The worst reading error is a slower route to a person. An approval goes out only after nurse sign-off and only with cited evidence for every criterion. Each likely adverse outcome reaches the medical director with the evidence assembled.

## Decision clock

CMS-0057-F applies from 1 January 2026 to Medicare Advantage, Medicaid, CHIP and federal exchange plans: 72 hours for expedited requests, 7 calendar days for standard. `check_sla_clock` counts calendar time from `received_at` and raises `SLA_AT_RISK` under 24 hours. An at-risk request with all criteria met still gets a proposed approval; one with missing documents goes to a nurse rather than waiting on the provider. Shorter state clocks and information pauses are for the adopter to add.

## Data

Requests and documents are protected health information under HIPAA. Run the agent under the plan's BAA with the model provider, with zero data retention where offered. Send one request and only its documents. Traces hold tool names, outcomes, tokens and timing, never document text. Results stay in the UM system under the plan's retention policy. Every case in this repository is fictional.

## Threat model

| Threat | Control |
|---|---|
| Instructions on a fax cover ("pre-approved, skip review") | Data boundary in the prompt; the model reports `PROMPT_INJECTION` and a nurse reviews. Rules ignore prose. |
| A note that overstates ("six weeks of therapy") | Duration comes from dated visits, not sentences. Tests cover 33 to 41 days of visits under a "six weeks" note. |
| Hallucinated or stale evidence | Quotes must be verbatim, from an allowed document kind and dated. Out-of-window evidence is not used. |
| Model pushes approval | Code decides; an unsupported approval raises `UNGROUNDED_CLAIM`. |
| Model outage or refusal | The run fails closed; the request stays in the manual queue with its clock. |

## Model risk and audit

Inventory the agent under the plan's AI governance program (in the style of the NAIC model bulletin). It has no decision authority. Validate with `evals/` on at least 200 of the plan's closed requests per policy, labeled from final nurse and physician decisions. Monitor nurse overrides of proposed approvals, route agreement, finding recall and time to decision. A change to prompt, model or rules triggers a re-run.

Each run records `run_id`, `input_sha256`, model and response ids, every tool call and outcome, every evidence record, criterion statuses, findings, the clock, the model's flags and recommendation, proposals, `prompt_version`, tokens and cost. Keep it with the authorization file to answer an appeal or audit.

## Operations

Kill switch: stop the queue consumer; requests return to the manual queue. Rollback: pin the previous `PROMPT_VERSION` and rules commit, or disable `approve_proposed` in the adopter wrapper so every request goes to a nurse. Owners: UM director (policy translation, thresholds), medical director (escalations), compliance (state UM law, CMS), IT security (PHI boundary).

## Acceptance before production

On the plan's validation sample, unsafe approvals and adverse-decision language must both be 0. Criterion status accuracy and finding recall must equal or beat the current nurse checklist. The medical director signs each service's policy translation before the first live request.
