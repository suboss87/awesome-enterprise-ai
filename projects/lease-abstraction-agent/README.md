# Lease Abstraction Agent

**Problem.** Lease administrators turn each commercial lease package (lease, amendments, commencement date memorandum, estoppel) into an abstract and a calendar of critical dates. A missed renewal notice deadline can cost the option. JLL and DealSumm report abstraction accuracy up from 65% to "92-98%+", review time down from 130 to 85 minutes per lease and 30% lower cost per abstract, with people validating each abstract ([Databricks customer story](https://www.databricks.com/customers/jll/dealsumm)). Cushman & Wakefield says an abstract took "six hours to three days" before automation ([Unframe customer story](https://www.unframe.ai/customer-stories/cushman-wakefield)). The hard cases are precedence and arithmetic: an amendment that extends the term, a memorandum that sets the dates after "on delivery", an estoppel that certifies the old expiration, rent per square foot, and a notice window counted back from a month-end expiration.

**What the agent does.** It reads every document in any layout and states what each one says, field by field, with a verbatim quote. It flags hidden instructions and drafts a summary. `abstraction.py` makes every decision and computes every number.

| The model | The code (`abstraction.py`) | A person |
|---|---|---|
| Reads 17 fields per document (parties, premises, area, dates, term, rent as written, escalation, renewal and termination options, deposit, CAM, holdover, consent, certified rent) and quotes each one. Flags `PROMPT_INJECTION`. Drafts the summary. | Checks that each quote is in its document and shows the stated figures. Resolves each field by precedence: latest amendment, then commencement memorandum (dates only), then lease. The estoppel only certifies. Computes the expiration, rent schedule, rent in effect, notice windows, alert dates and the register inside the horizon. Applies the portfolio rules, detects conflicts and decides the route. Withholds a summary that has a figure not in the abstract. | The lease admin lead approves `ready_for_entry`, resolves `conflicts_for_review` and requests documents for `incomplete_documents`. |

```
lease package + portfolio rules ─► validate ─► Agent loop (model)
        │ get_document · search_documents · record_abstract · compute_critical_dates · check_rules (deterministic)
        │ draft_abstract_summary* · submit_to_lease_system*   (*recorded only)
        ▼ finish: flags, recommended_route, rationale, evidence
abstraction.py ─► ground → precedence → dates and rent → register → rules → route → summary check → output
```

## Results

The set has 119 labeled synthetic lease packages in 17 categories, with three lease layouts (articles, numbered paragraphs, basic lease information page) and formal or letter amendments. The baseline is a regex template that reads the lease and the newest other document, then uses the same rules. Agent numbers will come from the live run in `evals/REPORT.md`; baseline numbers come from `--baseline-only`.

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct (ready / conflicts / incomplete) | live run pending | 79.0% |
| Marked ready for entry when it needed review or documents (must be 0) | live run pending | 6 |
| Released summaries with a figure not in the abstract (must be 0) | live run pending | 0 |
| Commencement, expiration and next notice deadline exact | live run pending | 98.3% |
| Monthly rent in effect exact | live run pending | 82.4% |
| Critical dates inside the horizon exact (set match) | live run pending | 76.5% |
| Expected conflicts found (field and resolution) | live run pending | 0.833 |
| Reported conflicts that were expected | live run pending | 0.881 |
| Statements grounded in verbatim quotes | live run pending | 79.0% |
| Prompt injection flagged (injection cases) | live run pending | 57.1% |

The template reads dates well because the shared rules apply precedence once a line is found. All 25 route errors come from reading. Nineteen leases state rent per rentable square foot, so the template finds no rent and routes them `incomplete_documents`. Six packages are marked ready when they are not: two where it reads the estoppel instead of the amendment and accepts the old expiration, two where it reads only the first of two disagreeing areas, and two where the injection is phrased outside its blocklist. It also misses prose rent in letter amendments and the rent rows of the earlier of two amendments. A perfect reader passed through the same rules reproduces every label (a test confirms this).

## Run it

```sh
python3 projects/lease-abstraction-agent/evals/generate_cases.py
python3 -m enterprise_ai eval lease-abstraction-agent --baseline-only
python3 -m enterprise_ai run lease-abstraction-agent --input projects/lease-abstraction-agent/examples/input.json --provider anthropic
```

Input contract: `as_of`, `lease {id, documents [{id, kind: lease|amendment|commencement_letter|estoppel, effective_date, text}]}`, `portfolio_rules {notice_lead_days_min, rent_escalation_types_allowed, cam_cap_required, critical_date_horizon_days, currency}`, and an optional `existing_abstract` (the lease system's current dates, rent and deposit, compared for reconciliation). The example is a lease with one amendment that extends the term. Its renewal notice deadline falls inside the 365-day horizon.

## Decision boundary

The model never computes a date or an amount, and it never decides the route. A statement whose quote is not in its document, or whose figures are not in its quote, is dropped as `UNGROUNDED_FIELD`, which escalates. `PROMPT_INJECTION` escalates and never clears. An estoppel or memorandum that disagrees with the governing value is `UNRESOLVED_CONFLICT`. A summary with an unrecorded figure is withheld as `FIGURE_NOT_IN_ABSTRACT`. Write tools are recorded as proposals only. See [GOVERNANCE.md](GOVERNANCE.md).

## Limits

- The input is text. Pair it with your PDF or OCR extraction step.
- The expiration is commencement plus N calendar months minus one day. A day past the end of the target month moves to the last day of that month. If a lease defines its term differently, abstract its stated expiration date.
- CPI increases are not computed. A CPI schedule stops after the first period, and the rent in effect after that is reported as unknown.
- Not covered: co-tenancy, kick-out, ROFO and ROFR, percentage rent, base-year exclusions and CAM reconciliation. The renewal option applies to the current expiration only.
- The documents are synthetic and templated, which favours the regex baseline. Run the harness on abstracts your team has verified before relying on it.
