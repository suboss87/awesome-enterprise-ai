# Candidates for agents 6 to 10

Scored against [RUBRIC.md](RUBRIC.md). Evidence sheets with sources are in
[research/usecase-hunt-2026-10-30.md](research/usecase-hunt-2026-10-30.md); the JSON the scorer reads is
`candidates.json`. The maintainer score is in the research file; the table below is Jev's independent read of
the same evidence, produced by `python3 tools/score_candidates.py docs/candidates.json --write docs/CANDIDATES.md`.

<!-- scores -->
| Candidate | Total /50 | acute pain | code decides | approval fits | data reachable | measurable | adoption evidence | roi mechanism | not generic | buildable simply | diversity | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Commercial credit memo drafting | 45.2 | 4.9 | 5.0 | 4.5 | 3.5 | 4.7 | 4.5 | 4.6 | 4.9 | 4.0 | 4.7 | build |
| Contract (NDA / MSA) playbook review | 43.9 | 4.9 | 4.8 | 4.5 | 4.1 | 5.0 | 3.2* | 4.4* | 4.9 | 3.2* | 4.9 | build |
| Lease abstraction + critical dates | 43.7 | 4.5 | 4.8 | 4.3* | 3.7 | 5.0 | 3.9* | 4.5 | 4.6 | 3.5* | 4.9 | build |
| Sales order entry from emailed POs | 42.4 | 4.1 | 4.3 | 4.8 | 3.8 | 4.9 | 3.3* | 4.2 | 4.6 | 3.7 | 4.6 | build |
| Cash application | 41.7 | 4.1* | 4.6 | 4.6 | 3.8 | 5.0 | 3.7* | 3.8* | 4.9 | 3.7 | 3.5* | hold |
| Prior-authorization clinical review, approve-only | 40.6 | 3.3* | 4.8 | 3.7* | 3.4 | 4.6 | 3.1* | 4.2 | 4.9 | 4.0 | 4.6 | build |
| Sanctions / name-screening alert adjudication | 40.0 | 2.6* | 4.6 | 4.8 | 3.5* | 4.9 | 2.9* | 3.8* | 4.9 | 4.0* | 4.0* | hold |
| Vendor SOC 2 report review / TPRM | 39.2 | 3.9* | 3.7 | 4.8 | 3.7 | 4.0* | 2.5* | 3.2 | 4.8 | 3.9 | 4.6 | hold |
| Expense report audit | 37.2 | 3.1* | 4.0 | 4.0* | 3.9 | 4.7 | 2.0* | 3.0 | 4.9 | 4.1 | 3.5* | hold |
| Chargeback representment | 37.0 | 3.5* | 4.2 | 4.0* | 3.3* | 4.4 | 1.4 | 3.0 | 4.6 | 4.2* | 4.2* | hold |
| SOX ITGC testing | 36.8 | 3.0* | 4.5 | 3.8* | 4.2 | 3.4* | 2.3 | 3.5 | 4.0 | 4.0 | 4.3* | hold |
| Mortgage condition clearing | 36.5 | 2.6* | 4.2 | 3.3* | 3.8 | 3.9* | 2.4 | 3.0 | 4.1 | 4.4 | 4.7 | hold |
| HTS / HS tariff classification | 36.0 | 2.5 | 3.0* | 4.1* | 3.4* | 4.9 | 2.6* | 3.1 | 4.8 | 2.8* | 4.9 | hold |
| KYB merchant onboarding review | 35.6 | 2.2 | 3.8 | 4.1* | 2.6* | 4.9 | 2.7* | 2.9* | 4.7 | 3.0* | 4.8 | hold |
| Payer denial appeal packet | 34.8 | 4.8 | 4.0 | 3.7* | 2.8* | 3.4* | 1.9* | 1.9 | 4.6 | 3.4* | 4.3* | hold |
| AR collections dispute triage | 34.7 | 3.9 | 3.6 | 3.6* | 3.9 | 3.4* | 2.0 | 3.1 | 3.9 | 3.4* | 4.0* | hold |
| FOIA exemption flagging | 33.8 | 3.7* | 2.9* | 3.0* | 3.5* | 3.4* | 3.1* | 3.1* | 3.8 | 2.4* | 4.9 | hold |
| Medical coding suggestion | 33.4 | 3.4* | 2.6* | 3.1* | 3.2* | 4.1* | 2.8* | 3.2 | 4.0 | 2.4* | 4.7 | hold |
| Pharmacovigilance AE case intake | 32.2 | 1.9 | 4.0 | 3.7* | 3.8 | 3.4* | 1.0 | 1.2 | 4.5 | 3.9 | 4.8 | hold |

Scores are Jev (TypeSafe System One) Score answers, 1 to 5, probability-weighted. `*` marks confidence below 0.5: a person reads that criterion. Thresholds in `tools/score_candidates.py`: total >= 38, every criterion >= 3, diversity >= 4.
<!-- /scores -->

## Decision (2026-10-30)

Both scores agree on the top of the list; they disagree on one candidate. Jev's confidence marks show where a
person had to read the evidence.

Build queue, in order:

| # | Agent | Why this one | Maintainer / Jev |
|---|---|---|---|
| 6 | Contract playbook review (`contract-review-agent`) | Legal ops is a new function; CUAD and LegalBench make labels credible; redlines only from approved fallback text | 46 / 43.9 |
| 7 | Commercial credit memo (`credit-memo-agent`) | Highest Jev score; spreads and policy checks are pure code; three named banks report hours saved | 45 / 45.2 |
| 8 | Lease abstraction and critical dates (`lease-abstraction-agent`) | Real estate is a new industry; date arithmetic and register rules are code; JLL and Cushman & Wakefield run it | 43 / 43.7 |
| 9 | Sales order entry from emailed POs (`order-entry-agent`) | Distribution is a new industry; the sell-side mirror of AP reuses the inbox adapter; touchless rate is the metric practitioners report | 45 / 42.4 |
| 10 | Prior authorization, approve-only (`prior-auth-agent`) | Healthcare payer is a new industry; CMS decision clocks give a hard SLA; an agent with no deny action answers the public concern about AI denials | 47 / 40.6 |

Held with a note:

- **Sanctions alert adjudication** scored 48 with the maintainer and 40.0 with Jev, where "acute pain" came back
  2.6 at low confidence. The Federal Reserve paper and the bank data say the pain is real; the sheet did not quote a
  cost per alert or analyst headcount. First reserve: it enters the queue if any of the five above fails its live eval bar.
- **Cash application** and **expense audit** are strong but sit in the same finance-ops family as the AP agent.
- Everything below 38 waits for better adoption evidence.
