# Governance and limits

Status: **experimental; deployment hold**. Passing synthetic tests is not enterprise production readiness.

## Trust boundary

The local operator controls input files, clock, mapping, suite and lineage completeness assertion. SHA-256 binds the selected bytes; it is not a signature, attestation or assurance that a validation actually ran in the asserted production environment. Native GX asset metadata is checked against explicit mappings. Logical partition and environment are not independently verified. A normalized packet can be authored by an operator; its digest checks cannot defend against a malicious operator rewriting the entire packet. There is no SSO, service authentication, secure audit ledger or live source refresh.

The comparison requires complete unchanged semantics and a strictly later retest. Any changed parameter, including row filters, column, thresholds and `mostly`, blocks readiness. Stable expectation IDs must be preserved across the suite; regenerated IDs safely fail comparison. Data fingerprints may change after correction. The supported dataframe fingerprint is preserved as GX provenance, not treated as a cryptographic data attestation. Supplied job status and waiver notes cannot override observed checks.

The dbt dependency graph describes potential consumers only. It does not demonstrate actual damage or root cause. The two provided exposures are synthetic. Missing coverage and owners block readiness; all declared reachable exposures remain in output. Multiple failures stay separate even when they share upstream dependencies.

No repair, SQL, webhook, ticket mutation or arbitrary network tool is exposed. Template mode is local. Optional live prioritization sends fixed evidence sentences (including owner and exposure IDs) plus explicitly approved runbook text to the existing provider. Raw samples and exception traces are excluded by construction, but approved text/identifiers still require disclosure review. Unapproved runbooks remain local. Provider outages fail rather than imply a successful AI run. Existing provider transport limits apply; this standalone CLI adds no worker wall-clock isolation.

## Before an enterprise pilot

An authorized data owner must validate real exporter compatibility, governed scope mappings, source access, freshness, retention, recovery and observed workflow usefulness. Integrate with the organization's identity/audit and existing ticketing controls. Test representative asset partitions, suites and declared consumers. Set a real evidence cutoff and evaluate at the current time. Do not use fixture/historical clocks for operational decisions.

Independent review, CI integration, source authorization and real-user acceptance remain pending at this project handoff. A reviewer's approval of a bounded experiment is not calibrated production certification. No scored A+ or accuracy percentage is claimed.

## Ownership and licensing

Project code, data, dbt-shaped fixture and narratives are original and use the repository license. No upstream implementation or community text is copied. GX is a development-only fixture generator, distributed upstream under Apache-2.0; no GX runtime source is vendored. Generated fixtures contain only the synthetic rows included here. See `examples/native/provenance.json` for artifact hashes and actual development dependency versions.
