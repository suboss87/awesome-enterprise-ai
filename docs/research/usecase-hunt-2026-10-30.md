# Use-case hunt 1: candidate agents 6-10 for awesome-enterprise-ai

Date: 2026-10-30. Method: WebSearch + WebFetch on primary pages; GitHub REST API via `gh` (stars / last push / license); HN Algolia API (2025+ stories).
Legend: **[V]** = number read on the fetched source page. **[S]** = number seen only in a search snippet (page blocked or not fetched); treat as unverified. **[vendor]** = vendor self-report, no independent audit.
Rubric columns: P = pain, B = decision boundary in code, H = human approval fits, D = data reachable, M = measurable, A = adoption evidence, R = ROI explicit, G = not generic, U = buildable, X = diversity vs current five. Max 50.

Overall finding on GitHub: for every candidate below, open-source repos are tiny (0-10 stars, mostly 2026 hobby/hackathon projects, almost none ship labeled evals with a non-AI baseline). That gap is the opportunity. The only well-adopted public assets are datasets/reference data (OpenSanctions, CUAD, LegalBench, CBP CROSS rulings, CMS code sets), which make synthetic generation and labeling credible.

## (a) Summary table

| # | Candidate | Industry / function | Owner role | ROI mechanism (quoted numbers + source) | P B H D M A R G U X | Total |
|---|---|---|---|---|---|---|
| 1 | Sanctions / name-screening alert adjudication | Banking compliance (KYC/sanctions) | Sanctions ops analyst / L1 screening team | Fed working paper: LLMs "reduced sanctions screening false positives by 92 percent" and raised detection 11% vs best fuzzy matcher [V] https://www.federalreserve.gov/econres/feds/can-llms-improve-sanctions-screening-in-the-financial-system-evidence-from-a-fuzzy-matching-assessment.htm ; top-10 Spanish bank "91.8% reduction in false positives across name and transaction screening" (early data) [V][vendor] SymphonyAI PDF | 5 5 5 5 5 4 4 5 5 5 | **48** |
| 2 | Prior-authorization clinical review, approve-only (payer UM) | Healthcare payer | UM nurse reviewer / medical director | Geisinger + WNS-HealthHelp + Anterior: "50-70% reduction" in TAT for escalated cases, "76% reduction in approvals requiring human review" [V] https://www.healthhelp.com/wp-content/uploads/HH-Geisinger-Case-Study_Transforming-Prior-Authorization-with-AI.pdf ; CMS-0057-F forces 72h expedited / 7-day standard decisions from 2026-01-01 [S] | 5 5 5 4 5 5 4 5 4 5 | **47** |
| 3 | Contract (NDA / MSA) playbook review and redline proposal | Legal ops | Commercial counsel / legal ops | RSM + LexCheck: ">75%" review-time cut, ">800 employee hours annually", ">1,400 NDAs", same-day turnaround [V] https://lexcheck.com/case-studies/rsm ; LogicMonitor: "$100K" monthly ROI, 50-70% faster first redline [S] Gartner page (403) | 4 4 5 5 5 4 4 5 5 5 | **46** |
| 4 | Commercial credit memo drafting (spread + policy checks) | Commercial banking / lending | Credit analyst / credit officer | Banesco USA: memo from "about a week" to "minutes"; "over 7,000 hours annually"; 280 memos/yr [V] https://workspace.google.com/customers/banescousa ; Taishin Bank: 20h to 4h, 4,300+ reports/yr [S] Moody's; Colony Bank SBA: 92 steps to 32, ~7 business days [V] https://www.americanbanker.com/news/colony-bank-uses-gen-ai-to-shave-days-off-sba-loan-approvals | 4 4 5 4 4 5 5 5 4 5 | **45** |
| 5 | Cash application: remittance reading + payment-to-invoice match proposal | Finance ops (AR / O2C) | Cash application analyst | SAP Cash App client: auto-match "58% to 84%" [V] https://blog.sap-press.com/ai-in-sap-s4hana-finance-3-practical-use-cases ; Addison Group (HighRadius): "80% straight-through" cash app, 10-day DSO cut [V][vendor] https://www.highradius.com/resources/value-creation/addison-group-collections/ ; Hackett: median auto-match 70% [S] | 4 5 5 5 5 4 4 5 5 3 | **45** |
| 6 | Expense report audit against written T&E policy | Finance ops (T&E) | T&E auditor / controller | Ramp policy agent beta: "85% fewer manual reviews", "15 times more policy violations" caught [V][vendor] https://ramp.com/blog/ramp-22-5-valuation ; AppZen: 258M expense lines audited in 2025 [S] | 4 5 5 5 5 4 4 5 5 3 | **45** |
| 7 | Sales order entry from emailed customer POs | Distribution / supply chain (O2C) | Order desk / customer service rep | Millcraft Paper: "60%" of inbound orders touchless; order entry costs "$8-12" each; ~500k stock lines/yr [V] https://distributionstrategy.com/2024/06/how-ai-has-improved-order-entry-other-efficiencies-at-millcraft-paper/ ; Conexiom ">85% touchless" [S][vendor] | 4 5 5 5 5 3 4 5 5 4 | **45** |
| 8 | Commercial lease abstraction + critical-date register | Real estate | Lease administrator | JLL + DealSumm: accuracy 65% to "92-98%+", review "130 minutes to 85 minutes" per lease, "30% lower cost" per abstract, humans validate before finalization [V] https://www.databricks.com/customers/jll/dealsumm ; Cushman & Wakefield: "six hours to three days" per lease before, 15+ active projects [V] https://www.unframe.ai/customer-stories/cushman-wakefield | 3 4 4 4 5 5 4 4 5 5 | **43** |
| 9 | HTS / HS tariff classification proposal | Trade compliance / logistics | Licensed customs broker / trade compliance analyst | ATLAS (CBP CROSS rulings): 10-digit accuracy 40% vs GPT-5-Thinking 25%; 6-digit 57.5% [V] https://arxiv.org/abs/2509.18400 ; Zonos: new model "29.4% fewer classification errors" [S][vendor] | 4 3 5 5 5 3 3 5 4 5 | **42** |
| 10 | KYB merchant onboarding file review | Payments / fintech compliance | Onboarding compliance analyst | TransferMate + Vivox: quality approval rate "approximately 60 per cent to around 80 per cent" in first two weeks live, up to 100 docs per case [V] https://thefintechtimes.com/transfermate-deploys-vivox-ai-agents-globally-to-automate-kyb-compliance/ ; Colony Bank KYB checks via Lama AI [V] (above) | 4 4 5 4 4 4 3 5 4 4 | **41** |
| 11 | Chargeback representment packet assembly | Payments / ecommerce ops | Disputes analyst | Justt: "2X" win-rate vs pre-Justt [S][vendor]; Chargeflow "300%" win-rate increase [S][vendor]. No verified named-customer numbers. | 4 5 5 5 4 2 3 5 5 3 | **41** |
| 12 | Pharmacovigilance AE case intake (validity + triage) | Life sciences safety | PV case processor / safety physician | Vendor claims only: 30-50% cost cut [S] HCLTech; PPD white paper had no numbers [V-negative]. Regulatory clock (15-day expedited) gives SLA pain. | 4 5 5 4 4 2 2 5 4 5 | **40** |
| 13 | Third-party (vendor) security risk assessment: SOC 2 report review | GRC / TPRM | TPRM analyst | Censinet Assessor Agent: "3.5 hours saved per assessment", "up to 66%" time cut; Renown Health adoption Feb 2025 [S][vendor] https://censinet.com/perspectives/assessor-agent-ai-reviews-evidence | 3 4 5 4 4 3 3 5 5 4 | **40** |
| 14 | SOX ITGC testing (change management / user access) | Internal audit | IT auditor / SOX PMO | Microsoft "SOX Change Management Testing Agent" (PDF unreadable, numbers [S]: 50 h/yr); fin. institution 1,000 h saved yr 1 [S] | 3 5 5 4 4 2 3 5 5 4 | **40** |
| 15 | Mortgage underwriting condition clearing | Mortgage lending | Underwriter / processor | Sun West: underwriting review "one hour" [S][vendor press]; lender productivity 31 to 42.2 files/month [S] unnamed | 4 4 5 4 4 2 3 5 4 4 | **39** |
| 16 | AR collections: dispute/short-pay email triage + dunning draft | Finance ops (AR) | Collections specialist | Addison Group: dunning agent "8,288+ hours saved annually", 17% less past due [V][vendor] (HighRadius page above) | 3 4 5 5 4 2 4 4 5 3 | **39** |
| 17 | Payer denial appeal packet (provider RCM) | Healthcare provider revenue cycle | Denials specialist | Problem size only: "$20 billion" spent overturning, ">450 million claims denied" yearly [V] https://www.nbcbayarea.com/news/business/money-report/new-ai-tool-for-fighting-health-insurance-denials-could-save-hospitals-billions-and-help-patients/3758895/ ; no verified outcome numbers (Waystar, SmarterDx launches) | 5 4 5 3 3 2 3 5 4 4 | **38** |
| 18 | Outpatient / ED medical coding suggestion | Healthcare provider RCM | Certified coder / HIM | Nym: "over 96 percent accuracy", 35% lower coding cost at one hospital ED [S][vendor]; OHSU story blocked (403) | 5 4 4 3 4 3 3 5 3 4 | **38** |
| 19 | FOIA request processing: exemption flagging + redaction proposal | Public sector | FOIA officer | DoD POC: 575 vs 200 pages/hour [S]; DHS ended FY2025 with 245,572 pending requests [S]; NARA OGIS: 18.6% of agencies use AI/ML in FOIA [S] | 4 3 5 4 3 2 3 5 4 5 | **38** |

