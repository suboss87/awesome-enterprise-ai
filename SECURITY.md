# Security

## Reporting

Report a vulnerability privately through GitHub Security Advisories on this repository. Do not open a public issue for a security problem. Expect an acknowledgement within 72 hours.

## Scope

In scope: the runtime (`enterprise_ai/`), the agents (`projects/`), the local workspace, the eval harness. Out of scope: provider behaviour, third-party models, and deployments that bypass the documented boundary.

## Design controls

- Documents and tool results are untrusted data. The system prompt states this; the loop never treats them as instructions.
- Tool inputs are validated against strict schemas before execution. Unknown tools are refused.
- Write tools are never executed. They produce proposals with `awaiting_approval`.
- Evidence quotes must exist verbatim in a supplied source or the result is rejected.
- Inputs are bounded (1 MB), tool results are truncated (20 000 characters), steps are limited.
- The workspace binds to 127.0.0.1, checks Host and Origin, uses a per-session token and a strict CSP, and logs nothing.
- Keys are read from the environment only. Error messages never include them.
