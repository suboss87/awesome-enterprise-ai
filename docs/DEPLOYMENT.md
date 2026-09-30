# Deployment and data handling

## What ships

Ten independently scoped Python workflows share a command-line interface and a single-user browser workspace. Python 3.11+ is the only local runtime dependency. The browser is served locally, with no external fonts, analytics or CDN dependencies. Inputs and results use JSON contracts; there are no packaged Salesforce, ServiceNow, SAP, insurer or equipment-control connectors.

The included HTTP server binds only to `127.0.0.1`. Keep it there. It is a local evaluation interface, **not a multiuser application server**. Do not expose it through a public tunnel, reverse proxy or shared workstation as though its session token were enterprise authentication.

## Modes and provider

- **Replay:** explicit recorded example interpretation. The browser only accepts the unchanged example in this mode. The CLI permits your own recorded responses for tests; they must still pass the schema and workflow validators.
- **Live:** actual OpenAI Responses API inference through a fixed HTTPS host, pinned `gpt-5.5-2026-04-23` model, structured outputs, medium reasoning and an 8,000-output-token cap. Requires `OPENAI_API_KEY` and model access. No fallback to a different model or replay.
- A model snapshot change requires rerunning evaluations; a successful HTTP connection alone is not verification.
- Provider redirects are rejected. The transport limits response size and has a 90-second timeout. There are no automatic retries, web tools or arbitrary remote-source fetches.

Only send data your organization permits this provider to process. `store: false` requests no Responses storage; it is **not** a promise of zero retention across provider infrastructure. Your provider agreement, region and organization settings determine applicable controls.

## Local handling

The workspace does not persist inputs, outputs or access logs. Results remain in the browser until replaced or the page closes. An exported JSON file is saved by the browser; CLI output follows your shell's redirection and logging rules. Treat both as business data. The server API key stays in the server environment and is never sent to browser JavaScript.

Requests are bounded to 500 KB, require a per-process workspace token, and validate Host and Origin. At most two workflow requests run concurrently. Responses disable caching and framing. These checks reduce local browser-origin attacks; they do not supply user identities, authorization or tenant isolation. Another local process under the same account can access this workspace.

Evaluation tooling deliberately writes input, request, provider response and result artifacts. `scripts/evaluate_workflows.py` uses restrictive file permissions and refuses to overwrite an output directory. Store its output outside the public repository; never commit customer inputs, provider traces or credentials.

## Before an operational deployment

The adopter owns:

1. Source-system authentication and authorization, including scope checks before data enters the workflow.
2. Data contracts, ingestion/OCR quality, record provenance and rejection of stale or incomplete exports.
3. Identity, organization isolation, secrets management, encryption, retention and authorized access to results.
4. A real application server or job runner, request lifecycle limits, observability, capacity, recovery and change control.
5. Representative evaluation against the current manual or automated baseline, with domain owners reviewing failures.
6. Explicit approval and an audited transaction layer for any future writes, plus idempotency and rollback behavior.

An exact quotation confirms that text exists in the supplied source. It does not prove entailment, source truth or policy authority. Model outputs can be wrong even when every deterministic check passes. All results require review; none is a legal, coverage, medical, safety or security-clearance determination.