Top 8 by score: 1 Sanctions, 2 Prior auth, 3 Contract playbook, 4 Credit memo, 5 Cash application, 6 Expense audit, 7 Sales order entry, 8 Lease abstraction. Runners-up with best diversity: 9 HTS classification, 10 KYB.

## (b) Per-candidate evidence, hard cases, metrics, tools, decision boundary

### 1. Sanctions / name-screening alert adjudication (48)
- Evidence: Federal Reserve FEDS working paper (Allen & Hatfield, Sep 2025): LLMs cut false positives 92%, detection +11% vs best fuzzy matcher; LLMs are ">four orders of magnitude slower", so authors propose a cascade (fuzzy/exact first, LLM only for uncertain cases) [V]. SymphonyAI Spanish bank (top-10 Spain): 91.8% FP reduction, "early data" [V][vendor]. FRBSF summary: https://www.frbsf.org/research-and-insights/publications/board-of-governors/2025/10/can-llms-improve-sanctions-screening-financial-system-evidence-fuzzy-matching-assessment/
- Repos/data: opensanctions/opensanctions 861 stars, push 2026-10-30, MIT; opensanctions/yente 184 stars, push 2026-10-30, MIT; moov-io/watchman 516 stars, push 2026-10-30, Apache-2.0. LLM adjudication repos: all 0-2 stars.
- Hard eval cases: transliteration (Arabic/Cyrillic/Chinese name variants), name-order swaps, common names with differing DOB/nationality, vessel/company aliases, partial secondary identifiers, 50%-rule ownership (OFAC), true hits disguised by typos. FP must never trade off recall: practitioners report "100% true positive retention" as the bar.
- Metrics: FP reduction at fixed recall (recall on true hits must be 1.0), alerts cleared per analyst hour, latency per alert, cost per alert. Non-AI baseline: Jaro-Winkler / token-set fuzzy at bank thresholds.
- Tools (6): `get_alert`, `get_customer_profile` (DOB, nationality, address, IDs), `get_list_entry` (OpenSanctions record), `compute_match_features` (deterministic name/DOB/country scores), `get_prior_dispositions`, `propose_disposition` (to case queue).
- Decision boundary: code computes feature scores and hard rules (any exact ID match or DOB+name match => escalate; never auto-clear above score X). Model only compares secondary attributes and writes rationale. Output = "propose false positive" or "escalate", always queued for L1 sign-off.

