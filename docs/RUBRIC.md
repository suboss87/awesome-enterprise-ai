# Rubric: what earns a place in this repo

Every project here must be something a real enterprise can adopt and measure. This rubric decides
what gets built. Candidates are scored before any code is written, the scores are public in
[CANDIDATES.md](CANDIDATES.md), and the same criteria are re-applied when a project is finished.

Scoring is done twice: by the maintainer and by Jev (TypeSafe System One) through
`tools/score_candidates.py`, which asks one Score question per criterion over the candidate's
evidence sheet and keeps thresholds in code. A candidate needs a total of 38/50 or more, no criterion
below 3, and a diversity score of 4 or 5 to enter the build queue.

| # | Criterion | 1 | 3 | 5 |
|---|---|---|---|---|
| 1 | Acute pain | Nice to have | A known cost center without numbers | Measured cost today: volume x minutes x wage, SLA penalties, leakage, with public numbers |
| 2 | Code decides | The model must judge eligibility or amounts | Mixed | Eligibility, thresholds, matching and routing are deterministic rules; the model reads, extracts, classifies, drafts |
| 3 | Approval fits | The value needs autonomous writes | Approval is possible but awkward | Output is a proposal into a queue that already exists (ERP, ticketing, CRM, GRC) |
| 4 | Data reachable | Needs proprietary feeds | Standard systems, hard to imitate | Inputs are email, PDFs, exports, logs or tickets that a seeded generator imitates faithfully |
| 5 | Measurable | No natural label | Labels possible, metric unclear | Practitioners already report a metric (straight-through rate, recall, cycle time, cost per item) and a non-AI baseline exists |
| 6 | Adoption evidence | Vendor marketing only | One credible source | Two or more independent public sources show production use with numbers |
| 7 | ROI mechanism | Vague productivity | Plausible | Explicit: who saves what, quoted with source |
| 8 | Not generic | Chatbot over documents, summaries | Specific but common | A named operational workflow with a named owner role and hard edge cases |
| 9 | Buildable simply | Needs orchestration framework, vector DB, fine-tuning | Several services | One agent, 5 to 8 tools, stdlib runtime, replayable |
| 10 | Diversity | Duplicates an existing project | Same industry, different task | New industry or function for this repo |

## What the rubric rejects on purpose

- Agents whose value depends on executing writes without a person.
- Use cases where the model must decide money, eligibility or liability.
- Demos that cannot have a golden set and a baseline.
- Anything a reader can find as a generic tutorial.

## The finished-project bar

A project leaves the build queue only when all of these hold:

1. README states what the model does, what code decides, and what a person approves, in one table.
2. 100+ labeled synthetic cases, labels fixed before any model call, generator seeded and deterministic.
3. `evals/REPORT.md` from a live run: agent vs baseline, two must-be-zero safety metrics, cost and latency per case.
4. Governance page: data boundary, approval gate, audit trail, failure modes, rollback.
5. Tests for rules, generator determinism, replay, and every defect found by an eval (see [FAILURE-LOG.md](FAILURE-LOG.md)).
6. Jev check of the README for overclaim and hedging before publication.
