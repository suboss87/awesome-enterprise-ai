# Proposal source integration review

The scoped Jev artifact review selected `publish_experimental` for commit `7a78b7c`. The request contained the actual adapter, ledger, shared validation, workflow, source tests, governance and independent review evidence. Raw response probabilities and request/response hashes are preserved beside this record.

A prior full-project scoring request returned HTTP 400 without a score. It was preserved, not retried. This smaller release judgment is not a new rubric score or a directly comparable quality improvement. Jev does not certify production deployment.

Verification: 220 tests across eleven suites and ten CLI replays passed. An independent reviewer reproduced a policy-revocation race during source refresh; commit `4c971d3` fixed it, and the unchanged attack failed closed. Fourteen other independent probe outcomes matched the frozen attack plan.

One live public README case satisfied two predefined semantic criteria, with six exact quotations and both answers initially unreviewed. Authenticated ingestion, staging, two explicitly labeled coding-agent demonstration decisions, and export succeeded. Changing the operator policy to revoked then blocked export. These are public-source integration results, not domain-expert acceptance or production accuracy.

The trusted OS account, policy owner and clock remain explicit boundaries. Private enterprise repository authorization, organizational reviewer identity, representative business evaluation and production operations are unverified. Proposal Evidence remains experimental.