### 2. Prior-authorization clinical review, approve-only (47)
- Evidence: Geisinger Health Plan + WNS-HealthHelp + Anterior: 50-70% TAT cut on escalated clinical cases, 76% fewer approvals needing human review, "near real-time approvals" [V]. Cohere Health: "85%" of PA decisions approved in real time [S][vendor] https://coherehealth.com/decision . Regulator: CMS-0057-F decision clocks (72h / 7 days) effective 2026-01-01, FHIR Prior Auth API by 2027-01-01 [S] https://www.techtarget.com/searchhealthit/news/366578002/CMS-Releases-Interoperability-and-Prior-Authorization-Final-Rule . CMS WISeR model (2026-2031, 6 states, AI-assisted PA in Medicare Part B) faces bipartisan repeal bills [S] https://www.dinsmore.com/publications/is-ai-wiser-cms-models-ai-based-prior-authorization-process-in-six-states/
- Community: HN "New Records Reveal Problems with Medicare's AI Prior Authorization Experiment" (2026-09) https://news.ycombinator.com/item?id=49628300 . The public concern is AI denials; an approve-only design answers it directly.
- Repos: acblabs/multi_llm 5 stars MIT (push 2026-06); drdgreed/pacca 3 stars MIT; none with labeled evals.
- Hard eval cases: criteria met only via a note buried in a scanned PDF; conflicting dates (conservative therapy duration short by days); wrong CPT/ICD pairing; missing imaging report; request that meets criteria for a different code; expedited flag misuse.
- Metrics: auto-approve precision (must be ~1.0: no approval that a nurse would deny), share routed to nurse, TAT vs 72h/7d clock, cost per case. Baseline: rules-only checklist on structured fields.
- Tools (7): `get_pa_request`, `get_clinical_documents`, `get_coverage_criteria` (policy as structured checklist), `extract_criterion_evidence` (model, cites page/line), `evaluate_criteria` (deterministic), `check_sla_clock`, `propose_decision` (approve or route to clinician; never deny).
- Decision boundary: code evaluates every criterion against extracted, cited evidence; approve only if all are met with citations; any gap routes to a nurse. The agent has no deny action.

