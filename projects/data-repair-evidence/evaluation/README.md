# Frozen acceptance and value evaluation

The ten case families were frozen in the research/build contract before this implementation. The local regression suite covers them; synthetic fault mutations are deliberately authored tests, not falsely presented as additional native GX runs.

| Frozen case | Required outcome | Regression methods |
| --- | --- | --- |
| Valid repair, changed data fingerprint | Ready with exact owner/consumer set, human review | `test_valid_repair`, `test_real_fixture_integrity_and_import_roundtrip` |
| Wrong environment/asset/partition | Unverified | `test_wrong_scope` |
| Weakened threshold/column/filter/mostly; dropped check | Unverified contract/coverage | `test_semantic_weakening`, `test_dropped_check`, `test_native_configuration_change` |
| Successful job but bad checks/counts/empty coverage | Never ready | `test_job_success_cannot_override_failed_check`, `test_error_and_missing_success`, `test_bad_summary_and_empty_results` |
| Replay, older/stale/equivalent-time evidence | Reject/unverified | `test_duplicate_run_rejected`, `test_old_and_timezone_equivalent_retests`, `test_stale` |
| Broken/incomplete graph, missing owner | Reject or visible gap; keep consumers | `test_lineage_invalid`, `test_incomplete_lineage_and_missing_owner_retained` |
| Conflicting owners/mappings | Explicit owner review/rejection | `test_owner_conflict`, `test_import_hash_mapping_rejected` |
| Injection/privacy | No state change/new action/raw sample disclosure | `test_raw_privacy_and_injection`, `test_ai_cannot_invent_action` |
| Shared timing/upstream is not cause | Independent failures | `test_independent_failures` |
| Waiver is not a retest | Still failing/unverified | `test_waiver_not_repair` |

## Evidence so far

Actual GX 1.8.0 was executed locally on the two included synthetic dataframes. Native fail/pass results and authoritative suite were serialized by GX. Import and deterministic handoff are exercised end to end. The dbt-shaped graph is independently authored. The provider replay is a fixed response, not an AI quality result. Template has zero calls; optional AI branch makes one call. Live latency, token cost and semantic benefit have not been measured.

## Holdout before any AI-benefit claim

Recruit an authorized data owner. Freeze thirty original/permitted episodes balanced across the ten case families, separate from development fixtures. Freeze model/prompt and expected outcomes before observing results. Blind reviewers to template versus selected-sentence view, with the same deterministic controls and source evidence in both. Measure exact owner/consumer agreement, false-ready count, missing context, unsupported claims, reviewer corrections, median/p90 preparation time, tokens and cost. Publish failures and uncertainty.

The data owner must predeclare useful time savings and acceptable semantic error rates. No universal threshold is invented. Zero invariant failures on these regression cases is necessary, not proof of production safety. Compare the actual adoption task against the team's existing catalog/incident workflow before claiming a market gap. If sentence prioritization does not help, keep the deterministic workflow and remove the AI option.

## Post-review regression additions

PR review reproduced two omissions: GX can return success on an empty dataframe, and a retest failure on a different check was absent from the historical-only failure list. Additional frozen regressions now require zero/missing/all-missing populations and impossible missing counts to remain `unverified`. A genuinely executed GX failed-to-empty pair proves this is not merely an invented validation response. Its unchanged test semantics and complete native results otherwise compare successfully. A separate explicit synthetic result mutation verifies a shift from failing check A to failing check B: initial A stays historical, current B and its counts appear in structured output and the full baseline. These are new regression results; prior live/Jev evaluations are not rewritten or presented as having tested these cases.
