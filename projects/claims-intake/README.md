# Claims Intake Workbench

**Prepare a complete evidence packet for an adjuster.**

A claim can stall because a document is missing, belongs to somebody else, or disagrees with the submitted facts. This workflow classifies supplied document text, extracts quoted fields, checks the packet against a configurable checklist, and drafts requests for missing evidence.

## Try it

From the repository root, with Python 3.11 or later:

```sh
python3 -m enterprise_ai run claims-intake \
  --input projects/claims-intake/examples/input.json \
  --mode replay --responses projects/claims-intake/examples/responses.json
```

The example contains an incident report and repair estimate for a fictional claimant. Both checklist items are present for review. This is **not a coverage or payment approval**. Replay makes no AI call.

To analyze your own packet, prepare its text using the same contract, configure `OPENAI_API_KEY`, and choose `--mode live`. The shared browser workspace supports input upload and result export.

## How it works

1. Supply claim facts, document requirements and page text.
2. AI identifies each document type and extracts supported fields with exact page quotations.
3. Python checks document coverage, quoted values, identity/date/currency conflicts and amount differences.
4. A reviewer inspects the checklist, original quotations, conflicts and information requests.

A complete document must satisfy each requirement. The workflow does not silently combine unrelated partial documents. A contradictory identity or event date prevents a document from satisfying the checklist. An amount difference remains visible for review; it does not deny the claim.

## Input contract

See [the complete example](examples/input.json).

| Field | Meaning |
|---|---|
| `claim` | Claim ID, claimant ID, ISO incident date, currency and decimal-string amount |
| `requirements` | Unique document types and their required fields |
| `documents[].id` | Unique document identifier |
| `documents[].pages` | Globally unique page IDs and text from your approved ingestion system |

Supported extracted fields: `claimant_id`, `incident_date`, `amount`, `currency`, `policy_id`. Identity, date and currency values must appear literally in cited text. Amounts may normalize thousands separators. Documents can be marked `unknown`; missing fields are not invented.

## Review and adoption

- This version consumes **page text**, not PDFs, photos or handwriting. OCR quality and non-ISO date normalization require a separate ingestion step and validation.
- Literal quotation checks prevent fabricated quotations, but do not prove that a field or document was interpreted correctly. Review the originals.
- The submitted claim has no authoritative policy record. Extracted policy IDs are not proof of coverage or policy identity.
- Requirements are supplied by the adopter. There is no universal regulatory or insurer checklist.
- No policy-system integration, claim submission, denial, payment or fraud determination is implemented.
- Trial with synthetic or appropriately authorized data and review [data handling](../../docs/DEPLOYMENT.md) before using personal information.

## Verification

```sh
python3 -m unittest discover -s projects/claims-intake/tests -v
```

Tests cover incomplete packets, contradictory identity, cross-document evidence, duplicate fields, fabricated citations and partial-document mixing. Shared regressions cover amount punctuation and numeric boundaries. See [collection verification](../../docs/VERIFICATION.md) for live evaluation results and limits.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).
