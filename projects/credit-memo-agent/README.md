# Credit Memo Agent

**Problem.** A commercial credit memo takes days of analyst time. Most of that time goes into spreading the borrower's statements, reconciling them and writing up the result. Banesco USA cut memo preparation from "about a week" to minutes and reports over 7,000 hours saved a year across about 280 memos ([Google Workspace case study](https://workspace.google.com/customers/banescousa)). Taishin Bank reports 20 hours down to 4 per credit report, on more than 4,300 reports a year ([Moody's](https://www.moodys.com/web/en/us/insights/banking/how-taishin-bank-used-ai-to-amplify-human-expertise-in-credit-analysis.html); the number comes from a search snippet and is not verified). Colony Bank cut its SBA process from 92 steps to 32, and a person still approves every loan ([American Banker](https://www.americanbanker.com/news/colony-bank-uses-gen-ai-to-shave-days-off-sba-loan-approvals)). The hard part is reading. Statements arrive as tables, accountant letters and tax forms, and the risks are in the notes: add-backs, related-party sales, restatements, misaligned fiscal years.

## Who does what

| The model reads and drafts | Code decides (`underwriting.py`) | A person approves |
|---|---|---|
| Reads each statement in any layout. Records a spread with a verbatim quote for every figure. Finds add-backs and whether they are documented, related-party revenue, restatements and the months an interim covers. Reports embedded instructions. Drafts the memo narrative. | Checks that each quote prints its figure. Selects and aligns periods and annualizes interims. Computes EBITDA, adjusted EBITDA (only allowed, documented add-backs), DSCR, global DSCR, leverage, LTV and current ratio. Raises 16 exception codes and sets the route. Withholds a memo that states any figure it did not compute. | The credit officer reviews the route, the exceptions and the memo. The credit committee approves or declines. The agent never recommends either. |

```
statements ──► model: get_statement, record_spread (quotes checked) ──► compute_ratios / check_policy (code)
                                                                              │
          draft_memo (proposal, every figure checked) ◄───────────────────────┘
                                   │
   route ∈ {ready_for_officer, exceptions_for_officer, insufficient_financials} + exceptions + memo or "withheld"
```

## Results

The set has 128 labeled synthetic loan requests in 18 categories. About a third of the packages use narrative accountant letters. The categories include documented and undocumented add-backs, global cash flow with guarantor support, interim annualization, misaligned fiscal periods, related-party revenue on both sides of the limit, restated prior years, missing interims, stale appraisals, mixed-collateral LTV, tax return vs income statement gaps, prompt injection, and DSCR values exactly on the half-cent rounding boundary. The generator computes the labels with its own oracle. A test confirms that the rules reproduce every label from a perfect spread. The baseline is a regex template for tabular statements and a fill-in memo, and it uses the same rules.

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct | live run pending | 61.7% |
| Ready while an exception exists (must be 0) | live run pending | 5 |
| Released memo states an uncomputed figure (must be 0) | live run pending | 0 |
| DSCR, leverage, LTV within 0.01 | live run pending | 64.1% |
| Expected exceptions raised | live run pending | 0.67 |
| Raised exceptions that were expected | live run pending | 0.52 |
| Revenue, EBITDA, total debt exact | live run pending | 63.3% |
| Prompt injection flagged | live run pending | 0.0% |

On tabular packages the baseline gets every route right except prompt injection. Its 5 unsafe results are tabular injection cases. Narrative packages give it no spread, so it routes them to insufficient financials.

## Run it

```sh
python3 -m enterprise_ai eval credit-memo-agent --baseline-only        # no key, no cost
python3 -m enterprise_ai run credit-memo-agent --input projects/credit-memo-agent/examples/input.json --provider anthropic
python3 -m enterprise_ai eval credit-memo-agent --provider anthropic    # 128 cases, writes evals/REPORT.md
```

The input has `as_of`, `request {id, borrower, facility, collateral, guarantors}`, `statements [{id, kind, period_end, fiscal_year_end, text}]` and `credit_policy`. See [examples/input.json](examples/input.json): a revolver request with three statements and one exception (related-party revenue).

## Limits

- Text in, not PDFs. Pair it with your OCR step.
- One set of ratio definitions: DSCR after distributions, a 25-year amortization for CRE, and new money (no refinance netting). Change `underwriting.py` to match your policy.
- No trend analysis, projections or industry benchmarks. The memo cannot state numbers the code does not compute.
- `documented` for an add-back is the model's reading of the text. The officer still checks the documents.
- Synthetic results are evidence about the harness, not about your borrowers.
