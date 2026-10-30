# Contract Review Agent

**Problem.** Legal ops teams compare every incoming NDA and MSA with a playbook. The work is slow and repetitive, and the expensive misses hide in odd places. RSM moved NDA review to a playbook tool and reports a review-time cut of more than 75%, more than 800 employee hours saved per year, and more than 1,400 NDAs reviewed ([LexCheck case study](https://lexcheck.com/case-studies/rsm)). A keyword checklist does not catch the hard cases. Examples: a "Mutual" title on one-way obligations, a residuals right inside a definition, a hiring ban in the confidentiality clause, a second duration in the survival clause.

**What the agent does.** It reads one contract in any clause layout. For each playbook topic, it states the value and quotes the sentence that supports it. It also flags instructions that are hidden in the contract text, and it drafts redlines from the playbook fallback text. `playbook.py` checks that every quote exists, compares the values with the playbook thresholds, assigns a risk tier and routes the contract.

| The model | The code (`playbook.py`) | A person |
|---|---|---|
| Reads the clauses and states 10 topic values with verbatim quotes. Flags `PROMPT_INJECTION`. Proposes fallback redlines. | Splits the text into clauses and grounds each quote. Applies the thresholds: term months, cap multiple, law allowlist, venue match, renewal notice, forbidden residuals or non-solicit. Assigns the tier `acceptable`, `counsel` or `walk_away` and decides the route. Withholds any redline that is not the fallback text. | Legal ops approves `approve_standard`. Counsel reviews `counsel_review` and `walk_away`, and approves every redline. |

```
contract + playbook ─► validate ─► Agent loop (model)
                                    │ get_clause · search_clauses · get_playbook_position
                                    │ compare_to_playbook (deterministic) · draft_redline* · submit_to_legal_queue*   (*recorded only)
                                    ▼ finish: terms [{topic, value, quote}], flags, recommended_route, evidence
                     playbook.py ─► ground quotes → deviations + risk tier → route → redline check → output
```

## Results

The set has 128 labeled synthetic contracts in 18 categories. There are four layouts: numbered paragraphs, SECTION headings, lettered sub-clauses, and definitions-first with decimal sub-clauses. The baseline is a keyword checklist that uses the same rules. The numbers come from [evals/REPORT.md](evals/REPORT.md).

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct (approve / counsel / walk away) | live run pending | 71.1% |
| Unsafe standard approvals (must be 0) | live run pending | 37 |
| Expected deviations found | live run pending | 0.635 |
| Reported deviations that were expected | live run pending | 0.635 |
| Released redlines use playbook fallback text only | live run pending | 100.0% |
| Terms grounded in verbatim quotes | live run pending | 89.1% |
| Prompt injection flagged (injection cases) | live run pending | 75.0% |
| Routed approve_standard (rate) | live run pending | 49.2% |

The baseline routes all standard contracts correctly. It also catches every case that has a clear keyword: venue mismatch, missing clause, low cap, term too long. In total it approves 37 contracts that need counsel. These include all 8 mislabeled one-way NDAs, 7 of 8 inconsistent terms, and every residuals or hiring ban phrased without "residual", "unaided memory", "solicit" or "hire". A perfect reader passed through the same rules reproduces every label (a test confirms this).

## Run it

```sh
python3 projects/contract-review-agent/evals/generate_cases.py
python3 -m enterprise_ai eval contract-review-agent --baseline-only
python3 -m enterprise_ai run contract-review-agent --input projects/contract-review-agent/examples/input.json --provider anthropic
```

Input contract: `as_of`, `contract {id, counterparty, paper: ours|theirs, type: NDA|MSA, text}`, `playbook {id, contract_type, positions [{topic, preferred, fallback, rule}]}`, `requester {role: legal_ops|sales|counsel}`. The example is a counterparty-paper NDA with two deviations: a hiring ban inside the confidentiality clause and auto-renewal without a notice window.

## Decision boundary

The model never decides the route. A term without a verbatim quote is dropped and escalates as `UNGROUNDED_TERM`. `PROMPT_INJECTION` escalates and never clears. A redline that differs from the fallback text is withheld as `REDLINE_NOT_FROM_PLAYBOOK`. Write tools are recorded as proposals only. See [GOVERNANCE.md](GOVERNANCE.md).

## Limits

- The input is text with numbered clauses. Pair it with your DOCX or PDF extraction step.
- There are ten topics with one playbook per contract type. Indemnities other than supplier IP, data protection and payment terms are not checked.
- `exclusions: overbroad` is a model classification. The rules trust it, and only the quote is checked.
- The contracts are synthetic English text, so they say nothing about your paper until this harness runs on a sample labeled by counsel.
