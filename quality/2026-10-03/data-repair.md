# Data Repair Evidence: artifact assessment

Jev selected `publish_experiment` for commit `ad57243`. Weighted readiness evidence score: **49.97/100** under the collection's frozen eight-dimension rubric. Resolved model: `jev-1.13.0`. First priority: `source_integration`.

This assessment includes the project code, relevant shared runtime, tests, native-fixture evidence, browser results, one live output, the frozen trial criteria and research counterevidence. It uses a scoped evidence set, not an identical full-portfolio bundle. Raw distributions, file/request hashes and call metadata are preserved here. The score is uncalibrated model judgment; it does not certify production readiness or prove a benefit over another tool.

Verification at assessment: 256 integrated tests and eleven CLI replays; 26 project tests and independent boundary/privacy checks. Real GX1.8.0 fail/pass artifacts were generated locally from original synthetic rows. The dbt manifest is an explicitly authored subset. A browser JSON-number hash mismatch was reproduced and fixed, then the same journey passed with HTTP200 and no console errors.

One live call selected all four existing baseline sentences. There is no demonstrated AI benefit, and the deterministic template remains the recommended starting point. The historical live output predates numeric canonicalization; model-facing statements stayed unchanged and inference was not repeated to seek a different result.

Mandatory production gates remain open: authenticated source/scope mapping, organizational identity and data controls, representative data-owner acceptance, and target operations/recovery. Distinct market value and time savings remain hypotheses. Publish only as an experimental local-export workflow with optional AI ordering.
