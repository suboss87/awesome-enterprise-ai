# Order Entry Agent

**Problem.** A distributor's order desk retypes customer purchase orders from email into the ERP. Millcraft Paper puts the cost of a manually entered order at USD 8 to 12 and reports that 60% of its inbound orders became touchless after it automated entry, on about 500,000 stock lines a year ([Distribution Strategy, 2024](https://distributionstrategy.com/2024/06/how-ai-has-improved-order-entry-other-efficiencies-at-millcraft-paper/)). Conexiom, a vendor, claims more than 85% touchless; we saw that number only in a search snippet and did not verify it. Orders arrive in every layout. Customers use their own part numbers, order cases when the list sells eaches, send stale prices, resend POs, and send RFQs with "order" in the subject.

## Who does what

| The model reads and drafts | Code decides (`ordering.py`) | A person approves |
|---|---|---|
| Classifies the document (PO, RFQ, quote acceptance, acknowledgement). Records the header and every line as printed, with a verbatim quote. Picks SKUs from the resolver's candidates. Reports embedded instructions. Drafts the customer query. | Checks that each quote prints its quantity, price and part code. Resolves customer, ship-to and parts. Converts cases and eaches. Checks contract price and tolerance, MOQ, stock and backorders, duplicates, credit and the PO total. Raises 17 finding codes, sets the route and prices the order at list. | The order desk rep works every `desk_review` item; the order desk lead approves exceptions. Write tools are proposals only. |

```
PO text + email ──► model: classify, lookup_customer, resolve_part (code), get_price, check_inventory, search_open_orders
                                   │
                    record_order_lines (quotes checked) ──► ordering.py: parts, units, price, MOQ, stock, duplicates, credit
                                                                  │
            route ∈ {auto_create, desk_review, reject} + findings + sales-order lines + proposed actions
```

## Results

The set has 122 labeled synthetic documents in 18 categories and four layouts: tabular PO, key-value PO, narrative email and EDI-like flat text. Categories cover customer part numbers, description-only and ambiguous lines, prices 2-4% and 8-10% off contract, cases against eaches, MOQ, resent POs, the same lines under a new PO two days later, credit limit and hold, unknown ship-tos, stock shortages, RFQs and quote acceptances, unknown customers, prompt injection and totals that do not add up. Some cases look wrong but are clean, such as a reorder five weeks later. 42 cases should be touchless, 66 need the desk and 14 should be rejected. The generator labels them with its own oracle, and a test confirms that the rules reproduce every label from a perfect reading. The baseline is a regex template for the tabular and key-value layouts with a keyword gate for RFQs, and it uses the same rules.

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct | live run pending | 74.6% |
| Auto-created when review or reject was expected (must be 0) | live run pending | 3 |
| Auto-created with a wrong SKU, quantity or price (must be 0) | live run pending | 0 |
| Order lines exact (SKU, sales quantity, price) | live run pending | 49.0% |
| Expected findings raised | live run pending | 0.46 |
| Raised findings that were expected | live run pending | 0.37 |
| Every line read and quoted verbatim (orders) | live run pending | 50.0% |
| Prompt injection flagged | live run pending | 0.0% |
| Touchless rate (34.4% is the most possible) | live run pending | 19.7% |

The baseline sends narrative emails and EDI text, which it cannot read, to the desk. That flatters its route accuracy when the desk was expected anyway; the cost shows in the touchless rate. Its 3 unsafe auto-creates are injection cases in layouts it can read.

## Run it

```sh
python3 -m enterprise_ai eval order-entry-agent --baseline-only        # no key, no cost
python3 -m enterprise_ai run order-entry-agent --input projects/order-entry-agent/examples/input.json --provider anthropic
python3 -m enterprise_ai eval order-entry-agent --provider anthropic    # 122 cases, writes evals/REPORT.md
```

The input has `as_of`, `document {id, channel, text, email_body?}`, `erp {customers, price_lists, customer_part_numbers, inventory, open_orders}` and `policy {price_tolerance_pct, partial_ship_allowed, backorder_allowed, credit_check_required_above, max_order_total_without_approval, duplicate_window_days}`. The `document` block has the shape that `adapters/ap_inbox.py` builds from an email. See [examples/input.json](examples/input.json): an emailed PO with one price 2% above contract and one line that names no part code.

## Limits

- Text in, not PDFs or faxes. Pair it with your OCR step.
- Description matching uses the price list's words. A customer's own wording ("blue nitrile L") needs a cross-reference entry, or it goes to the desk.
- Two units, each and case. No pallets, weights or lengths. One currency, with no tax, freight or promotions.
- No "same as last order" requests. Order history is read only to detect duplicates.
- Synthetic results are evidence about the harness, not about your customers' orders.
