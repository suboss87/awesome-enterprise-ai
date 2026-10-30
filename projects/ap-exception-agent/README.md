# AP Exception Agent

**Problem.** Processing a supplier invoice costs about USD 9.90 and one in five raises an exception that a person must chase ([Ardent Partners, 2026](https://www.medius.com/resources/guides-reports/ardent-partners-state-of-ap/)). Best-in-class teams run at USD 2.67 and 9%. The gap is reading: invoices arrive in every layout, by email, with covering notes that sometimes carry fraud.

**What the agent does.** It reads the invoice text in any layout, classifies the document, extracts header and lines, looks up the vendor, purchase order, goods receipts and the AP ledger through read-only tools, reads the covering email for changed bank details or pressure, and drafts the vendor query. The rules in `matching.py` then run the 3-way match, duplicate search and tolerances and decide the route. Releasing payment and sending the query are proposals a person approves.

```
invoice text + email ──► model: classify, extract, read risk ──► tools: vendor / PO / receipts / ledger / policy
                                                                      │
                     rules: 3-way match, duplicates, tax, bank, limit ◄┘
                                   │
          route ∈ {auto_approve, human_review, reject} + flags + evidence quotes + proposed actions
```

## Results

120 labeled synthetic invoices across 16 categories, four layouts (tabular, key-value, narrative email, German/European with decimal commas). Baseline: regex templates for two layouts plus generic fallback, same rules. Full table in [evals/REPORT.md](evals/REPORT.md).

| Metric | Agent (gpt-5.5, 2026-10-30) | Baseline |
|---|---:|---:|
| Route correct | 100.0% | 79.2% |
| Unsafe auto-approvals (must be 0) | 0 | 13 |
| Expected flags recalled | 1.00 | 0.67 |
| Key fields exact (number, POs, total, vendor) | 100.0% | 73.3% |
| Prompt injection flagged | 100.0% | 0.0% |
| Cost per invoice | USD 0.049 | 0 |
| Latency p50 / p95 | 18.6 s / 27.2 s | under 1 s |

The baseline's 13 unsafe approvals come from prompt-injection text it cannot see and from layouts it cannot read. The synthetic text is clean; OCR noise will lower the agent's field accuracy and should be measured on your own scans.

## Run it

```sh
python3 -m enterprise_ai run ap-exception-agent                                  # recorded replay, no key
python3 -m enterprise_ai run ap-exception-agent --input my-case.json --provider anthropic
python3 -m enterprise_ai eval ap-exception-agent --provider anthropic              # 120 cases, writes evals/REPORT.md
```

Input contract: `as_of`, `invoice {id, channel, text, email_body?}`, `erp {vendors, purchase_orders, goods_receipts, ap_ledger}`, `policy {currency, unit_price_tolerance_pct, total_tolerance_pct, auto_approve_limit, tax_rate_pct}`. See [examples/input.json](examples/input.json).

## Decision boundary

The model never decides the route. Its flags `PROMPT_INJECTION` and `SUSPICIOUS_REQUEST` can escalate but never clear. Write tools are recorded as proposals. Details in [GOVERNANCE.md](GOVERNANCE.md).

## Limits

- Text in, not PDFs: pair it with your OCR step.
- One currency per policy; no conversion, no tax jurisdictions beyond one rate.
- Vendor matching is token overlap on names and exact tax id; a vendor master with many near-duplicate names needs your own resolver.
- Synthetic results are evidence about the harness, not about your invoices.
