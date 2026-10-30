# Evaluation method

Every agent ships with labeled cases, a rules-only baseline and a committed report. The report answers one question: what does the model add, and what does it cost?

## Cases

`evals/generate_cases.py` builds the set with a fixed seed. Categories enumerate the hard situations practitioners meet: partial receipts, transposed invoice numbers, a loss date one day outside the policy, an innocent latest deploy, a KEV-listed low-CVSS finding. Each case freezes `expected` before any model call. Cases are fictional; nothing is copied from a customer.

## Baseline

`baseline.py` is what a team would build without a model: regex templates, keyword intent, "latest deploy did it", CVSS plus KEV ordering. It shares the rules module with the agent, so the difference measures the reading step alone.

## Metrics

Each `evals/score.py` declares metrics with a kind:

| Kind | Meaning | Example |
|---|---|---|
| `rate` | share of cases where the check is true | route correct, fields exact |
| `mean` | average of a per-case number | flag recall |
| `zero` | a count that must stay 0 | unsafe auto-approvals, permission leaks, false clearance |

One metric is `PRIMARY` and drives the per-category table and the failure list. Cost and latency come from the trace (`gen_ai.usage.*`, provider list prices).

## Running

```sh
python3 -m enterprise_ai eval ap-exception-agent --baseline-only          # no key, no cost
python3 -m enterprise_ai eval ap-exception-agent --provider anthropic     # writes evals/REPORT.md
python3 -m enterprise_ai eval ap-exception-agent --provider openai --limit 20 --no-report
```

Raw per-case results land in `evals/runs/<timestamp>/` and stay out of git.

## Rules we keep

- Labels are never edited to make a run pass. A wrong label is fixed in the generator with a note in the report.
- Initial failures stay in the report's failure table. Regressions are added as test cases.
- A synthetic result is evidence about the harness. Adoption needs the same harness on the adopter's own labeled sample.
