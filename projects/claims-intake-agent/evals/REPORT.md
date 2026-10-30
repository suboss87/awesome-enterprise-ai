# Evaluation report: claims-intake-agent

**Status: live evaluation pending.** The full 130-case live run on 2026-10-30 stopped after 16 cases because the
provider account ran out of credits (HTTP 429). The partial result is shown for transparency only; it is not the
committed benchmark. Re-run with `python3 -m enterprise_ai eval claims-intake-agent --provider anthropic` (or `openai`).

## Partial live result (gpt-5.5-2026-04-23, 16 cases, all `clean_collision`)

| Metric | Agent |
|---|---:|
| Route correct | 16/16 |
| Policy, authoritative date and VIN exact | 16/16 |
| Cost per case | USD 0.061 |

## Baseline (rules only, 130 cases, no model)

| Metric | Baseline |
|---|---:|
| Route correct | 87.7% |
| Marked ready when it was not (must be 0) | 16 |
| Expected flags recalled | 0.814 |
| All documents classified correctly | 100.0% |
| Policy, authoritative date and VIN exact | 81.7% |
| Missing-document list exact | 96.9% |
| Prompt injection flagged | 0.0% |
| Pre-existing damage flagged | 0.0% |

The baseline reads the structured FNOL form, police report, estimate and registration well. Its 16 unsafe
`ready_for_adjuster` outcomes come from the free-text signals it cannot see: a note about prior damage in the
estimate, instructions embedded in a document, and dates spelled out in a call transcript.
