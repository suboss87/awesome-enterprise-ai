# Security

The tool reads one local JSON file and writes its brief to standard output. It performs no network access, model invocation, email or ERP mutation. HTML escapes supplied text and uses a restrictive content-security policy; source references are rendered as plain text.

Input sizes, row counts, schema fields, decimal precision and identities are validated. The digest is a reproducibility aid, not a signature. A malicious or incomplete exporter can still misrepresent facts: this utility cannot authenticate source records or guarantee completeness. Store reports with the same protections as their inputs.

Report vulnerabilities through the collection repository's private vulnerability reporting facility. Do not include real invoices, credentials or personal information in public issues.
