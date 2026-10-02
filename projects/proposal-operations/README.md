# Proposal Evidence Workbench

**Experimental.** Local examples and tests pass, but Jev retained an operational-deployment hold after the fresh evaluation. Evaluate with synthetic data; source-system integration, identity controls and operational validation remain open. This project is included for inspection and development, not as an approved reference release. See the [verification record](../../docs/VERIFICATION.md).

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
- `sources`: 0–100 objects with unique `id`, `text`, `valid_from`, `valid_until`, and `approval` (`approved`, `draft`, `revoked`, or `superseded`). Validity dates are inclusive and cannot be reversed.

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

## Local review ledger

The optional CLI adds durable human decisions to an immutable draft snapshot. It runs on a trusted, single-user POSIX workstation. It does **not** add enterprise authentication or a document-system connector; the experimental hold remains.

Prepare a private working directory outside the repository, export the latest source/requirement packet from your authorized system, and set its `as_of` to today's UTC date. Do not change historical validity dates to make evidence pass. The following commands assume that packet is saved as `$HOME/.proposal-review/current.json`:

```sh
mkdir -m 700 "$HOME/.proposal-review"
python3 -m enterprise_ai run proposal-operations \
  --input "$HOME/.proposal-review/current.json" --mode live \
  > "$HOME/.proposal-review/result.json"
python3 -m enterprise_ai.proposal_review --db "$HOME/.proposal-review/reviews.sqlite" stage \
  --input "$HOME/.proposal-review/current.json" --result "$HOME/.proposal-review/result.json"
```

Set `DRAFT_ID` to the returned SHA-256 identifier. Inspect the actual draft, all evidence and unresolved requirements before deciding. `inspect` returns the current decision sequence, or null for a never-reviewed row; use revision `0` only for its first decision.

```sh
python3 -m enterprise_ai.proposal_review --db "$HOME/.proposal-review/reviews.sqlite" inspect --draft "$DRAFT_ID"
python3 -m enterprise_ai.proposal_review --db "$HOME/.proposal-review/reviews.sqlite" decide \
  --draft "$DRAFT_ID" --current-input "$HOME/.proposal-review/current.json" \
  --requirement req-1 --decision approve --expected-revision 0 \
  --note 'Verified the answer and plan restriction against the cited source.'
python3 -m enterprise_ai.proposal_review --db "$HOME/.proposal-review/reviews.sqlite" export \
  --draft "$DRAFT_ID" --current-input "$HOME/.proposal-review/current.json" \
  > "$HOME/.proposal-review/approved.json"
python3 -m unittest discover -s tests -p test_proposal_review.py -v
```

Refresh `current.json` from the source system before **every** decision/export. The CLI checks today's UTC date, but cannot discover an upstream revocation omitted from an operator-provided export. An old packet relabeled with today's date is not evidence of freshness.

### What the ledger enforces

- Approval binds to the complete staged input and result, including exact requirement, draft and source content/metadata. Every source is bound, including uncited material: adding contradictory evidence requires a new review.
- Source or requirement changes require a fresh run and new draft identifier; changed draft text also starts unreviewed. Source validity is recomputed on the current UTC date. Any stale or changed binding fails the whole export rather than silently including an invalid answer.
- Only `supported` answers can be approved. Gaps, conflicts and evidence-review rows are withheld. Exports may be partial; `withheld_count` identifies how many answers remain excluded.
- Decisions persist in SQLite transactions. Concurrent reviewers using the same previous revision cannot overwrite each other silently. A rejection supersedes prior approval while retaining decision history.
- Reviewer identity is the actual local OS UID/account, not a caller-supplied name. The database directory must be owned by that account and private (0700); its database file must be private (0600). Changing the local account or granting database access changes the trust boundary.

### Remaining production work

The ledger trusts the machine, OS account, clock and supplied source export. It is not a tamper-proof audit log: its owner/admin can edit SQLite, alter application code or replace files. Hashes detect changed stored draft bindings, not a malicious privileged actor. Decisions are local account attestations, not organizational authorization or segregation of duties.

There is no authenticated source fetch, source-system permission check, remote revocation notification, enterprise identity/role integration, encryption-at-rest service, managed backup, retention automation or bid-system submission. Database, input and exported files contain proposal content; use organizational disk encryption, access controls and backup/retention procedures. A bank deployment requires these integrations and independently validated operating controls before production use.

## Governance and acceptance

See [domain review responsibilities, evaluation metrics and deployment gates](GOVERNANCE.md).

Input and current-source files are limited to 500 KB. Result files may be up to 10 MB, matching the shared serialized CLI output limit. A large valid response can therefore enter the same review path as a small one.
