# Integration

The agents read plain JSON and propose actions. Connecting them to real systems is two adapters per
agent: one that builds the input, one that carries approved proposals into the system of record. This
page documents the first shipped adapter and the pattern for the rest.

## Shipped: AP inbox adapter

`adapters/ap_inbox.py` turns a vendor email plus an ERP export into an AP Exception Agent case.

| Source | How | Notes |
|---|---|---|
| Email | A `.eml` file (drop folder, saved message) or an IMAP folder via `imaplib` in read-only mode | Text, CSV and HTML attachments are read directly. PDFs use `pdftotext` when installed; otherwise the attachment is listed under `attachments_need_ocr` and the body is used, so nothing is skipped silently. Images are always listed for OCR. |
| ERP | Four CSV exports: `vendors.csv`, `purchase_orders.csv` (one row per PO line), `goods_receipts.csv` (one row per receipt line), `ap_ledger.csv` | Every ERP produces these. Replace `erp_from_csv()` with an API client when you connect SAP, Oracle, NetSuite or Dynamics; the agent input does not change. |
| Policy | A JSON file with currency, tolerances, auto-approve limit and tax rate | Lives with the finance team, not in code. |

```sh
python3 -m adapters.ap_inbox --eml inbox/INV-2265.eml --erp exports/ --policy policy.json --out case.json
python3 -m enterprise_ai run ap-exception-agent --input case.json          # live
python3 -m adapters.ap_inbox --imap imap.example.com --user ap@example.com --erp exports/ --policy policy.json --out inbox-cases/
```

The IMAP password comes from `AP_INBOX_PASSWORD`; it is never written to disk. The adapter does not
flag, move or delete messages. A `.meta.json` beside each case records sender, subject, date and which
attachments were used or need OCR.

`adapters/fixtures/ap/` holds an email and CSV exports derived from the project example, and
`adapters/tests/test_ap_inbox.py` proves the adapter rebuilds the example exactly and that the built
case runs through the agent on the recorded replay.

## The pattern for the other agents

| Agent | Input adapter | Output carrier |
|---|---|---|
| AP Exception | Email or scanner drop + ERP export (shipped) | Post `release_for_payment` and `send_vendor_query` proposals as ERP workflow items after approval |
| Support Resolution | Ticket webhook (Zendesk, Freshdesk, ServiceNow) + order API + policy repository export | Draft reply and action into the ticket as an internal note for the agent to send |
| Incident Investigation | Alert webhook + log search API + deploy history + runbook repository | RCA draft as an incident timeline comment; mitigation as a change request |
| Claims Intake | Claims mailbox or portal upload + policy admin system lookup | Triage and missing-information request as claim notes in the claims system |
| Vulnerability Triage | SBOM (CycloneDX/SPDX) + scanner findings + deployment inventory + KEV/EPSS feeds | VEX document and tickets as pull requests and tracker issues after approval |

Rules for every adapter:

1. Build the input; never pre-decide. The adapter formats records, the agent's rules decide.
2. Read-only against the source. Nothing is marked, moved or acknowledged by the adapter.
3. Proposals leave through an approval queue. The carrier runs only on an approved proposal id and
   writes the trace id into the target system for audit.
4. Secrets come from the environment or a secret manager, never from flags or files in the repo.