### 3. Contract (NDA / MSA) playbook review (46)
- Evidence: RSM (LexCheck) >75% time cut, >800 h/yr, >1,400 NDAs, avoided new hires [V]. LogicMonitor case on Gartner: $100K monthly ROI, 50-70% faster redlining [S] (403). LegalOn / SimpleDocs launched playbook features 2025 [S] https://www.lawnext.com/2025/02/simpledocs-launches-simpleai-an-ai-powered-contract-review-tool-with-customizable-playbooks-plus-video-demo.html
- Repos/data: The-Atticus-Project/cuad 575 stars (510 contracts, 41 clause types; push 2023; license field empty on GitHub), HazyResearch/legalbench 652 stars (push 2026-03-30). Playbook-review repos: contract-opf/contract-toaster 3 stars Apache-2.0.
- Hard eval cases: mutual vs one-way NDA mislabeled; residuals clause hidden in definitions; non-solicit inside confidentiality section; governing-law vs venue mismatch; term auto-renewal; carve-out that negates the main clause; liability cap that excludes the counterparty's IP indemnity.
- Metrics: clause-level deviation recall/precision vs counsel labels, % contracts routed "standard - approve", minutes per contract, cost per contract. Baseline: keyword/regex clause finder + checklist.
- Tools (6): `get_contract` (docx/pdf to text with clause ids), `get_playbook` (positions + fallback language as data), `extract_clauses` (model), `compare_to_playbook` (deterministic thresholds: term months, cap multiples, jurisdiction allowlist), `draft_redline` (model, only from approved fallback text), `submit_to_legal_queue`.
- Decision boundary: code decides which playbook position is violated and the risk tier; the model extracts and drafts with approved fallback language only. Counsel approves every redline.

