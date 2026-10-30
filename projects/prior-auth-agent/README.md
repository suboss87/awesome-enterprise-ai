# Prior Authorization Agent

**Problem.** Utilization management (UM) nurses at a health plan read faxed clinical packets against coverage criteria, under a clock. Since 1 January 2026, CMS-0057-F requires Medicare Advantage, Medicaid, CHIP and exchange plans to decide expedited requests within 72 hours and standard requests within 7 calendar days ([TechTarget](https://www.techtarget.com/searchhealthit/news/366578002/CMS-Releases-Interoperability-and-Prior-Authorization-Final-Rule)). Geisinger Health Plan, WNS-HealthHelp and Anterior report a "50-70% reduction" in turnaround on escalated clinical cases and a "76% reduction in approvals requiring human review" ([HealthHelp](https://www.healthhelp.com/wp-content/uploads/HH-Geisinger-Case-Study_Transforming-Prior-Authorization-with-AI.pdf)). The public concern is AI that denies care; CMS's WISeR model faces repeal bills ([Dinsmore](https://www.dinsmore.com/publications/is-ai-wiser-cms-models-ai-based-prior-authorization-process-in-six-states/)). This agent can propose approval or route to a clinician. It has no adverse action.

## Who does what

| The model reads and drafts | Code decides (`criteria.py`) | A person approves |
|---|---|---|
| Reads notes, therapy logs, imaging and lab reports, referrals and OCR-noisy faxes. Per criterion, records verbatim quotes with the date of each event, and measured values (BMI, HbA1c). Reports embedded instructions. Drafts the provider request. | Checks each quote is verbatim, from an allowed document kind and dated. Uses only evidence inside the lookback window. Computes therapy duration from dated visits (long gaps restart it), compares values with thresholds, flags disagreeing documents. Checks code pairs, eligibility, exclusions, site of service, peer-review triggers, duplicates and the CMS-0057-F clock. Raises 13 finding codes and sets the route. | The UM nurse signs off a proposed approval, works routed requests and sends provider requests. The medical director reviews every likely adverse outcome; only a physician makes that determination. |

```
packet ──► model: get_document, search_documents, record_criterion_evidence (quotes, dates checked)
                          │
     evaluate_criteria + check_sla_clock (code) ──► propose_decision / request_additional_information (proposals)
                          │
 route ∈ {approve_proposed, nurse_review, medical_director_review, information_requested} + findings + due time
```

`approve_proposed` needs every applicable criterion met on verbatim, dated, in-window evidence and no other finding except an at-risk clock. A model approval the rules do not support raises `UNGROUNDED_CLAIM` and goes to a nurse. A provider request is released only when it lists exactly the missing criteria and has no adverse-decision language.

## Results

122 labeled synthetic requests in 18 categories over three policies (lumbar MRI, bariatric surgery, glucose monitor). Hard cases include 33 to 41 days of therapy when 42 are required (the note says "six weeks"), a criterion met only on an OCR-noisy fax, therapy gaps, invalid code pairs, documents that fit a different code, stale evidence, two notes with conflicting BMI, values just under the threshold (BMI 39.9, HbA1c 6.9), peer-review triggers, exclusions, ineligible members, duplicates, referral-only packets, expedited requests with under 24 hours left, and prompt injection on a fax cover. The generator labels with its own oracle; a test confirms a perfect reader reproduces every label through the agent. The baseline is date regexes plus a keyword table per criterion, over the same rules.

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct | live run pending | 83.6% |
| Approval proposed when the label is not approve (must be 0) | live run pending | 7 |
| Output or proposal states an adverse decision (must be 0) | live run pending | 0 |
| Every criterion status exact | live run pending | 81.1% |
| Expected findings raised / raised findings expected | live run pending | 0.89 / 0.81 |
| Quotes verbatim and dated; approvals cite every criterion | live run pending | 100.0% |
| Hours left on the clock within 0.1 | live run pending | 100.0% |
| Prompt injection flagged | live run pending | 0.0% |
| Share proposed for approval (labels: 18.9%) | live run pending | 17.2% |

All 7 baseline unsafe approvals are injection cases. The baseline cannot read OCR faxes (0 of 7) or visit dates written in prose, so it asks for more information on those.

## Run it

```sh
python3 -m enterprise_ai eval prior-auth-agent --baseline-only        # no key, no cost
python3 -m enterprise_ai run prior-auth-agent --input projects/prior-auth-agent/examples/input.json --provider anthropic
python3 -m enterprise_ai eval prior-auth-agent --provider anthropic    # 122 cases, writes evals/REPORT.md
```

Input: `as_of`, `request {id, received_at, expedited, member, requesting_provider, service}`, `documents [{id, kind, date, text}]`, `coverage_policy`, `plan`, optional `authorization_history`. [examples/input.json](examples/input.json) is an expedited glucose-monitor request whose criteria are met across a lab report and a clinic note.

## Limits

- Text in, not PDFs or images. Pair it with your fax OCR.
- Translating a medical policy (InterQual, MCG or your own) into `criteria` is clinical work that a person validates.
- `met_claim` on presence criteria is the model's reading; the nurse reads the quote before sign-off.
- The clock is calendar time from receipt, without pauses or state-specific clocks.
- Synthetic results are evidence about the harness, not about your members.
