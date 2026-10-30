# Failure log

Every defect an evaluation or a review found in this repo, what caused it, and the fix. Kept public
on purpose: the evals exist to find these, and a reader deciding whether to adopt an agent should see
what broke and how it was caught. Newest first.

| Date | Project | Found by | Defect | Cause | Fix | Test |
|---|---|---|---|---|---|---|
| 2026-10-30 | incident-investigation-agent | Live eval (132 cases): 9 dependency outages labeled capacity_exhaustion, 2 capacity cases routed insufficient_evidence | Reason codes were an enum without definitions; "OOMKilled" on a dependency read as capacity; model asked for metrics the tools do not offer | `REASON_DEFINITIONS` in `triage.py`, rendered into the prompt; rule that log lines at a limit are sufficient | Filtered re-run on the four affected categories: 42/42 correct, 0 false blame (was 31/42); full re-run follows |
| 2026-10-30 | support-resolution-agent | Live eval (142 cases): one injection case scored as not resisted | Promise detector matched "No refund has been issued" and withheld a correct reply | `promised_completion()` ignores negated sentences | `test_reply_that_denies_an_action_is_not_a_contradiction` |
| 2026-10-30 | support-resolution-agent | Live eval: 3 of 6 cross-tenant policy cases escalated | `SUSPICIOUS_REQUEST` was undefined; the model flagged customers who quoted another brand's policy | Prompt defines the flag as fraud or account-takeover signals only | Full re-run |
| 2026-10-30 | runtime | Recording the incident replay on Anthropic: HTTP 400 "minimum is not supported" | Strict tool schemas reject numeric and string bounds | `_strict()` moves bounds into descriptions; `validate_schema` still enforces them | Runtime tests; all four replays recorded |
| 2026-10-30 | claims-intake-agent | Review of generator | `name_similar` accepted any shared token; OCR VIN swaps without confusable characters | Stricter rule (same tokens, or same surname and first initial); generator guarantees a confusable character | Generator determinism + rules tests |
| 2026-10-30 | vulnerability-triage-agent | Review of generator | Go purls lost their namespace; Maven range target selection raised StopIteration; three mislabeled categories | `component_name` joins namespace with "/"; explicit target selection; labels regenerated | Rules tests |
| 2026-10-30 | ap-exception-agent | Review and live eval (120 cases) | Generator emitted 2 of 4 layouts; transposed-digit duplicate equal to original; multi-PO lines untagged; drafts from write tools never captured | Layout index fixed; fallback digit change; all referenced POs tried; drafts derived from proposed actions | Generator and agent tests; live run 100% route |
| 2026-10-30 | runtime | Running an eval with no credits (HTTP 429) wrote a partial report | Runner treated account failures as per-case errors | `EvalAborted` on account failures; no report written | Runtime tests |

## How to add an entry

Run the eval, read the failure table in `evals/REPORT.md`, find the cause in the case input and the
agent output, fix the rule or the prompt, add a test that fails before the fix, re-run, then add a row.
Prompt fixes bump `PROMPT_VERSION`; rule fixes get a unit test. Label fixes are allowed only when the
label was wrong, and the row must say so.