### 4. Commercial credit memo drafting (45)
- Evidence: Banesco USA (Gemini): week to minutes, 7,000+ h/yr, 280 memos/yr [V]. Taishin Bank (Moody's): 20h to 4h, 4,300 reports/yr [S] https://www.moodys.com/web/en/us/insights/banking/how-taishin-bank-used-ai-to-amplify-human-expertise-in-credit-analysis.html . Colony Bank (Lama AI): SBA steps 92 to 32, ~7 business days, human approval mandatory [V]. Customers Bank: 76,000 cumulative hours saved, select loans closed in 7 days vs 30-60 [S] PYMNTS.
- Repos: credit-memo repos 1-2 stars; none with evals.
- Hard eval cases: add-backs in adjusted EBITDA; inconsistent fiscal year ends; guarantor global cash flow; covenant computed on wrong period; related-party revenue; restated statements; missing interim financials.
- Metrics: field-level spread accuracy, ratio exactness (DSCR, leverage, LTV), policy-exception recall, analyst hours per memo, cost per memo. Baseline: template + manual spread (or OCR-only spread).
- Tools (7): `get_loan_request`, `get_financial_statements`, `extract_spread` (model), `compute_ratios` (deterministic), `check_credit_policy` (thresholds, exceptions), `get_collateral_and_guarantors`, `draft_memo_sections` (model narrative citing figures) -> credit officer queue.
- Decision boundary: code computes every number and flags every exception; the model drafts narrative only and cannot state a figure that is not in the computed spread. No approve/decline recommendation from the model.

### 5. Cash application (45)
- Evidence: SAP Cash Application client: 58% to 84% auto-match, attributed to data prep + exception categories + confidence thresholds, not the algorithm alone [V]. Addison Group (HighRadius): 80% STP, 60% analyst time freed, 10-day DSO cut [V][vendor]. Hackett 2025 vendor study: median auto-match 70%, one-third above 80% [S] (403). Uber TextSense invoice extraction: 90% accuracy, 70% handling-time cut, HITL side-by-side review [V] https://www.uber.com/blog/advancing-invoice-document-processing-using-genai (AP side; shows the extract-then-validate pattern).
- Repos: DevFoundry-labs/remitmatch 0 stars MIT; mdansaridw/AR-Cash-Reconciliation 1 star MIT.
- Hard eval cases: one payment for many invoices with deductions; short-pay with remittance in email body; remittance arrives days after payment; payer is a parent company; currency/bank fees; invoice numbers with typos; unapplied cash that is actually a prepayment.
- Metrics: auto-match rate at 0 false applications, unapplied cash %, exceptions per 100 payments, cost per payment. Baseline: exact reference + amount match (classic lockbox rules).
- Tools (6): `get_bank_transaction`, `get_remittance_docs` (email/PDF), `extract_remittance_lines` (model), `get_open_items`, `match_candidates` (deterministic subset-sum/tolerance), `propose_application` (to AR queue, with deduction codes).
- Decision boundary: matching and tolerances in code; model reads remittances and proposes deduction reason codes. Overlap note: same finance-ops family as AP 3-way match; distinct process (O2C) and owner.

### 6. Expense report audit (45)
- Evidence: Ramp policy agents (beta, 2025): 85% fewer manual reviews, 15x more violations caught [V][vendor]; PYMNTS launch piece had no numbers [V-negative]. AppZen 258M lines audited in 2025 [S]. SAP Concur Verify, Navan Audit Engine (2026) [S]. MS Dynamics 365 BC "Expense Agent" [S].
- Repos: SuperGitlab/ai-expense-auditor 3 stars; AMANxSHARMA01/auditable-expense-agent 1 star. No evals.
- Hard eval cases: AI-generated/edited receipts; duplicate across two employees; split transactions to dodge limits; alcohol inside a meal line; per-diem vs actual in same trip; foreign-currency receipts; attendee count vs per-person cap; policy text ambiguity ("reasonable").
- Metrics: violation recall, false-flag rate, % auto-approved, auditor minutes per report, recovered $ per 1,000 reports. Baseline: rules engine (amount caps, MCC blocks, duplicate hash).
- Tools (6): `get_expense_report`, `get_receipts`, `extract_receipt_fields` (model), `get_policy_rules` (structured caps by category/city), `run_policy_checks` (deterministic + duplicate detection), `propose_disposition` (approve / return / escalate with citations).
- Decision boundary: caps, per-diems, duplicates in code; model reads receipts and maps free-text policy to categories. Overlap note: finance ops; distinct owner and data.

### 7. Sales order entry from emailed POs (45)
- Evidence: Millcraft Paper: 60% touchless, $8-12 cost per manual order, mistakes down [V]. Conexiom >85% touchless [S][vendor]; Bridgenext distributor case [S]; 2026 launches by Toolbx and WizCommerce for distributors [S] https://distributionstrategy.com/2026/09/toolbx-launches-ai-order-entry-for-building-supply-distributors/ . YC company Comena in this space [S].
- Repos: near zero (ShopFloorIQ 0 stars).
- Hard eval cases: customer part number vs internal SKU; unit-of-measure mismatch (case vs each); price on PO differs from contract price; ship-to not on file; PO revision/duplicate PO; free-text "same as last order"; mixed handwritten fax.
- Metrics: touchless rate at 0 wrong-line orders, line-level accuracy, minutes per order, cost per order. Baseline: template/OCR mapping per customer.
- Tools (7): `get_inbound_email`, `extract_po_lines` (model), `resolve_customer`, `map_sku` (deterministic cross-reference, then model suggestion), `get_contract_price`, `check_credit_and_stock`, `propose_sales_order` (ERP draft queue).
- Decision boundary: price, credit hold, UoM conversions, duplicate-PO detection in code; model extracts and suggests SKU mappings only where cross-reference fails. Overlap note: mirror image of AP matching on the sell side.

### 8. Lease abstraction + critical dates (43)
- Evidence: JLL + DealSumm on Databricks: 92-98%+ accuracy over 2,500+ data points, 130 to 85 min review, 30% lower cost, human validation before finalization [V]. Cushman & Wakefield + Unframe: in production, 15+ projects, before "six hours to three days" [V]. VTS Asset Intelligence launch 2026 [S].
- Repos: effectively none (1-star bot).
- Hard eval cases: amendment overrides base lease; renewal option notice window computed from a defined term; CAM caps with base-year exclusions; co-tenancy and kick-out clauses; rent steps stated as % vs fixed; conflicting commencement dates.
- Metrics: field-level accuracy vs analyst abstract, critical-date exactness (days), minutes per lease, cost per lease. Baseline: manual abstract template / regex.
- Tools (6): `get_lease_package` (base + amendments), `extract_terms` (model, with citations), `apply_amendments` (deterministic precedence), `compute_critical_dates` (deterministic), `validate_abstract` (cross-field rules), `submit_abstract` (lease admin queue).
- Decision boundary: amendment precedence and date math in code; model only extracts cited clauses. Weakness: mostly extraction; less "decision" than others.

### 9. HTS / HS tariff classification (42)
- Evidence: ATLAS (NeurIPS 2025 benchmark, CBP CROSS): 10-digit 40%, GPT-5-Thinking 25%, Gemini 2.5 Pro 12.5% [V]; model on HF: flexifyai/atlas-llama3.3-70b-hts-classification. Zonos Classify rebuilt (2026-09): 29.4% fewer errors [S][vendor]; Flexport Customs Technology Suite (Oct 2025) [S]; IDB paper: LLM accuracy 60-90% by HS level [S].
- Repos: kitanjali/trade-classify 2 stars MIT. CBP CROSS rulings give a public labeled set.
- Hard eval cases: sets/kits (GRI 3), parts vs accessories, material composition thresholds (textiles), "principally used" tests, chapter/section note exclusions, products that changed heading after 2022 HS revision.
- Metrics: 6-digit and 10-digit accuracy, escalation rate, duty $ error, broker minutes per SKU. Baseline: keyword/embedding nearest CROSS ruling.
- Tools (6): `get_product`, `search_cross_rulings`, `get_hts_text` (headings + notes), `apply_gri_checks` (deterministic exclusions), `compute_duty`, `propose_classification` (broker queue).
- Decision boundary: weaker; the classification is itself the judgment. Code can enforce note exclusions, confidence thresholds and duty math. Broker signs.

### 10. KYB merchant onboarding review (41)
- Evidence: TransferMate + Vivox AI: QA approval 60% to 80% in first two weeks live, up to 100 docs per case, 24+ verification APIs [V]. Colony Bank KYB via LexisNexis inside Lama AI [V]. COLIBRIX ONE multi-year Vivox deal [S]. YC Arva AI [S].
- Hard eval cases: UBO chain through 3+ holding companies; registry name differs from trading name; expired certificate of incorporation; prohibited MCC hidden in website text; director on PEP list; address is a mail drop.
- Metrics: analyst-agreement rate, % auto-cleared low risk, cycle time, cost per case. Baseline: checklist + registry API only.
- Tools (7): `get_application`, `get_documents`, `extract_entity_facts` (model), `query_registry`, `screen_parties` (deterministic list match), `compute_risk_tier` (rules), `propose_decision` (onboarding queue).
- Overlap: shares screening with #1; pick one of #1 / #10.

### 11. Chargeback representment (41)
- Evidence: vendor-only numbers (Justt 2x, Chargeflow 300%) [S]. HN "The madness of SaaS chargebacks" 81 pts / 112 comments (2025-09) https://news.ycombinator.com/item?id=45248446 shows practitioner pain. Repo airasalish/warrant 5 stars MIT claims a sealed held-out set.
- Hard cases: Visa CE 3.0 qualifying prior transactions; reason code 10.4 vs 13.1 evidence differences; partial refunds already issued; digital goods delivery proof.
- Tools: `get_dispute`, `get_order_and_delivery`, `get_prior_transactions`, `select_evidence_by_reason_code` (deterministic matrix), `draft_rebuttal`, `submit_to_review_queue`. Decision boundary: fight/accept by code (amount, reason code, evidence completeness).

### 12. Pharmacovigilance AE case intake (40)
- Evidence: HCLTech, Tech Mahindra, ArisGlobal, PPD market it; no verified customer numbers (PPD paper read: none) [V-negative]. Strong regulatory clock (expedited 15-day reports).
- Hard cases: missing one of four validity elements; literature article with several patients; seriousness inferred from narrative; duplicate reports from patient and HCP; product name misspelled.
- Tools: `get_source_doc`, `extract_case_fields`, `check_validity` (4 minimum criteria, deterministic), `assess_seriousness_rules`, `code_terms` (MedDRA lookup suggestion), `detect_duplicate`, `propose_case` (safety DB queue). Data: MedDRA is licensed; synthetic needs a stand-in vocabulary.

### 13. Vendor SOC 2 report review / TPRM (40)
- Evidence: Censinet Assessor Agent 3.5 h saved per assessment, up to 66% [S][vendor]; Renown Health adoption [S]; Bitsight SOC 2 AI insights [S]. Repo arthurpanhku/DocSentinel 89 stars MIT (questionnaires + docs).
- Hard cases: report period gap > 3 months; carve-out of key subservice org; qualified opinion; exceptions noted in testing; CUECs the customer does not meet; bridge letter missing.
- Tools: `get_vendor`, `get_soc_report`, `extract_report_facts`, `check_report_rules` (dates, opinion, scope, exceptions), `map_to_control_set`, `propose_risk_rating` (GRC queue).

### 14. SOX ITGC testing (40)
- Evidence: Microsoft SOX Change Management Testing Agent PDF (unreadable image) [S]; internal audit stories 60% testing-time cut for 175 controls [S]; YC Midship, Arden [S]. Evidence thin and mostly vendor.
- Tools: `get_control`, `get_population`, `select_sample` (deterministic), `get_evidence`, `test_attributes` (model reads tickets/approvals; code checks dates, SoD), `propose_workpaper`.

### 15. Mortgage condition clearing (39)
- Evidence: Sun West "one-hour" underwriting reviews [S][vendor press]; unnamed lender 31 to 42.2 files/month [S]. Weak independent evidence.
- Tools: `get_loan_file`, `get_conditions`, `extract_doc_facts`, `check_condition_rules` (dates, amounts, seasoning), `propose_clear_or_reissue`.

### 16. AR collections dispute triage (39)
- Evidence: Addison Group dunning agent 8,288 h/yr [V][vendor]. Others are content-farm stats. Better folded into #5 as a second workflow.

### 17. Payer denial appeal packet (38)
- Evidence: problem size verified ($20B, 450M denials) [V]; Waystar AltitudeCreate and SmarterDx SmarterDenials launches have no outcome numbers [V-negative]; Aspirion Best in KLAS 2025 [S]. HN Launch: WorkDone (YC X25) AI chart audit 79 pts https://news.ycombinator.com/item?id=44063000 .
- Hard cases: CARC/RARC mapping, timely-filing limits per payer, medical necessity vs coding denials, appeal level (1st vs external review).
- Tools: `get_denial` (835 CARC/RARC), `get_claim_and_chart`, `classify_denial` (deterministic CARC map + model for free text), `check_appeal_deadline`, `get_payer_policy`, `draft_appeal_letter`, `submit_to_worklist`.

### 18. Medical coding suggestion (38)
- Evidence: Nym 96% accuracy, 35% lower coding cost [S][vendor]; KLAS autonomous coding report [S]; Ambience/OpenAI coding model (HN 2025-05) [S]. Repos: cyanheads/medical-codes-mcp-server 2 stars Apache-2.0; briankfung/phantom-codes 2 stars MIT (hallucination benchmark).
- Weakness: code assignment is the judgment; NCCI edits and MUEs give some deterministic checks. CPT is AMA-licensed (synthetic friction).

### 19. FOIA exemption flagging (38)
- Evidence: pilot-level only (DoD POC 575 vs 200 pages/h; DHS-Deloitte contract; NARA OGIS 18.6%) [S]; critics note DHS publishes no error or override rates [S] https://www.remio.ai/post/dhs-ai-foia-redactions-promise-speed-but-risk-deeper-secrecy . Public-sector diversity is the draw; evidence and boundary are weak.

## (c) Rejected

- Freight invoice audit: near-duplicate of AP 3-way match (contract rate vs invoice vs shipment). Evidence mostly vendor stat pages.
- dbt / data-pipeline failure triage (Headway "De-Bug-T", ~88% troubleshooting cut [S], page 403): near-duplicate of incident root-cause agent.
- HR case / employee inquiry agent (Hoag Health: 73% AI resolution, 86% faster [V] https://www.zendesk.com/customer/hoag-health/ ; Salesforce "Techforce"): chatbot over a knowledge base; generic.
- Security questionnaire answering (Fiddler AI 87%, Cubiko 85% [S][vendor]): RAG over docs, generic; HN flags answers may be contractual representations https://news.ycombinator.com/item?id=49726115 .
- RFP response drafting (Microsoft/Responsive 21,100 h [S]): generic doc generation, no decision boundary.
- Flux / variance commentary at month-end: numbers come from content-farm sites (stealthagents, chatfin); no verified named case; narrative generation only.
- Deal desk discount approval: evidence is vendor blueprint pages; the approval itself is already rules in CPQ.
- Warranty claims validation: only aggregator stats (stealthagents) found; no named production case verified.
- Utility bill audit (Nectar, Gravity [S]): vendor-only, thin; revisit for energy diversity.
- Interconnection application completeness (DOE AI4IX $30M [S]): grants and pilots, no production evidence yet.
- Sales tax exemption certificate validation (Avalara ECM AI [S]): good rule boundary but no outcome numbers found.
- Procurement intake (Coupa "450+ customers" Navi agents, Zip TEI 386% ROI [S]): platform claims, intake routing is mostly forms + rules; Trustpilot numbers in snippets were internally inconsistent.
- AML transaction-monitoring alert triage: evidence is mostly predictive ML (Valley Bank/DataRobot 22%, NICE 31-33%), not GenAI; fold the GenAI part (narrative/SAR draft) into #1 or a later agent.
- Insurance underwriting submission intake, subrogation: same industry as claims intake agent.
- Autonomous medical coding as direct-to-bill: requires autonomous writes; only the suggestion form (#18) is in scope.

## Verification notes
- Blocked (403) and therefore unverified: Gartner LogicMonitor case, Healthcare IT News OHSU, Headway blog, Hackett Business Wire release.
- PDFs read via pdftotext: Geisinger/HealthHelp case (verified), SymphonyAI Spanish bank (verified, "early data"). Microsoft SOX agent PDF is image-only (not verified).
- Numbers from stealthagents.com, chatfin.ai, delos.so, simbo.ai pages were not used as evidence (content-farm style, no sources).
