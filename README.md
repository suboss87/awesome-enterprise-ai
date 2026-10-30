<div align="center">

# Awesome Enterprise AI

### Five enterprise AI agents. Each solves one acute back-office problem and reports measured results against a non-AI baseline.

[The agents](#the-agents) · [Run one in two minutes](#run-one-in-two-minutes) · [How they are built](docs/ARCHITECTURE.md) · [How they are measured](docs/EVALUATION.md)

</div>

Most enterprise AI pilots never reach production. The ones that do share a shape: a narrow back-office workflow, a hard baseline, a measured result and a human approval gate. This collection is five such agents, built the way I would build them for a bank or an insurer, small enough to read in an afternoon.

Each agent uses a model for what models are good at: reading messy documents, noticing what a regex cannot, drafting. Plain code owns the decision: tolerances, matching, ranking, the route. Nothing is executed without a person. Every run leaves a trace with tool calls, tokens and cost.

## The agents

| Agent | Acute problem | What the model reads | What the rules decide | Report |
|---|---|---|---|---|
| [AP Exception Agent](projects/ap-exception-agent/) | Invoices cost about USD 9.90 each to process and 20% raise an exception (Ardent Partners 2026). | Any invoice layout, the covering email, embedded instructions, changed bank details. | 3-way match, duplicates, tolerances, the route. | [evals/REPORT.md](projects/ap-exception-agent/evals/REPORT.md) |
| [Support Resolution Agent](projects/support-resolution-agent/) | Median AI support resolution is about 65%, and vendors overstate it by counting deflection. | The ticket, the permitted policy sections, the order. | Eligibility, limits, tenant and role boundaries, the proposed action. | [evals/REPORT.md](projects/support-resolution-agent/evals/REPORT.md) |
| [Incident Investigation Agent](projects/incident-investigation-agent/) | Teams report 40 to 70% MTTR reductions when investigation starts from structured context. | Alerts, logs, deploys, runbooks; ranks hypotheses with evidence. | Timeline ordering, evidence binding, what counts as a confirmed cause. | [evals/REPORT.md](projects/incident-investigation-agent/evals/REPORT.md) |
| [Claims Intake Agent](projects/claims-intake-agent/) | A large carrier cut claim setup time 48% by automating first notice of loss. | FNOL form, police report, estimate, photo notes. | Completeness against coverage, conflict arbitration, triage. | [evals/REPORT.md](projects/claims-intake-agent/evals/REPORT.md) |
| [Vulnerability Triage Agent](projects/vulnerability-triage-agent/) | 71 to 88% of SCA findings are false positives without reachability. | Advisories, reachability hints; writes justifications and tickets. | KEV, EPSS, reachability ranking; VEX status needs a named approver. | [evals/REPORT.md](projects/vulnerability-triage-agent/evals/REPORT.md) |

Live results are committed for the AP Exception Agent. The other four show baseline numbers and a pending note until their live runs complete; the harness and cases are in place.

Every project folder has the same parts: `README.md`, `agent.py`, `baseline.py`, `evals/` with 100 or more labeled cases and a committed report, `GOVERNANCE.md`, `tests/`, `examples/`. The [project standard](CONTRIBUTING.md) lists what each must contain.

## Run one in two minutes

Python 3.11 or newer. Standard library only.

```sh
git clone https://github.com/suboss87/awesome-enterprise-ai.git
cd awesome-enterprise-ai
python3 -m enterprise_ai run ap-exception-agent          # replays recorded model calls, no key needed
python3 -m enterprise_ai serve                           # http://127.0.0.1:8765, shows the tool-call trace
```

With a key, run live and measure:

```sh
export ANTHROPIC_API_KEY=...                             # or OPENAI_API_KEY
python3 -m enterprise_ai run ap-exception-agent --input your-invoice-case.json
python3 -m enterprise_ai eval ap-exception-agent          # 120 cases, agent vs baseline, writes evals/REPORT.md
```

## What you can inspect

- **The decision boundary.** `GOVERNANCE.md` in each project says what the agent does alone, what it proposes, and what it never does.
- **The evidence.** Every finding quotes the source verbatim. The runtime rejects a result whose quote is not in the document.
- **The trace.** Each run records every model call and tool call with OpenTelemetry GenAI attribute names, token usage and cost.
- **The baseline.** The report shows the agent and the rules-only alternative on the same cases, so the model's contribution is a number, not a claim.

## Design notes

[Architecture](docs/ARCHITECTURE.md) explains the runtime and the model/code split. [Evaluation](docs/EVALUATION.md) explains cases, baselines and metrics. [Deployment](docs/DEPLOYMENT.md) describes the data flow, keys and the controls to add before an operational trial. [Security](SECURITY.md) lists the design controls and how to report a problem.

The twelve earlier workflows are preserved at tag [`v0.2-archive`](https://github.com/suboss87/awesome-enterprise-ai/tree/v0.2-archive).

---

Built by [Subash Natarajan](https://github.com/suboss87) · [MIT license](LICENSE)
