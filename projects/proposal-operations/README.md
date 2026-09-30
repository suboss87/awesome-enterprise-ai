# Proposal Evidence Workbench

Sales engineers review an RFP question set against a dated, approved evidence library. The workbench produces a requirement-by-requirement response matrix, highlights contradictions and evidence gaps, and removes affirmative drafts backed by expired, future, or unapproved sources.

## Try it

From the repository root:

```sh
python3 -m enterprise_ai run proposal-operations --input projects/proposal-operations/examples/input.json --mode replay --responses projects/proposal-operations/examples/responses.json
python3 -m unittest discover -s projects/proposal-operations/tests -v
```

Replay is a hand-authored offline demonstration. Set `OPENAI_API_KEY` and use `--mode live` without `--responses` for real inference. Python standard library only.

## Business flow

1. Export an RFP to numbered requirements and approved product documentation to source records.
2. AI matches requirements to exact quotations, drafts supported responses and identifies contradictions.
3. Rules enforce complete requirement coverage and source validity on the supplied review date.
4. Review the unresolved queue before reviewing draftable answers. Every row stays `unreviewed`; nothing is submitted or certified.

The example answers a SAML question with a plan-specific source. Expire that source and the affirmative draft is removed, leaving an evidence-review task.

## Input contract

- `as_of`: ISO review date.
- `requirements`: 1–100 objects with unique `id` (128 characters maximum) and `text` (10,000 maximum).
- `sources`: 0–100 objects with unique `id`, `text`, `valid_from`, `valid_until`, and `approval` (`approved` or `draft`). Validity dates are inclusive and cannot be reversed.

Unknown fields, duplicate IDs, missing output rows, fabricated quotation text and unknown citation IDs are rejected. IDs belong to separate requirement and source namespaces. No source is fetched from a URL. Documents must be parsed and normalized before input; this tool does not parse PDFs or spreadsheets.

## Output and interpretation

`matrix` includes the original requirement, status, draft, exact evidence, invalid-source reasons and review status. `source_validity` records each source's date/approval state. `actions` gives a review queue.

- `supported`: current approved evidence was cited; draft still needs human verification.
- `gap`: no answer is drafted.
- `conflict`: at least two distinct sources were cited and the answer is withheld.
- `evidence_review`: cited material was expired, future or unapproved, so the draft is withheld.

AI handles semantic requirement matching and contradictions. Rules control dates, approval labels, coverage and exact citations. They do not prove that a quotation entails the answer. No legal compliance verdict, bid submission, win probability or automatic approval is generated.

## Evaluation

Ten frozen synthetic cases in `evaluation/cases.json` cover current evidence, stale and future sources, missing evidence, contradictions, invented citations, duplicate/omitted requirements and affirmative drafts attached to gaps. Replay tests verify state handling, not live answer correctness.

Before relying on generated drafts, evaluate independently labeled requirement/evidence packets against keyword answer lookup and a simple retrieval baseline. Measure unsupported claims, contradiction recall, stale-evidence reliance, coverage and reviewer correction time. Actual customer RFPs and enterprise deployment have not been evaluated.

## Adoption

Keep approval and validity metadata under document-owner control. Restrict source access before exporting the packet; this module does not implement a multi-user document permission system. Product capabilities and proposal content may be confidential. Live mode sends supplied text to the configured model provider; apply organizational data policies.

## Collection workspace and current evidence

Run `python3 -m enterprise_ai serve` from the collection root to try this workflow in the browser, upload a compatible JSON export, inspect results and export JSON. [Deployment and data handling](../../docs/DEPLOYMENT.md) explains the single-user boundary and live provider. [Verification](../../docs/VERIFICATION.md) records the actual inference trials, initial failures, corrective regressions and independent semantic review; authored fixtures above remain distinct from live evaluation.
