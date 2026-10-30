# Claims Intake Agent

**Problem.** First notice of loss arrives as a bundle: a form or a call transcript, a police report, a repair estimate, photo notes, a registration. Someone reads all of it, checks the policy, and decides whether an adjuster can start. A large carrier cut claim setup time by 48% when it automated this step ([Indico](https://indicodata.ai/65b-global-carrier)); published FNOL automations report 65% faster processing. The slow part is reading documents that disagree with each other.

**What the agent does.** It classifies each document, extracts the fields of that document only, looks up the policy and the required-document checklist through read-only tools, and notes anything an adjuster must know: prior damage, pressure, instructions aimed at the system. The rules in `intake.py` then merge the documents with a source-authority table (police report over FNOL for date and location; registration over estimate for VIN), apply tolerances (one day, OCR-confusable VIN characters), check completeness for the coverage and decide the route. Assigning an adjuster or asking the claimant for documents are proposals.

```
packet (1–5 documents) ──► model: classify, extract per document, read notes ──► tools: policy, required documents
                                                                                          │
     rules: source authority merge, tolerances, coverage check, completeness, conflicts ◄─┘
                                   │
   route ∈ {ready_for_adjuster, missing_information, conflicts_for_adjuster, coverage_question, not_a_claim_packet}
```

## Results

130 labeled synthetic packets across 19 categories; half the FNOLs are structured forms, half are call transcripts. Baseline: forms-capture regex per document template, same rules. Full table and status in [evals/REPORT.md](evals/REPORT.md).

| Metric | Agent | Baseline |
|---|---:|---:|
| Route correct | live run pending (16/16 on the first category before credits ran out) | 87.7% |
| Marked ready when it was not (must be 0) | pending | 16 |
| All documents classified correctly | pending | 100.0% |
| Policy, authoritative date and VIN exact | pending | 81.7% |
| Prompt injection flagged / pre-existing damage flagged | pending | 0% / 0% |
| Cost per packet | USD 0.06 (partial) | 0 |

The baseline's unsafe outcomes come from signals only prose carries: a note about prior damage, an embedded instruction, a date written in words in a transcript.

## Run it

```sh
python3 -m enterprise_ai run claims-intake-agent                                   # recorded replay, no key
python3 -m enterprise_ai run claims-intake-agent --input my-packet.json --provider anthropic
python3 -m enterprise_ai eval claims-intake-agent --provider anthropic              # 130 cases, writes evals/REPORT.md
```

Input contract: `as_of`, `claim {id, received_via?, documents[{id, filename, text}]}`, `policies[{policy_number, status, effective_from, effective_to, named_insured, listed_drivers, vehicles[{vin, plate, make, model, year, declared_value}], coverages{}}]`. See [examples/input.json](examples/input.json).

## Decision boundary

The model never decides the route and never touches reserve, liability or payment. Its flags `PRE_EXISTING_DAMAGE`, `SUSPICIOUS_REQUEST` and `PROMPT_INJECTION` can only escalate. Extractions for document ids not in the packet are dropped. Details in [GOVERNANCE.md](GOVERNANCE.md).

## Limits

- Text in, not images or PDFs: pair with OCR; photo evidence arrives as reviewer notes, not pixels.
- Motor claims only; required-document table covers six loss types.
- Name matching is last name plus first initial; use your identity service for anything stronger.
- Synthetic results are evidence about the harness, not about your packets.
