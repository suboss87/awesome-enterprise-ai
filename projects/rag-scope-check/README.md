# RAG Scope Check

**Find retrieval paths that are permission-safe but still fail the user.**

Status: experimental. Local SQLite reproduction and exported-case checks work; a real source-system integration and production validation remain open.

## The problem

A finance user asks for an expense policy. Retrieval returns the public handbook but misses the private policy they are allowed to read. No document leaks, so a safety-only gate can pass while the answer quality suffers.

RAG Scope Check measures returned-document leaks, authorized recall per tenant/cohort, and top-k underfill. Its executable demo separates source permissions from the index's permission copy. Synchronizing that copy changes the retrieval result while preserving the query, source grants, relevance labels and thresholds.

## Run it

Requirements: Git, Python 3.10+ with SQLite FTS5. No model, API key, package installation or database service.

```sh
git clone https://github.com/suboss87/rag-scope-check.git
cd rag-scope-check
git checkout cfeb20db068ed25b1ad4a5e544dbfd19114e58a1
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

## Why this exists

- A [practitioner report](https://www.reddit.com/r/Rag/comments/1w3q78p/our_rag_permissions_filter_is_safe_and_still/) describes safe filtering suppressing useful private results. This is one unverified account, not independent proof of widespread demand.
- [pgvector documents filtered-search underfill](https://github.com/pgvector/pgvector#filtering) and existing tuning options. Underfill has several causes; this project does not claim to diagnose them from a count alone.
- [raggate](https://raggate.net/product.html) describes permission regression testing. Its inaccessible source was not audited, so we do not claim global novelty or that it lacks particular features.

The contribution demonstrated here is a small, inspectable check combining permission safety with useful authorized recall. The current implementation accepts exported evidence; it does not enforce authorization.

## Limits and next step

The SQLite fixture deliberately plants a missed grant. Its source table is a simulated authority. Real use requires permissions from an independent source system, reviewed relevance labels and stable document IDs. A passing result only covers supplied cases; it is not a security certification.

The first maintenance fix rejects duplicate JSON permission fields and empty evaluation batches that previously produced misleading PASS results. [Reproduce the rejected input](https://github.com/suboss87/rag-scope-check/tree/cfeb20db068ed25b1ad4a5e544dbfd19114e58a1/docs/evidence/input-integrity).

Next: establish a reproducible integration with a genuine source permission authority before broadening claims. Jev's source-oracle assessment recommended narrowing scope; that recommendation is retained.

[Source and schema](https://github.com/suboss87/rag-scope-check) · [Recorded demo evidence](https://github.com/suboss87/rag-scope-check/tree/cfeb20db068ed25b1ad4a5e544dbfd19114e58a1/docs/evidence/permission-sync) · [Report a vulnerability privately](https://github.com/suboss87/rag-scope-check/security/advisories/new)
