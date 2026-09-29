# RAG Scope Check

**Help employees find the information they are entitled to use.**

Status: experimental. Local SQLite reproduction and exported-case checks work; a real source-system integration and production validation remain open.

## Business problem

A finance user asks for an expense policy. Retrieval returns the public handbook but misses the private policy they are allowed to read. No document leaks, so a safety-only gate can pass while the answer quality suffers.

A missed policy can mean another support ticket, an interrupted task, or a decision made with incomplete guidance. The same workflow can arise in finance operations, manufacturing support, or employee self-service. These are intended use cases, not verified customer deployments.

## How the workflow changes

**Before:** the team checks that restricted information is hidden, then discovers employees cannot find useful information they should see.

**With this project:** run reviewed questions against the assistant's retrieval output, check whether permitted answers were found, and identify the affected user group before releasing a retrieval change.

RAG Scope Check measures returned-document leaks, authorized recall per tenant/cohort, and top-k underfill. Its executable demo separates source permissions from the index's permission copy. Synchronizing that copy changes the retrieval result while preserving the query, source grants, relevance labels and thresholds.

## Run it

Requirements: Git, Python 3.10+ with SQLite FTS5. No model, API key, package installation or database service.

```sh
git clone https://github.com/suboss87/rag-scope-check.git
cd rag-scope-check
git checkout c07538117764b4a39de377091cdb50b2117b4831
python3 -m unittest discover -s tests -v

python3 examples/sqlite_acl_demo.py > stale.jsonl
python3 -m rag_scope_check stale.jsonl --min-cohort-recall 0.8 --max-underfill-rate 0
# Expected: FAIL, exit 1. Recall 0, underfill 1, zero leaks.

python3 examples/sqlite_acl_demo.py --sync-permissions > corrected.jsonl
python3 -m rag_scope_check corrected.jsonl --min-cohort-recall 0.8 --max-underfill-rate 0
# Expected: PASS, exit 0. Recall 1, underfill 0, zero leaks.
```

Run the two gate commands separately when using a shell configured to stop on nonzero exit. The first failure is intentional.

The collection's daily workflow repeats both paths with unchanged thresholds and checks their exit codes and measured results. To run its verifier from this collection, point it at the checkout above:

```sh
python3 scripts/verify_rag_demo.py /path/to/rag-scope-check
```

## Use it with your workflow

Export document IDs returned by your assistant before it constructs a model response. For each case, supply the user's independently verified document permissions, reviewed relevant documents, and how many documents are eligible. No document text is required.

The checker produces a report of permission violations, missed relevant answers, and short result sets by user group. It does not change permissions, retrieve documents, or call a model. [Input contract](https://github.com/suboss87/rag-scope-check#feed-it-from-your-pipeline).

**Success in a trial:** known unauthorized results fail; known permitted answers are found at your agreed threshold; invalid or missing required evidence cannot produce a passing result. Use your own representative cases before connecting a release gate.

## Limits and next step

The SQLite fixture deliberately plants a missed grant. Its source table is a simulated authority. Real use requires permissions from an independent source system, reviewed relevance labels and stable document IDs. A passing result only covers supplied cases; it is not a security certification.

The first maintenance fix rejects duplicate JSON permission fields and empty evaluation batches that previously produced misleading PASS results. [Reproduce the rejected input](https://github.com/suboss87/rag-scope-check/tree/c07538117764b4a39de377091cdb50b2117b4831/docs/evidence/input-integrity).

Next: establish a reproducible integration with a genuine source permission authority before broadening claims. The current release deliberately keeps that integration boundary explicit.

[Source and schema](https://github.com/suboss87/rag-scope-check) · [Recorded demo evidence](https://github.com/suboss87/rag-scope-check/tree/c07538117764b4a39de377091cdb50b2117b4831/docs/evidence/permission-sync) · [Report a vulnerability privately](https://github.com/suboss87/rag-scope-check/security/advisories/new)
