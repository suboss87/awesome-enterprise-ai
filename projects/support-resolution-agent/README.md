# Support Resolution Agent

**Problem.** Median AI support resolution is about 65%, and vendors overstate it by counting deflection. The hard tickets are the return one day outside the window, the order that belongs to someone else, the section only a manager may see, the ticket that tells the bot to ignore the policy.

**What the agent does.** It reads one ticket, looks up the customer's order, searches only the policy sections the requester's tenant and role may see, drafts a reply with verbatim citations and proposes an action. Code decides eligibility, applies the role's refund limit and verifies every citation. Nothing is executed; a person approves.

## Architecture

```
ticket + records ─► validate ─► Agent loop (model)
                                 │ get_customer · lookup_order (refuses other customers/tenants)
                                 │ search_policy (tenant + role + effective-date filter, then rank)
                                 │ get_limits · propose_action* · send_reply*   (*recorded, never run)
                                 ▼ finish: intent, order, cited_policy, draft_reply, proposed_action
                    policy.py ─► version in force on order date → eligibility → role limit → route
                                 citation check (verbatim, visible) → leak / grounding findings
                    build_output ─► summary, metrics, findings, actions awaiting approval
```

## Results

142 labeled synthetic tickets across 17 categories, two tenants, three policy versions, three requester roles. Baseline: keyword macro on the same rules. Full table in [evals/REPORT.md](evals/REPORT.md).

| Metric | Agent (claude-opus-5-5, 2026-10-30) | Baseline |
|---|---:|---:|
| Route correct (resolve / escalate / refuse) | 100.0% | 83.1% |
| Action correct (type, amount, order) | 100.0% | 81.0% |
| Permission leaks (must be 0) | 0 | 0 |
| Unauthorised resolve actions (must be 0) | 0 | 0 |
| Reply grounded in visible policy | 99.3% | 86.6% |
| Escalation flag correct | 100.0% | 88.7% |
| Prompt injection resisted (injection cases) | 100.0% | 100.0% |
| Intent correct | 99.3% | 80.3% |
| Resolved without a person (rate) | 50.0% | 40.1% |
| Cost per ticket | USD 0.085 | 0 |
| Latency p50 / p95 | 15.5 s / 20.7 s | under 1 s |

The first live run scored 87.5% on injection resistance and 97.9% on escalation; both were code and prompt defects, not model errors, and are logged in [docs/FAILURE-LOG.md](../../docs/FAILURE-LOG.md). The one remaining intent miss is a ticket that says "refund" for a delivered order with nothing missing; the agent read it as a return and still refused correctly.

The baseline is a keyword macro on the same rules. It fails every ambiguous-intent and two-orders case and misreads paraphrases.

## Run it

```sh
python3 projects/support-resolution-agent/evals/generate_cases.py
python3 -m enterprise_ai eval support-resolution-agent --baseline-only
python3 -m enterprise_ai run support-resolution-agent --input projects/support-resolution-agent/examples/input.json --provider openai
```

Fill the agent column with `python3 -m enterprise_ai eval support-resolution-agent --provider openai --workers 6`.

## Decision boundary

The model classifies, finds, drafts and flags. `policy.py` picks the policy version in force when the order was placed, computes eligibility from order state and policy parameters, caps amounts by refundable balance and role limit, and routes. A rejected model proposal is logged as `MODEL_DISAGREES`. A citation from a hidden section is a `PERMISSION_LEAK` and the reply is withheld. See `GOVERNANCE.md`.

## Limits

Synthetic English tickets, two fictional tenants, seven policy topics. Policy parameters (windows, goodwill days) arrive as structured fields beside the prose; a real policy store must supply them. Partial refunds are whole lines. Retrieval is token overlap over a few sections, deliberately. Synthetic results say nothing about an adopter's tickets until the harness runs on their labeled sample.
