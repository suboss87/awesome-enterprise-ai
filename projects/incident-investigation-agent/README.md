# Incident Investigation Agent

## The problem

Root-cause analysis is the slow part of an incident. On OpenRCA, 335 real failures with full telemetry, the best model finds the (component, reason, time) triple in 11.34% of cases; on ITBench's 59 SRE tasks every model scores below 50%. The usual shortcut, "the latest deploy did it", is fast and often wrong, and a wrong first hypothesis costs the on-call engineer the first hour.

## What the agent does

Given one incident and its telemetry window, the agent reads alerts, logs, deploys, config changes, runbooks and the dependency graph through bounded tools (50 items per call, filtered by service, pattern, level and time). It builds a causal timeline, ranks two to four hypotheses, records for each the one query that could disprove it, names a root cause with evidence ids, and drafts the RCA. Mitigation and the RCA post are proposals only.

## Architecture

```
incident + telemetry ──► agent.py: validate, build read tools, overview per service
                          │  model loop: get_alerts · query_logs · get_deploys · get_config_changes
                          │             search_runbooks · get_dependencies · (propose_mitigation, post_rca_draft = proposals)
                          ▼
                        triage.py: bind evidence ids to telemetry and window
                                   cause before first alert? cause item + symptom alert? disproving check?
                                   route = confirmed | unconfirmed | insufficient_evidence
                          ▼
                        output: summary, metrics, findings, actions awaiting approval, trace
```

`baseline.py` names the most recent deploy or config change on the impacted service before the first alert, else the first failing dependency, and runs the same rules.

## Results

Live evaluation pending (provider credits exhausted on 2026-10-30); baseline numbers below. Full table in [evals/REPORT.md](evals/REPORT.md); 132 seeded cases across 13 categories.

| Metric | Agent | Baseline |
|---|---:|---:|
| Root cause correct (component and reason) | n/a | 69.7% |
| Component correct | n/a | 89.4% |
| Cause start within 2 minutes | n/a | 70.2% |
| Route correct (confirmed / unconfirmed / insufficient) | n/a | 91.7% |
| Innocent component blamed (must be 0) | n/a | 24 |
| Fabricated evidence ids or quotes (must be 0) | n/a | 0 |
| Hypotheses with a disproving check | n/a | 1.0 |
| Cause placed before first symptom | n/a | 91.9% |
| Missing data named (insufficient cases) | n/a | 0.0% |
| Injection resisted (injection cases) | n/a | 100.0% |
| Injection reported as a finding (injection cases) | n/a | 0.0% |

The baseline scores 0% on the delayed-effect deploy, the dependency outage behind an innocent deploy, capacity exhaustion, certificate expiry and the alert storm, and blames an innocent component 24 times.

## Run it

```sh
python3 -m enterprise_ai run incident-investigation-agent --input projects/incident-investigation-agent/examples/input.json --provider openai
python3 -m enterprise_ai eval incident-investigation-agent --baseline-only
python3 -m enterprise_ai eval incident-investigation-agent --provider openai --workers 6     # writes evals/REPORT.md
```

## Decision boundary

The agent reads and drafts. Code decides the route from cited evidence; the model's confidence is logged, never trusted. Nothing is rolled back, restarted or closed without a person. See [GOVERNANCE.md](GOVERNANCE.md).

## Limits

Synthetic incidents with templated log lines; no metrics or traces as sources; `data_corruption` is in the reason enum but has no cases; `get_deploys` and `get_config_changes` return the first 50 items only; the example replay is recorded on the first live run.
